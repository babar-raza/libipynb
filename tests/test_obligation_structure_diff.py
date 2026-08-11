"""Failure-first tests for stable-identity notebook diff and guarded patches."""

from __future__ import annotations

from collections.abc import Callable
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
                    "attachments": {
                        "plot.png": {"image/png": "cGxvdA=="}
                    },
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
    attachment_change = next(
        item for item in result.cell_changes if item.cell_id == "beta"
    )

    assert change.moved is True
    assert change.before_index == 0
    assert change.after_index == 1
    assert {item.field for item in change.field_changes} == {
        CellField.SOURCE,
        CellField.METADATA,
        CellField.EXECUTION_COUNT,
        CellField.OUTPUTS,
    }
    assert {
        item.field for item in attachment_change.field_changes
    } == {CellField.ATTACHMENTS}
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
        item
        for item in diff_notebooks(base, target).cell_changes
        if item.cell_id == "gamma"
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

    applied = diff_notebooks(
        base,
        target,
        policy=DiffPolicy(ignore_execution_counts=True),
    ).to_patch().apply(base)

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


@pytest.mark.parametrize(
    "mutate, message",
    [
        (lambda value: value.cells[0].pop("id"), "missing"),
        (lambda value: value.cells[1].update(id="alpha"), "unique"),
    ],
)
def test_diff_rejects_missing_or_duplicate_stable_cell_ids(
    mutate: Callable[[NotebookDocument], object],
    message: str,
) -> None:
    document = _document()
    mutate(document)

    with pytest.raises(ValueError, match=message):
        diff_notebooks(document, _document())
