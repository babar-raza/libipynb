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

import pytest

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
SVG_BYTES = b"<svg></svg>"
SVG_B64 = base64.b64encode(SVG_BYTES).decode("ascii")


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


class TestQ61ExportResultMetadataMutationAfterAccessDoesNotChangeLaterReads:
    """LIBIPYNB-Q61 (LIBIPYNB-Q43 follow-up): ExportResult.metadata had the
    identical mutation-after-access gap LIBIPYNB-Q43 fixed 12 times over
    elsewhere in this codebase -- a plain, directly mutable dict with no
    __post_init__ at all, so `result.metadata["x"] = "evil"` silently
    corrupted every later read of the SAME instance. Left unprotected
    under a deliberate, documented prior decision (LIBIPYNB-Q11a) citing
    a real technical concern -- a mappingproxy is not json.dumps()-able --
    that this fix resolves via deep_freeze/deep_thaw, the same pattern
    already used elsewhere in this codebase to solve exactly this
    conflict for CLI JSON output."""

    def test_metadata_rejects_item_assignment(self) -> None:
        result = ExportResult(content="hello", resources=(), metadata={"nested": {"a": 1}})

        with pytest.raises(TypeError):
            result.metadata["nested"] = {}  # type: ignore[index]
        with pytest.raises(TypeError):
            result.metadata["nested"]["a"] = 999  # type: ignore[index]

    def test_mutating_metadata_does_not_change_a_later_read(self) -> None:
        result = ExportResult(content="hello", resources=(), metadata={"a": 1, "b": "safe"})

        first_read = result.metadata
        with pytest.raises(TypeError):
            first_read["a"] = "EVIL_MUTATED"  # type: ignore[index]

        second_read = result.metadata
        assert second_read == {"a": 1, "b": "safe"}
        assert second_read == first_read

    def test_metadata_is_not_aliased_to_the_callers_own_dict(self) -> None:
        source = {"a": 1}
        result = ExportResult(content="hello", resources=(), metadata=source)

        source["a"] = "mutated-after-construction"

        assert result.metadata["a"] == 1

    def test_default_empty_metadata_is_also_frozen(self) -> None:
        result = ExportResult(content="hello")

        assert result.metadata == {}
        with pytest.raises(TypeError):
            result.metadata["new"] = "evil"  # type: ignore[index]


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


# ── LIBIPYNB-Q11a: resource-collection safety hardening ─────────────────────


def _attachment_cell_with_key(key: str, data_b64: str = PNG_B64) -> dict[str, Any]:
    return {
        "cell_type": "markdown",
        "source": f"![img](attachment:{key})",
        "attachments": {key: {"image/png": data_b64}},
    }


def _multi_mime_attachment_cell(key: str = "figure") -> dict[str, Any]:
    return {
        "cell_type": "markdown",
        "source": "figure",
        "attachments": {key: {"image/png": PNG_B64, "image/svg+xml": SVG_B64}},
    }


def _invalid_base64_attachment_cell(key: str = "broken.png") -> dict[str, Any]:
    return {
        "cell_type": "markdown",
        "source": "broken",
        "attachments": {key: {"image/png": "not-valid-base64!!!"}},
    }


def test_cross_cell_attachment_filename_collision_is_disambiguated_by_cell_index() -> None:
    doc = _load(
        [
            _attachment_cell_with_key("logo.png", PNG_B64),
            _attachment_cell_with_key("logo.png", SVG_B64),
        ]
    )
    result = MarkdownExporter().export(doc)
    filenames = [r.filename for r in result.resources]
    assert len(filenames) == len(set(filenames)), f"filenames must be unique: {filenames}"
    assert "logo.png" in filenames
    assert any(name != "logo.png" and name.endswith("logo.png") for name in filenames)


def test_same_cell_multi_mime_attachment_collision_is_disambiguated_by_extension() -> None:
    doc = _load([_multi_mime_attachment_cell()])
    result = MarkdownExporter().export(doc)
    filenames = sorted(r.filename for r in result.resources)
    assert len(filenames) == 2
    assert len(set(filenames)) == 2, f"filenames must be unique: {filenames}"
    assert filenames == ["figure.png", "figure.svg"]


