"""Installed-package proof for nbformat attachment structures."""

from __future__ import annotations

import importlib.metadata
import json
from pathlib import Path

import nbformat

import libipynb as factory


def _notebook_with_attachments() -> dict[str, object]:
    return {
        "nbformat": 4,
        "nbformat_minor": 5,
        "metadata": {},
        "cells": [
            {
                "cell_type": "markdown",
                "id": "markdown-attachment",
                "metadata": {},
                "source": "![pixel](attachment:pixel.png)",
                "attachments": {
                    "pixel.png": {
                        "image/png": "iVBORw0KGgoAAAANSUhEUgAAAAEAAAAB"
                    }
                },
            },
            {
                "cell_type": "raw",
                "id": "raw-attachment",
                "metadata": {},
                "source": "attachment:notes.txt",
                "attachments": {
                    "notes.txt": {
                        "text/plain": "preserved text",
                        "application/vnd.example+json": "{\"preserved\":true}",
                    }
                },
            },
        ],
    }


def test_attachment_mapping_and_references_roundtrip_with_official_oracle() -> None:
    source = _notebook_with_attachments()
    encoded = json.dumps(source, ensure_ascii=False)

    official = nbformat.reads(encoded, as_version=nbformat.NO_CONVERT)
    nbformat.validate(official)

    document = factory.loads(encoded)
    serialized = json.loads(factory.dumps(document, profile="declared"))
    reloaded = factory.loads(json.dumps(serialized))

    assert reloaded.raw == source
    for cell in reloaded.cells:
        attachments = cell["attachments"]
        referenced_name = str(cell["source"]).split("attachment:", 1)[1].rstrip(")")
        assert referenced_name in attachments
        assert all("/" in mime_type for mime_type in attachments[referenced_name])


def test_attachment_proof_uses_installed_production_namespace(is_editable_install) -> None:
    origin = Path(factory.__file__).resolve()
    dist = importlib.metadata.distribution("libipynb")
    if is_editable_install(dist):
        assert "libipynb" in str(origin).lower()
    else:
        assert "site-packages" in str(origin).lower()
