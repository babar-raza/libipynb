"""Exporter adapter interfaces and built-in implementations.

IPYNB-EXPORT-001: exporter adapters return main output plus ancillary
resources, with exporter-specific logic outside the core parser.
"""

from __future__ import annotations

import base64
import binascii
import json
import re
import subprocess
import sys
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from .._internal.immutable import deep_freeze
from .._internal.paths import is_safe_resource_filename as _is_safe_resource_filename
from ..errors import NotebookError
from ..model.document import NotebookDocument, cell_from_dict

# LIBIPYNB-Q9: _is_safe_resource_filename used to be defined here; it now
# lives in libipynb._internal.paths (shared with model.attachments, which
# needs the identical check but cannot import from this module -- see that
# module's docstring). Re-exported under its original local name so every
# other call site in this file is unaffected.


@dataclass(frozen=True, slots=True)
class AncillaryResource:
    """A resource extracted during export (image, attachment, etc.)."""

    filename: str
    mime_type: str
    data: bytes
    source_path: tuple[str | int, ...]

    def __post_init__(self) -> None:
        # LIBIPYNB-Q11a: `_collect_resources()` already only ever constructs
        # this with a filename it validated itself -- this guard is defense
        # in depth against direct construction (this class is public) with
        # a path-traversal-unsafe filename bypassing that check entirely.
        if not _is_safe_resource_filename(self.filename):
            raise ValueError(f"unsafe resource filename: {self.filename!r}")


@dataclass(frozen=True, slots=True)
class ExportResult:
    """Main output plus any ancillary resources collected during export.

    LIBIPYNB-Q61 (LIBIPYNB-Q43 follow-up): ``metadata`` was previously an
    ordinary mutable ``dict``, not wrapped in ``types.MappingProxyType``
    (LIBIPYNB-Q11a's original reasoning: no corruption bug had been
    demonstrated against it, and a bare ``mappingproxy`` is not
    ``json.dumps()``-able, a foot-gun for any future CLI export subcommand
    serializing this metadata directly). Now ``deep_freeze``-d in
    ``__post_init__``, matching every other result-object field this
    codebase protects against mutation-after-access (LIBIPYNB-Q43) -- the
    ``json.dumps()`` concern is resolved the same way it already is for
    ``model.diff``/``model.parameters``' own CLI JSON output: thaw with
    ``deep_thaw`` immediately before serializing, never serialize the
    frozen field directly.

    LIBIPYNB-Q15b: ``content`` is ``str | bytes``, not ``str`` alone --
    a real design decision, not a mechanical widening. PDF output
    (:class:`NbconvertExporter` with ``fmt="pdf"``) is inherently binary and
    cannot be represented as ``str`` without either a lossy encoding or a
    separate result type. A distinct binary-result dataclass was considered
    and rejected: it would fragment every caller's handling logic across two
    result shapes for what is, structurally, the exact same
    content-plus-resources-plus-metadata contract every other exporter
    already returns. Every exporter that predates this decision
    (:class:`MarkdownExporter`, :class:`PythonScriptExporter`,
    :class:`HtmlExporter`, :class:`JupytextExporter`) is unaffected and
    still always returns ``str`` -- check ``metadata["format"]`` or
    ``isinstance(result.content, bytes)`` when the format is not known
    ahead of time.
    """

    content: str | bytes
    resources: tuple[AncillaryResource, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "metadata", deep_freeze(dict(self.metadata)))


@runtime_checkable
class ExportAdapter(Protocol):
    """Protocol for notebook export adapters."""

    def export(self, document: NotebookDocument) -> ExportResult: ...


