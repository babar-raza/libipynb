"""Exporter adapter interfaces and built-in implementations.

IPYNB-EXPORT-001: exporter adapters return main output plus ancillary
resources, with exporter-specific logic outside the core parser.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Any, Protocol, runtime_checkable

from ..model.document import Cell, CodeCell, IpynbDocument, cell_from_dict


def _is_safe_resource_filename(name: str) -> bool:
    """An attachment key is untrusted document content, not a path -- reject
    anything that is not a bare filename (no separators, no ``..`` segments,
    not absolute) before it becomes an AncillaryResource.filename a caller
    might join onto a directory when writing exported resources to disk."""

    if not name or name in {".", ".."} or "\\" in name:
        return False
    candidate = PurePosixPath(name)
    return candidate.name == name and ".." not in candidate.parts


@dataclass(frozen=True, slots=True)
class AncillaryResource:
    """A resource extracted during export (image, attachment, etc.)."""

    filename: str
    mime_type: str
    data: bytes
    source_path: tuple[str | int, ...]


@dataclass(frozen=True, slots=True)
class ExportResult:
    """Main output plus any ancillary resources collected during export."""

    content: str
    resources: tuple[AncillaryResource, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class ExportAdapter(Protocol):
    """Protocol for notebook export adapters."""

    def export(self, document: IpynbDocument) -> ExportResult: ...


def _collect_resources(
    cells: list[dict[str, Any]],
) -> list[AncillaryResource]:
    resources: list[AncillaryResource] = []
    counter: dict[str, int] = {}
    for cell_index, cell_raw in enumerate(cells):
        for key, attachment_bundle in cell_raw.get("attachments", {}).items():
            if isinstance(attachment_bundle, dict) and _is_safe_resource_filename(key):
                for mime, payload in attachment_bundle.items():
                    if isinstance(payload, str) and "/" in mime:
                        try:
                            data = base64.b64decode(payload)
                        except Exception:
                            continue
                        resources.append(
                            AncillaryResource(
                                filename=key,
                                mime_type=mime,
                                data=data,
                                source_path=("cells", cell_index, "attachments", key),
                            )
                        )
        if cell_raw.get("cell_type") != "code":
            continue
        for out_index, output in enumerate(cell_raw.get("outputs", [])):
            if not isinstance(output, dict):
                continue
            bundle = output.get("data", {})
            if not isinstance(bundle, dict):
                continue
            for mime, payload in bundle.items():
                if not mime.startswith("image/"):
                    continue
                if not isinstance(payload, str):
                    continue
                try:
                    data = base64.b64decode(payload)
                except Exception:
                    continue
                ext = mime.split("/", 1)[1].split("+", 1)[0]
                n = counter.get(ext, 0)
                filename = f"output_{cell_index}_{n}.{ext}"
                counter[ext] = n + 1
                if not _is_safe_resource_filename(filename):
                    continue
                resources.append(
                    AncillaryResource(
                        filename=filename,
                        mime_type=mime,
                        data=data,
                        source_path=("cells", cell_index, "outputs", out_index, "data", mime),
                    )
                )
    return resources


class MarkdownExporter:
    """Export a notebook as Markdown with fenced code blocks."""

    def export(self, document: IpynbDocument) -> ExportResult:
        parts: list[str] = []
        resources = _collect_resources(document.cells)
        for cell_raw in document.cells:
            cell = cell_from_dict(cell_raw)
            if cell.cell_type == "markdown":
                parts.append(cell.source)
            elif cell.cell_type == "code":
                parts.append(f"```python\n{cell.source}\n```")
            elif cell.cell_type == "raw":
                parts.append(cell.source)
            else:
                parts.append(f"<!-- unknown cell type: {cell.cell_type} -->")
        return ExportResult(
            content="\n\n".join(parts),
            resources=tuple(resources),
            metadata={
                "format": "markdown",
                "cell_count": document.cell_count,
            },
        )


class PythonScriptExporter:
    """Export code cells as a Python script with markdown as comments."""

    def export(self, document: IpynbDocument) -> ExportResult:
        parts: list[str] = []
        resources = _collect_resources(document.cells)
        for cell_raw in document.cells:
            cell = cell_from_dict(cell_raw)
            if cell.cell_type == "code":
                parts.append(cell.source)
            elif cell.cell_type == "markdown":
                commented = "\n".join(f"# {line}" for line in cell.source.splitlines())
                parts.append(commented)
        return ExportResult(
            content="\n\n".join(parts),
            resources=tuple(resources),
            metadata={
                "format": "python",
                "cell_count": document.cell_count,
            },
        )
