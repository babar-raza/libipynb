"""Tests for active content sanitization.

Verifies that the sanitizer detects and handles script injection, dangerous
MIME types, SVG-embedded scripts, and file-protocol references.
"""

from __future__ import annotations

from libipynb import NotebookDocument, sanitize
from libipynb.security import SanitizationMode, SanitizationPolicy


def _notebook_with_output(
    output_type: str,
    data: dict,
    *,
    cell_id: str = "sec-cell-0",
) -> NotebookDocument:
    """Build a NotebookDocument containing a single cell with one output."""
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
                "cell_type": "code",
                "id": cell_id,
                "metadata": {},
                "source": "",
                "execution_count": None,
                "outputs": [
                    {
                        "output_type": output_type,
                        "metadata": {},
                        "data": data,
                    },
                ],
            },
        ],
    }
    return NotebookDocument(raw)


# ---------------------------------------------------------------------------
# Script tags in HTML output
# ---------------------------------------------------------------------------


def test_script_tags_in_html_output_detected() -> None:
    """HTML output containing <script> tags must be flagged by the sanitizer."""
    doc = _notebook_with_output(
        "display_data",
        {"text/html": "<div><script>alert(1)</script></div>"},
    )

    report = sanitize(doc, dry_run=True)

    assert report.count > 0, "Sanitizer should detect script tags in HTML output"

    # At least one finding should mention the script hazard.
    hazard_texts = [h for f in report.findings for h in f.hazards]
    assert any("script" in h.lower() for h in hazard_texts), (
        f"Expected a 'script'-related hazard, got: {hazard_texts}"
    )


def test_script_tags_removed_in_remove_mode() -> None:
    """In REMOVE mode the sanitizer must actually strip the dangerous content."""
    doc = _notebook_with_output(
        "display_data",
        {"text/html": "<div><script>alert(1)</script></div>"},
    )
    policy = SanitizationPolicy(mode=SanitizationMode.REMOVE)
    report = sanitize(doc, policy=policy)

    assert report.applied, "REMOVE mode should apply changes"
    assert report.count > 0


# ---------------------------------------------------------------------------
# JavaScript MIME type
# ---------------------------------------------------------------------------


def test_javascript_mime_type_detected() -> None:
    """Output with application/javascript MIME type must be flagged."""
    doc = _notebook_with_output(
        "display_data",
        {"application/javascript": "console.log('pwned')"},
    )

    report = sanitize(doc, dry_run=True)

    assert report.count > 0, "application/javascript MIME type should be detected"
    media_types_found = {f.media_type for f in report.findings}
    assert "application/javascript" in media_types_found, (
        f"Expected application/javascript in findings, got: {media_types_found}"
    )


# ---------------------------------------------------------------------------
# SVG with embedded script
# ---------------------------------------------------------------------------


def test_svg_with_script_detected() -> None:
    """SVG output containing an embedded <script> tag must be flagged."""
    malicious_svg = (
        '<svg xmlns="http://www.w3.org/2000/svg">'
        '<script type="text/javascript">alert("xss")</script>'
        '<circle cx="50" cy="50" r="40"/>'
        "</svg>"
    )
    doc = _notebook_with_output(
        "display_data",
        {"image/svg+xml": malicious_svg},
    )

    report = sanitize(doc, dry_run=True)

    assert report.count > 0, "SVG with embedded script should be detected"
    # The finding should reference the SVG media type.
    media_types_found = {f.media_type for f in report.findings}
    assert "image/svg+xml" in media_types_found, (
        f"Expected image/svg+xml in findings, got: {media_types_found}"
    )


# ---------------------------------------------------------------------------
# file:// protocol references
# ---------------------------------------------------------------------------


def test_file_protocol_references_detected() -> None:
    """HTML output referencing file:// URLs must be flagged."""
    doc = _notebook_with_output(
        "display_data",
        {"text/html": '<img src="file:///etc/passwd">'},
    )

    report = sanitize(doc, dry_run=True)

    assert report.count > 0, "file:// protocol reference should be detected"

    # At least one finding should list the file:// reference.
    all_refs = [r for f in report.findings for r in f.references]
    assert any("file://" in r for r in all_refs), (
        f"Expected a file:// reference in findings, got: {all_refs}"
    )


# ---------------------------------------------------------------------------
# Lossless mode does not mutate
# ---------------------------------------------------------------------------


def test_lossless_mode_does_not_mutate_document() -> None:
    """LOSSLESS mode must report findings without modifying the document."""
    doc = _notebook_with_output(
        "display_data",
        {"text/html": "<script>alert(1)</script>"},
    )
    import copy

    snapshot = copy.deepcopy(doc.raw)

    policy = SanitizationPolicy(mode=SanitizationMode.LOSSLESS)
    report = sanitize(doc, policy=policy)

    assert doc.raw == snapshot, "LOSSLESS mode must not mutate the document"
    assert not report.applied, "LOSSLESS mode should not apply changes"
