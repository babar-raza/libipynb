"""Failure-first tests for stable-identity notebook diff and guarded patches."""

from __future__ import annotations

from copy import deepcopy
from itertools import permutations

import pytest

from libipynb import (
    NotebookDocument,
    diff_notebooks,
)
from libipynb.model import CellField, DiffPolicy, PatchPreconditionError


def _document() -> NotebookDocument:
    return NotebookDocument(
        {
            "nbformat": 4,
            "nbformat_minor": 5,
            "metadata": {
                "kernelspec": {
                    "name": "python3",
                    "display_name": "Python 3",
                },
                "execution": {"run_id": "base"},
                "vendor": {"preserve": True},
            },
            "cells": [
                {
                    "cell_type": "code",
                    "id": "alpha",
                    "metadata": {
                        "tags": ["important"],
                        "execution": {"duration": 1},
                    },
                    "source": "value = 1",
                    "execution_count": 1,
                    "outputs": [
                        {
                            "output_type": "execute_result",
                            "execution_count": 1,
                            "data": {"text/plain": "1"},
                            "metadata": {"collapsed": False},
                        }
                    ],
                },
                {
                    "cell_type": "markdown",
                    "id": "beta",
                    "metadata": {},
                    "source": "Explanation",
                    "attachments": {"plot.png": {"image/png": "cGxvdA=="}},
                },
                {
                    "cell_type": "raw",
                    "id": "gamma",
                    "metadata": {"format": "text/plain"},
                    "source": "raw",
                },
            ],
        }
    )


def test_diff_tracks_move_and_each_semantic_cell_field() -> None:
    base = _document()
    target = _document()
    alpha = target.cells.pop(0)
    alpha["source"] = ["value = 2\n"]
    alpha["metadata"]["tags"] = ["important", "changed"]
    alpha["execution_count"] = 2
    alpha["outputs"] = [
        {
            "output_type": "stream",
            "name": "stdout",
            "text": "two\n",
        }
    ]
    target.cells.insert(1, alpha)
    target.cells[0]["attachments"]["plot.png"]["image/png"] = "bmV3"

    result = diff_notebooks(base, target)
    change = next(item for item in result.cell_changes if item.cell_id == "alpha")
    attachment_change = next(item for item in result.cell_changes if item.cell_id == "beta")

    assert change.moved is True
    assert change.before_index == 0
    assert change.after_index == 1
    assert {item.field for item in change.field_changes} == {
        CellField.SOURCE,
        CellField.METADATA,
        CellField.EXECUTION_COUNT,
        CellField.OUTPUTS,
    }
    assert {item.field for item in attachment_change.field_changes} == {CellField.ATTACHMENTS}
    assert attachment_change.moved is False
    assert not change.added
    assert not change.removed


def test_ignore_policy_suppresses_only_declared_transient_changes() -> None:
    base = _document()
    target = _document()
    target.raw["metadata"]["execution"] = {"run_id": "target"}
    target.cells[0]["metadata"]["execution"] = {"duration": 99}
    target.cells[0]["execution_count"] = 99
    target.cells[0]["outputs"][0]["execution_count"] = 99
    target.cells[0]["outputs"][0]["metadata"]["collapsed"] = True
    target.cells[0]["outputs"][0]["data"]["text/plain"] = "99"

    result = diff_notebooks(
        base,
        target,
        policy=DiffPolicy(
            ignore_outputs=True,
            ignore_execution_counts=True,
            ignored_metadata_keys=("collapsed", "execution"),
        ),
    )

    assert result.has_changes is False
    applied = result.to_patch().apply(base)
    assert applied.raw == base.raw