def _collect_resources(
    cells: list[dict[str, Any]],
) -> tuple[list[AncillaryResource], list[tuple[str | int, ...]]]:
    """Returns ``(resources, skipped_paths)`` -- ``skipped_paths`` records
    the ``source_path`` of every attachment/output image payload that could
    not be turned into an :class:`AncillaryResource` (corrupt base64, or an
    unresolvable filename collision), so callers can surface a count instead
    of a payload silently vanishing with zero diagnostic (LIBIPYNB-Q11a).
    """
    resources: list[AncillaryResource] = []
    skipped: list[tuple[str | int, ...]] = []
    used_filenames: set[str] = set()
    output_ext_counter: dict[str, int] = {}

    for cell_index, cell_raw in enumerate(cells):
        for key, attachment_bundle in cell_raw.get("attachments", {}).items():
            if not (isinstance(attachment_bundle, dict) and _is_safe_resource_filename(key)):
                continue
            # LIBIPYNB-Q11a: a single attachment key legitimately maps to
            # more than one MIME representation of the same image (e.g. both
            # `image/png` and `image/svg+xml` under one key) -- the naive
            # `filename=key` for every representation collided with itself
            # within a single cell, silently overwriting on disk. Append a
            # MIME-derived extension whenever more than one representation
            # is present, mirroring the output-branch's own extension
            # scheme, so same-cell multi-MIME entries never collide.
            mime_items = [
                (mime, payload)
                for mime, payload in attachment_bundle.items()
                if isinstance(payload, str) and "/" in mime
            ]
            multi_mime = len(mime_items) > 1
            for mime, payload in mime_items:
                source_path: tuple[str | int, ...] = ("cells", cell_index, "attachments", key, mime)
                try:
                    data = base64.b64decode(payload, validate=True)
                except (ValueError, binascii.Error):
                    skipped.append(source_path)
                    continue
                candidate = key
                if multi_mime:
                    ext = mime.split("/", 1)[1].split("+", 1)[0]
                    candidate = f"{key}.{ext}"
                if candidate in used_filenames:
                    # Cross-cell collision: two different cells attached a
                    # resource under the identical (possibly
                    # extension-disambiguated) filename.
                    candidate = f"cell{cell_index}_{candidate}"
                if candidate in used_filenames or not _is_safe_resource_filename(candidate):
                    skipped.append(source_path)
                    continue
                used_filenames.add(candidate)
                resources.append(
                    AncillaryResource(
                        filename=candidate,
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
                source_path = ("cells", cell_index, "outputs", out_index, "data", mime)
                try:
                    data = base64.b64decode(payload, validate=True)
                except (ValueError, binascii.Error):
                    skipped.append(source_path)
                    continue
                ext = mime.split("/", 1)[1].split("+", 1)[0]
                n = output_ext_counter.get(ext, 0)
                filename = f"output_{cell_index}_{n}.{ext}"
                output_ext_counter[ext] = n + 1
                if filename in used_filenames or not _is_safe_resource_filename(filename):
                    skipped.append(source_path)
                    continue
                used_filenames.add(filename)
                resources.append(
                    AncillaryResource(
                        filename=filename,
                        mime_type=mime,
                        data=data,
                        source_path=source_path,
                    )
                )
    return resources, skipped


#: LIBIPYNB-Q11b: validates a fence language resolved from notebook metadata
#: before it is spliced into a generated Markdown code-fence marker. Without
#: this check, an attacker-controlled `language_info.name` containing a
#: newline or backtick could break out of the fence (a latent
#: markdown-injection vector the language-resolution fix would otherwise
#: introduce). Real kernel language names (python, r, julia, ...) all match
#: comfortably within this class.
_SAFE_FENCE_LANGUAGE = re.compile(r"^[A-Za-z0-9_+-]{1,32}$")


def _resolve_fence_language(document: NotebookDocument) -> str:
    """Mirrors `adapters/execute.py::_resolve_kernel()`'s own
    `language_info`-then-`kernelspec.language` precedence. Falls back to
    `"python"` -- the exporter's own long-standing default -- whenever no
    declared language is present or it fails the character-class check."""
    metadata = document.metadata
    language = metadata.get("language_info", {}).get("name") or metadata.get("kernelspec", {}).get(
        "language"
    )
    # LIBIPYNB-Q11b Gate G2 nitpick: `.match()` (not `.fullmatch()`) lets a
    # string consisting of the allowed characters plus exactly one trailing
    # newline through, since `$` matches just before a final `\n` -- not an
    # injection vector (no backtick can follow), but `.fullmatch()` is the
    # correct check for "the whole value must be safe," so use it.
    if isinstance(language, str) and _SAFE_FENCE_LANGUAGE.fullmatch(language):
        return language
    return "python"


class MarkdownExporter:
    """Export a notebook as Markdown with fenced code blocks."""

    def export(self, document: NotebookDocument) -> ExportResult:
        parts: list[str] = []
        resources, skipped = _collect_resources(document.cells)
        fence_language = _resolve_fence_language(document)
        for cell_raw in document.cells:
            cell = cell_from_dict(cell_raw)
            if cell.cell_type == "markdown":
                parts.append(cell.source)
            elif cell.cell_type == "code":
                parts.append(f"```{fence_language}\n{cell.source}\n```")
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
                "skipped_resources": len(skipped),
                "skipped_paths": tuple(skipped),
            },
        )


