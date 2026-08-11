"""Shared fixtures for libipynb / nbformat interoperability tests."""

from __future__ import annotations

from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"
VALID_DIR = FIXTURES_DIR / "valid"
INVALID_DIR = FIXTURES_DIR / "invalid"
CORPUS_DIR = FIXTURES_DIR / "corpus"


@pytest.fixture
def nbformat_available():
    """Skip the test if nbformat is not installed."""
    pytest.importorskip("nbformat", reason="nbformat is not installed")


def _collect_notebooks(directory: Path) -> list[Path]:
    """Return sorted .ipynb paths under *directory*, or empty if it does not exist."""
    if not directory.is_dir():
        return []
    return sorted(directory.glob("*.ipynb"))


def _notebook_id(path: Path) -> str:
    """Human-readable pytest ID derived from the fixture filename."""
    return path.stem


@pytest.fixture(
    params=_collect_notebooks(VALID_DIR),
    ids=[_notebook_id(p) for p in _collect_notebooks(VALID_DIR)],
)
def valid_fixture_path(request: pytest.FixtureRequest) -> Path:
    """Yield each valid fixture path one at a time."""
    return request.param


@pytest.fixture(
    params=_collect_notebooks(INVALID_DIR),
    ids=[_notebook_id(p) for p in _collect_notebooks(INVALID_DIR)],
)
def invalid_fixture_path(request: pytest.FixtureRequest) -> Path:
    """Yield each invalid fixture path one at a time."""
    return request.param


@pytest.fixture(
    params=_collect_notebooks(CORPUS_DIR),
    ids=[_notebook_id(p) for p in _collect_notebooks(CORPUS_DIR)],
)
def corpus_fixture_path(request: pytest.FixtureRequest) -> Path:
    """Yield each corpus fixture path one at a time."""
    return request.param
