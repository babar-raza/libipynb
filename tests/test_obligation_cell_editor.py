"""Failure-first tests for stable-ID notebook cell collection editing."""

from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy

import nbformat
import pytest
from libipynb import (
    CellEditOperation,
    CellEditReport,
    CellEditor,
    CellQuery,
    IpynbDocument,
    dumps,
    edit_cells,
    loads,
)


def _document() -> IpynbDocument:
    return IpynbDocument(
        {
            "nbformat": 4,
            "nbformat_minor": 5,
            "metadata": {"vendor": {"preserve": True}},
            "cells": [
                {
                    "cell_type": "code",
                    "id": "alpha",
                    "metadata": {
                        "tags": ["setup", "remove"],
                        "slideshow": {"slide_type": "slide"},
                    },
                    "source": "value = 1",
                    "execution_count": 1,
                    "outputs": [],
                },
                {
                    "cell_type": "markdown",
                    "id": "beta",
                    "metadata": {"tags": ["keep"]},
                    "source": "Explanation",
                },
                {
                    "cell_type": "raw",
                    "id": "gamma",
                    "metadata": {
                        "tags": ["remove"],
                        "format": "text/plain",
                    },
                    "source": ["raw ", "content"],
                },
            ],
        }
    )


def _valid(document: IpynbDocument) -> None:
    nbformat.validate(nbformat.from_dict(deepcopy(document.raw)))


def test_insert_move_replace_remove_are_stable_id_operations() -> None:
    document = _document()
    editor = edit_cells(document)
    vendor = deepcopy(document.raw["metadata"])
    inserted = {
        "cell_type": "markdown",
        "id": "delta",
        "metadata": {"tags": ["new"]},
        "source": "New",
    }

    insert_report = editor.insert(inserted, index=1)
    move_report = editor.move("delta", 0)
    replace_report = editor.replace(
        "delta",
        {
            "cell_type": "raw",
            "id": "ignored-by-preserve-id",
            "metadata": {"format": "text/plain"},
            "source": "replacement",
        },
    )
    remove_report = editor.remove("delta")

    assert insert_report.changes[0].operation is CellEditOperation.INSERT
    assert move_report.changes[0].operation is CellEditOperation.MOVE
    assert replace_report.changes[0].operation is CellEditOperation.REPLACE
    assert replace_report.changes[0].cell_id == "delta"
    assert remove_report.changes[0].operation is CellEditOperation.REMOVE
    assert [cell["id"] for cell in document.cells] == [
        "alpha",
        "beta",
        "gamma",
    ]
    assert document.raw["metadata"] == vendor
    assert inserted == {
        "cell_type": "markdown",
        "id": "delta",
        "metadata": {"tags": ["new"]},
        "source": "New",
    }
    _valid(document)


def test_copy_uses_deterministic_unique_ids_and_deep_copies() -> None:
    document = _document()
    editor = edit_cells(document)

    first = editor.copy("alpha")
    second = editor.copy("alpha")
    copied = document.cells[1]
    copied["metadata"]["tags"].append("copy-only")

    assert first.changes[0].cell_id == "alpha-copy"
    assert second.changes[0].cell_id == "alpha-copy-2"
    assert [cell["id"] for cell in document.cells][:3] == [
        "alpha",
        "alpha-copy-2",
        "alpha-copy",
    ]
    assert "copy-only" not in document.cells[0]["metadata"]["tags"]
    _valid(document)


def test_search_combines_id_type_tag_metadata_and_source_criteria() -> None:
    editor = edit_cells(_document())

    matches = editor.search(
        CellQuery(
            cell_type="code",
            tag="setup",
            metadata={"slideshow": {"slide_type": "slide"}},
            source_text="value",
        )
    )
    no_matches = editor.search(
        CellQuery(
            cell_id="alpha",
            metadata={"slideshow": {"slide_type": "fragment"}},
        )
    )

    assert [cell.id for cell in matches] == ["alpha"]
    assert no_matches == ()


def test_bulk_remove_has_deterministic_report_and_safe_empty_query() -> None:
    preview_document = _document()
    apply_document = _document()
    preview_editor = edit_cells(preview_document)
    apply_editor = edit_cells(apply_document)
    before = deepcopy(preview_document.raw)
    query = CellQuery(tag="remove")

    preview = preview_editor.remove_where(query, dry_run=True)
    applied = apply_editor.remove_where(query)

    assert preview.changes == applied.changes
    assert [item.cell_id for item in applied.changes] == ["alpha", "gamma"]
    assert preview.applied is False
    assert preview_document.raw == before
    assert [cell["id"] for cell in apply_document.cells] == ["beta"]
    with pytest.raises(ValueError, match="criterion"):
        apply_editor.remove_where(CellQuery())
    with pytest.raises(ValueError, match="at least one key"):
        CellQuery(metadata={})
    _valid(apply_document)


