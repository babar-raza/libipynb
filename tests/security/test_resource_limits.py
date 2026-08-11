"""Tests for NotebookResourceLimits enforcement."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from libipynb import load, loads, NotebookResourceLimitError
from libipynb.security.limits import NotebookResourceLimits

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
ADVERSARIAL = FIXTURES / "adversarial"


def _minimal_notebook(
    *,
    cells: list[dict] | None = None,
    metadata: dict | None = None,
) -> dict:
    """Build a minimal valid nbformat 4.5 notebook dict."""
    return {
        "nbformat": 4,
        "nbformat_minor": 5,
        "metadata": metadata or {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"}},
        "cells": cells or [],
    }


def _code_cell(source: str = "", *, cell_id: str = "cell-0") -> dict:
    return {
        "cell_type": "code",
        "id": cell_id,
        "metadata": {},
        "source": source,
        "execution_count": None,
        "outputs": [],
    }


# ---------------------------------------------------------------------------
# max_input_bytes
# ---------------------------------------------------------------------------


def test_huge_json_input_exceeds_max_input_bytes() -> None:
    """A notebook JSON string larger than 64 MiB must raise NotebookResourceLimitError."""
    # Build a notebook whose serialized form exceeds the 64 MiB default.
    # A single cell with a very long source string is the cheapest way.
    filler = "x" * (65 * 1024 * 1024)  # 65 MiB of padding
    nb = _minimal_notebook(cells=[_code_cell(source=filler)])
    payload = json.dumps(nb)
    assert len(payload.encode()) > 64 * 1024 * 1024

    with pytest.raises(NotebookResourceLimitError, match="max_input_bytes"):
        loads(payload)


# ---------------------------------------------------------------------------
# max_nesting_depth
# ---------------------------------------------------------------------------


def test_deeply_nested_json_exceeds_max_nesting_depth() -> None:
    """Loading a fixture with 59 nesting levels and a limit of 10 must raise."""
    fixture = ADVERSARIAL / "deeply-nested-metadata.ipynb"
    assert fixture.exists(), f"Missing adversarial fixture: {fixture}"

    strict_limits = NotebookResourceLimits(max_nesting_depth=10)

    with pytest.raises(NotebookResourceLimitError, match="max_nesting_depth"):
        load(fixture, mode="recovery", limits=strict_limits)


# ---------------------------------------------------------------------------
# max_entries
# ---------------------------------------------------------------------------


def test_notebook_with_excessive_entries_exceeds_max_entries() -> None:
    """A notebook with many cells/outputs must be rejected when max_entries is tiny."""
    cells = [_code_cell(source=f"print({i})", cell_id=f"cell-{i}") for i in range(50)]
    nb = _minimal_notebook(cells=cells)
    payload = json.dumps(nb)

    tiny_limits = NotebookResourceLimits(max_entries=10)

    with pytest.raises(NotebookResourceLimitError, match="max_entries"):
        loads(payload, limits=tiny_limits)


# ---------------------------------------------------------------------------
# Default limits accept normal notebooks
# ---------------------------------------------------------------------------


def test_default_limits_allow_normal_notebooks() -> None:
    """A normal, well-formed notebook must load without errors under defaults."""
    nb = _minimal_notebook(cells=[_code_cell(source="1 + 1", cell_id="ok-1")])
    payload = json.dumps(nb)

    doc = loads(payload, mode="recovery")
    assert doc.cell_count == 1


def test_default_limits_allow_fixture_notebooks() -> None:
    """The huge-base64-output fixture (~1 MiB) must load under default limits."""
    fixture = ADVERSARIAL / "huge-base64-output.ipynb"
    if not fixture.exists():
        pytest.skip("huge-base64-output.ipynb fixture not available")

    doc = load(fixture, mode="recovery")
    assert doc.cell_count >= 1


# ---------------------------------------------------------------------------
# with_overrides
# ---------------------------------------------------------------------------


def test_custom_limits_can_be_stricter() -> None:
    """with_overrides produces a new object with the requested tighter values."""
    base = NotebookResourceLimits()
    strict = base.with_overrides(max_input_bytes=1024, max_entries=5)

    assert strict.max_input_bytes == 1024
    assert strict.max_entries == 5
    # Unchanged fields keep their defaults.
    assert strict.max_output_bytes == base.max_output_bytes
    assert strict.max_nesting_depth == base.max_nesting_depth


def test_with_overrides_rejects_unknown_limit() -> None:
    """Passing an unknown limit name to with_overrides must raise TypeError."""
    with pytest.raises(TypeError):
        NotebookResourceLimits().with_overrides(max_bananas=42)


def test_limits_reject_non_positive_values() -> None:
    """NotebookResourceLimits must reject zero or negative values."""
    with pytest.raises(ValueError):
        NotebookResourceLimits(max_input_bytes=0)

    with pytest.raises(ValueError):
        NotebookResourceLimits(max_nesting_depth=-1)