def test_patch_is_atomic_machine_applicable_and_rejects_stale_base() -> None:
    base = _document()
    target = _document()
    target.cells[0]["source"] = "value = 2"
    target.cells.append(
        {
            "cell_type": "markdown",
            "id": "delta",
            "metadata": {},
            "source": "Added",
        }
    )
    del target.cells[2]
    target.cells.insert(0, target.cells.pop(1))
    before = deepcopy(base.raw)

    patch = diff_notebooks(base, target).to_patch()
    applied = patch.apply(base)

    assert applied.raw == target.raw
    assert base.raw == before

    stale = _document()
    stale.cells[0]["source"] = "concurrent edit"
    stale_before = deepcopy(stale.raw)
    with pytest.raises(PatchPreconditionError, match="precondition"):
        patch.apply(stale)
    assert stale.raw == stale_before


def test_patch_preserves_ignored_values_on_existing_cells() -> None:
    base = _document()
    target = _document()
    target.cells[0]["source"] = "value = 2"
    target.cells[0]["execution_count"] = 50
    target.cells[0]["outputs"] = []
    target.cells[0]["metadata"]["execution"] = {"duration": 50}

    patch = diff_notebooks(
        base,
        target,
        policy=DiffPolicy(
            ignore_outputs=True,
            ignore_execution_counts=True,
            ignored_metadata_keys=("execution",),
        ),
    ).to_patch()
    applied = patch.apply(base)

    assert applied.cells[0]["source"] == "value = 2"
    assert applied.cells[0]["execution_count"] == 1
    assert applied.cells[0]["outputs"] == base.cells[0]["outputs"]
    assert applied.cells[0]["metadata"]["execution"] == {"duration": 1}


def test_insertions_do_not_turn_unchanged_cells_into_move_noise() -> None:
    base = _document()
    target = _document()
    target.cells.insert(
        0,
        {
            "cell_type": "markdown",
            "id": "inserted",
            "metadata": {},
            "source": "New first cell",
        },
    )

    result = diff_notebooks(base, target)

    assert [item.cell_id for item in result.cell_changes] == ["inserted"]
    assert result.cell_changes[0].added
    assert not result.cell_changes[0].moved


def test_missing_and_explicit_null_are_distinct_report_states() -> None:
    base = _document()
    target = _document()
    target.cells[2]["vendor_optional"] = None

    change = next(
        item for item in diff_notebooks(base, target).cell_changes if item.cell_id == "gamma"
    ).field_changes[0]

    assert change.field is CellField.OTHER
    assert change.before is None
    assert change.after is None
    assert change.before_present is False
    assert change.after_present is True


def test_ignored_count_is_not_copied_to_a_different_output_type() -> None:
    base = _document()
    target = _document()
    target.cells[0]["outputs"] = [
        {
            "output_type": "display_data",
            "data": {"text/plain": "changed type"},
            "metadata": {},
        }
    ]

    applied = (
        diff_notebooks(
            base,
            target,
            policy=DiffPolicy(ignore_execution_counts=True),
        )
        .to_patch()
        .apply(base)
    )

    assert applied.cells[0]["outputs"][0]["output_type"] == "display_data"
    assert "execution_count" not in applied.cells[0]["outputs"][0]


def test_policy_cannot_hide_non_json_target_data() -> None:
    target = _document()
    target.cells[0]["outputs"] = [object()]

    with pytest.raises(ValueError, match="JSON-compatible"):
        diff_notebooks(
            _document(),
            target,
            policy=DiffPolicy(ignore_outputs=True),
        )


@pytest.mark.parametrize("order", tuple(permutations(("alpha", "beta", "gamma"))))
def test_permutation_patch_and_reverse_patch_are_metamorphic(
    order: tuple[str, str, str],
) -> None:
    base = _document()
    target = _document()
    by_id = {cell["id"]: cell for cell in target.cells}
    target.raw["cells"] = [by_id[cell_id] for cell_id in order]

    forward = diff_notebooks(base, target)
    repeated = diff_notebooks(base, target)
    reverse = diff_notebooks(target, base)

    assert forward == repeated
    assert forward.to_patch().apply(base).raw == target.raw
    assert reverse.to_patch().apply(target).raw == base.raw


