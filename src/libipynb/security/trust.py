"""Content-addressed notebook trust with a pluggable signature store."""

from __future__ import annotations

import hashlib
import hmac
import sqlite3
import stat
from collections import OrderedDict
from collections.abc import Iterator
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from threading import RLock
from typing import Any, Protocol, Self, runtime_checkable

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


class SqliteSignatureStore:
    """File-backed signature store that survives a process restart.

    Conforms to the same :class:`SignatureStore` protocol as
    :class:`MemorySignatureStore`. This is purely opt-in: the default
    trust behavior (``HmacNotebookNotary()`` with no ``store=``) remains
    the process-local, non-persistent :class:`MemorySignatureStore` --
    callers must explicitly construct and pass this store to get
    durability. This is a from-scratch SQLite schema tailored to this
    store's own three-method contract, not a byte-compatible adapter over
    the official nbformat ``nbsignatures.db`` file (a genuinely different,
    larger undertaking not required by this store's own contract).
    """

    def __init__(
        self,
        path: str | Path,
        *,
        max_signatures: int | None = 65_535,
    ) -> None:
        if max_signatures is not None and (
            isinstance(max_signatures, bool)
            or not isinstance(max_signatures, int)
            or max_signatures <= 0
        ):
            raise ValueError("max_signatures must be a positive integer or None")
        self._max_signatures = max_signatures
        self._lock = RLock()
        # check_same_thread=False: this store serializes all access itself
        # via `_lock`, so the underlying connection is never touched by two
        # threads concurrently despite being shared across them.
        self._connection = sqlite3.connect(str(path), check_same_thread=False)
        with self._lock:
            self._connection.execute("PRAGMA journal_mode=WAL")
            self._connection.execute(
                "CREATE TABLE IF NOT EXISTS signatures ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "digest TEXT NOT NULL, "
                "algorithm TEXT NOT NULL, "
                "UNIQUE (digest, algorithm))"
            )
            self._connection.commit()
        # WAL mode creates `-wal`/`-shm` sidecar files alongside the main
        # database file; restrict all three (Gate G2 finding: only the main
        # file was restricted originally, leaving the sidecars -- which can
        # hold recently-written digest/algorithm rows, though never the HMAC
        # secret itself -- world-readable on POSIX until the next checkpoint).
        for suffix in ("", "-wal", "-shm"):
            _restrict_to_owner(f"{path}{suffix}")

    def store_signature(self, digest: str, algorithm: str) -> None:
        digest, algorithm = _store_key(digest, algorithm)
        with self._lock:
            self._connection.execute(
                "INSERT OR REPLACE INTO signatures (digest, algorithm) VALUES (?, ?)",
                (digest, algorithm),
            )
            if self._max_signatures is not None:
                self._connection.execute(
                    "DELETE FROM signatures WHERE id NOT IN "
                    "(SELECT id FROM signatures ORDER BY id DESC LIMIT ?)",
                    (self._max_signatures,),
                )
            self._connection.commit()

    def check_signature(self, digest: str, algorithm: str) -> bool:
        digest, algorithm = _store_key(digest, algorithm)
        with self._lock:
            cursor = self._connection.execute(
                "SELECT 1 FROM signatures WHERE digest = ? AND algorithm = ? LIMIT 1",
                (digest, algorithm),
            )
            return cursor.fetchone() is not None

    def remove_signature(self, digest: str, algorithm: str) -> None:
        digest, algorithm = _store_key(digest, algorithm)
        with self._lock:
            self._connection.execute(
                "DELETE FROM signatures WHERE digest = ? AND algorithm = ?",
                (digest, algorithm),
            )
            self._connection.commit()

    def __len__(self) -> int:
        with self._lock:
            cursor = self._connection.execute("SELECT COUNT(*) FROM signatures")
            row = cursor.fetchone()
            return int(row[0]) if row is not None else 0

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_exc_info: object) -> None:
        self.close()


def _restrict_to_owner(path: str | Path) -> None:
    """Best-effort owner-only file permissions (POSIX); a no-op where
    unsupported (Windows has no equivalent `chmod` bit for this) or where
    the underlying filesystem rejects the change -- this is defense in
    depth for a locally-stored trust database, not the sole control: an
    attacker able to write to this file still cannot forge a signature the
    HMAC notary will accept, since doing so requires the notary's own
    secret, which this store never sees or stores."""

    try:
        Path(path).chmod(stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass


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
        # Not `store or MemorySignatureStore()`: any store implementing
        # `__len__` (both MemorySignatureStore and SqliteSignatureStore do)
        # is falsy while empty, so `or` would silently discard a caller's
        # explicit, empty store on every first use and replace it with a
        # throwaway MemorySignatureStore -- discovered via SqliteSignatureStore
        # (LIBIPYNB-V2): a fresh persistent store looked identical to "no
        # store provided," so nothing was ever actually persisted. Check
        # identity against None instead, which is correct regardless of the
        # store's own truthiness.
        selected_store = store if store is not None else MemorySignatureStore()
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
    "SqliteSignatureStore",
    "TrustNotary",
    "TrustRecord",
    "TrustStatus",
    "TrustVerification",
]
