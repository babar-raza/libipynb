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
                    "outputs": [{"output_type": "stream", "name": "stderr", "text": "y"}],
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


# ── LIBIPYNB-P2: nbstripout-parity per-cell keep_output marker ─────────────


def _document_with_keep_marker(*, via: str) -> NotebookDocument:
    cell_metadata: dict[str, object] = {}
    if via == "metadata_flag":
        cell_metadata["keep_output"] = True
    elif via == "tag":
        cell_metadata["tags"] = ["keep_output"]
    return NotebookDocument(
        {
            "nbformat": 4,
            "nbformat_minor": 5,
            "metadata": {},
            "cells": [
                {
                    "cell_type": "code",
                    "id": "kept",
                    "metadata": cell_metadata,
                    "source": "",
                    "execution_count": 7,
                    "outputs": [{"output_type": "stream", "name": "stdout", "text": "keep me"}],
                },
                {
                    "cell_type": "code",
                    "id": "stripped",
                    "metadata": {},
                    "source": "",
                    "execution_count": 9,
                    "outputs": [{"output_type": "stream", "name": "stdout", "text": "strip me"}],
                },
            ],
        }
    )


def test_keep_output_metadata_flag_exempts_a_cell_from_stripping_by_default() -> None:
    document = _document_with_keep_marker(via="metadata_flag")
    cleanup(document)
    kept, stripped = document.cells
    assert kept["outputs"] != []
    assert kept["execution_count"] == 7
    assert stripped["outputs"] == []
    assert stripped["execution_count"] is None


def test_keep_output_tag_exempts_a_cell_from_stripping_by_default() -> None:
    document = _document_with_keep_marker(via="tag")
    cleanup(document)
    kept, stripped = document.cells
    assert kept["outputs"] != []
    assert kept["execution_count"] == 7
    assert stripped["outputs"] == []


def test_keep_output_marker_can_be_disabled_by_policy() -> None:
    document = _document_with_keep_marker(via="metadata_flag")
    cleanup(document, policy=CleanupPolicy(respect_keep_output_marker=False))
    kept, _stripped = document.cells
    assert kept["outputs"] == []
    assert kept["execution_count"] is None


def test_reset_execution_counts_also_resets_a_kept_outputs_own_execution_count() -> None:
    """LIBIPYNB-P2 Gate G8 finding: real nbstripout resets an execute_result
    output's own embedded execution_count in lockstep with the cell-level
    one when outputs are kept; a kept output's execution_count is exactly
    as much version-control noise as the cell-level one."""
    document = NotebookDocument(
        {
            "nbformat": 4,
            "nbformat_minor": 5,
            "metadata": {},
            "cells": [
                {
                    "cell_type": "code",
                    "id": "kept",
                    "metadata": {},
                    "source": "",
                    "execution_count": 7,
                    "outputs": [
                        {
                            "output_type": "execute_result",
                            "execution_count": 7,
                            "data": {"text/plain": "7"},
                            "metadata": {},
                        }
                    ],
                }
            ],
        }
    )
    cleanup(document, policy=CleanupPolicy(output_types=frozenset()))
    (cell,) = document.cells
    assert cell["execution_count"] is None
    assert cell["outputs"][0]["execution_count"] is None
    assert cell["outputs"][0]["data"] == {"text/plain": "7"}


def test_reset_execution_counts_false_leaves_a_kept_outputs_execution_count_alone() -> None:
    document = NotebookDocument(
        {
            "nbformat": 4,
            "nbformat_minor": 5,
            "metadata": {},
            "cells": [
                {
                    "cell_type": "code",
                    "id": "kept",
                    "metadata": {},
                    "source": "",
                    "execution_count": 7,
                    "outputs": [
                        {
                            "output_type": "execute_result",
                            "execution_count": 7,
                            "data": {"text/plain": "7"},
                            "metadata": {},
                        }
                    ],
                }
            ],
        }
    )
    cleanup(document, policy=CleanupPolicy(output_types=frozenset(), reset_execution_counts=False))
    (cell,) = document.cells
    assert cell["execution_count"] == 7
    assert cell["outputs"][0]["execution_count"] == 7


def test_keep_output_marker_does_not_exempt_cell_metadata_stripping() -> None:
    """keep_output only preserves outputs/execution_count -- an
    independently-selected cell_metadata_keys strip still applies, matching
    nbstripout's own separation of these two concerns."""
    document = NotebookDocument(
        {
            "nbformat": 4,
            "nbformat_minor": 5,
            "metadata": {},
            "cells": [
                {
                    "cell_type": "code",
                    "id": "kept",
                    "metadata": {"keep_output": True, "ExecuteTime": {"start": 1}},
                    "source": "",
                    "execution_count": 1,
                    "outputs": [{"output_type": "stream", "name": "stdout", "text": "x"}],
                }
            ],
        }
    )
    cleanup(document, policy=CleanupPolicy(cell_metadata_keys=frozenset({"ExecuteTime"})))
    (cell,) = document.cells
    assert cell["outputs"] != []
    assert "ExecuteTime" not in cell["metadata"]
