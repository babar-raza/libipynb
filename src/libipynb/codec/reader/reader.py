"""Bounded Jupyter Notebook JSON reader."""

from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from os import PathLike
from pathlib import Path
from typing import Any, NoReturn, TextIO

from ..._internal.probe import ProbeResult
from ...security.limits import NotebookResourceLimits as ResourceLimits

from ...errors import IpynbParseError
from ...model import IpynbDocument, NotebookVersion, RecoveryAction
from ...security.limits import bounded_object_pairs_hook, effective_limits, enforce_structure

CELL_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")
Source = str | bytes | PathLike[str] | TextIO


def _enforce_text_size(text: str, limits: ResourceLimits) -> str:
    encoded_size = len(text.encode("utf-8"))
    limits.enforce("max_input_bytes", encoded_size)
    limits.enforce("max_decompressed_bytes", encoded_size)
    return text


def _read_source(source: Source, limits: ResourceLimits) -> str:
    if isinstance(source, bytes):
        limits.enforce("max_input_bytes", len(source))
        try:
            return _enforce_text_size(source.decode("utf-8"), limits)
        except UnicodeDecodeError as exc:
            raise IpynbParseError(f"notebook is not valid UTF-8: {exc}") from exc
    if hasattr(source, "read"):
        text = source.read()
        if not isinstance(text, str):
            raise TypeError("notebook text stream read() must return str")
        return _enforce_text_size(text, limits)
    if isinstance(source, str) and source.lstrip().startswith(("{", "[")):
        return _enforce_text_size(source, limits)
    path = Path(source)
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise IpynbParseError(f"cannot read notebook source {source!r}: {exc}") from exc
    limits.enforce("max_input_bytes", size)
    try:
        return _enforce_text_size(path.read_text(encoding="utf-8"), limits)
    except (OSError, UnicodeDecodeError) as exc:
        raise IpynbParseError(f"cannot read notebook source {source!r}: {exc}") from exc


def _generate_cell_id(used_ids: set[str]) -> str:
    return _generate_cell_id_for({}, used_ids)


def _generate_cell_id_for(
    cell: dict[str, Any], used_ids: set[str]
) -> str:
    """Return a deterministic valid ID for ``cell``.

    The collision counter is part of the digest input, so equivalent inputs
    produce equivalent normalized notebooks across clean runs.
    """
    canonical = json.dumps(
        {key: value for key, value in cell.items() if key != "id"},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=repr,
    ).encode("utf-8")
    counter = 0
    while True:
        digest = hashlib.sha256(canonical + counter.to_bytes(8, "big")).hexdigest()
        candidate = digest[:16]
        if candidate not in used_ids:
            return candidate
        counter += 1


def ensure_cell_id(cell: dict[str, Any], used_ids: set[str]) -> dict[str, Any]:
    cell_id = cell.get("id")
    if (
        not isinstance(cell_id, str)
        or CELL_ID_PATTERN.fullmatch(cell_id) is None
        or cell_id in used_ids
    ):
        cell_id = _generate_cell_id_for(cell, used_ids)
    cell["id"] = cell_id
    used_ids.add(cell_id)
    return cell


def _raise_parse(
    code: str,
    message: str,
    path: tuple[str | int, ...] = (),
) -> NoReturn:
    raise IpynbParseError(message, code=code, context={"path": path})


def _recover_missing(
    mapping: dict[str, Any],
    key: str,
    value: Any,
    *,
    code: str,
    path: tuple[str | int, ...],
    message: str,
    actions: list[RecoveryAction],
) -> None:
    if key not in mapping:
        mapping[key] = value
        actions.append(RecoveryAction(code, path, message))


