"""Content-addressed IPYNB corpus integrity proof for libipynb.

LIBIPYNB-Q21 (P0-F) digest policy: every hash in this file authenticates
*normalized text bytes* (CRLF/CR canonicalized to LF), never exact
git-checkout bytes and never sdist-archive bytes. This matters because git
line-ending settings (``core.autocrlf``) mean the exact bytes on disk for a
tracked text file genuinely differ between a Windows checkout (CRLF, if
``core.autocrlf=true``, the common Windows default) and a Linux checkout of
the identical commit (LF, the canonical blob content) -- hashing raw
on-disk bytes made this integrity check pass or fail purely based on which
OS/git-config combination checked the repo out, independent of the actual
notebook content. Reuses ``canonical_schema_digest`` (already applied to
the vendored nbformat schemas, for the identical reason -- see
``validation/schema.py``'s own docstring) rather than a second,
independently-maintained normalization implementation. A root
``.gitattributes`` additionally forces these paths to check out as LF in
the first place, so this normalization is belt-and-suspenders, not the
only thing standing between this test and a platform-dependent failure.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from libipynb import NotebookParseError, load
from libipynb.validation.schema import canonical_schema_digest, schema_diagnostics

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
VALID = FIXTURES / "valid"
INVALID = FIXTURES / "invalid"

# Recomputed against LF-normalized content (see module docstring) --
# these no longer match the raw bytes of a CRLF checkout, by design.
VALID_HASHES = {
    "minimal.ipynb": "33b5ee284b44179f7121ecb1c766dc6503fa349913fb1678d2dcdef2d117454f",
    "code-and-markdown.ipynb": "760f80283f4e2601bf35c9593cce19b8645fa3e2a9871ee017a36295cb05c2a4",
    "with-outputs.ipynb": "22461b0253a600f0aac0afd8ba5ecc8d60c2efcc4cf6188a808544367308b79e",
}

# LIBIPYNB-Q2 (real-world corpus sourcing): {category: {filename: sha256}}
# for every fixture vendored via scripts/fetch_fixture.py (see
# tests/fixtures/PROVENANCE.md's "Vendored real-world fixtures" table,
# which fetch_fixture.py itself keeps in sync with this dict's own hashes
# -- so this can never silently drift from what was actually vendored).
# Deliberately empty until the maintainer approves and vendors the first
# real-world fixture; see PROVENANCE.md's "Repeatable sourcing process".
# Hashed the same normalized way as VALID_HASHES above -- see this file's
# own module docstring for the policy.
REAL_WORLD_HASHES: dict[str, dict[str, str]] = {}


def _sha256(path: Path) -> str:
    return canonical_schema_digest(path.read_bytes())


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


def test_crlf_and_lf_variants_of_the_same_content_hash_identically(tmp_path: Path) -> None:
    """LIBIPYNB-Q21 (P0-F): proves the fix, not just re-derives new
    hardcoded numbers -- the exact same logical content, checked out with
    Windows-style CRLF line endings (simulating a core.autocrlf=true
    checkout) versus Unix-style LF (simulating a Linux/CI checkout, the
    canonical git blob form), must hash identically under this file's own
    _sha256() -- confirmed on this exact Windows checkout AND directly
    against a raw-bytes LF string (simulating a Linux checkout) in the
    same test process, so this doesn't depend on this test actually
    running on two different machines to prove the point."""
    content = json.dumps(
        {"nbformat": 4, "nbformat_minor": 5, "metadata": {"a": 1}, "cells": []}, indent=2
    ).encode()
    assert b"\r\n" not in content  # json.dumps produces bare \n

    lf_path = tmp_path / "lf.ipynb"
    crlf_path = tmp_path / "crlf.ipynb"
    lf_path.write_bytes(content)
    crlf_path.write_bytes(content.replace(b"\n", b"\r\n"))

    assert lf_path.read_bytes() != crlf_path.read_bytes()  # sanity: genuinely different bytes
    assert _sha256(lf_path) == _sha256(crlf_path)


def test_gitattributes_forces_lf_for_content_addressed_paths() -> None:
    """The .gitattributes policy is belt-and-suspenders alongside the
    hashing normalization above -- a fresh checkout should be LF for
    these paths in the first place, on any platform. Checked via `git
    check-attr` rather than re-implementing gitattributes pattern
    matching here."""
    import subprocess

    repo_root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        ["git", "check-attr", "eol", "--", "tests/fixtures/valid/minimal.ipynb"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        pytest.skip(f"git check-attr unavailable in this environment: {result.stderr.strip()}")
    assert "eol: lf" in result.stdout


def _real_world_cases() -> list[tuple[str, str, str]]:
    return [
        (category, filename, expected)
        for category, files in REAL_WORLD_HASHES.items()
        for filename, expected in files.items()
    ]


@pytest.mark.parametrize(("category", "filename", "expected"), _real_world_cases())
def test_vendored_real_world_fixture_is_digest_bound_and_strictly_valid(
    category: str,
    filename: str,
    expected: str,
) -> None:
    """LIBIPYNB-Q2: mirrors test_active_valid_corpus_is_digest_bound_and_
    strictly_valid above, generalized across whichever category directory
    a vendored real-world fixture lands in (not just valid/, since the
    qualifying criteria in PROVENANCE.md don't restrict real-world
    fixtures to that one category). Parametrized over REAL_WORLD_HASHES,
    so this test collects zero cases -- and therefore proves nothing yet
    -- until that dict is populated; see PROVENANCE.md's own "Repeatable
    sourcing process" for how a vendored fixture's hash gets added here."""
    path = FIXTURES / category / filename
    assert _sha256(path) == expected
    value = _json(path)
    minor = value["nbformat_minor"]

    assert value["nbformat"] == 4
    assert 0 <= minor <= 5
    assert schema_diagnostics(value, minor=minor) == []
    assert load(path, mode="strict").nbformat_minor == minor
