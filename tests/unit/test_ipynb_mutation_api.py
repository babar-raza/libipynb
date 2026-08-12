"""Tests for the structural mutation API on NotebookDocument (FACT-IPYNB-104).

Prior to this fix, NotebookDocument had no mutation methods at all — the only
existing mutation test (test_ipynb_document_mutation.py) works around this
by appending directly to ``.cells``, which also means any caller-created
cell lacks a valid id (compounding the cell-id defect). These tests prove
the real add_cell/remove_cell/clear_outputs API: new cells get a valid
unique id automatically, removal doesn't disturb the rest, and
clear_outputs resets execution state per nbformat convention.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from libipynb import CELL_ID_PATTERN, NotebookDocument, dump, load

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
VALID_DIR = FIXTURES / "valid"


def _fresh_doc() -> NotebookDocument:
    return NotebookDocument({"nbformat": 4, "nbformat_minor": 5, "metadata": {}, "cells": []})


class TestAddCell:
    def test_add_cell_appends_by_default(self):
        doc = NotebookDocument.from_file(str(VALID_DIR / "code-and-markdown.ipynb"))
        original_count = doc.cell_count
        new_cell = doc.add_cell(cell_type="markdown", source="appended")
        assert doc.cell_count == original_count + 1
        assert doc.cells[-1] is new_cell
        assert new_cell["source"] == "appended"

    def test_add_cell_has_valid_unique_id(self):
        doc = _fresh_doc()
        doc.add_cell(cell_type="code", source="a")
        cell = doc.add_cell(cell_type="code", source="b")
        assert CELL_ID_PATTERN.match(cell["id"])
        assert doc.cells[0]["id"] != doc.cells[1]["id"]

    def test_add_cell_at_specific_index(self):
        doc = _fresh_doc()
        doc.add_cell(cell_type="code", source="first")
        doc.add_cell(cell_type="code", source="third")
        doc.add_cell(cell_type="markdown", source="second", index=1)

        sources = [c["source"] for c in doc.cells]
        assert sources == ["first", "second", "third"]

    def test_add_cell_defaults_to_code_with_empty_outputs(self):
        doc = _fresh_doc()
        cell = doc.add_cell()
        assert cell["cell_type"] == "code"
        assert cell["outputs"] == []
        assert cell["execution_count"] is None

    def test_add_markdown_cell_has_no_outputs_key(self):
        doc = _fresh_doc()
        cell = doc.add_cell(cell_type="markdown", source="# hi")
        assert "outputs" not in cell
        assert "execution_count" not in cell

    def test_add_cell_with_metadata(self):
        doc = _fresh_doc()
        cell = doc.add_cell(cell_type="code", source="x", metadata={"tags": ["param"]})
        assert cell["metadata"] == {"tags": ["param"]}

    def test_added_cell_survives_save_and_reload_with_same_id(self):
        doc = NotebookDocument.from_file(str(VALID_DIR / "minimal.ipynb"))
        new_cell = doc.add_cell(cell_type="code", source="z = 1")

        with tempfile.TemporaryDirectory() as td:
            dest = Path(td) / "d.ipynb"
            dump(doc, dest, profile="declared")
            reloaded = load(dest)

        assert reloaded.cells[-1]["id"] == new_cell["id"]
        assert reloaded.cells[-1]["source"] == "z = 1"


class TestRemoveCell:
    def test_remove_cell_returns_removed_cell(self):
        doc = NotebookDocument.from_file(str(VALID_DIR / "code-and-markdown.ipynb"))
        first_cell = doc.cells[0]
        removed = doc.remove_cell(0)
        assert removed == first_cell

    def test_remove_cell_reduces_count(self):
        doc = NotebookDocument.from_file(str(VALID_DIR / "code-and-markdown.ipynb"))
        original_count = doc.cell_count
        doc.remove_cell(0)
        assert doc.cell_count == original_count - 1

    def test_remove_cell_leaves_others_unaffected(self):
        doc = _fresh_doc()
        doc.add_cell(cell_type="code", source="a")
        doc.add_cell(cell_type="code", source="b")
        doc.add_cell(cell_type="code", source="c")

        doc.remove_cell(1)  # remove "b"

        sources = [c["source"] for c in doc.cells]
        assert sources == ["a", "c"]

    def test_remove_cell_out_of_range_raises(self):
        doc = _fresh_doc()
        with pytest.raises(IndexError):
            doc.remove_cell(0)

    def test_remove_all_cells_one_at_a_time(self):
        doc = _fresh_doc()
        doc.add_cell(cell_type="code", source="a")
        doc.add_cell(cell_type="code", source="b")
        doc.remove_cell(0)
        doc.remove_cell(0)
        assert doc.is_empty


class TestClearOutputs:
    def test_clear_outputs_resets_outputs_to_empty_list(self):
        doc = NotebookDocument.from_file(str(VALID_DIR / "with-outputs.ipynb"))
        assert len(doc.cells[0]["outputs"]) > 0
        doc.clear_outputs(0)
        assert doc.cells[0]["outputs"] == []

    def test_clear_outputs_resets_execution_count_to_none(self):
        doc = NotebookDocument.from_file(str(VALID_DIR / "with-outputs.ipynb"))
        assert doc.cells[0]["execution_count"] == 5
        doc.clear_outputs(0)
        assert doc.cells[0]["execution_count"] is None

    def test_clear_outputs_returns_the_cell(self):
        doc = NotebookDocument.from_file(str(VALID_DIR / "with-outputs.ipynb"))
        cell = doc.clear_outputs(0)
        assert cell is doc.cells[0]

    def test_clear_outputs_on_non_code_cell_raises(self):
        doc = _fresh_doc()
        doc.add_cell(cell_type="markdown", source="# hi")
        with pytest.raises(ValueError):
            doc.clear_outputs(0)

    def test_clear_outputs_survives_save_reload(self):
        doc = NotebookDocument.from_file(str(VALID_DIR / "with-outputs.ipynb"))
        doc.clear_outputs(0)

        with tempfile.TemporaryDirectory() as td:
            dest = Path(td) / "cleared.ipynb"
            dump(doc, dest, profile="declared")
            reloaded = load(dest)

        assert reloaded.cells[0]["outputs"] == []
        assert reloaded.cells[0]["execution_count"] is None

    def test_clear_outputs_does_not_affect_other_cells(self):
        doc = _fresh_doc()
        doc.add_cell(cell_type="code", source="a")
        cell_b = doc.add_cell(cell_type="code", source="b")
        cell_b["outputs"] = [{"output_type": "stream", "name": "stdout", "text": "b\n"}]
        cell_b["execution_count"] = 2

        doc.clear_outputs(0)

        assert doc.cells[1]["outputs"] == [
            {"output_type": "stream", "name": "stdout", "text": "b\n"}
        ]
        assert doc.cells[1]["execution_count"] == 2