def _parse(
    text: str, *, mode: str, limits: ResourceLimits
) -> IpynbDocument:
    if mode not in {"strict", "preservation", "recovery"}:
        raise ValueError("mode must be 'strict', 'preservation', or 'recovery'")
    try:
        data = json.loads(text, object_pairs_hook=bounded_object_pairs_hook(limits))
    except json.JSONDecodeError as exc:
        raise IpynbParseError(
            f"invalid JSON: {exc}",
            code="IPYNB_JSON",
            context={"line": exc.lineno, "column": exc.colno, "offset": exc.pos},
        ) from exc
    except (RecursionError, MemoryError) as exc:
        raise IpynbParseError(
            "JSON complexity exceeds safe parser limits",
            code="IPYNB_JSON_COMPLEXITY",
            context={"path": ()},
        ) from exc
    if not isinstance(data, dict):
        _raise_parse("IPYNB_ROOT", "notebook root must be a JSON object")
    enforce_structure(data, limits)
    if "nbformat" not in data:
        _raise_parse(
            "IPYNB_VERSION",
            "missing required key: nbformat",
            ("nbformat",),
        )
    major = data.get("nbformat")
    if isinstance(major, bool) or not isinstance(major, int):
        _raise_parse(
            "IPYNB_VERSION",
            "nbformat must be an integer",
            ("nbformat",),
        )
    declared_minor = data.get("nbformat_minor")
    if declared_minor is not None and (
        isinstance(declared_minor, bool)
        or not isinstance(declared_minor, int)
        or declared_minor < 0
    ):
        _raise_parse(
            "IPYNB_MINOR_VERSION",
            "nbformat_minor must be a non-negative integer",
            ("nbformat_minor",),
        )

    declared_version = NotebookVersion(major, declared_minor)
    notebook = deepcopy(data) if mode == "recovery" else data
    actions: list[RecoveryAction] = []
    if mode == "strict" and "nbformat_minor" not in notebook:
        _raise_parse(
            "IPYNB_MINOR_VERSION",
            "strict mode requires nbformat_minor",
            ("nbformat_minor",),
        )
    if mode == "recovery":
        _recover_missing(
            notebook,
            "nbformat_minor",
            0,
            code="IPYNB_RECOVER_MINOR",
            path=("nbformat_minor",),
            message="synthesized the legacy default minor version 0",
            actions=actions,
        )
        _recover_missing(
            notebook,
            "metadata",
            {},
            code="IPYNB_RECOVER_METADATA",
            path=("metadata",),
            message="synthesized an empty notebook metadata object",
            actions=actions,
        )
        _recover_missing(
            notebook,
            "cells",
            [],
            code="IPYNB_RECOVER_CELLS",
            path=("cells",),
            message="synthesized an empty cell array",
            actions=actions,
        )

    minor = notebook.get("nbformat_minor")
    if minor is not None and (
        isinstance(minor, bool) or not isinstance(minor, int) or minor < 0
    ):
        _raise_parse(
            "IPYNB_MINOR_VERSION",
            "nbformat_minor must be a non-negative integer",
            ("nbformat_minor",),
        )
    if mode == "strict" and (
        major != 4 or not isinstance(minor, int) or minor > 5
    ):
        rendered_minor = "missing" if minor is None else str(minor)
        _raise_parse(
            "IPYNB_UNSUPPORTED_VERSION",
            f"strict profile supports nbformat 4.0 through 4.5, "
            f"got {major}.{rendered_minor}",
            ("nbformat", "nbformat_minor"),
        )

    metadata = notebook.get("metadata")
    if mode == "strict" and "metadata" not in notebook:
        _raise_parse(
            "IPYNB_METADATA",
            "strict mode requires notebook metadata",
            ("metadata",),
        )
    if metadata is not None and not isinstance(metadata, dict):
        _raise_parse(
            "IPYNB_METADATA",
            "metadata must be an object",
            ("metadata",),
        )
    raw_cells = notebook.get("cells")
    if mode == "strict" and "cells" not in notebook:
        _raise_parse("IPYNB_CELLS", "strict mode requires cells", ("cells",))
    if raw_cells is None:
        raw_cells = []
    if not isinstance(raw_cells, list):
        _raise_parse("IPYNB_CELLS", "cells must be an array", ("cells",))

    used_ids: set[str] = set()
    for index, raw_cell in enumerate(raw_cells):
        if not isinstance(raw_cell, dict):
            _raise_parse(
                "IPYNB_CELL",
                f"cell {index} is not a JSON object",
                ("cells", index),
            )
        cell = raw_cell
        cell_path = ("cells", index)
        if mode == "recovery":
            _recover_missing(
                cell,
                "cell_type",
                "raw",
                code="IPYNB_RECOVER_CELL_TYPE",
                path=(*cell_path, "cell_type"),
                message="synthesized the legacy default raw cell type",
                actions=actions,
            )
            _recover_missing(
                cell,
                "metadata",
                {},
                code="IPYNB_RECOVER_CELL_METADATA",
                path=(*cell_path, "metadata"),
                message="synthesized an empty cell metadata object",
                actions=actions,
            )
            _recover_missing(
                cell,
                "source",
                "",
                code="IPYNB_RECOVER_CELL_SOURCE",
                path=(*cell_path, "source"),
                message="synthesized an empty cell source",
                actions=actions,
            )
            if cell.get("cell_type") == "code":
                _recover_missing(
                    cell,
                    "outputs",
                    [],
                    code="IPYNB_RECOVER_OUTPUTS",
                    path=(*cell_path, "outputs"),
                    message="synthesized an empty code-cell output array",
                    actions=actions,
                )
                _recover_missing(
                    cell,
                    "execution_count",
                    None,
                    code="IPYNB_RECOVER_EXECUTION_COUNT",
                    path=(*cell_path, "execution_count"),
                    message="synthesized a null code-cell execution count",
                    actions=actions,
                )

        cell_type = cell.get("cell_type")
        if mode == "strict" and cell_type not in {"code", "markdown", "raw"}:
            _raise_parse(
                "IPYNB_CELL_TYPE",
                f"invalid or missing cell_type {cell_type!r}",
                (*cell_path, "cell_type"),
            )
        cell_metadata = cell.get("metadata")
        if mode == "strict" and "metadata" not in cell:
            _raise_parse(
                "IPYNB_CELL_METADATA",
                "strict mode requires cell metadata",
                (*cell_path, "metadata"),
            )
        if cell_metadata is not None and not isinstance(cell_metadata, dict):
            _raise_parse(
                "IPYNB_CELL_METADATA",
                "cell metadata must be an object",
                (*cell_path, "metadata"),
            )
        source = cell.get("source")
        if mode == "strict" and "source" not in cell:
            _raise_parse(
                "IPYNB_CELL_SOURCE",
                "strict mode requires cell source",
                (*cell_path, "source"),
            )
        if source is not None and (
            not isinstance(source, (str, list))
            or isinstance(source, list)
            and any(not isinstance(line, str) for line in source)
        ):
            _raise_parse(
                "IPYNB_CELL_SOURCE",
                "cell source must be a string or an array of strings",
                (*cell_path, "source"),
            )
        if mode == "strict" and cell_type == "code":
            outputs = cell.get("outputs")
            count = cell.get("execution_count")
            if not isinstance(outputs, list):
                _raise_parse(
                    "IPYNB_OUTPUTS",
                    "strict mode requires code-cell outputs to be an array",
                    (*cell_path, "outputs"),
                )
            if isinstance(count, bool) or (
                count is not None and not isinstance(count, int)
            ):
                _raise_parse(
                    "IPYNB_EXECUTION_COUNT",
                    "execution_count must be an integer or null",
                    (*cell_path, "execution_count"),
                )
            if "execution_count" not in cell:
                _raise_parse(
                    "IPYNB_EXECUTION_COUNT",
                    "strict mode requires code-cell execution_count",
                    (*cell_path, "execution_count"),
                )
        if mode == "strict" and isinstance(minor, int) and minor >= 5:
            cell_id = cell.get("id")
            if (
                not isinstance(cell_id, str)
                or CELL_ID_PATTERN.fullmatch(cell_id) is None
                or cell_id in used_ids
            ):
                _raise_parse(
                    "IPYNB_CELL_ID",
                    f"invalid, missing, or duplicate cell id {cell_id!r}",
                    (*cell_path, "id"),
                )
            used_ids.add(cell_id)

    if mode == "strict":
        from ...validation.schema import schema_diagnostics

        if not isinstance(minor, int):
            raise AssertionError("strict mode must have an integer minor version")
        schema_errors = schema_diagnostics(notebook, minor=minor)
        if schema_errors:
            first = schema_errors[0]
            _raise_parse(
                first.code,
                first.message,
                first.location.path if first.location is not None else (),
            )

    detected_version = NotebookVersion(
        major,
        minor if isinstance(minor, int) and not isinstance(minor, bool) else None,
    )
    return IpynbDocument(
        notebook,
        declared_version=declared_version,
        detected_version=detected_version,
        recovery_actions=actions,
    )


