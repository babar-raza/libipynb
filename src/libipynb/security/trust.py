"""Content-addressed notebook trust with a pluggable signature store."""

from __future__ import annotations

import hashlib
import hmac
from collections import OrderedDict
from collections.abc import Iterator
from dataclasses import dataclass
from enum import Enum
from threading import RLock
from typing import Any, Protocol, runtime_checkable

from ..model import NotebookDocument
from .limits import NotebookResourceLimits as ResourceLimits
from .limits import effective_limits

STRONG_HMAC_ALGORITHMS = frozenset({"sha256", "sha384", "sha512"})


@runtime_checkable
class SignatureStore(Protocol):
    """Official-compatible storage contract for notebook signatures."""

    def store_signature(self, digest: str, algorithm: str) -> None: ...

    def check_signature(self, digest: str, algorithm: str) -> bool: ...

    def remove_signature(self, digest: str, algorithm: str) -> None: ...


@runtime_checkable
class TrustNotary(Protocol):
    """Injectable notebook-notary contract."""

    def compute_signature(
        self,
        document: NotebookDocument,
        *,
        limits: ResourceLimits | None = None,
    ) -> str: ...

    def sign(
        self,
        document: NotebookDocument,
        *,
        limits: ResourceLimits | None = None,
    ) -> TrustRecord: ...

    def verify(
        self,
        document: NotebookDocument,
        *,
        limits: ResourceLimits | None = None,
    ) -> TrustVerification: ...

    def revoke(
        self,
        document: NotebookDocument,
        *,
        limits: ResourceLimits | None = None,
    ) -> bool: ...


class TrustStatus(str, Enum):
    TRUSTED = "trusted"
    UNTRUSTED = "untrusted"


@dataclass(frozen=True, slots=True)
class TrustRecord:
    """Content signature stored by a notary backend."""

    digest: str
    algorithm: str


@dataclass(frozen=True, slots=True)
class TrustVerification:
    """Structured trust result kept separate from schema validation."""

    status: TrustStatus
    record: TrustRecord
    reason: str | None = None

    @property
    def trusted(self) -> bool:
        return self.status is TrustStatus.TRUSTED


class MemorySignatureStore:
    """Thread-safe bounded in-memory signature store.

    This store is process-local. Applications requiring durable trust can
    inject any backend implementing :class:`SignatureStore`, including an
    adapter over the official nbformat SQLite signature store.
    """

    def __init__(self, *, max_signatures: int = 65_535) -> None:
        if (
            isinstance(max_signatures, bool)
            or not isinstance(max_signatures, int)
            or max_signatures <= 0
        ):
            raise ValueError("max_signatures must be a positive integer")
        self._max_signatures = max_signatures
        self._data: OrderedDict[tuple[str, str], None] = OrderedDict()
        self._lock = RLock()

    def store_signature(self, digest: str, algorithm: str) -> None:
        key = _store_key(digest, algorithm)
        with self._lock:
            self._data.pop(key, None)
            self._data[key] = None
            while len(self._data) > self._max_signatures:
                self._data.popitem(last=False)

    def check_signature(self, digest: str, algorithm: str) -> bool:
        key = _store_key(digest, algorithm)
        with self._lock:
            if key not in self._data:
                return False
            self._data.move_to_end(key)
            return True

    def remove_signature(self, digest: str, algorithm: str) -> None:
        key = _store_key(digest, algorithm)
        with self._lock:
            self._data.pop(key, None)

    def __len__(self) -> int:
        with self._lock:
            return len(self._data)


def _store_key(digest: str, algorithm: str) -> tuple[str, str]:
    if not isinstance(digest, str) or not digest:
        raise ValueError("digest must be a non-empty string")
    if not isinstance(algorithm, str) or not algorithm:
        raise ValueError("algorithm must be a non-empty string")
    return digest, algorithm


@dataclass(frozen=True, slots=True)
class _Value:
    value: Any
    path: tuple[str | int, ...]
    depth: int


@dataclass(frozen=True, slots=True)
class _Chunk:
    value: bytes


