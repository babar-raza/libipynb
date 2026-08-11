"""Failure-first configurable, dry-runnable, idempotent notebook cleanup."""

from __future__ import annotations

from copy import deepcopy

from libipynb import NotebookDocument, cleanup
from libipynb.model import CleanupPolicy


def _document() -> NotebookDocument:
    return NotebookDocument(
        {
            "nbformat": 4,
            "nbformat_minor": 5,
            "metadata": {"widgets": {"state": {}}, "keep": True},
            "cells": [
                {
                    "cell_type": "code",
                    "id": "selected",
                    "metadata": {"transient": 1, "keep": True},
                    "source": "",
                    "execution_count": 3,
                    "outputs": [
                        {"output_type": "stream", "name": "stdout", "text": "x"},
                        {
                            "output_type": "display_data",
                            "data": {"text/plain": "display"},
                            "metadata": {},
                        },
                        {
                            "output_type": "error",
                            "ename": "ValueError",
                            "evalue": "bad",
                            "traceback": ["bad"],
                        },
                    ],
                },
                {
                    "cell_type": "code",
                    "id": "untouched",
                    "metadata": {"transient": 2},
                    "source": "",
                    "execution_count": 5,
                    "outputs": [
                        {"output_type": "stream", "name": "stderr", "text": "y"}
                    ],
                },
            ],
        }
    )


def test_dry_run_report_equals_actual_selective_cleanup_and_does_not_mutate() -> None:
    document = _document()
    original = deepcopy(document.raw)
    policy = CleanupPolicy(
        cell_ids=frozenset({"selected"}),
        output_types=frozenset({"stream"}),
        notebook_metadata_keys=frozenset({"widgets"}),
        cell_metadata_keys=frozenset({"transient"}),
        reset_execution_counts=True,
    )

    preview = cleanup(document, policy=policy, dry_run=True)
    assert preview.changed
    assert document.raw == original

    applied = document.cleanup(policy=policy)
    assert applied == preview
    assert "widgets" not in document.metadata
    assert document.metadata["keep"] is True
    selected, untouched = document.cells
    assert [item["output_type"] for item in selected["outputs"]] == [
        "display_data",
        "error",
    ]
    assert selected["execution_count"] is None
    assert selected["metadata"] == {"keep": True}
    assert untouched == original["cells"][1]

    second = cleanup(document, policy=policy)
    assert not second.changed
    assert second.changes == ()


def test_default_cleanup_clears_all_outputs_and_counts_but_not_metadata() -> None:
    document = _document()

    report = cleanup(document)

    assert report.changed
    assert all(cell["outputs"] == [] for cell in document.code_cells)
    assert all(cell["execution_count"] is None for cell in document.code_cells)
    assert document.metadata["widgets"] == {"state": {}}
    assert document.cells[0]["metadata"]["transient"] == 1