def test_dry_run_matches_apply_and_noop_reports_are_explicit() -> None:
    preview_document = _document()
    apply_document = _document()

    preview = edit_cells(preview_document).move("gamma", 0, dry_run=True)
    applied = edit_cells(apply_document).move("gamma", 0)
    noop = edit_cells(apply_document).move("gamma", 0)

    assert preview.changes == applied.changes
    assert preview_document.cells[0]["id"] == "alpha"
    assert apply_document.cells[0]["id"] == "gamma"
    assert preview.would_change and not preview.applied
    assert applied.would_change and applied.applied
    assert not noop.would_change and not noop.applied


@pytest.mark.parametrize(
    "cell, message",
    [
        (
            {
                "cell_type": "markdown",
                "id": "alpha",
                "metadata": {},
                "source": "duplicate",
            },
            "unique",
        ),
        (
            {
                "cell_type": "code",
                "id": "delta",
                "metadata": {},
                "source": "missing fields",
            },
            "execution_count",
        ),
        (
            {
                "cell_type": "markdown",
                "id": "bad id",
                "metadata": {},
                "source": "invalid ID",
            },
            "cell ID",
        ),
    ],
)
def test_insert_rejects_invalid_or_duplicate_cells_without_mutation(
    cell: dict[str, object],
    message: str,
) -> None:
    document = _document()
    before = deepcopy(document.raw)

    with pytest.raises(ValueError, match=message):
        edit_cells(document).insert(cell)

    assert document.raw == before


def test_replace_and_bulk_failure_are_atomic() -> None:
    document = _document()
    before = deepcopy(document.raw)

    with pytest.raises(ValueError, match="outputs"):
        edit_cells(document).replace(
            "beta",
            {
                "cell_type": "code",
                "id": "beta",
                "metadata": {},
                "source": "invalid",
                "execution_count": None,
            },
        )
    assert document.raw == before

    document.cells[1]["id"] = "alpha"
    duplicated = deepcopy(document.raw)
    with pytest.raises(ValueError, match="unique"):
        edit_cells(document)
    assert document.raw == duplicated


def test_future_unknown_cells_survive_unrelated_edit_unchanged() -> None:
    document = _document()
    document.raw["nbformat_minor"] = 6
    document.cells.append(
        {
            "cell_type": "future-cell",
            "id": "future",
            "metadata": {"vendor": {"keep": True}},
            "source": "future",
            "future_payload": {"nested": [1, 2, 3]},
        }
    )
    future = deepcopy(document.cells[-1])

    edit_cells(document).move("gamma", 0)

    assert next(
        cell for cell in document.cells if cell["id"] == "future"
    ) == future


_EditorOperation = Callable[[CellEditor, bool], CellEditReport]


@pytest.mark.parametrize(
    "operation",
    [
        lambda editor, dry_run: editor.insert(
            {
                "cell_type": "markdown",
                "id": "delta",
                "metadata": {},
                "source": "inserted",
            },
            index=1,
            dry_run=dry_run,
        ),
        lambda editor, dry_run: editor.move(
            "gamma",
            0,
            dry_run=dry_run,
        ),
        lambda editor, dry_run: editor.copy(
            "alpha",
            dry_run=dry_run,
        ),
        lambda editor, dry_run: editor.replace(
            "beta",
            {
                "cell_type": "markdown",
                "id": "will-be-preserved",
                "metadata": {"tags": ["replacement"]},
                "source": "replaced",
            },
            dry_run=dry_run,
        ),
        lambda editor, dry_run: editor.remove(
            "gamma",
            dry_run=dry_run,
        ),
        lambda editor, dry_run: editor.remove_where(
            CellQuery(tag="remove"),
            dry_run=dry_run,
        ),
    ],
)
def test_every_mutation_dry_run_matches_apply_and_save_reload(
    operation: _EditorOperation,
) -> None:
    preview_document = _document()
    apply_document = _document()
    before = deepcopy(preview_document.raw)

    preview = operation(edit_cells(preview_document), True)
    applied = operation(edit_cells(apply_document), False)
    reloaded = loads(dumps(apply_document))

    assert preview.changes == applied.changes
    assert preview_document.raw == before
    assert reloaded.raw == apply_document.raw
    assert [cell["id"] for cell in reloaded.cells] == [
        cell["id"] for cell in apply_document.cells
    ]
    _valid(reloaded)
