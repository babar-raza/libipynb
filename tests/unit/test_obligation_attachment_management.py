"""Failure-first tests for typed, reference-safe attachment management."""

from __future__ import annotations

from copy import deepcopy

import pytest

from libipynb import (
    NotebookDocument,
    manage_attachments,
    validate,
)
from libipynb.model import AttachmentReferencePolicy


def _document(
    source: str | list[str] = "![plot](attachment:plot.png)",
) -> NotebookDocument:
    return NotebookDocument(
        {
            "nbformat": 4,
            "nbformat_minor": 5,
            "metadata": {"vendor": {"preserve": True}},
            "cells": [
                {
                    "cell_type": "markdown",
                    "id": "markdown",
                    "metadata": {"custom": {"preserve": True}},
                    "source": source,
                    "attachments": {
                        "plot.png": {
                            "image/png": "cGxvdA==",
                            "application/vnd.example+json": {"keep": True},
                        }
                    },
                },
                {
                    "cell_type": "code",
                    "id": "code",
                    "metadata": {},
                    "source": "",
                    "execution_count": None,
                    "outputs": [],
                },
            ],
        }
    )


def _codes(document: NotebookDocument) -> set[str]:
    return {item.code for item in validate(document).diagnostics}


def test_add_resolves_missing_reference_and_preserves_unknown_metadata() -> None:
    document = _document("![new](attachment:new.json)")
    document.cells[0]["attachments"] = {}
    before_metadata = deepcopy(document.raw["metadata"])

    report = manage_attachments(document).add(
        "markdown",
        "new.json",
        {"application/json": {"value": 1}},
    )

    assert report.applied is True
    assert report.would_change is True
    assert report.count == 1
    assert report.changes[0].references == 1
    assert document.raw["metadata"] == before_metadata
    assert validate(document).is_valid


def test_add_rejects_invalid_cells_bundles_and_accidental_replacement() -> None:
    manager = manage_attachments(_document())

    with pytest.raises(ValueError, match="markdown or raw"):
        manager.add("code", "bad.txt", {"text/plain": "bad"})
    with pytest.raises(ValueError, match="MIME"):
        manager.add("markdown", "bad.txt", {"invalid": "bad"})
    with pytest.raises(ValueError, match="already exists"):
        manager.add("markdown", "plot.png", {"image/png": "replacement"})


def test_rename_rewrites_encoded_references_and_preserves_source_shape() -> None:
    document = _document(
        [
            "![one](attachment:plot.png)\n",
            "![two](attachment:plot%2Epng)",
        ]
    )

    report = manage_attachments(document).rename(
        "markdown",
        "plot.png",
        "final plot.png",
    )

    cell = document.cells[0]
    assert isinstance(cell["source"], list)
    assert len(cell["source"]) == 2
    assert "final plot.png" in cell["attachments"]
    assert "plot.png" not in cell["attachments"]
    assert "attachment:final%20plot.png" in "".join(cell["source"])
    assert report.changes[0].references == 2
    assert report.changes[0].dangling_references == 0
    assert validate(document).is_valid


def test_remove_refuses_dangling_reference_unless_explicitly_allowed() -> None:
    document = _document()
    manager = manage_attachments(document)
    before = deepcopy(document.raw)

    with pytest.raises(ValueError, match="still referenced"):
        manager.remove("markdown", "plot.png")
    assert document.raw == before

    report = manager.remove(
        "markdown",
        "plot.png",
        reference_policy=AttachmentReferencePolicy.LEAVE_DANGLING,
    )
    assert report.changes[0].dangling_references == 1
    assert "IPYNB_ATTACHMENT_MISSING" in _codes(document)


def test_remove_unreferenced_attachment_is_valid_and_idempotently_absent() -> None:
    document = _document("no attachment reference")
    manager = manage_attachments(document)

    report = manager.remove("markdown", "plot.png")
    assert report.applied
    assert validate(document).is_valid
    with pytest.raises(KeyError, match="plot.png"):
        manager.remove("markdown", "plot.png")


def test_dry_run_report_matches_apply_without_mutating() -> None:
    preview_document = _document()
    apply_document = _document()
    before = deepcopy(preview_document.raw)

    preview = manage_attachments(preview_document).rename(
        "markdown",
        "plot.png",
        "renamed.png",
        dry_run=True,
    )
    applied = manage_attachments(apply_document).rename(
        "markdown",
        "plot.png",
        "renamed.png",
    )

    assert preview.changes == applied.changes
    assert preview_document.raw == before
    assert preview.applied is False
    assert preview.would_change is True
    assert applied.applied is True