def _signature_chunks(
    root: dict[str, Any],
    limits: ResourceLimits,
) -> Iterator[bytes]:
    """Yield the official traversal stream with bounded iterative walking."""

    stack: list[_Value | _Chunk] = [_Value(root, (), 0)]
    entries = 0
    payload_bytes = 0
    while stack:
        item = stack.pop()
        if isinstance(item, _Chunk):
            chunk = item.value
            payload_bytes += len(chunk)
            limits.enforce("max_input_bytes", payload_bytes)
            limits.enforce("max_decompressed_bytes", payload_bytes)
            yield chunk
            continue

        value = item.value
        limits.enforce("max_nesting_depth", item.depth)
        if isinstance(value, dict):
            keys = sorted(value)
            if any(not isinstance(key, str) for key in keys):
                raise TypeError("notebook mappings must use string keys")
            entries += len(keys)
            limits.enforce("max_entries", entries)
            for key in reversed(keys):
                if item.path == ("metadata",) and key == "signature":
                    continue
                stack.append(_Value(value[key], (*item.path, key), item.depth + 1))
                stack.append(_Chunk(key.encode("utf-8")))
        elif isinstance(value, (list, tuple)):
            entries += len(value)
            limits.enforce("max_entries", entries)
            for index in reversed(range(len(value))):
                stack.append(
                    _Value(
                        value[index],
                        (*item.path, index),
                        item.depth + 1,
                    )
                )
        elif isinstance(value, str):
            stack.append(_Chunk(value.encode("utf-8")))
        elif value is None or isinstance(value, (bool, int, float)):
            stack.append(_Chunk(str(value).encode("utf-8")))
        else:
            raise TypeError(
                "notebook trust signatures require JSON-compatible values; "
                f"unsupported value at {item.path!r}"
            )


class HmacNotebookNotary:
    """Strong-HMAC notebook notary with explicit secret and storage backend."""

    def __init__(
        self,
        *,
        secret: bytes,
        algorithm: str = "sha256",
        store: SignatureStore | None = None,
    ) -> None:
        if not isinstance(secret, bytes) or len(secret) < 32:
            raise ValueError("notary secret must contain at least 32 bytes")
        normalized_algorithm = algorithm.casefold()
        if normalized_algorithm not in STRONG_HMAC_ALGORITHMS:
            raise ValueError(
                "algorithm must be one of: " + ", ".join(sorted(STRONG_HMAC_ALGORITHMS))
            )
        if normalized_algorithm not in hashlib.algorithms_available:
            raise ValueError(
                f"algorithm is unavailable in this Python runtime: {normalized_algorithm}"
            )
        selected_store = store or MemorySignatureStore()
        if not isinstance(selected_store, SignatureStore):
            raise TypeError("store must implement the SignatureStore protocol")
        self._secret = bytes(secret)
        self.algorithm = normalized_algorithm
        self.store = selected_store

    def compute_signature(
        self,
        document: NotebookDocument,
        *,
        limits: ResourceLimits | None = None,
    ) -> str:
        """Compute a bounded official-compatible HMAC without mutating input."""

        if not isinstance(document, NotebookDocument):
            raise TypeError("document must be an NotebookDocument")
        digest = hmac.new(self._secret, digestmod=self.algorithm)
        for chunk in _signature_chunks(document.raw, effective_limits(limits)):
            digest.update(chunk)
        return digest.hexdigest()

    def sign(
        self,
        document: NotebookDocument,
        *,
        limits: ResourceLimits | None = None,
    ) -> TrustRecord:
        """Store trust for exactly the current notebook content."""

        record = self._record(document, limits=limits)
        self.store.store_signature(record.digest, record.algorithm)
        return record

    def verify(
        self,
        document: NotebookDocument,
        *,
        limits: ResourceLimits | None = None,
    ) -> TrustVerification:
        """Verify current content without modifying notebook metadata."""

        record = self._record(document, limits=limits)
        trusted = self.store.check_signature(record.digest, record.algorithm)
        return TrustVerification(
            TrustStatus.TRUSTED if trusted else TrustStatus.UNTRUSTED,
            record,
            None if trusted else "signature_not_found",
        )

    def check_signature(
        self,
        document: NotebookDocument,
        *,
        limits: ResourceLimits | None = None,
    ) -> bool:
        """Official-style boolean verification compatibility method."""

        return self.verify(document, limits=limits).trusted

    def revoke(
        self,
        document: NotebookDocument,
        *,
        limits: ResourceLimits | None = None,
    ) -> bool:
        """Remove trust for exactly the document's current content."""

        return self.revoke_record(self._record(document, limits=limits))

    def unsign(
        self,
        document: NotebookDocument,
        *,
        limits: ResourceLimits | None = None,
    ) -> bool:
        """Official-style revocation compatibility method."""

        return self.revoke(document, limits=limits)

    def revoke_record(self, record: TrustRecord) -> bool:
        """Remove a previously retained record without notebook access."""

        if not isinstance(record, TrustRecord):
            raise TypeError("record must be a TrustRecord")
        existed = self.store.check_signature(record.digest, record.algorithm)
        if existed:
            self.store.remove_signature(record.digest, record.algorithm)
        return existed

    def _record(
        self,
        document: NotebookDocument,
        *,
        limits: ResourceLimits | None,
    ) -> TrustRecord:
        return TrustRecord(
            self.compute_signature(document, limits=limits),
            self.algorithm,
        )


__all__ = [
    "STRONG_HMAC_ALGORITHMS",
    "HmacNotebookNotary",
    "MemorySignatureStore",
    "SignatureStore",
    "TrustNotary",
    "TrustRecord",
    "TrustStatus",
    "TrustVerification",
]
