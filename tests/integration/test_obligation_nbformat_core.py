"""Installed-package and official-oracle proof for the nbformat 4.5 core."""

from __future__ import annotations

import importlib.metadata
import json
from pathlib import Path

import nbformat

import libipynb as factory


def _complete_core_notebook() -> dict[str, object]:
    return {
        "nbformat": 4,
        "nbformat_minor": 5,
        "metadata": {
            "kernelspec": {
                "display_name": "Python 3",
                "language": "python",
                "name": "python3",
            },
            "language_info": {
                "name": "python",
                "version": "3.13",
                "mimetype": "text/x-python",
                "file_extension": ".py",
            },
            "org.example": {"unicode": "λ"},
        },
        "cells": [
            {
                "cell_type": "markdown",
                "id": "markdown-cell",
                "metadata": {"tags": ["documentation", "reviewed"]},
                "source": ["# Heading\n", "Unicode λ"],
            },
            {
                "cell_type": "raw",
                "id": "raw-cell",
                "metadata": {"format": "text/plain"},
                "source": "literal raw text",
            },
            {
                "cell_type": "code",
                "id": "code-cell",
                "metadata": {"tags": ["production"]},
                "source": "raise RuntimeError('not executed by parsing')",
                "execution_count": 7,
                "outputs": [
                    {
                        "output_type": "stream",
                        "name": "stdout",
                        "text": ["line one\n", "line two\n"],
                    },
                    {
                        "output_type": "display_data",
                        "data": {
                            "text/plain": "safe representation",
                            "text/html": "<script>globalThis.notebookRan=true</script>",
                            "image/svg+xml": "<svg onload=\"globalThis.svgRan=true\"/>",
                            "application/javascript": "globalThis.jsRan=true",
                        },
                        "metadata": {
                            "text/html": {"isolated": True}
                        },
                    },
                    {
                        "output_type": "execute_result",
                        "execution_count": 7,
                        "data": {
                            "text/plain": "42",
                            "application/vnd.example+json": {"answer": 42},
                        },
                        "metadata": {
                            "application/vnd.example+json": {"expanded": True}
                        },
                    },
                    {
                        "output_type": "error",
                        "ename": "RuntimeError",
                        "evalue": "demonstration",
                        "traceback": [
                            "Traceback (most recent call last):",
                            "RuntimeError: demonstration",
                        ],
                    },
                ],
            },
        ],
    }


def test_complete_core_vector_validates_and_roundtrips_without_execution() -> None:
    source = _complete_core_notebook()
    encoded = json.dumps(source, ensure_ascii=False)

    official = nbformat.reads(encoded, as_version=nbformat.NO_CONVERT)
    nbformat.validate(official)

    document = factory.loads(encoded)
    assert factory.validate(document).is_valid
    assert [cell["cell_type"] for cell in document.cells] == [
        "markdown",
        "raw",
        "code",
    ]
    assert [output["output_type"] for output in document.cells[2]["outputs"]] == [
        "stream",
        "display_data",
        "execute_result",
        "error",
    ]

    serialized = json.loads(factory.dumps(document, profile="declared"))
    reloaded = factory.loads(json.dumps(serialized, ensure_ascii=False))

    assert serialized == source
    assert reloaded.raw == source
    assert reloaded.cells[2]["source"] == "raise RuntimeError('not executed by parsing')"
    assert (
        reloaded.cells[2]["outputs"][1]["data"]["application/javascript"]
        == "globalThis.jsRan=true"
    )


def test_core_proof_uses_installed_production_namespace(is_editable_install) -> None:
    origin = Path(factory.__file__).resolve()
    dist = importlib.metadata.distribution("libipynb")
    if is_editable_install(dist):
        assert "libipynb" in str(origin).lower()
    else:
        assert "site-packages" in str(origin).lower()
