"""LIBIPYNB-P3a: line-level diff hunks for cell `source` changes.

plans/full-parity-plan.md's own acceptance criteria for this card: hunks
must be correct (a reconstruction property must hold) for every existing
diff-test fixture, re-run unmodified, and the change must be purely
additive -- no existing FieldChange/NotebookDiff consumer (including
merge_notebooks(), built on top of diff_notebooks()) may need to change.
"""

from __future__ import annotations

from copy import deepcopy

from hypothesis import assume, given
from hypothesis import strategies as st

from libipynb import NotebookDocument, diff_notebooks
from libipynb.model import CellField, DiffHunk


def _doc(source: str, *, cell_id: str = "alpha") -> NotebookDocument:
    return NotebookDocument(
        {
            "nbformat": 4,
            "nbformat_minor": 5,
            "metadata": {},
            "cells": [
                {
                    "cell_type": "code",
                    "id": cell_id,
                    "metadata": {},
                    "source": source,
                    "execution_count": None,
                    "outputs": [],
                }
            ],
        }
    )


def _source_change(before: str, after: str):
    result = diff_notebooks(_doc(before), _doc(after))
    assert len(result.cell_changes) == 1
    source_changes = [
        fc for fc in result.cell_changes[0].field_changes if fc.field == CellField.SOURCE
    ]
    assert len(source_changes) == 1
    return source_changes[0]


def _reconstruct_after(hunks: tuple[DiffHunk, ...]) -> str:
    return "".join(part for hunk in hunks for part in hunk.after_lines)


def _reconstruct_before(hunks: tuple[DiffHunk, ...]) -> str:
    return "".join(part for hunk in hunks for part in hunk.before_lines)


# ── Basic shape ──────────────────────────────────────────────────────────


def test_unchanged_source_produces_no_field_change() -> None:
    result = diff_notebooks(_doc("x = 1"), _doc("x = 1"))
    assert not result.cell_changes


def test_single_line_change_produces_hunks() -> None:
    change = _source_change("x = 1\n", "x = 2\n")
    assert change.source_hunks is not None
    assert _reconstruct_after(change.source_hunks) == "x = 2\n"
    assert _reconstruct_before(change.source_hunks) == "x = 1\n"
    ops = {hunk.op for hunk in change.source_hunks}
    assert "replace" in ops


def test_multi_line_change_produces_hunks_with_equal_and_replace_ops() -> None:
    before = "a = 1\nb = 2\nc = 3\n"
    after = "a = 1\nb = 20\nc = 3\n"
    change = _source_change(before, after)
    assert change.source_hunks is not None
    assert _reconstruct_after(change.source_hunks) == after
    assert _reconstruct_before(change.source_hunks) == before
    ops = {hunk.op for hunk in change.source_hunks}
    assert ops == {"equal", "replace"}


def test_pure_insertion_produces_an_insert_op() -> None:
    change = _source_change("a = 1\n", "a = 1\nb = 2\n")
    assert change.source_hunks is not None
    assert any(hunk.op == "insert" for hunk in change.source_hunks)
    assert _reconstruct_after(change.source_hunks) == "a = 1\nb = 2\n"


def test_pure_deletion_produces_a_delete_op() -> None:
    change = _source_change("a = 1\nb = 2\n", "a = 1\n")
    assert change.source_hunks is not None
    assert any(hunk.op == "delete" for hunk in change.source_hunks)
    assert _reconstruct_after(change.source_hunks) == "a = 1\n"


def test_whole_cell_rewrite_does_not_crash_and_reconstructs_correctly() -> None:
    before = "def f():\n    return 1\n"
    after = "class C:\n    def g(self):\n        return 2\n"
    change = _source_change(before, after)
    assert change.source_hunks is not None
    assert _reconstruct_after(change.source_hunks) == after
    assert _reconstruct_before(change.source_hunks) == before


