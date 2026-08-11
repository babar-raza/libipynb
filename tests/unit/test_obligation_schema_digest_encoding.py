"""TC-FF6-IPYNB-SCHEMA-DIGEST-001: schema integrity must not depend on encoding.

The vendored official nbformat schemas are verified by digest before use. That
guard hashed raw bytes, so on a Windows checkout -- where git rewrites LF to
CRLF -- every digest mismatched and all six schemas failed to load, breaking
every schema-validated operation on that platform while the identical source
passed on Linux.

These tests pin both halves: encoding must not decide integrity, and genuinely
different content must still be rejected. The second half matters most -- the
cheap "fix" of relaxing the guard would pass the first half and destroy the
protection.
"""

from __future__ import annotations

import hashlib
import json
from importlib import resources
from pathlib import Path

import pytest

from libipynb.validation.schema import (
    SCHEMA_DIGESTS,
    SCHEMA_SOURCE_VERSION,
    SchemaArtifactError,
    canonical_schema_digest,
)

MINORS = list(range(6))
VENDORED = (
    Path(__file__).resolve().parents[2]
    / "src/libipynb/validation/schemas"
)


def _official_bytes(minor: int) -> bytes:
    return (
        resources.files("nbformat.v4")
        .joinpath(f"nbformat.v4.{minor}.schema.json")
        .read_bytes()
    )


# ── The pinned digests are the official ones ───────────────────────────────


@pytest.mark.parametrize("minor", MINORS)
def test_pinned_digest_matches_the_official_nbformat_schema(minor: int) -> None:
    """The constants are the authority; the vendored copy must conform to them."""
    official = hashlib.sha256(_official_bytes(minor)).hexdigest()
    assert SCHEMA_DIGESTS[minor] == official


def test_declared_source_version_matches_the_installed_oracle() -> None:
    import nbformat

    assert SCHEMA_SOURCE_VERSION == f"nbformat-{nbformat.__version__}"


# ── Encoding must not decide integrity ─────────────────────────────────────


@pytest.mark.parametrize("minor", MINORS)
def test_vendored_schema_is_the_official_content(minor: int) -> None:
    vendored = (VENDORED / f"nbformat.v4.{minor}.schema.json").read_bytes()
    assert json.loads(vendored) == json.loads(_official_bytes(minor))


@pytest.mark.parametrize("minor", MINORS)
def test_crlf_encoded_schema_has_the_pinned_digest(minor: int) -> None:
    """The exact shape that broke every Windows checkout."""
    crlf = _official_bytes(minor).replace(b"\n", b"\r\n")
    assert canonical_schema_digest(crlf) == SCHEMA_DIGESTS[minor]


@pytest.mark.parametrize("minor", MINORS)
def test_lf_encoded_schema_has_the_pinned_digest(minor: int) -> None:
    """The platform that already worked must keep working."""
    assert canonical_schema_digest(_official_bytes(minor)) == SCHEMA_DIGESTS[minor]


def test_lone_cr_line_endings_also_canonicalize() -> None:
    cr = _official_bytes(0).replace(b"\n", b"\r")
    assert canonical_schema_digest(cr) == SCHEMA_DIGESTS[0]


# ── The guard must still catch real tampering ──────────────────────────────


def test_content_change_is_still_rejected() -> None:
    """Relaxing the digest into uselessness would pass every test above."""
    tampered = _official_bytes(0).replace(b'"cells"', b'"CELLS"')
    assert canonical_schema_digest(tampered) != SCHEMA_DIGESTS[0]


def test_whitespace_inside_a_json_string_is_not_normalized_away() -> None:
    """Canonicalization is line endings only, not general whitespace stripping."""
    original = _official_bytes(0)
    injected = original.replace(b"JSON schema.", b"JSON  schema.", 1)
    assert injected != original
    assert canonical_schema_digest(injected) != SCHEMA_DIGESTS[0]


# ── The loader works end to end on this platform ───────────────────────────


@pytest.mark.parametrize("minor", MINORS)
def test_every_minor_schema_loads(minor: int) -> None:
    from libipynb.validation.schema import _schema

    schema = _schema(minor)
    assert schema["$schema"]
    assert "cells" in schema["properties"]


def test_minimal_notebook_validates_against_the_official_schema() -> None:
    from libipynb.validation.validator import validate

    notebook = {
        "cells": [
            {
                "cell_type": "code",
                "execution_count": None,
                "metadata": {},
                "outputs": [],
                "source": [],
            }
        ],
        "metadata": {},
        "nbformat": 4,
        "nbformat_minor": 0,
    }
    assert validate(notebook, profile="4.0").is_valid


def test_missing_schema_resource_still_raises() -> None:
    from libipynb.validation.schema import _resource_name

    with pytest.raises(ValueError):
        _resource_name(99)


def test_schema_artifact_error_is_still_reachable() -> None:
    """The error type must remain part of the contract, not be deleted."""
    assert issubclass(SchemaArtifactError, RuntimeError)
