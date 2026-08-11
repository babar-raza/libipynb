"""Obligation tests for explicit, reportable active-content sanitization."""

from __future__ import annotations

from copy import deepcopy
import socket

import pytest
from libipynb.errors import NotebookResourceLimitError as ResourceLimitError
from libipynb.security.limits import NotebookResourceLimits as ResourceLimits
from libipynb import (
    IpynbDocument,
    SanitizationMode,
    SanitizationPolicy,
    sanitize,
)


def _hostile_document() -> IpynbDocument:
    return IpynbDocument(
        {
            "nbformat": 4,
            "nbformat_minor": 5,
            "metadata": {"owner": {"keep": True}},
            "cells": [
                {
                    "cell_type": "markdown",
                    "id": "markdown",
                    "metadata": {},
                    "source": (
                        "<script>window.pwned = true</script>\n"
                        "[remote](https://example.invalid/track)"
                    ),
                    "attachments": {
                        "unsafe.html": {
                            "text/html": '<img src="https://example.invalid/a.png">',
                            "image/png": "c2FmZQ==",
                        }
                    },
                },
                {
                    "cell_type": "code",
                    "id": "code",
                    "metadata": {},
                    "source": "raise RuntimeError('must never run')",
                    "execution_count": 1,
                    "outputs": [
                        {
                            "output_type": "display_data",
                            "metadata": {},
                            "data": {
                                "image/svg+xml": (
                                    '<svg><image href="file:///etc/passwd"/></svg>'
                                ),
                                "application/javascript": (
                                    "fetch('https://example.invalid/collect')"
                                ),
                                "text/plain": "safe representation",
                            },
                        }
                    ],
                },
            ],
        }
    )


def test_lossless_mode_reports_without_mutating_or_marking() -> None:
    document = _hostile_document()
    before = deepcopy(document.raw)

    report = sanitize(
        document,
        policy=SanitizationPolicy(mode=SanitizationMode.LOSSLESS),
    )

    assert document.raw == before
    assert report.count == 4
    assert report.applied is False
    assert report.would_change is False
    assert {finding.action for finding in report.findings} == {"reported"}
    assert any("active_element:script" in item.hazards for item in report.findings)
    assert any(
        "https://example.invalid/track" in item.references
        for item in report.findings
    )
    assert all(len(item.payload_sha256) == 64 for item in report.findings)
    assert "notebook_security" not in document.metadata


def test_remove_mode_drops_only_the_unsafe_renderable_payloads() -> None:
    document = _hostile_document()

    report = sanitize(
        document,
        policy=SanitizationPolicy(mode=SanitizationMode.REMOVE),
    )

    markdown, code = document.cells
    assert markdown["source"] == ""
    assert markdown["attachments"]["unsafe.html"] == {
        "image/png": "c2FmZQ=="
    }
    assert code["source"] == "raise RuntimeError('must never run')"
    assert code["outputs"][0]["data"] == {"text/plain": "safe representation"}
    assert document.metadata == {"owner": {"keep": True}}
    assert report.applied is True
    assert report.would_change is True
    assert {finding.action for finding in report.findings} == {"removed"}


def test_quarantine_mode_moves_payloads_out_of_renderable_locations() -> None:
    document = _hostile_document()

    report = sanitize(
        document,
        policy=SanitizationPolicy(mode=SanitizationMode.QUARANTINE),
    )

    quarantine = document.raw["metadata"]["notebook_security"]["quarantine"]
    assert len(quarantine) == report.count == 4
    assert all(
        set(item)
        == {
            "action",
            "hazards",
            "media_type",
            "path",
            "payload",
            "payload_sha256",
            "references",
            "schema_version",
        }
        for item in quarantine
    )
    assert document.cells[0]["source"] == ""
    assert document.cells[1]["outputs"][0]["data"] == {
        "text/plain": "safe representation"
    }
    assert {finding.action for finding in report.findings} == {"quarantined"}

    after_first_pass = deepcopy(document.raw)
    second = sanitize(
        document,
        policy=SanitizationPolicy(mode=SanitizationMode.QUARANTINE),
    )
    assert second.count == 0
    assert second.applied is False
    assert second.would_change is False
    assert document.raw == after_first_pass


