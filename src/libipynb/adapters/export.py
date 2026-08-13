"""Exporter adapter interfaces and built-in implementations.

IPYNB-EXPORT-001: exporter adapters return main output plus ancillary
resources, with exporter-specific logic outside the core parser.
"""

from __future__ import annotations

import base64
import binascii
import json
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any, Protocol, runtime_checkable

from ..errors import NotebookError
from ..model.document import NotebookDocument, cell_from_dict


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

    def export(self, document: NotebookDocument) -> ExportResult: ...


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
                        except (ValueError, binascii.Error):
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
                except (ValueError, binascii.Error):
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

    def export(self, document: NotebookDocument) -> ExportResult:
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

    def export(self, document: NotebookDocument) -> ExportResult:
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


class HtmlExporter:
    """Export a notebook to self-contained HTML via the real `nbconvert` tool.

    LIBIPYNB-V5: wraps `python -m nbconvert --to html --stdout` as a
    subprocess rather than importing nbconvert as a Python module --
    `src/libipynb/**` must never do so (`tests/unit/test_import_boundary.py`
    statically enforces this for exactly this reason: `nbconvert` is a
    test-time oracle/exec-extra tool, not a runtime dependency of the core
    package). This is the same "wrap the real tool without a Python import
    dependency on it" pattern already used by :mod:`libipynb.adapters.execute`
    and the git diff/merge driver integration -- not a workaround invented
    for this adapter alone.

    One-directional: HTML is not a format libipynb (or nbconvert) can read
    back into an equivalent notebook, unlike :class:`JupytextExporter`.
    Requires the ``export`` extra (``pip install libipynb[export]``), or any
    other installation that provides ``python -m nbconvert`` on this same
    interpreter.
    """

    def __init__(self, *, timeout: float = 120.0) -> None:
        self.timeout = timeout

    def export(self, document: NotebookDocument) -> ExportResult:
        with tempfile.TemporaryDirectory() as tmp_dir:
            source_path = Path(tmp_dir) / "notebook.ipynb"
            source_path.write_text(json.dumps(document.raw), encoding="utf-8")
            try:
                completed = subprocess.run(
                    [
                        sys.executable,
                        "-m",
                        "nbconvert",
                        "--to",
                        "html",
                        "--stdout",
                        str(source_path),
                    ],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    timeout=self.timeout,
                    check=False,
                )
            except FileNotFoundError as exc:
                raise NotebookError(
                    "HTML export requires nbconvert to be installed "
                    "(pip install libipynb[export] or pip install nbconvert)",
                    code="export_tool_unavailable",
                ) from exc
            except subprocess.TimeoutExpired as exc:
                raise NotebookError(
                    f"nbconvert did not finish converting to HTML within {self.timeout}s",
                    code="export_tool_timeout",
                ) from exc

        if completed.returncode != 0:
            # Gate G2 finding: the common "not installed" case does not
            # raise FileNotFoundError (sys.executable itself always exists)
            # -- `python -m nbconvert` runs successfully as a process and
            # exits non-zero with "No module named nbconvert" on stderr.
            # Detect that specific message so this case gets the same
            # actionable, install-pointing error as a genuinely missing
            # interpreter, instead of a generic "failed" message.
            if "No module named nbconvert" in completed.stderr:
                raise NotebookError(
                    "HTML export requires nbconvert to be installed "
                    "(pip install libipynb[export] or pip install nbconvert)",
                    code="export_tool_unavailable",
                )
            raise NotebookError(
                f"nbconvert failed converting to HTML: {completed.stderr.strip()}",
                code="export_tool_failed",
            )
        return ExportResult(
            content=completed.stdout,
            resources=(),
            metadata={
                "format": "html",
                "cell_count": document.cell_count,
                "reversible": False,
            },
        )


class JupytextExporter:
    """Export a notebook to Jupytext's paired-text format via the real
    `jupytext` library.

    LIBIPYNB-V5: unlike :class:`HtmlExporter`, `jupytext` is imported
    directly -- it is not in `test_import_boundary.py`'s forbidden list.
    `jupytext.reads()`/`writes()` are used with the notebook passed as a
    JSON *string* (``fmt="ipynb"``), not a dict, so jupytext's own internal
    ipynb reader constructs whatever object it needs -- this module never
    imports `nbformat` itself, preserving libipynb's independent-
    implementation design even though jupytext transitively depends on it.

    Round-trips: unlike HTML, Jupytext's text formats are designed to be
    read back into an equivalent notebook (by jupytext itself, not by
    libipynb). Requires the ``export`` extra (``pip install
    libipynb[export]``) or a standalone `jupytext` install.
    """

    def __init__(self, *, fmt: str = "py:percent") -> None:
        self.fmt = fmt

    def export(self, document: NotebookDocument) -> ExportResult:
        try:
            import jupytext  # type: ignore[import-untyped]
        except ImportError as exc:
            raise NotebookError(
                "Jupytext export requires the jupytext package "
                "(pip install libipynb[export] or pip install jupytext)",
                code="export_tool_unavailable",
            ) from exc

        try:
            node = jupytext.reads(json.dumps(document.raw), fmt="ipynb")
            content = jupytext.writes(node, fmt=self.fmt)
        except Exception as exc:  # jupytext raises its own varied error types
            raise NotebookError(
                f"jupytext failed exporting to {self.fmt!r}: {exc}",
                code="export_tool_failed",
            ) from exc

        return ExportResult(
            content=content,
            resources=(),
            metadata={
                "format": f"jupytext:{self.fmt}",
                "cell_count": document.cell_count,
                "reversible": True,
            },
        )