def test_corrupt_base64_attachment_payload_is_skipped_and_counted_not_silently_dropped() -> None:
    doc = _load([_invalid_base64_attachment_cell(), _attachment_cell_with_key("ok.png")])
    result = MarkdownExporter().export(doc)
    assert len(result.resources) == 1
    assert result.resources[0].filename == "ok.png"
    assert result.metadata["skipped_resources"] == 1
    assert len(result.metadata["skipped_paths"]) == 1
    assert result.metadata["skipped_paths"][0][:2] == ("cells", 0)


def test_no_corrupt_payloads_means_zero_skipped_resources() -> None:
    doc = _load([_attachment_cell()])
    result = MarkdownExporter().export(doc)
    assert result.metadata["skipped_resources"] == 0
    assert result.metadata["skipped_paths"] == ()


def test_ancillary_resource_direct_construction_rejects_a_path_traversal_filename() -> None:
    with pytest.raises(ValueError, match="unsafe resource filename"):
        AncillaryResource(
            filename="../../../etc/passwd",
            mime_type="image/png",
            data=PNG_BYTES,
            source_path=("cells", 0, "attachments", "x"),
        )


def test_ancillary_resource_direct_construction_accepts_a_safe_filename() -> None:
    resource = AncillaryResource(
        filename="safe.png",
        mime_type="image/png",
        data=PNG_BYTES,
        source_path=("cells", 0, "attachments", "safe.png"),
    )
    assert resource.filename == "safe.png"


def test_single_attachment_common_case_is_unaffected_by_collision_handling() -> None:
    """Non-regression: the ordinary, non-colliding single-attachment case
    (already covered by test_attachment_resources_are_collected above) must
    keep its bare filename, not grow a spurious cell-index or extension
    suffix just because the collision-handling machinery now exists."""
    doc = _load([_attachment_cell()])
    result = MarkdownExporter().export(doc)
    assert [r.filename for r in result.resources] == ["logo.png"]


# ── LIBIPYNB-Q11b: export content-fidelity fixes ─────────────────────────────


def _notebook_with_language(cells: list[dict[str, Any]], language: str) -> dict[str, Any]:
    doc = _notebook(cells)
    doc["metadata"]["language_info"] = {"name": language}
    return doc


def test_markdown_fence_uses_the_notebooks_declared_kernel_language() -> None:
    document = loads(
        json.dumps(_notebook_with_language([_code("println(1)")], "julia")), mode="strict"
    )
    result = MarkdownExporter().export(document)
    assert "```julia\nprintln(1)\n```" in result.content


def test_markdown_fence_falls_back_to_python_when_no_language_is_declared() -> None:
    doc = _load([_code("x = 1")])
    result = MarkdownExporter().export(doc)
    assert "```python\nx = 1\n```" in result.content


def test_markdown_fence_rejects_an_injection_attempt_in_the_declared_language() -> None:
    """A declared language containing a backtick/newline must not be
    spliced verbatim into the fence marker -- that would let notebook
    content break out of the code fence in the rendered Markdown."""
    malicious_language = "python\n```\n<script>alert(1)</script>\n```python"
    document = loads(
        json.dumps(_notebook_with_language([_code("x = 1")], malicious_language)), mode="strict"
    )
    result = MarkdownExporter().export(document)
    assert "```python\nx = 1\n```" in result.content
    assert "<script>" not in result.content


def test_markdown_fence_rejects_a_language_with_a_bare_trailing_newline() -> None:
    """Gate G2 nitpick: `.match()` (not `.fullmatch()`) would let a
    language value consisting of otherwise-safe characters plus exactly
    one trailing newline through, since `$` matches just before a final
    newline -- not exploitable as an injection (no backtick can follow),
    but the fence must still fall back to "python" rather than splicing
    in extra whitespace from an invalid value."""
    document = loads(
        json.dumps(_notebook_with_language([_code("x = 1")], "python\n")), mode="strict"
    )
    result = MarkdownExporter().export(document)
    assert "```python\nx = 1\n```" in result.content


def test_python_exporter_represents_raw_cells_as_a_comment_block_instead_of_dropping_them() -> None:
    doc = _load([_raw("some raw content"), _code("x = 1")])
    result = PythonScriptExporter().export(doc)
    assert "# [raw cell]" in result.content
    assert "# some raw content" in result.content
    assert "x = 1" in result.content
