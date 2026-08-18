"""Tests for active content sanitization.

Verifies that the sanitizer detects and handles script injection, dangerous
MIME types, SVG-embedded scripts, and file-protocol references.
"""

from __future__ import annotations

import pytest

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


# ---------------------------------------------------------------------------
# LIBIPYNB-Q8: regression coverage for the previously-untested detector
# surface -- 13 of 14 _ACTIVE_ELEMENTS categories, the event-handler
# heuristic, and the javascript:/CSS url() detectors were confirmed
# implemented and functionally correct by the forensic audit's own
# differential probe, but had zero dedicated tests (only <script> was
# tested above). Closes that gap.
# ---------------------------------------------------------------------------

_ACTIVE_ELEMENT_PAYLOADS: dict[str, str] = {
    "applet": '<applet code="x.class"></applet>',
    "audio": '<audio src="x.mp3"></audio>',
    "embed": '<embed src="x.swf">',
    "form": '<form action="/submit"></form>',
    "frame": '<frame src="x.html">',
    "frameset": "<frameset></frameset>",
    "iframe": '<iframe src="x.html"></iframe>',
    "link": '<link rel="stylesheet" href="x.css">',
    "meta": '<meta http-equiv="refresh" content="0;url=x">',
    "object": '<object data="x.swf"></object>',
    "script": "<script>alert(1)</script>",
    "source": '<source src="x.mp4">',
    "style": "<style>body{background:url(x.png)}</style>",
    "video": '<video src="x.mp4"></video>',
}


def _assert_hazard_detected(report, expected_substring: str) -> None:
    """Shared assertion helper: at least one finding's hazards must mention
    the expected substring -- used by every parametrized case below so a
    detector regression fails loudly and specifically, not just count==0."""
    assert report.count > 0, f"expected at least one finding for {expected_substring!r}"
    hazard_texts = [h for f in report.findings for h in f.hazards]
    assert any(expected_substring in h.lower() for h in hazard_texts), (
        f"expected a hazard containing {expected_substring!r}, got: {hazard_texts}"
    )


@pytest.mark.parametrize("tag", sorted(_ACTIVE_ELEMENT_PAYLOADS))
def test_every_active_element_category_is_detected(tag: str) -> None:
    doc = _notebook_with_output("display_data", {"text/html": _ACTIVE_ELEMENT_PAYLOADS[tag]})

    report = sanitize(doc, dry_run=True)

    _assert_hazard_detected(report, f"active_element:{tag}")


@pytest.mark.parametrize("attr", ["onerror", "onclick", "onload", "onmouseover", "onfocus"])
def test_event_handler_attributes_are_detected(attr: str) -> None:
    doc = _notebook_with_output(
        "display_data", {"text/html": f'<img src="x.png" {attr}="alert(1)">'}
    )

    report = sanitize(doc, dry_run=True)

    _assert_hazard_detected(report, f"event_handler:{attr}")


def test_javascript_uri_in_href_is_detected() -> None:
    doc = _notebook_with_output(
        "display_data", {"text/html": '<a href="javascript:alert(1)">click</a>'}
    )

    report = sanitize(doc, dry_run=True)

    all_refs = [r for f in report.findings for r in f.references]
    assert any(r.startswith("javascript:") for r in all_refs), all_refs


def test_css_url_javascript_scheme_is_detected() -> None:
    doc = _notebook_with_output(
        "display_data",
        {"text/html": '<div style="background:url(javascript:alert(1))"></div>'},
    )

    report = sanitize(doc, dry_run=True)

    all_refs = [r for f in report.findings for r in f.references]
    assert any(r.startswith("javascript:") for r in all_refs), all_refs


# ---------------------------------------------------------------------------
# LIBIPYNB-Q8: the closed text/markdown output-MIME blind spot -- an
# identical hazardous payload delivered as text/markdown output/attachment
# data was previously invisible to sanitize() in every mode, while the same
# payload as text/html output data or markdown cell SOURCE was correctly
# caught.
# ---------------------------------------------------------------------------


def test_markdown_mime_output_hazard_is_now_detected() -> None:
    doc = _notebook_with_output("display_data", {"text/markdown": "[click](javascript:alert(1))"})

    report = sanitize(doc, dry_run=True)

    assert report.count > 0
    all_refs = [r for f in report.findings for r in f.references]
    assert any(r.startswith("javascript:") for r in all_refs), all_refs


def test_markdown_mime_output_hazard_is_suppressed_when_inspect_markdown_is_false() -> None:
    doc = _notebook_with_output("display_data", {"text/markdown": "[click](javascript:alert(1))"})

    report = sanitize(doc, policy=SanitizationPolicy(inspect_markdown=False), dry_run=True)

    assert report.count == 0


def test_markdown_mime_attachment_hazard_is_detected() -> None:
    raw = {
        "nbformat": 4,
        "nbformat_minor": 5,
        "metadata": {},
        "cells": [
            {
                "cell_type": "markdown",
                "id": "c1",
                "metadata": {},
                "source": "see ![x](attachment:img)",
                "attachments": {"img": {"text/markdown": "[x](javascript:alert(1))"}},
            }
        ],
    }

    report = sanitize(NotebookDocument(raw), dry_run=True)

    all_refs = [r for f in report.findings for r in f.references]
    assert any(r.startswith("javascript:") for r in all_refs), all_refs


def test_markdown_mime_output_with_charset_parameter_is_still_detected() -> None:
    """A parameterized MIME type (RFC 2046, e.g. `; charset=utf-8`) is legal
    in a Jupyter output's data bundle. Before this fix, `text/markdown;
    charset=utf-8` failed every exact-string comparison in the sanitizer
    (it never equalled the bare `"text/markdown"` string), so the payload
    bypassed scanning entirely -- a real gap a fresh independent review
    found in the original text/markdown fix. This must be caught the same
    way the bare `text/markdown` key already is."""
    doc = _notebook_with_output(
        "display_data", {"text/markdown; charset=utf-8": "[click](javascript:alert(1))"}
    )

    report = sanitize(doc, dry_run=True)

    assert report.count > 0
    all_refs = [r for f in report.findings for r in f.references]
    assert any(r.startswith("javascript:") for r in all_refs), all_refs


def test_html_mime_output_with_charset_parameter_is_still_detected() -> None:
    """Same parameterized-MIME-type gap, but for the pre-existing
    active_mime_types set membership check (not just the markdown gate) --
    `text/html; charset=utf-8` must still be recognized as an active MIME
    type and scanned, not silently skipped because it doesn't exactly equal
    a bare `"text/html"` string."""
    doc = _notebook_with_output(
        "display_data", {"text/html; charset=utf-8": "<script>alert(1)</script>"}
    )

    report = sanitize(doc, dry_run=True)

    assert report.count > 0
    all_hazards = [h for f in report.findings for h in f.hazards]
    assert any("script" in h for h in all_hazards), all_hazards


def test_markdown_mime_attachment_with_charset_parameter_is_still_detected() -> None:
    raw = {
        "nbformat": 4,
        "nbformat_minor": 5,
        "metadata": {},
        "cells": [
            {
                "cell_type": "markdown",
                "id": "c1",
                "metadata": {},
                "source": "see ![x](attachment:img)",
                "attachments": {
                    "img": {"text/markdown; charset=utf-8": "[x](javascript:alert(1))"}
                },
            }
        ],
    }

    report = sanitize(NotebookDocument(raw), dry_run=True)

    all_refs = [r for f in report.findings for r in f.references]
    assert any(r.startswith("javascript:") for r in all_refs), all_refs