def test_mark_untrusted_preserves_payload_and_is_idempotent() -> None:
    document = _hostile_document()
    original_cells = deepcopy(document.cells)

    first = sanitize(
        document,
        policy=SanitizationPolicy(mode=SanitizationMode.MARK_UNTRUSTED),
    )
    first_state = deepcopy(document.raw)
    marks = document.raw["metadata"]["notebook_security"]["untrusted"]

    assert document.cells == original_cells
    assert len(marks) == first.count == 4
    assert all("payload" not in mark for mark in marks)
    assert {finding.action for finding in first.findings} == {"marked_untrusted"}
    assert first.applied is True
    assert first.would_change is True

    second = sanitize(
        document,
        policy=SanitizationPolicy(mode=SanitizationMode.MARK_UNTRUSTED),
    )
    assert second.findings == first.findings
    assert second.applied is False
    assert second.would_change is False
    assert document.raw == first_state


def test_dry_run_matches_apply_report_without_mutation() -> None:
    preview_document = _hostile_document()
    apply_document = _hostile_document()
    before = deepcopy(preview_document.raw)
    policy = SanitizationPolicy(mode=SanitizationMode.QUARANTINE)

    preview = sanitize(preview_document, policy=policy, dry_run=True)
    applied = sanitize(apply_document, policy=policy)

    assert preview.findings == applied.findings
    assert preview_document.raw == before
    assert preview.applied is False
    assert preview.would_change is True
    assert applied.applied is True


def test_external_references_are_detected_without_network_access(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_network(*args: object, **kwargs: object) -> None:
        raise AssertionError(f"network access attempted: {args!r}, {kwargs!r}")

    monkeypatch.setattr(socket, "create_connection", fail_network)
    document = _hostile_document()

    report = sanitize(
        document,
        policy=SanitizationPolicy(mode=SanitizationMode.LOSSLESS),
    )

    references = {
        reference
        for finding in report.findings
        for reference in finding.references
    }
    assert "https://example.invalid/track" in references
    assert "file:///etc/passwd" in references


def test_catalog_and_external_reference_scanning_are_configurable() -> None:
    document = IpynbDocument(
        {
            "nbformat": 4,
            "nbformat_minor": 5,
            "metadata": {},
            "cells": [
                {
                    "cell_type": "markdown",
                    "id": "markdown",
                    "metadata": {},
                    "source": "[remote](relative/image.png)",
                    "attachments": {
                        "custom": {
                            "application/vnd.example.active": "opaque payload"
                        }
                    },
                }
            ],
        }
    )

    disabled = sanitize(
        document,
        policy=SanitizationPolicy(
            active_mime_types=frozenset(),
            inspect_external_references=False,
        ),
    )
    custom = sanitize(
        document,
        policy=SanitizationPolicy(
            active_mime_types=frozenset(
                {"application/vnd.example.active"}
            ),
            inspect_markdown=False,
        ),
    )

    assert disabled.count == 0
    assert custom.count == 1
    assert custom.findings[0].media_type == "application/vnd.example.active"


def test_scanning_is_bounded_and_reserved_metadata_is_never_overwritten() -> None:
    document = _hostile_document()
    tiny = ResourceLimits(max_decompressed_bytes=32)

    with pytest.raises(ResourceLimitError, match="max_decompressed_bytes"):
        sanitize(document, limits=tiny)

    document.raw["metadata"]["notebook_security"] = "owned-by-caller"
    with pytest.raises(TypeError, match="metadata.notebook_security"):
        sanitize(
            document,
            policy=SanitizationPolicy(mode=SanitizationMode.MARK_UNTRUSTED),
        )
    assert document.raw["metadata"]["notebook_security"] == "owned-by-caller"
