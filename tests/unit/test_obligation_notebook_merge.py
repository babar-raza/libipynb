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
    NotebookDocument,
    merge_notebooks,
)
from libipynb.model import CellConflict, ConflictKind, MergeReport


def _base() -> NotebookDocument:
    return NotebookDocument(
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


def _find(document: NotebookDocument, cell_id: str) -> dict:
    (cell,) = [c for c in document.cells if c.get("id") == cell_id]
    return cell


def _clone(document: NotebookDocument) -> NotebookDocument:
    return NotebookDocument(deepcopy(document.raw))


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


def test_identical_cell_added_independently_on_both_sides_is_not_a_conflict() -> None:
    """Neither side's diff is against a base cell here -- the id never
    existed in base. Found by fuzzing (fuzz/fuzz_diff_merge.py): the first
    version of this code assumed every non-removed, non-`None`-change cell
    id existed in base_cells and crashed with a raw KeyError."""
    base = _base()
    ours = _clone(base)
    theirs = _clone(base)
    new_cell = {
        "cell_type": "code",
        "id": "new-shared-id",
        "metadata": {},
        "source": "same = True",
        "execution_count": None,
        "outputs": [],
    }
    ours.raw["cells"].append(deepcopy(new_cell))
    theirs.raw["cells"].append(deepcopy(new_cell))

    result = merge_notebooks(base, ours, theirs)

    assert result.report.has_conflicts is False
    assert _find(result.merged, "new-shared-id")["source"] == "same = True"


def test_cell_added_independently_on_both_sides_with_different_content_conflicts() -> None:
    base = _base()
    ours = _clone(base)
    theirs = _clone(base)
    ours.raw["cells"].append(
        {
            "cell_type": "code",
            "id": "new-shared-id",
            "metadata": {},
            "source": "ours_version = True",
            "execution_count": None,
            "outputs": [],
        }
    )
    theirs.raw["cells"].append(
        {
            "cell_type": "code",
            "id": "new-shared-id",
            "metadata": {},
            "source": "theirs_version = True",
            "execution_count": None,
            "outputs": [],
        }
    )

    result = merge_notebooks(base, ours, theirs)

    assert result.report.has_conflicts is True
    (conflict,) = [c for c in result.report.conflicts if c.cell_id == "new-shared-id"]
    assert conflict.kind is ConflictKind.EDIT_EDIT
    assert conflict.ours_value["source"] == "ours_version = True"
    assert conflict.theirs_value["source"] == "theirs_version = True"
    # A merged cell still exists (never a KeyError) -- ours, explicitly
    # reported as an unresolved placeholder, not silently final.
    assert _find(result.merged, "new-shared-id")["source"] == "ours_version = True"


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
    """ "Never hide conflicts inside executable source": a conflicted source
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
    _find(ours, "alpha")["outputs"] = [{"output_type": "stream", "name": "stdout", "text": "1\n"}]

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


# ── LIBIPYNB-Q10: notebook-level metadata conflicts ─────────────────────────


def test_diverging_notebook_metadata_is_reported_as_a_conflict() -> None:
    """The exact repro from the forensic audit: kernelspec.name diverges on
    both sides -- previously has_conflicts was False with zero signal."""
    base = _base()
    ours = _clone(base)
    theirs = _clone(base)
    ours.raw["metadata"]["kernelspec"]["name"] = "ours-kernel"
    theirs.raw["metadata"]["kernelspec"]["name"] = "theirs-kernel"

    result = merge_notebooks(base, ours, theirs)

    assert result.report.has_conflicts
    (conflict,) = result.report.conflicts_of(ConflictKind.NOTEBOOK_METADATA)
    assert conflict.cell_id is None
    assert conflict.field_name == "metadata.kernelspec.name"
    assert conflict.ours_value == "ours-kernel"
    assert conflict.theirs_value == "theirs-kernel"
    # base-wins-on-conflict, matching the module's existing cell-level
    # conflict philosophy: merged output is still base's original value.
    assert result.merged.raw["metadata"]["kernelspec"]["name"] == "python3"


def test_agreeing_notebook_metadata_change_is_not_a_conflict() -> None:
    base = _base()
    ours = _clone(base)
    theirs = _clone(base)
    ours.raw["metadata"]["kernelspec"]["name"] = "same-kernel"
    theirs.raw["metadata"]["kernelspec"]["name"] = "same-kernel"

    result = merge_notebooks(base, ours, theirs)

    assert result.report.conflicts_of(ConflictKind.NOTEBOOK_METADATA) == ()


def test_unrelated_metadata_edits_on_different_paths_are_not_a_conflict() -> None:
    """Precision check: two genuinely non-overlapping metadata edits landing
    under the same top-level key must NOT be falsely flagged."""
    base = _base()
    base.raw["metadata"]["language_info"] = {"version": "3.9"}
    ours = _clone(base)
    theirs = _clone(base)
    ours.raw["metadata"]["language_info"]["version"] = "3.10"
    theirs.raw["metadata"]["kernelspec"]["name"] = "python3.11"

    result = merge_notebooks(base, ours, theirs)

    assert result.report.conflicts_of(ConflictKind.NOTEBOOK_METADATA) == ()


def test_one_sided_metadata_change_is_not_a_conflict_and_is_still_not_applied() -> None:
    """Documents the preserved, intentional scope boundary: this card is
    detection-only for TWO-sided divergence -- a one-sided notebook-
    metadata edit remains silently dropped, matching the module's existing
    documented scope (top-level metadata VALUE merging is a separate,
    unbuilt capability)."""
    base = _base()
    ours = _clone(base)
    theirs = _clone(base)
    ours.raw["metadata"]["kernelspec"]["name"] = "ours-only-kernel"

    result = merge_notebooks(base, ours, theirs)

    assert result.report.conflicts_of(ConflictKind.NOTEBOOK_METADATA) == ()
    assert result.merged.raw["metadata"]["kernelspec"]["name"] == "python3"  # still base's


def test_notebook_metadata_conflict_composes_with_a_cell_level_conflict() -> None:
    base = _base()
    ours = _clone(base)
    theirs = _clone(base)
    _find(ours, "alpha")["source"] = "x = 1  # ours"
    _find(theirs, "alpha")["source"] = "x = 1  # theirs"
    ours.raw["metadata"]["kernelspec"]["name"] = "ours-kernel"
    theirs.raw["metadata"]["kernelspec"]["name"] = "theirs-kernel"

    result = merge_notebooks(base, ours, theirs)

    kinds = {c.kind for c in result.report.conflicts}
    assert kinds == {ConflictKind.EDIT_EDIT, ConflictKind.NOTEBOOK_METADATA}


# ── LIBIPYNB-Q3: pre-4.5 (no cell-id) notebooks ─────────────────────────────


def _pre_45_base() -> NotebookDocument:
    return NotebookDocument(
        {
            "nbformat": 4,
            "nbformat_minor": 4,
            "metadata": {"kernelspec": {"name": "python3"}},
            "cells": [
                {
                    "cell_type": "code",
                    "metadata": {},
                    "source": "x = 1",
                    "execution_count": None,
                    "outputs": [],
                },
                {
                    "cell_type": "code",
                    "metadata": {},
                    "source": "y = 2",
                    "execution_count": None,
                    "outputs": [],
                },
            ],
        }
    )


def test_merge_succeeds_on_pre_45_notebooks_and_preserves_an_unchanged_cell() -> None:
    """LIBIPYNB-Q3 blocker fix: merge_notebooks() used to crash uncaught via
    diff_notebooks()'s own cell-id requirement on any nbformat 4.0-4.4
    notebook -- the majority-case real-world shape. A cell unchanged on
    both sides must merge cleanly with no conflict, proving _cell_map's
    original-vs-synthesized correlation is wired correctly (diff_notebooks
    alone stopping crashing is not sufficient -- merge needs its own
    coordinated fix, see model/merge.py::_synthesized_copy)."""
    base = _pre_45_base()
    ours = _clone(base)
    theirs = _clone(base)

    result = merge_notebooks(base, ours, theirs)  # must not raise

    assert not result.report.has_conflicts
    assert len(result.merged.cells) == 2
    # No synthesized id leaks into merge output -- pre-4.5 target stays id-less.
    assert all("id" not in cell for cell in result.merged.cells)


def test_merge_resolves_a_one_sided_change_on_a_pre_45_notebook() -> None:
    base = _pre_45_base()
    ours = _clone(base)
    theirs = _clone(base)
    ours.cells[0]["source"] = "x = 100"

    result = merge_notebooks(base, ours, theirs)

    assert not result.report.has_conflicts
    assert result.merged.cells[0]["source"] == "x = 100"
    assert result.merged.cells[1]["source"] == "y = 2"


def test_merge_detects_a_conflict_on_a_pre_45_notebook_instead_of_silently_duplicating_both_edits() -> (
    None
):
    """LIBIPYNB-Q3: a subtler correctness gap found while implementing the
    blocker fix. Since id-less cells are matched by content hash, editing
    the SAME base cell differently on both sides gives each edit a
    DIFFERENT synthesized id -- naive id-based reconciliation would then
    see "base cell removed on both sides" plus two unrelated same-position
    "added" cells, and silently keep BOTH in the merged output (duplicated,
    divergent content, no conflict reported). This must instead be
    detected and reported as a real conflict, with base's original value
    standing pending resolution -- never both sides' values kept."""
    base = _pre_45_base()
    ours = _clone(base)
    theirs = _clone(base)
    ours.cells[0]["source"] = "x = 100  # ours"
    theirs.cells[0]["source"] = "x = 100  # theirs"

    result = merge_notebooks(base, ours, theirs)

    assert result.report.has_conflicts
    (conflict,) = result.report.conflicts
    assert conflict.kind == ConflictKind.EDIT_EDIT
    assert conflict.ours_value["source"] == "x = 100  # ours"
    assert conflict.theirs_value["source"] == "x = 100  # theirs"
    # Base's original value stands for the conflicted cell -- present
    # exactly once, never either side's conflicting edit, never duplicated.
    sources = [cell["source"] for cell in result.merged.cells]
    assert sources.count("x = 1") == 1
    assert "x = 100  # ours" not in sources
    assert "x = 100  # theirs" not in sources
    assert "y = 2" in sources
    assert len(result.merged.cells) == 2


def _pre_45_code_cell(source: str) -> dict:
    return {
        "cell_type": "code",
        "metadata": {},
        "source": source,
        "execution_count": None,
        "outputs": [],
    }


def test_merge_never_loses_a_cell_when_ours_also_inserts_an_unrelated_cell_near_an_edit() -> None:
    """Independent Gate G2 review finding #1: an earlier version of the fix
    above correlated same-position replacements by comparing
    added_change.after_index == removed_change.before_index directly --
    which breaks the moment ANY other cell is also added on that side,
    because that shifts every later index. Concretely: inserting a new,
    completely unrelated cell right before editing another one is an
    everyday editing pattern, not a contrived corner case. The old logic
    picked the unrelated new cell as the "replacement" by raw index,
    silently dropping it from the merge output while letting the real
    edit through with no conflict reported at all.

    A second attempt tried to disambiguate this exact shape via
    content-similarity, but a second independent review broke THAT too
    (see the "picks the wrong cell entirely" test below) -- so the
    correlation logic was deliberately narrowed to only ever resolve an
    unambiguous, single-candidate case (see merge.py's own
    `_find_same_position_replacement_id` docstring for the full history).
    For this genuinely ambiguous shape (one edit, one adjacent unrelated
    insertion, on ONE side only), the guarantee that actually matters is
    upheld: the real divergent edit is never conflated with the unrelated
    cell, nothing is ever dropped, and no wrong value is ever reported --
    even though the divergent edit itself is not flagged as a conflict in
    this ambiguous shape (an accepted, documented limitation, not a bug)."""
    base = _pre_45_base()
    ours = _clone(base)
    theirs = _clone(base)
    ours.cells.insert(0, _pre_45_code_cell("new_cell"))
    ours.cells[1]["source"] = "x = 100  # ours"
    theirs.cells[0]["source"] = "x = 100  # theirs"

    result = merge_notebooks(base, ours, theirs)

    sources = [cell["source"] for cell in result.merged.cells]
    # The genuinely new, unrelated cell must never be silently dropped.
    assert "new_cell" in sources
    # Both real, divergent edits must survive somewhere in the output --
    # never conflated with the unrelated cell, never lost.
    assert "x = 100  # ours" in sources
    assert "x = 100  # theirs" in sources
    assert "y = 2" in sources
    # No conflict's own recorded value may ever be the wrong (unrelated)
    # cell's content.
    for conflict in result.report.conflicts:
        assert conflict.ours_value.get("source") != "new_cell"
        assert conflict.theirs_value.get("source") != "new_cell"


def test_merge_never_loses_a_cell_when_both_sides_insert_an_unrelated_cell_near_their_edit() -> (
    None
):
    """The symmetric case: both sides independently insert their own new,
    unrelated cell immediately before their own divergent edit of the same
    base cell. This is genuinely ambiguous (SequenceMatcher cannot cleanly
    separate the insertion from the edit on either side), so no conflict
    is expected to be flagged here -- what matters is that neither
    genuinely new inserted cell, nor either real edit, is ever lost or
    misattributed."""
    base = _pre_45_base()
    ours = _clone(base)
    theirs = _clone(base)
    ours.cells.insert(0, _pre_45_code_cell("new_ours"))
    ours.cells[1]["source"] = "x = 100  # ours"
    theirs.cells.insert(0, _pre_45_code_cell("new_theirs"))
    theirs.cells[1]["source"] = "x = 100  # theirs"

    result = merge_notebooks(base, ours, theirs)

    sources = [cell["source"] for cell in result.merged.cells]
    assert "new_ours" in sources
    assert "new_theirs" in sources
    assert "x = 100  # ours" in sources
    assert "x = 100  # theirs" in sources


def test_merge_never_loses_a_cell_when_two_adjacent_base_cells_are_both_edited_differently() -> (
    None
):
    """Independent Gate G2 review finding #2 (re-review of the fix above):
    when TWO ADJACENT id-less base cells are each edited differently on
    both sides -- no unrelated insertion needed at all, just an ordinary
    "edit two consecutive cells in one commit" -- `SequenceMatcher` reports
    ONE combined 2-wide replace block covering both removed base cells,
    which `_find_same_position_replacement_id` correctly declines (more
    than one base cell in the block). No conflict is flagged for either
    cell in this shape, but -- the property that matters -- all four real,
    divergent edits must survive in the output, none dropped, none
    conflated with each other."""
    base = _pre_45_base()
    base.cells.append(_pre_45_code_cell("z = 3"))
    ours = _clone(base)
    theirs = _clone(base)
    ours.cells[0]["source"] = "x = 100  # ours"
    ours.cells[1]["source"] = "y = 200  # ours"
    theirs.cells[0]["source"] = "x = 100  # theirs"
    theirs.cells[1]["source"] = "y = 200  # theirs"

    result = merge_notebooks(base, ours, theirs)

    sources = [cell["source"] for cell in result.merged.cells]
    assert "x = 100  # ours" in sources
    assert "y = 200  # ours" in sources
    assert "x = 100  # theirs" in sources
    assert "y = 200  # theirs" in sources
    assert "z = 3" in sources


def test_merge_never_picks_an_unrelated_cell_that_merely_resembles_the_base_cell_more_than_the_real_edit() -> (
    None
):
    """Independent Gate G2 review finding #2's more severe half: a content-
    similarity-based disambiguation attempt (tried between the two review
    passes) could be fooled by a genuinely new, unrelated inserted cell
    that happened to textually resemble the base cell's ORIGINAL content
    more than a substantially-rewritten TRUE edit did -- e.g. a plausible
    extra `import` line inserted next to a real edit that rewrites the
    cell's logic entirely. That heuristic would confidently (not just
    ambiguously) pick the unrelated cell as "the replacement," silently
    dropping it from the output and reporting the WRONG content in the
    resulting conflict -- worse than the original bug, not a fix for it.
    The correlation logic no longer attempts content-similarity guessing
    at all (see merge.py's own docstring): this exact shape must now
    decline safely, keeping the unrelated cell, both real edits, and
    reporting no conflict with fabricated content."""
    base = _pre_45_base()
    base.cells[0]["source"] = "import pandas as pd\nimport numpy as np"
    ours = _clone(base)
    theirs = _clone(base)
    unrelated_import_cell = _pre_45_code_cell(
        "import os\nimport sys\nimport json\nimport pandas as pd\nimport numpy as np"
    )
    ours.cells.insert(0, unrelated_import_cell)
    ours.cells[1]["source"] = "x = compute_something_totally_different_zzz()"
    theirs.cells[0]["source"] = "z = compute_something_else_totally_different_yyy()"

    result = merge_notebooks(base, ours, theirs)

    sources = [cell["source"] for cell in result.merged.cells]
    assert unrelated_import_cell["source"] in sources
    assert "x = compute_something_totally_different_zzz()" in sources
    assert "z = compute_something_else_totally_different_yyy()" in sources
    # No conflict may ever report the unrelated cell's content as though it
    # were one side's edit of the base cell.
    for conflict in result.report.conflicts:
        assert conflict.ours_value.get("source") != unrelated_import_cell["source"]
        assert conflict.theirs_value.get("source") != unrelated_import_cell["source"]