def test_diff_rejects_duplicate_stable_cell_ids() -> None:
    """An explicit, malformed duplicate id is still a real diagnostic --
    LIBIPYNB-Q3 only closes the "no id at all" gap, never id corruption."""
    document = _document()
    document.cells[1].update(id="alpha")  # collides with cells[0]'s "alpha"

    with pytest.raises(ValueError, match="unique"):
        diff_notebooks(document, _document())


def test_diff_synthesizes_a_missing_cell_id_instead_of_raising() -> None:
    """LIBIPYNB-Q3 regression: nbformat 4.0-4.4 notebooks -- the majority of
    real-world existing .ipynb files -- have no cell ids at all. This used
    to raise ValueError unconditionally; a missing id must now be
    synthesized internally instead, never mutating the caller's document."""
    document = _document()
    document.cells[0].pop("id")

    diff_notebooks(document, _document())  # must not raise

    # Must not mutate the caller's document.
    assert "id" not in document.cells[0]


def _pre_45_document(cells: list[dict]) -> NotebookDocument:
    """A genuine, id-less nbformat-4.4 notebook -- the majority-case
    real-world shape LIBIPYNB-Q3 fixes diffing for."""
    return NotebookDocument(
        {
            "nbformat": 4,
            "nbformat_minor": 4,
            "metadata": {
                "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"}
            },
            "cells": cells,
        }
    )


def _pre_45_code_cell(source: str) -> dict:
    return {
        "cell_type": "code",
        "source": source,
        "metadata": {},
        "outputs": [],
        "execution_count": None,
    }


def test_diff_synthesized_ids_are_stable_across_independent_calls() -> None:
    """LIBIPYNB-Q3: two independent diff_notebooks() calls on the same
    id-less input must synthesize the SAME ids for unchanged cells (content
    -> SHA-256 digest -> id is a pure function), not just avoid crashing.
    Regression-proofs this directly rather than trusting the algorithm."""
    before = _pre_45_document([_pre_45_code_cell("a = 1"), _pre_45_code_cell("b = 2")])
    after = _pre_45_document([_pre_45_code_cell("a = 1"), _pre_45_code_cell("b = 3")])

    first = diff_notebooks(before, after)
    second = diff_notebooks(before, after)

    assert first.cell_changes == second.cell_changes


def test_diff_reports_an_unchanged_id_less_cell_as_unchanged_not_remove_add() -> None:
    """An unchanged id-less cell synthesizes to the SAME id on both sides
    (content is a pure function -> same digest) and therefore never appears
    in cell_changes at all -- proven here alongside a genuinely changed
    sibling cell, which correctly DOES appear (as remove+add, per the
    honest, documented id-less-change limitation covered by the next test)
    so this isn't just "an empty notebook produces an empty diff"."""
    unchanged_source = "a = 1"
    before = _pre_45_document([_pre_45_code_cell(unchanged_source), _pre_45_code_cell("b = 2")])
    after = _pre_45_document([_pre_45_code_cell(unchanged_source), _pre_45_code_cell("b = 3")])

    diff = diff_notebooks(before, after)

    # The unchanged first cell must not appear in cell_changes at all.
    changed_indices = {
        index for change in diff.cell_changes for index in (change.before_index, change.after_index)
    }
    assert 0 not in changed_indices
    # The genuinely changed second cell does appear (as remove+add, since
    # id-less content changes cannot be told apart from a different cell).
    assert changed_indices == {1, None}


def test_diff_reports_a_changed_id_less_cell_as_remove_and_add() -> None:
    """Accepted, documented limitation: without any stable id, a genuinely
    changed id-less cell is indistinguishable from a different cell -- this
    is honest behavior, not a bug (see _with_stable_cell_ids' docstring)."""
    before = _pre_45_document([_pre_45_code_cell("a = 1")])
    after = _pre_45_document([_pre_45_code_cell("a = 2")])

    diff = diff_notebooks(before, after)

    assert len(diff.cell_changes) == 2
    kinds = {(change.added, change.removed) for change in diff.cell_changes}
    assert kinds == {(True, False), (False, True)}


