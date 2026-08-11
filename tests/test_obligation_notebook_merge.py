"""IPYNB-MERGE-001 against the shipped namespace.

MUST: "Merge by stable cell identity and structure; detect move/edit,
delete/edit, output, and metadata conflicts; produce an explicit conflict
report and never hide conflicts inside executable source."

required_tests: "Conflict-matrix fixtures (move/edit, delete/edit, output,
metadata)."

`merge_notebooks` is genuinely new source (model/merge.py) -- IPYNB-MERGE-001
was ipynb's one capability with zero mapped source (0 modules, 0 tests),
the sole `missing` obligation out of ipynb's 68 (all others already
`partial`). Built on `diff_notebooks` (model/diff.py), which already
matches cells by stable id and classifies field-level changes; a three-way
merge is two of those two-way diffs reconciled cell by cell.
"""

from __future__ import annotations

from copy import deepcopy

from libipynb import (
    CellConflict,
    ConflictKind,
    IpynbDocument,
    MergeReport,
    merge_notebooks,
)


def _base() -> IpynbDocument:
    return IpynbDocument(
        {
            "nbformat": 4,
            "nbformat_minor": 5,
            "metadata": {"kernelspec": {"name": "python3"}},
            "cells": [
                {
                    "cell_type": "code",
                    "id": "alpha",
                    "metadata": {"tags": []},
                    "source": "x = 1",
                    "execution_count": None,
                    "outputs": [],
                },
                {
                    "cell_type": "markdown",
                    "id": "beta",
                    "metadata": {},
                    "source": "# Title",
                },
                {
                    "cell_type": "code",
                    "id": "gamma",
                    "metadata": {"tags": []},
                    "source": "y = 2",
                    "execution_count": None,
                    "outputs": [],
                },
            ],
        }
    )


def _find(document: IpynbDocument, cell_id: str) -> dict:
    (cell,) = [c for c in document.cells if c.get("id") == cell_id]
    return cell


def _clone(document: IpynbDocument) -> IpynbDocument:
    return IpynbDocument(deepcopy(document.raw))


# ── No divergence: clean merges, no conflicts ───────────────────────────────


def test_identical_ours_and_theirs_produce_no_conflicts() -> None:
    base = _base()
    result = merge_notebooks(base, _clone(base), _clone(base))

    assert result.report.has_conflicts is False
    assert result.report.conflicts == ()
    assert [c["id"] for c in result.merged.cells] == ["alpha", "beta", "gamma"]


def test_change_on_only_one_side_is_applied_without_conflict() -> None:
    base = _base()
    ours = _clone(base)
    _find(ours, "alpha")["source"] = "x = 99"

    result = merge_notebooks(base, ours, _clone(base))

    assert result.report.has_conflicts is False
    assert _find(result.merged, "alpha")["source"] == "x = 99"


def test_identical_change_on_both_sides_is_applied_without_conflict() -> None:
    base = _base()
    ours = _clone(base)
    theirs = _clone(base)
    _find(ours, "alpha")["source"] = "x = 42"
    _find(theirs, "alpha")["source"] = "x = 42"

    result = merge_notebooks(base, ours, theirs)

    assert result.report.has_conflicts is False
    assert _find(result.merged, "alpha")["source"] == "x = 42"


def test_addition_on_one_side_is_carried_into_the_merge() -> None:
    base = _base()
    ours = _clone(base)
    ours.add_cell(cell_type="code", source="z = 3", index=None)

    result = merge_notebooks(base, ours, _clone(base))

    assert result.report.has_conflicts is False
    assert len(result.merged.cells) == 4


# ── EDIT_EDIT: both sides change the same field to different values ────────


