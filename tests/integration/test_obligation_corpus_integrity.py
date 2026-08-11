"""Content-addressed IPYNB corpus integrity proof for libipynb."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest

from libipynb import NotebookParseError, load
from libipynb.validation.schema import schema_diagnostics

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
VALID = FIXTURES / "valid"
INVALID = FIXTURES / "invalid"

VALID_HASHES = {
    "minimal.ipynb": "60b1be44941df5d0394431f5c4a900937c6106d65888bd39ea9da9c76ca29b2b",
    "code-and-markdown.ipynb": "77c6d7cc3b70c2a34a2dc4f9c08a71ca20a146c579a9e41e21514bfc5c903a00",
    "with-outputs.ipynb": "03ac5f4dfae9bb393b88e39b11c2b12a7df7599e7918791e1ef837eb939e53ba",
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


@pytest.mark.parametrize(("filename", "expected"), VALID_HASHES.items())
def test_active_valid_corpus_is_digest_bound_and_strictly_valid(
    filename: str,
    expected: str,
) -> None:
    path = VALID / filename
    assert _sha256(path) == expected
    value = _json(path)
    minor = value["nbformat_minor"]

    assert value["nbformat"] == 4
    assert 0 <= minor <= 5
    assert schema_diagnostics(value, minor=minor) == []
    assert load(path, mode="strict").nbformat_minor == minor


def test_invalid_fixture_fails_strict_load() -> None:
    with pytest.raises(NotebookParseError):
        load(INVALID / "missing-nbformat.ipynb", mode="strict")
