"""Tests for path traversal protection.

Verifies that export adapters and attachment handling reject path-traversal
attempts and other unsafe filenames.
"""

from __future__ import annotations

import json

import pytest

from libipynb import loads, NotebookDocument
from libipynb.adapters import MarkdownExporter


def _notebook_with_attachment(
    filename: str,
    mime_type: str = "image/png",
    data_b64: str = "iVBORw0KGgo=",
) -> NotebookDocument:
    """Build a NotebookDocument with a single markdown cell containing an attachment."""
    raw = {
        "nbformat": 4,
        "nbformat_minor": 5,
        "metadata": {
            "kernelspec": {
                "display_name": "Python 3",
                "language": "python",
                "name": "python3",
            },
        },
        "cells": [
            {
                "cell_type": "markdown",
                "id": "attach-cell-0",
                "metadata": {},
                "source": f"![image](attachment:{filename})",
                "attachments": {
                    filename: {
                        mime_type: data_b64,
                    },
                },
            },
        ],
    }
    return NotebookDocument(raw)


# ---------------------------------------------------------------------------
# Path traversal in export
# ---------------------------------------------------------------------------


def test_export_rejects_path_traversal() -> None:
    """Exporting a document whose attachment name traverses paths must be safe.

    The MarkdownExporter must either reject the traversal-named attachment
    entirely, sanitize the filename to a safe form, or raise an error --
    it must NEVER emit an AncillaryResource whose filename contains '..'.
    """
    traversal_name = "../../../etc/passwd"
    doc = _notebook_with_attachment(traversal_name)

    exporter = MarkdownExporter()

    # The exporter should either raise or produce safe resource names.
    try:
        result = exporter.export(doc)
    except (ValueError, OSError):
        # Raising on unsafe filenames is an acceptable defense.
        return

    # If it did not raise, verify no emitted resource contains path traversal.
    for resource in result.resources:
        assert ".." not in resource.filename, (
            f"Exported resource filename contains path traversal: {resource.filename!r}"
        )
        assert "/" not in resource.filename, (
            f"Exported resource filename contains directory separator: {resource.filename!r}"
        )
        assert "\\" not in resource.filename, (
            f"Exported resource filename contains backslash: {resource.filename!r}"
        )


# ---------------------------------------------------------------------------
# Malicious attachment names
# ---------------------------------------------------------------------------


_MALICIOUS_NAMES = [
    "../../etc/shadow",
    "..\\..\\windows\\system32\\config\\sam",
    "/etc/passwd",
    "C:\\Windows\\System32\\config\\SAM",
    "foo/../../../bar",
    "\x00evil.png",
]


@pytest.mark.parametrize("name", _MALICIOUS_NAMES)
def test_malicious_attachment_names_rejected(name: str) -> None:
    """Attachment names with directory traversal or absolute paths must be rejected.

    The export pipeline must either skip the resource, sanitize the name, or
    raise an error -- never emit the unsafe name verbatim.
    """
    doc = _notebook_with_attachment(name)
    exporter = MarkdownExporter()

    try:
        result = exporter.export(doc)
    except (ValueError, OSError):
        # Raising is acceptable -- the unsafe name was caught.
        return

    for resource in result.resources:
        assert ".." not in resource.filename, (
            f"Unsafe attachment name leaked through: {resource.filename!r}"
        )
        # Must be a bare filename (no directory components).
        assert "/" not in resource.filename, (
            f"Resource filename has forward slash: {resource.filename!r}"
        )
        assert "\\" not in resource.filename, (
            f"Resource filename has backslash: {resource.filename!r}"
        )
        assert not resource.filename.startswith(("C:", "/")), (
            f"Resource filename is absolute: {resource.filename!r}"
        )


# ---------------------------------------------------------------------------
# Safe attachment names pass through
# ---------------------------------------------------------------------------


def test_safe_attachment_name_accepted() -> None:
    """A normal, safe attachment filename must be preserved in the export."""
    doc = _notebook_with_attachment("chart.png")
    exporter = MarkdownExporter()

    result = exporter.export(doc)

    # The safe name should appear as a resource.
    resource_names = [r.filename for r in result.resources]
    assert any("chart" in n for n in resource_names), (
        f"Expected 'chart.png' in exported resources, got: {resource_names}"
    )