class PythonScriptExporter:
    """Export code cells as a Python script with markdown as comments."""

    def export(self, document: NotebookDocument) -> ExportResult:
        parts: list[str] = []
        resources, skipped = _collect_resources(document.cells)
        for cell_raw in document.cells:
            cell = cell_from_dict(cell_raw)
            if cell.cell_type == "code":
                parts.append(cell.source)
            elif cell.cell_type == "markdown":
                commented = "\n".join(f"# {line}" for line in cell.source.splitlines())
                parts.append(commented)
            elif cell.cell_type == "raw":
                # LIBIPYNB-Q11b: previously dropped entirely while still
                # counted in metadata.cell_count -- represented as a
                # comment block (mirroring the markdown-cell convention
                # above) rather than executable code, since raw-cell
                # content has no defined language and may not even be
                # Python-syntax-valid.
                commented = "\n".join(f"# {line}" for line in cell.source.splitlines())
                parts.append(f"# [raw cell]\n{commented}")
        return ExportResult(
            content="\n\n".join(parts),
            resources=tuple(resources),
            metadata={
                "format": "python",
                "cell_count": document.cell_count,
                "skipped_resources": len(skipped),
                "skipped_paths": tuple(skipped),
            },
        )


#: LIBIPYNB-Q15b: formats whose `output_mimetype` (confirmed by importing
#: the real, installed `nbconvert` package directly in a throwaway
#: interpreter -- never in `src/libipynb` itself, per the import-boundary
#: rule below) is not `text/*`. nbconvert's own `StdoutWriter`
#: (`nbconvert.writers.stdout.StdoutWriter.write`) unconditionally wraps
#: stdout in a UTF-8 *text* codec writer (`nbconvert.utils.io
#: .unicode_std_stream`) -- confirmed by reading that source directly --
#: so piping a binary format through `--stdout` would silently corrupt it.
#: Scoped to `pdf`/`webpdf` (both produce a `.pdf` file) -- `qtpdf`/
#: `qtpng` need a Qt WebEngine install this environment doesn't have and
#: report a surprising `file_extension` (`.html`, not their real output
#: extension) that would need its own separate verification; out of scope
#: for this card, which only names `pdf`/`webpdf`/`slides` explicitly.
_BINARY_NBCONVERT_FORMATS = frozenset({"pdf", "webpdf"})


