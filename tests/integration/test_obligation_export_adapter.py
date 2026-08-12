"""IPYNB-EXPORT-001 against the shipped namespace.

SAL-IPYNB-OBL-AABAEFD635A6381D (SHOULD): provide exporter adapter interfaces
returning main output plus ancillary resources; keep exporter-specific
preprocessors and resources outside the core parser.

Required proof: exporter adapter contract test with ancillary-resource
collection.
"""

from __future__ import annotations

import base64
import json
from typing import Any

from libipynb import loads
from libipynb.adapters import (
    AncillaryResource,
    ExportAdapter,
    ExportResult,
    MarkdownExporter,
    PythonScriptExporter,
)

PNG_BYTES = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\xde\xad\xbe\xef"
PNG_B64 = base64.b64encode(PNG_BYTES).decode("ascii")


def _notebook(cells: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "nbformat": 4,
        "nbformat_minor": 5,
        "metadata": {},
        "cells": [
            {**cell, "id": f"cell-{i}", "metadata": cell.get("metadata", {})}
            for i, cell in enumerate(cells)
        ],
    }


def _code(source: str, outputs: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {
        "cell_type": "code",
        "source": source,
        "outputs": outputs or [],
        "execution_count": None,
    }


def _markdown(source: str) -> dict[str, Any]:
    return {"cell_type": "markdown", "source": source}


def _raw(source: str) -> dict[str, Any]:
    return {"cell_type": "raw", "source": source}


def _attachment_cell() -> dict[str, Any]:
    return {
        "cell_type": "markdown",
        "source": "![img](attachment:logo.png)",
        "attachments": {
            "logo.png": {"image/png": PNG_B64},
        },
    }


def _output_with_image() -> dict[str, Any]:
    return {
        "output_type": "display_data",
        "data": {"image/png": PNG_B64, "text/plain": "fallback"},
        "metadata": {},
    }


def _load(cells: list[dict[str, Any]]) -> Any:
    return loads(json.dumps(_notebook(cells)), mode="strict")


# ── Protocol conformance ─────────────────────────────────────────────────────


def test_markdown_exporter_satisfies_the_export_adapter_protocol() -> None:
    assert isinstance(MarkdownExporter(), ExportAdapter)


def test_python_exporter_satisfies_the_export_adapter_protocol() -> None:
    assert isinstance(PythonScriptExporter(), ExportAdapter)


def test_export_result_contains_content_and_resources() -> None:
    result = ExportResult(content="hello", resources=(), metadata={"k": 1})
    assert result.content == "hello"
    assert result.resources == ()
    assert result.metadata == {"k": 1}


def test_ancillary_resource_carries_filename_mime_data_and_path() -> None:
    resource = AncillaryResource(
        filename="img.png",
        mime_type="image/png",
        data=PNG_BYTES,
        source_path=("cells", 0, "attachments", "img.png"),
    )
    assert resource.filename == "img.png"
    assert resource.mime_type == "image/png"
    assert resource.data == PNG_BYTES
    assert resource.source_path == ("cells", 0, "attachments", "img.png")


# ── Markdown exporter ────────────────────────────────────────────────────────


def test_markdown_export_renders_markdown_cells_as_is() -> None:
    doc = _load([_markdown("# Title")])
    result = MarkdownExporter().export(doc)
    assert "# Title" in result.content


def test_markdown_export_wraps_code_cells_in_fences() -> None:
    doc = _load([_code("x = 1")])
    result = MarkdownExporter().export(doc)
    assert "```python\nx = 1\n```" in result.content


def test_markdown_export_includes_raw_cells() -> None:
    doc = _load([_raw("raw text")])
    result = MarkdownExporter().export(doc)
    assert "raw text" in result.content


def test_markdown_export_metadata_contains_format_and_cell_count() -> None:
    doc = _load([_markdown("a"), _code("b")])
    result = MarkdownExporter().export(doc)
    assert result.metadata["format"] == "markdown"
    assert result.metadata["cell_count"] == 2


# ── Python script exporter ────────────────────────────────────────────────────


def test_python_export_includes_code_cells() -> None:
    doc = _load([_code("x = 1"), _code("y = 2")])
    result = PythonScriptExporter().export(doc)
    assert "x = 1" in result.content
    assert "y = 2" in result.content


def test_python_export_comments_markdown_cells() -> None:
    doc = _load([_markdown("# Title\nParagraph")])
    result = PythonScriptExporter().export(doc)
    assert "# # Title" in result.content
    assert "# Paragraph" in result.content


def test_python_export_metadata_contains_format() -> None:
    doc = _load([_code("pass")])
    result = PythonScriptExporter().export(doc)
    assert result.metadata["format"] == "python"


# ── Ancillary resource collection ────────────────────────────────────────────


def test_attachment_resources_are_collected() -> None:
    doc = _load([_attachment_cell()])
    result = MarkdownExporter().export(doc)
    assert len(result.resources) == 1
    resource = result.resources[0]
    assert resource.filename == "logo.png"
    assert resource.mime_type == "image/png"
    assert resource.data == PNG_BYTES
    assert resource.source_path[0] == "cells"


def test_output_image_resources_are_collected() -> None:
    doc = _load([_code("plot()", [_output_with_image()])])
    result = MarkdownExporter().export(doc)
    image_resources = [r for r in result.resources if r.mime_type.startswith("image/")]
    assert len(image_resources) >= 1
    assert image_resources[0].data == PNG_BYTES


def test_resources_are_collected_from_both_attachments_and_outputs() -> None:
    doc = _load([_attachment_cell(), _code("plot()", [_output_with_image()])])
    result = MarkdownExporter().export(doc)
    assert len(result.resources) == 2


def test_empty_notebook_produces_no_resources() -> None:
    doc = _load([_code("pass")])
    result = MarkdownExporter().export(doc)
    assert result.resources == ()


def test_python_exporter_also_collects_resources() -> None:
    doc = _load([_code("plot()", [_output_with_image()])])
    result = PythonScriptExporter().export(doc)
    assert len(result.resources) >= 1


# ── Custom adapter via protocol ──────────────────────────────────────────────


def test_custom_adapter_conforming_to_protocol_works() -> None:
    class HtmlStubExporter:
        def export(self, document: Any) -> ExportResult:
            return ExportResult(
                content=f"<html>{document.cell_count} cells</html>",
                resources=(),
                metadata={"format": "html"},
            )

    adapter = HtmlStubExporter()
    assert isinstance(adapter, ExportAdapter)
    doc = _load([_code("pass"), _markdown("hi")])
    result = adapter.export(doc)
    assert "2 cells" in result.content
