"""Digest-checked validation against the official nbformat 4.x schemas."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterator, Mapping
from functools import lru_cache
from importlib import resources
from types import MappingProxyType
from typing import Any, Final

from .._internal.core_shim import Diagnostic, SourceLocation
from jsonschema import ValidationError, validators  # type: ignore[import-untyped]

SCHEMA_SOURCE_VERSION: Final = "nbformat-5.10.4"
SCHEMA_DIGESTS: Final[Mapping[int, str]] = MappingProxyType(
    {
        0: "573477534050198c20629c0dc2ef2b543479a41d5dbc87b3ba614e85a191c2de",
        1: "eea4f3b35fae4fd3afafe96fa6ceebe64686e3457b3035ed43c0e7999bb30be0",
        2: "08b23013c5148935f39184245ac96dbc001d526f2321ad82eb8dd98dabf732fd",
        3: "1441b5c14cd69f0dc7de0e7ef85471b41119beb2dc401c209ca2433cfbd398a3",
        4: "dddf3bff4c0bd42bd467117321d72bceddb8de7361b0cc9581bd8318e9b4d3c8",
        5: "523e3578ddbfcad52933d2423dc5951114ef73f48df180b6a601498ba5ca071a",
    }
)


class SchemaArtifactError(RuntimeError):
    """Raised when a vendored schema is absent, changed, or invalid."""


def canonical_schema_digest(payload: bytes) -> str:
    """SHA-256 of ``payload`` with line endings canonicalized to LF.

    The integrity guard must answer "is this the official schema content", not
    "was this file checked out on the same operating system as the one that
    computed the pin". Hashing raw bytes conflated the two: on a Windows
    checkout git rewrites LF to CRLF, so every vendored schema mismatched its
    pinned digest and none would load, breaking every schema-validated
    operation on that platform while the identical source passed on Linux.

    Canonicalization is deliberately limited to line endings (CRLF and lone CR
    to LF), matching this repository's declared
    ``digest_policy.tracked_text_canonicalization: CRLF_TO_LF``. Any other
    difference -- a changed key, a changed value, even an extra space inside a
    string -- still changes the digest, so the guard keeps its real purpose.
    """
    return hashlib.sha256(
        payload.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    ).hexdigest()


def _resource_name(minor: int) -> str:
    if minor not in SCHEMA_DIGESTS:
        raise ValueError("schema minor must be between 0 and 5")
    return f"nbformat.v4.{minor}.schema.json"


@lru_cache(maxsize=6)
def _schema(minor: int) -> dict[str, Any]:
    name = _resource_name(minor)
    try:
        payload = (
            resources.files(__package__)
            .joinpath("schemas", name)
            .read_bytes()
        )
    except (FileNotFoundError, OSError) as exc:
        raise SchemaArtifactError(f"official schema resource {name} is missing") from exc
    actual = canonical_schema_digest(payload)
    expected = SCHEMA_DIGESTS[minor]
    if actual != expected:
        raise SchemaArtifactError(
            f"official schema resource {name} has digest {actual}, "
            f"expected {expected}"
        )
    try:
        value = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SchemaArtifactError(
            f"official schema resource {name} is not valid JSON"
        ) from exc
    if not isinstance(value, dict):
        raise SchemaArtifactError(
            f"official schema resource {name} must contain an object"
        )
    return value


@lru_cache(maxsize=6)
def _validator(minor: int) -> Any:
    schema = _schema(minor)
    validator_type = validators.validator_for(schema)
    try:
        validator_type.check_schema(schema)
    except Exception as exc:
        raise SchemaArtifactError(
            f"official schema resource {_resource_name(minor)} is invalid"
        ) from exc
    return validator_type(schema)


def _is_discriminator_mismatch(error: ValidationError) -> bool:
    path = tuple(error.absolute_path)
    return (
        error.validator in {"const", "enum"}
        and bool(path)
        and path[-1] in {"cell_type", "output_type"}
    )


def _relevant_errors(error: ValidationError) -> Iterator[ValidationError]:
    """Select the branch matching a cell/output discriminator.

    The official schema represents cells and outputs with ``oneOf``. Reporting
    every failed branch would emit misleading raw/markdown errors for a code
    cell, so groups whose discriminator rejects the actual type are removed.
    """

    if error.validator != "oneOf" or not error.context:
        yield error
        return
    groups: dict[int, list[ValidationError]] = {}
    for child in error.context:
        schema_path = tuple(child.schema_path)
        if not schema_path or not isinstance(schema_path[0], int):
            yield error
            return
        groups.setdefault(schema_path[0], []).append(child)
    viable = [
        children
        for children in groups.values()
        if not any(_is_discriminator_mismatch(child) for child in children)
    ]
    if len(viable) != 1:
        yield error
        return
    for child in viable[0]:
        yield from _relevant_errors(child)


def _additional_property_paths(
    error: ValidationError,
) -> tuple[tuple[str | int, ...], ...]:
    if not isinstance(error.instance, Mapping) or not isinstance(
        error.schema, Mapping
    ):
        return ()
    properties = error.schema.get("properties", {})
    known = set(properties) if isinstance(properties, Mapping) else set()
    raw_patterns = error.schema.get("patternProperties", {})
    patterns = (
        tuple(re.compile(str(pattern)) for pattern in raw_patterns)
        if isinstance(raw_patterns, Mapping)
        else ()
    )
    unknown = [
        key
        for key in error.instance
        if key not in known
        and not any(pattern.search(str(key)) for pattern in patterns)
    ]
    base = tuple(error.absolute_path)
    return tuple((*base, str(key)) for key in sorted(unknown, key=str))


def _required_property_paths(
    error: ValidationError,
) -> tuple[tuple[str | int, ...], ...]:
    if not isinstance(error.instance, Mapping):
        return ()
    required = error.validator_value
    if not isinstance(required, list):
        return ()
    base = tuple(error.absolute_path)
    return tuple(
        (*base, str(key))
        for key in required
        if isinstance(key, str) and key not in error.instance
    )


def _paths(error: ValidationError) -> tuple[tuple[str | int, ...], ...]:
    if error.validator == "additionalProperties":
        expanded = _additional_property_paths(error)
        if expanded:
            return expanded
    if error.validator == "required":
        expanded = _required_property_paths(error)
        if expanded:
            return expanded
    return (tuple(error.absolute_path),)


def _code(error: ValidationError) -> str:
    suffix = re.sub(r"[^A-Za-z0-9]+", "_", str(error.validator)).strip("_")
    return f"IPYNB_SCHEMA_{suffix.upper() or 'INVALID'}"


def schema_diagnostics(
    value: Mapping[str, Any],
    *,
    minor: int,
) -> list[Diagnostic]:
    """Return deterministic official-schema diagnostics for one exact minor."""

    try:
        raw_errors = list(_validator(minor).iter_errors(value))
    except SchemaArtifactError as exc:
        return [
            Diagnostic(
                code="IPYNB_SCHEMA_ARTIFACT",
                message=str(exc),
                location=SourceLocation(path=()),
            )
        ]
    diagnostics = [
        Diagnostic(
            code=_code(error),
            message=error.message,
            location=SourceLocation(path=path),
        )
        for raw_error in raw_errors
        for error in _relevant_errors(raw_error)
        for path in _paths(error)
    ]
    return sorted(
        diagnostics,
        key=lambda item: (
            tuple(str(part) for part in item.location.path)
            if item.location is not None
            else (),
            item.code,
            item.message,
        ),
    )


__all__ = [
    "SCHEMA_DIGESTS",
    "SCHEMA_SOURCE_VERSION",
    "SchemaArtifactError",
    "canonical_schema_digest",
    "schema_diagnostics",
]