class TestQ43TargetSnapshotMutationAfterAccessDoesNotChangeWhatAPatchApplies:
    """LIBIPYNB-Q43 Gate-G2 review finding: `_target_snapshot` was a bare,
    directly mutable dict field on `NotebookDiff`/`NotebookPatch` -- both
    `frozen=True`, but `frozen` only blocks *reassigning* the field, not
    mutating it in place, and their own `__post_init__` deep-copies only
    ever guarded against *aliasing* the constructor's input, not later
    in-place mutation via the field itself. Demonstrated live: mutating
    `NotebookDiff._target_snapshot` directly before calling `to_patch()`
    silently changed what `NotebookPatch.apply()` actually wrote into the
    resulting document -- undermining the "preconditioned patch
    application" guarantee this module's own docstring claims. A
    single-level `types.MappingProxyType` wrap alone was tried and found
    insufficient (also demonstrated live during this same investigation):
    it only blocks the *top* level -- a notebook snapshot is a
    multi-level structure, and `proxy["metadata"]` still returned an
    unwrapped, fully mutable nested dict."""

    def test_diff_target_snapshot_top_level_rejects_item_assignment(self) -> None:
        base = _document()
        target = _document()
        target.raw["metadata"]["title"] = "changed"
        diff = diff_notebooks(base, target)

        with pytest.raises(TypeError):
            diff._target_snapshot["metadata"] = {}  # type: ignore[index]

    def test_diff_target_snapshot_nested_dict_also_rejects_item_assignment(self) -> None:
        """The exact gap a shallow MappingProxyType wrap would miss."""
        base = _document()
        target = _document()
        target.raw["metadata"]["title"] = "changed"
        diff = diff_notebooks(base, target)

        with pytest.raises(TypeError):
            diff._target_snapshot["metadata"]["title"] = "TAMPERED"  # type: ignore[index]

    def test_mutating_the_frozen_field_does_not_change_what_to_patch_apply_produces(self) -> None:
        base = _document()
        target = _document()
        target.raw["metadata"]["title"] = "original-title"
        diff = diff_notebooks(base, target)

        with pytest.raises(TypeError):
            diff._target_snapshot["metadata"]["title"] = "TAMPERED"  # type: ignore[index]

        patch = diff.to_patch()
        applied = patch.apply(base)
        assert applied.metadata.get("title") == "original-title"

    def test_notebook_diff_has_a_safe_target_snapshot_property_matching_notebookpatch(
        self,
    ) -> None:
        """NotebookPatch already had a deep-copying `target_snapshot`
        property; NotebookDiff had no accessor at all, so the only way
        to read the pending target was reaching into the private field
        directly."""
        base = _document()
        target = _document()
        target.raw["metadata"]["title"] = "changed"
        diff = diff_notebooks(base, target)

        snapshot = diff.target_snapshot
        assert isinstance(snapshot, dict)
        assert snapshot["metadata"]["title"] == "changed"

        # Genuinely mutable and fully independent from the object's own state.
        snapshot["metadata"]["title"] = "locally-mutated-copy-only"
        assert diff.target_snapshot["metadata"]["title"] == "changed"

    def test_notebook_patch_target_snapshot_property_is_also_deeply_immune(self) -> None:
        base = _document()
        target = _document()
        target.raw["metadata"]["title"] = "changed"
        patch = diff_notebooks(base, target).to_patch()

        with pytest.raises(TypeError):
            patch._target_snapshot["metadata"]["title"] = "TAMPERED"  # type: ignore[index]

        applied = patch.apply(base)
        assert applied.metadata.get("title") == "changed"
