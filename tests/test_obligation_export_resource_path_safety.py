"""IPYNB-SEC-001 -- exported ancillary resource filenames reject path traversal.

MUST (SAL-IPYNB-OBL-DB823E1426D979E1): "Prevent path traversal and
unapproved absolute-path access when resolving any detached or referenced
resource."

Before this slice, an attachment cell's dict key (untrusted document
content) flowed directly into AncillaryResource.filename with no
validation. A caller exporting resources to disk by joining
`output_dir / resource.filename` would inherit whatever path-traversal
shape the notebook's author chose -- `../../../etc/cron.d/evil`,
an absolute path, or a Windows-style `..\\..\\evil` sequence.
"""

from __future__ import annotations

import base64
import json
from typing import Any

from libipynb import MarkdownExporter, loads

PNG_B64 = base64.b64encode(b"\x89PNG\r\n\x1a\n").decode("ascii")


def _notebook_with_attachment_key(key: str) -> dict[str, Any]:
    return {
        "nbformat": 4,
        "nbformat_minor": 5,
        "metadata": {},
        "cells": [
            {
                "cell_type": "markdown",
                "id": "cell-0",
                "metadata": {},
                "source": "image",
                "attachments": {key: {"image/png": PNG_B64}},
            }
        ],
    }


def _resource_filenames(key: str) -> list[str]:
    document = loads(json.dumps(_notebook_with_attachment_key(key)), mode="strict")
    result = MarkdownExporter().export(document)
    return [resource.filename for resource in result.resources]


def test_a_bare_filename_attachment_key_is_collected() -> None:
    assert _resource_filenames("logo.png") == ["logo.png"]


def test_a_relative_traversal_attachment_key_is_rejected() -> None:
    assert _resource_filenames("../../../etc/cron.d/evil") == []


def test_an_absolute_path_attachment_key_is_rejected() -> None:
    assert _resource_filenames("/etc/passwd") == []


def test_a_nested_subdirectory_attachment_key_is_rejected() -> None:
    assert _resource_filenames("nested/traversal.png") == []


def test_a_windows_style_traversal_attachment_key_is_rejected() -> None:
    assert _resource_filenames("..\\..\\evil.png") == []


def test_the_literal_dotdot_attachment_key_is_rejected() -> None:
    assert _resource_filenames("..") == []


def test_a_filename_that_merely_starts_with_dots_is_still_collected() -> None:
    assert _resource_filenames("..hidden.png") == ["..hidden.png"]