class NbconvertExporter:
    """Export a notebook to any format the real `nbconvert` CLI supports, by
    shelling out to `python -m nbconvert --to <fmt>`.

    LIBIPYNB-V5/Q15b: wraps the real tool as a subprocess rather than
    importing nbconvert as a Python module -- `src/libipynb/**` must never
    do so (`tests/unit/test_import_boundary.py` statically enforces this:
    `nbconvert` is a test-time oracle/exec-extra tool, not a runtime
    dependency of the core package). Same "wrap the real tool without a
    Python import dependency on it" pattern already used by
    :mod:`libipynb.adapters.execute` and the git diff/merge driver
    integration.

    Text formats (``html``, ``slides``, ``script``, ``markdown``, ``rst``,
    ``asciidoc``, ...) are captured via ``--stdout``, exactly as the
    original ``HtmlExporter`` always did -- :attr:`ExportResult.content`
    is ``str``. Binary formats (currently ``pdf``/``webpdf`` --
    see :data:`_BINARY_NBCONVERT_FORMATS`) cannot go through ``--stdout``
    at all (see that constant's docstring) and are instead written to a
    real file via ``--output-dir`` and read back from disk --
    :attr:`ExportResult.content` is ``bytes``.

    All formats here are one-directional: nbconvert output is not a format
    libipynb (or nbconvert) can read back into an equivalent notebook,
    unlike :class:`JupytextExporter`. Requires the ``export`` extra
    (``pip install libipynb[export]``), or any other installation that
    provides ``python -m nbconvert`` on this same interpreter -- plus,
    for ``pdf``, a working LaTeX toolchain, or for ``webpdf``, a working
    Playwright/Chromium install; neither is bundled by the ``export``
    extra itself (matching real `nbconvert`'s own equivalent, separate
    requirement for these two formats).
    """

    def __init__(self, fmt: str = "html", *, timeout: float = 120.0) -> None:
        if not fmt:
            raise ValueError("fmt must be a non-empty nbconvert format name")
        self.fmt = fmt
        self.timeout = timeout

    def export(self, document: NotebookDocument, *, title: str | None = None) -> ExportResult:
        """``title``, if given, becomes the exported document's ``<title>``
        (confirmed for the ``html``/``slides`` templates, which both prefer
        ``nb.metadata.title`` over their filename-derived fallback and
        HTML-escape it themselves -- see LIBIPYNB-Q11b; not independently
        verified for ``pdf``/``webpdf`` in this environment, see this
        card's own environment-blocked note).
        """
        is_binary = self.fmt in _BINARY_NBCONVERT_FORMATS
        raw = document.raw
        if title is not None:
            sanitized_title = Path(title).stem
            raw = {**raw, "metadata": {**raw.get("metadata", {}), "title": sanitized_title}}
        with tempfile.TemporaryDirectory() as tmp_dir:
            source_path = Path(tmp_dir) / "notebook.ipynb"
            source_path.write_text(json.dumps(raw), encoding="utf-8")
            # LIBIPYNB-V5 Gate G2: `tests/integration/test_obligation_security_baseline.py`
            # statically enforces that every subprocess call in this file
            # invokes `[sys.executable, "-m", "nbconvert", ...]` as an
            # inline list *literal* at the call site (not a variable built
            # up beforehand) -- the format-dependent tail is spliced in via
            # `*tail_args` inside that same literal so the fixed three-token
            # prefix stays statically verifiable.
            tail_args = (
                ["--output-dir", tmp_dir, str(source_path)]
                if is_binary
                else ["--stdout", str(source_path)]
            )
            try:
                completed = subprocess.run(
                    [sys.executable, "-m", "nbconvert", "--to", self.fmt, *tail_args],
                    capture_output=True,
                    text=not is_binary,
                    encoding="utf-8" if not is_binary else None,
                    timeout=self.timeout,
                    check=False,
                )
            except FileNotFoundError as exc:
                raise NotebookError(
                    f"{self.fmt} export requires nbconvert to be installed "
                    "(pip install libipynb[export] or pip install nbconvert)",
                    code="export_tool_unavailable",
                ) from exc
            except subprocess.TimeoutExpired as exc:
                raise NotebookError(
                    f"nbconvert did not finish converting to {self.fmt} within {self.timeout}s",
                    code="export_tool_timeout",
                ) from exc

            if completed.returncode != 0:
                # Gate G2 finding (originally against HtmlExporter, applies
                # identically here): the common "not installed" case does
                # not raise FileNotFoundError (sys.executable itself always
                # exists) -- `python -m nbconvert` runs successfully as a
                # *process* and exits non-zero with "No module named
                # nbconvert" on stderr. Detect that specific message so
                # this case gets the same actionable, install-pointing
                # error as a genuinely missing interpreter.
                stderr_text = (
                    completed.stderr
                    if isinstance(completed.stderr, str)
                    else (completed.stderr or b"").decode("utf-8", errors="replace")
                )
                if "No module named nbconvert" in stderr_text:
                    raise NotebookError(
                        f"{self.fmt} export requires nbconvert to be installed "
                        "(pip install libipynb[export] or pip install nbconvert)",
                        code="export_tool_unavailable",
                    )
                raise NotebookError(
                    f"nbconvert failed converting to {self.fmt}: {stderr_text.strip()}",
                    code="export_tool_failed",
                )

            content: str | bytes
            if is_binary:
                output_path = Path(tmp_dir) / "notebook.pdf"
                if not output_path.is_file():
                    raise NotebookError(
                        f"nbconvert reported success but produced no output file "
                        f"for format {self.fmt!r} (expected {output_path.name})",
                        code="export_tool_failed",
                    )
                content = output_path.read_bytes()
                # LIBIPYNB-Q59: a success exit code plus an output file
                # existing does not mean the file's CONTENT is actually
                # usable -- a broken/incomplete LaTeX distribution (or
                # Playwright/Chromium install, for webpdf) can exit 0 while
                # emitting an empty or truncated stub. Both binary formats
                # this adapter supports (pdf/webpdf, see
                # _BINARY_NBCONVERT_FORMATS) produce PDF output, so a
                # minimal, cheap, genuinely discriminating check is the
                # standard PDF magic-byte header -- distinct from, and
                # complementary to, the missing-file check above.
                if not content:
                    raise NotebookError(
                        f"nbconvert reported success but produced an empty output file "
                        f"for format {self.fmt!r} (expected {output_path.name})",
                        code="export_tool_failed",
                    )
                if not content.startswith(b"%PDF-"):
                    raise NotebookError(
                        f"nbconvert reported success but the output file for format "
                        f"{self.fmt!r} does not look like a valid PDF (missing the "
                        f"'%PDF-' header) -- likely a truncated or corrupted output "
                        f"from an incomplete LaTeX/Playwright install",
                        code="export_tool_failed",
                    )
            else:
                content = completed.stdout

        return ExportResult(
            content=content,
            resources=(),
            metadata={
                "format": self.fmt,
                "cell_count": document.cell_count,
                "reversible": False,
            },
        )


class HtmlExporter(NbconvertExporter):
    """Thin backward-compatible alias for ``NbconvertExporter(fmt="html")``.

    LIBIPYNB-Q15b: kept as its own name since it predates the generalized
    :class:`NbconvertExporter` and existing callers already import/
    construct it directly by this name -- byte-identical behavior to
    before this card, including its ``title=`` keyword (LIBIPYNB-Q11b).
    """

    def __init__(self, *, timeout: float = 120.0) -> None:
        super().__init__("html", timeout=timeout)


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
