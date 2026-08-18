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
        manager.add("markdown", "plot.png", {"image/png": "cmVwbGFjZQ=="})


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


def test_rename_with_a_longer_name_preserves_unrelated_sibling_line_content() -> None:
    """LIBIPYNB-Q9 regression: renaming to a LONGER name used to corrupt
    every source line after the renamed reference, because the old/buggy
    implementation sliced the REWRITTEN text at the OLD (pre-rename)
    per-item lengths. Uses a second, completely unrelated sibling line
    (no attachment reference at all) to prove that line's own content
    survives byte-for-byte, not just that the segment COUNT is unchanged."""
    document = _document(
        [
            "![plot](attachment:plot.png)\n",
            "this line has nothing to do with the attachment\n",
        ]
    )

    manage_attachments(document).rename("markdown", "plot.png", "a-much-longer-final-plot-name.png")

    cell = document.cells[0]
    assert isinstance(cell["source"], list)
    assert len(cell["source"]) == 2
    assert (
        "".join(cell["source"]) == "![plot](attachment:a-much-longer-final-plot-name.png)\n"
        "this line has nothing to do with the attachment\n"
    )
    # The unrelated second line must be intact, not truncated/spliced.
    assert cell["source"][1] == "this line has nothing to do with the attachment\n"
    assert validate(document).is_valid


def test_add_rejects_a_path_traversal_attachment_name() -> None:
    manager = manage_attachments(_document())

    for unsafe_name in ("../../etc/passwd", "/etc/passwd", "..", "a/b.png"):
        with pytest.raises(ValueError, match="safe filename"):
            manager.add("markdown", unsafe_name, {"image/png": "cGxvdA=="})


def test_add_rejects_malformed_base64_payload() -> None:
    manager = manage_attachments(_document())

    with pytest.raises(ValueError, match="not valid base64"):
        manager.add("markdown", "bad.png", {"image/png": "not-valid-base64!!!"})


def test_rename_to_a_path_traversal_name_is_rejected_but_removing_a_preexisting_bad_name_still_works() -> (
    None
):
    """LIBIPYNB-Q9: new/renamed-to names are validated for path safety, but
    an already-stored (e.g. hand-edited-file-loaded) unsafe name can still
    be used as a pure LOOKUP key for remove()/rename()'s old_name -- so a
    caller isn't permanently unable to clean up bad pre-existing data."""
    document = _document()
    document.cells[0]["attachments"]["../evil.png"] = {"image/png": "cGxvdA=="}
    manager = manage_attachments(document)

    with pytest.raises(ValueError, match="safe filename"):
        manager.rename("markdown", "plot.png", "../evil2.png")

    # But removing the pre-existing bad name (a pure lookup, not a new
    # write) still works -- a legitimate defensive-repair path.
    report = manager.remove(
        "markdown", "../evil.png", reference_policy=AttachmentReferencePolicy.LEAVE_DANGLING
    )
    assert report.applied is True


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
