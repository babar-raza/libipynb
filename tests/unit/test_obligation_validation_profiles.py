"""Failure-first declared/current validation and semantic diagnostics."""

from __future__ import annotations

from libipynb import validate
from libipynb.diagnostics import DiagnosticSeverity as Severity


def _codes(report: object, severity: Severity | None = None) -> set[str]:
    diagnostics = report.diagnostics
    return {item.code for item in diagnostics if severity is None or item.severity is severity}


def test_future_declared_profile_is_valid_with_separate_forward_warnings() -> None:
    notebook = {
        "nbformat": 4,
        "nbformat_minor": 6,
        "metadata": {},
        "vendor_root": {"preserve": True},
        "cells": [
            {
                "cell_type": "future_cell",
                "id": "future-cell",
                "metadata": {},
                "source": "future",
                "vendor": {"keep": True},
            },
            {
                "cell_type": "code",
                "id": "future-output",
                "metadata": {},
                "source": "",
                "execution_count": None,
                "outputs": [
                    {
                        "output_type": "future_output",
                        "vendor": {"keep": True},
                    }
                ],
            },
        ],
    }

    declared = validate(notebook, profile="declared")
    assert declared.is_valid
    assert {
        "IPYNB_FORWARD_VERSION",
        "IPYNB_FORWARD_FIELD",
        "IPYNB_FORWARD_CELL_TYPE",
        "IPYNB_FORWARD_OUTPUT_TYPE",
    } <= _codes(declared, Severity.WARNING)

    current = validate(notebook, profile="current")
    assert not current.is_valid
    assert "IPYNB_PROFILE" in _codes(current, Severity.ERROR)


def test_attachment_reference_integrity_and_mime_bundles() -> None:
    valid = {
        "nbformat": 4,
        "nbformat_minor": 5,
        "metadata": {},
        "cells": [
            {
                "cell_type": "markdown",
                "id": "attachments",
                "metadata": {},
                "source": "![image](attachment:image.png)",
                "attachments": {
                    "image.png": {
                        "image/png": "aW1hZ2U=",
                        "application/vnd.example+json": {"retained": True},
                    }
                },
            }
        ],
    }
    assert validate(valid, profile="declared").is_valid

    broken = {
        **valid,
        "cells": [
            {
                **valid["cells"][0],
                "source": "![missing](attachment:missing.png)",
                "attachments": {"orphan.png": {"image/png": "aW1hZ2U="}},
            }
        ],
    }
    report = validate(broken, profile="declared")
    assert not report.is_valid
    assert "IPYNB_ATTACHMENT_MISSING" in _codes(report, Severity.ERROR)
    assert "IPYNB_ATTACHMENT_ORPHAN" in _codes(report, Severity.WARNING)


def test_malformed_cells_outputs_tags_and_mime_bundles_have_exact_diagnostics() -> None:
    notebook = {
        "nbformat": 4,
        "nbformat_minor": 5,
        "metadata": {},
        "cells": [
            {
                "cell_type": "markdown",
                "id": "bad-source",
                "metadata": {"tags": ["duplicate", "duplicate", "has,comma"]},
                "source": ["valid", 3],
                "attachments": {"bad": []},
            },
            {
                "cell_type": "code",
                "id": "bad-outputs",
                "metadata": {},
                "source": "",
                "execution_count": None,
                "outputs": [
                    {
                        "output_type": "stream",
                        "name": "side-channel",
                        "text": 42,
                    },
                    {
                        "output_type": "display_data",
                        "data": [],
                        "metadata": [],
                    },
                    {
                        "output_type": "error",
                        "ename": "ValueError",
                        "evalue": "bad",
                        "traceback": ["ok", 3],
                    },
                ],
            },
        ],
    }

    report = validate(notebook, profile="declared")

    assert not report.is_valid
    assert {
        "IPYNB_TAG_DUPLICATE",
        "IPYNB_TAG_COMMA",
        "IPYNB_CELL_SOURCE",
        "IPYNB_ATTACHMENT_BUNDLE",
        "IPYNB_STREAM_NAME",
        "IPYNB_STREAM_TEXT",
        "IPYNB_MIME_BUNDLE",
        "IPYNB_OUTPUT_METADATA",
        "IPYNB_ERROR_TRACEBACK",
    } <= _codes(report, Severity.ERROR)