def test_edit_edit_conflict_on_source_is_reported() -> None:
    base = _base()
    ours = _clone(base)
    theirs = _clone(base)
    _find(ours, "alpha")["source"] = "x = 1  # ours"
    _find(theirs, "alpha")["source"] = "x = 1  # theirs"

    result = merge_notebooks(base, ours, theirs)

    assert result.report.has_conflicts is True
    (conflict,) = result.report.conflicts_of(ConflictKind.EDIT_EDIT)
    assert conflict.cell_id == "alpha"
    assert conflict.field_name == "source"
    assert conflict.ours_value == "x = 1  # ours"
    assert conflict.theirs_value == "x = 1  # theirs"


def test_conflicting_source_falls_back_to_base_not_either_side() -> None:
    """"Never hide conflicts inside executable source": a conflicted source
    field is never a marker splice of both sides, and never silently
    resolved to one side either -- it keeps base's own value pending real
    resolution."""
    base = _base()
    ours = _clone(base)
    theirs = _clone(base)
    _find(ours, "alpha")["source"] = "x = 1  # ours"
    _find(theirs, "alpha")["source"] = "x = 1  # theirs"

    result = merge_notebooks(base, ours, theirs)

    merged_source = _find(result.merged, "alpha")["source"]
    assert merged_source == "x = 1"  # base's original, untouched
    assert "<<<<<<<" not in merged_source
    assert ">>>>>>>" not in merged_source
    assert "ours" not in merged_source
    assert "theirs" not in merged_source


# ── DELETE_EDIT: one side deletes, the other edits ──────────────────────────


def test_delete_edit_conflict_is_reported() -> None:
    base = _base()
    ours = _clone(base)
    theirs = _clone(base)
    ours.cells[:] = [c for c in ours.cells if c["id"] != "beta"]
    _find(theirs, "beta")["source"] = "# Renamed Title"

    result = merge_notebooks(base, ours, theirs)

    (conflict,) = result.report.conflicts_of(ConflictKind.DELETE_EDIT)
    assert conflict.cell_id == "beta"
    # the conflicted cell survives (base's version) pending resolution
    assert _find(result.merged, "beta")["source"] == "# Title"


def test_delete_without_any_edit_on_the_other_side_is_not_a_conflict() -> None:
    base = _base()
    ours = _clone(base)
    ours.cells[:] = [c for c in ours.cells if c["id"] != "beta"]

    result = merge_notebooks(base, ours, _clone(base))

    assert result.report.has_conflicts is False
    assert [c["id"] for c in result.merged.cells] == ["alpha", "gamma"]


def test_both_sides_deleting_the_same_cell_is_not_a_conflict() -> None:
    base = _base()
    ours = _clone(base)
    theirs = _clone(base)
    ours.cells[:] = [c for c in ours.cells if c["id"] != "beta"]
    theirs.cells[:] = [c for c in theirs.cells if c["id"] != "beta"]

    result = merge_notebooks(base, ours, theirs)

    assert result.report.has_conflicts is False
    assert [c["id"] for c in result.merged.cells] == ["alpha", "gamma"]


# ── OUTPUT: both sides change a code cell's outputs differently ────────────


def test_output_conflict_is_reported() -> None:
    base = _base()
    ours = _clone(base)
    theirs = _clone(base)
    _find(ours, "alpha")["outputs"] = [
        {"output_type": "stream", "name": "stdout", "text": "ours\n"}
    ]
    _find(theirs, "alpha")["outputs"] = [
        {"output_type": "stream", "name": "stdout", "text": "theirs\n"}
    ]

    result = merge_notebooks(base, ours, theirs)

    (conflict,) = result.report.conflicts_of(ConflictKind.OUTPUT)
    assert conflict.cell_id == "alpha"
    assert conflict.field_name == "outputs"
    assert _find(result.merged, "alpha")["outputs"] == []  # base's original


def test_output_change_on_only_one_side_is_not_a_conflict() -> None:
    base = _base()
    ours = _clone(base)
    _find(ours, "alpha")["outputs"] = [
        {"output_type": "stream", "name": "stdout", "text": "1\n"}
    ]

    result = merge_notebooks(base, ours, _clone(base))

    assert result.report.has_conflicts is False
    assert _find(result.merged, "alpha")["outputs"] == [
        {"output_type": "stream", "name": "stdout", "text": "1\n"}
    ]