def loads(
    data: str | bytes,
    *,
    mode: str = "strict",
    limits: ResourceLimits | None = None,
) -> IpynbDocument:
    selected = effective_limits(limits)
    return _parse(_read_source(data, selected), mode=mode, limits=selected)


def load(
    source: Source,
    *,
    mode: str = "strict",
    limits: ResourceLimits | None = None,
) -> IpynbDocument:
    selected = effective_limits(limits)
    return _parse(_read_source(source, selected), mode=mode, limits=selected)


def load_ipynb(
    source: Source, *, limits: ResourceLimits | None = None
) -> dict[str, Any]:
    # Alpha compatibility facade: retain its characterized normalization.
    # The production ``load``/``loads`` APIs never synthesize IDs implicitly.
    notebook = load(source, mode="recovery", limits=limits).raw
    used_ids: set[str] = set()
    cells = notebook.get("cells", [])
    if isinstance(cells, list):
        for cell in cells:
            if isinstance(cell, dict):
                ensure_cell_id(cell, used_ids)
    return notebook


def probe(
    source: Source, *, limits: ResourceLimits | None = None
) -> ProbeResult:
    try:
        document = load(source, mode="preservation", limits=limits)
    except Exception as exc:
        return ProbeResult(False, 0.0, "ipynb", reason=str(exc))
    confidence = 1.0 if document.nbformat == 4 else 0.5
    return ProbeResult(
        True,
        confidence,
        "ipynb",
        profile=f"nbformat-{document.nbformat}.{document.nbformat_minor}",
    )


def probe_ipynb(source: Source, *, limits: ResourceLimits | None = None) -> bool:
    return bool(probe(source, limits=limits))