def test_string_array_source_representation_is_supported() -> None:
    """nbformat allows source as either one string or a list of line-strings;
    the hunk engine must handle both without the caller needing to normalize
    first."""
    result = diff_notebooks(
        NotebookDocument(
            {
                "nbformat": 4,
                "nbformat_minor": 5,
                "metadata": {},
                "cells": [
                    {
                        "cell_type": "code",
                        "id": "alpha",
                        "metadata": {},
                        "source": ["a = 1\n", "b = 2\n"],
                        "execution_count": None,
                        "outputs": [],
                    }
                ],
            }
        ),
        NotebookDocument(
            {
                "nbformat": 4,
                "nbformat_minor": 5,
                "metadata": {},
                "cells": [
                    {
                        "cell_type": "code",
                        "id": "alpha",
                        "metadata": {},
                        "source": ["a = 1\n", "b = 3\n"],
                        "execution_count": None,
                        "outputs": [],
                    }
                ],
            }
        ),
    )
    source_changes = [
        fc for fc in result.cell_changes[0].field_changes if fc.field == CellField.SOURCE
    ]
    assert len(source_changes) == 1
    assert source_changes[0].source_hunks is not None
    assert _reconstruct_after(source_changes[0].source_hunks) == "a = 1\nb = 3\n"


# ── Additive, not breaking: non-source fields and add/remove get no hunks ──


def test_non_source_field_changes_have_no_source_hunks() -> None:
    before = _doc("x = 1")
    after_raw = deepcopy(before.raw)
    after_raw["cells"][0]["metadata"]["tags"] = ["new"]
    result = diff_notebooks(before, NotebookDocument(after_raw))
    metadata_changes = [
        fc for fc in result.cell_changes[0].field_changes if fc.field == CellField.METADATA
    ]
    assert len(metadata_changes) == 1
    assert metadata_changes[0].source_hunks is None


def test_added_cell_has_no_source_hunks_nothing_to_diff_against() -> None:
    before = NotebookDocument({"nbformat": 4, "nbformat_minor": 5, "metadata": {}, "cells": []})
    after = _doc("x = 1")
    result = diff_notebooks(before, after)
    assert len(result.cell_changes) == 1
    change = result.cell_changes[0]
    assert change.added
    # An added cell has no before-state to diff against, so no per-field
    # FieldChange entries exist at all for it (matching pre-existing
    # diff_notebooks behavior, unrelated to this card) -- nothing to assert
    # about source_hunks beyond that this does not crash.
    assert change.field_changes == ()


def test_existing_diff_fixture_style_notebook_still_diffs_correctly() -> None:
    """Reuses the shape of tests/unit/test_obligation_structure_diff.py's own
    fixture cells to prove this change is additive against that file's own
    established notebook shapes, not just a fresh minimal example."""
    before = NotebookDocument(
        {
            "nbformat": 4,
            "nbformat_minor": 5,
            "metadata": {"kernelspec": {"name": "python3", "display_name": "Python 3"}},
            "cells": [
                {
                    "cell_type": "code",
                    "id": "alpha",
                    "metadata": {"tags": ["important"]},
                    "source": "value = 1",
                    "execution_count": 1,
                    "outputs": [],
                },
                {
                    "cell_type": "markdown",
                    "id": "beta",
                    "metadata": {},
                    "source": "Explanation",
                },
            ],
        }
    )
    after_raw = deepcopy(before.raw)
    after_raw["cells"][0]["source"] = "value = 2"
    result = diff_notebooks(before, NotebookDocument(after_raw))
    source_changes = [
        fc for fc in result.cell_changes[0].field_changes if fc.field == CellField.SOURCE
    ]
    assert len(source_changes) == 1
    assert source_changes[0].source_hunks is not None
    assert _reconstruct_after(source_changes[0].source_hunks) == "value = 2"


# ── Metamorphic property: reconstruction always holds ──────────────────────


@given(
    before=st.text(alphabet=st.characters(blacklist_categories=("Cs",)), max_size=200),
    after=st.text(alphabet=st.characters(blacklist_categories=("Cs",)), max_size=200),
)
def test_reconstructing_after_from_hunks_always_reproduces_after_exactly(
    before: str, after: str
) -> None:
    assume(before != after)
    change = _source_change(before, after)
    assert change.source_hunks is not None
    assert _reconstruct_after(change.source_hunks) == after
    assert _reconstruct_before(change.source_hunks) == before