# ── METADATA: both sides change cell metadata differently ──────────────────


def test_metadata_conflict_is_reported() -> None:
    base = _base()
    ours = _clone(base)
    theirs = _clone(base)
    _find(ours, "gamma")["metadata"] = {"tags": ["ours-tag"]}
    _find(theirs, "gamma")["metadata"] = {"tags": ["theirs-tag"]}

    result = merge_notebooks(base, ours, theirs)

    (conflict,) = result.report.conflicts_of(ConflictKind.METADATA)
    assert conflict.cell_id == "gamma"
    assert conflict.field_name == "metadata"
    assert _find(result.merged, "gamma")["metadata"] == {"tags": []}  # base's


# ── MOVE_EDIT: one side moves the cell, the other edits its content ────────


def test_move_edit_conflict_is_reported() -> None:
    base = _base()
    ours = _clone(base)
    theirs = _clone(base)
    # ours: move gamma to the front (position only, no content change)
    ours.cells[:] = [_find(ours, "gamma"), _find(ours, "alpha"), _find(ours, "beta")]
    # theirs: edit gamma's content in place (no reorder)
    _find(theirs, "gamma")["source"] = "y = 999"

    result = merge_notebooks(base, ours, theirs)

    move_edit_conflicts = result.report.conflicts_of(ConflictKind.MOVE_EDIT)
    assert any(conflict.cell_id == "gamma" for conflict in move_edit_conflicts)


def test_move_on_only_one_side_is_not_a_conflict() -> None:
    base = _base()
    ours = _clone(base)
    ours.cells[:] = [_find(ours, "gamma"), _find(ours, "alpha"), _find(ours, "beta")]

    result = merge_notebooks(base, ours, _clone(base))

    assert result.report.has_conflicts is False


def test_both_sides_reordering_without_content_changes_is_not_flagged() -> None:
    """Documented scope boundary: pure position divergence between `ours`
    and `theirs` (neither edited content) is not one of the four named
    conflict categories and is not invented here."""
    base = _base()
    ours = _clone(base)
    theirs = _clone(base)
    ours.cells[:] = [_find(ours, "gamma"), _find(ours, "alpha"), _find(ours, "beta")]
    theirs.cells[:] = [_find(theirs, "beta"), _find(theirs, "gamma"), _find(theirs, "alpha")]

    result = merge_notebooks(base, ours, theirs)

    assert result.report.conflicts_of(ConflictKind.MOVE_EDIT) == ()


# ── Report shape ─────────────────────────────────────────────────────────


def test_report_and_conflict_types_are_the_shipped_namespace_types() -> None:
    base = _base()
    ours = _clone(base)
    theirs = _clone(base)
    _find(ours, "alpha")["source"] = "a"
    _find(theirs, "alpha")["source"] = "b"

    result = merge_notebooks(base, ours, theirs)

    assert isinstance(result.report, MergeReport)
    assert all(isinstance(c, CellConflict) for c in result.report.conflicts)


def test_multiple_independent_conflicts_are_all_reported_together() -> None:
    base = _base()
    ours = _clone(base)
    theirs = _clone(base)
    _find(ours, "alpha")["source"] = "x = 1  # ours"
    _find(theirs, "alpha")["source"] = "x = 1  # theirs"
    _find(ours, "gamma")["metadata"] = {"tags": ["a"]}
    _find(theirs, "gamma")["metadata"] = {"tags": ["b"]}

    result = merge_notebooks(base, ours, theirs)

    kinds = {c.kind for c in result.report.conflicts}
    assert kinds == {ConflictKind.EDIT_EDIT, ConflictKind.METADATA}
    assert len(result.report.conflicts) == 2
