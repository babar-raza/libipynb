"""Deterministic Jupyter Notebook JSON writer."""

from __future__ import annotations

import json
from copy import deepcopy
from os import PathLike
from pathlib import Path
from typing import Any, Mapping, TextIO

from ..errors import NotebookWriteError
from ..model import NotebookDocument
from ..security import IPYNB_DEFAULT_LIMITS
from .reader import Source, ensure_cell_id, load

Destination = str | PathLike[str] | TextIO


def _as_mapping(value: NotebookDocument | Mapping[str, Any]) -> Mapping[str, Any]:
    if isinstance(value, NotebookDocument):
        return value.raw
    if isinstance(value, Mapping):
        return value
    raise TypeError("document must be an NotebookDocument or mapping")


def _profile_version(
    profile: str | None, source: Mapping[str, Any]
) -> tuple[int, int]:
    selected = profile or "4.5"
    if selected.startswith("nbformat-"):
        selected = selected.removeprefix("nbformat-")
    if selected == "declared":
        major = source.get("nbformat")
        minor = source.get("nbformat_minor")
        if (
            isinstance(major, bool)
            or not isinstance(major, int)
            or major != 4
            or isinstance(minor, bool)
            or not isinstance(minor, int)
            or minor < 0
        ):
            raise NotebookWriteError(
                "declared profile requires a non-negative nbformat 4.x version"
            )
        return major, minor
    if selected not in {"4.0", "4.1", "4.2", "4.3", "4.4", "4.5"}:
        raise ValueError(
            "profile must be 'declared' or one of nbformat 4.0 through 4.5"
        )
    major, minor = selected.split(".", 1)
    return int(major), int(minor)


def _normalized(
    value: NotebookDocument | Mapping[str, Any], *, profile: str | None
) -> dict[str, Any]:
    source = deepcopy(dict(_as_mapping(value)))
    major, minor = _profile_version(profile, source)
    if profile == "declared" or (
        isinstance(profile, str)
        and profile.removeprefix("nbformat-") == "declared"
    ):
        return source

    declared_major = source.get("nbformat")
    declared_minor = source.get("nbformat_minor")
    if (declared_major, declared_minor) != (major, minor):
        raise NotebookWriteError(
            f"writing nbformat {major}.{minor} from declared version "
            f"{declared_major}.{declared_minor} requires explicit upgrade()",
            code="IPYNB_EXPLICIT_UPGRADE_REQUIRED",
            context={
                "declared_version": (declared_major, declared_minor),
                "target_version": (major, minor),
            },
        )

    from ..validation import validate

    report = validate(source, profile=f"nbformat-{major}.{minor}")
    if not report.is_valid:
        first = report.errors[0]
        raise NotebookWriteError(
            f"notebook is not valid for nbformat {major}.{minor}: {first.message}",
            code=first.code,
            context={
                "path": first.location.path if first.location is not None else (),
                "error_count": len(report.errors),
            },
        )
    return source


def _legacy_normalized(
    value: NotebookDocument | Mapping[str, Any],
) -> dict[str, Any]:
    source = deepcopy(dict(_as_mapping(value)))
    source["nbformat"] = 4
    source["nbformat_minor"] = 5
    source.setdefault("metadata", {})
    raw_cells = source.setdefault("cells", [])
    if not isinstance(raw_cells, list):
        raise NotebookWriteError("cells must be an array")

    used_ids: set[str] = set()
    cells: list[dict[str, Any]] = []
    for index, raw_cell in enumerate(raw_cells):
        if not isinstance(raw_cell, dict):
            raise NotebookWriteError(f"cell {index} must be an object")
        cell = dict(raw_cell)
        cell.setdefault("cell_type", "raw")
        cell.setdefault("metadata", {})
        cell.setdefault("source", "")
        if cell["cell_type"] == "code":
            cell.setdefault("outputs", [])
            cell.setdefault("execution_count", None)
        ensure_cell_id(cell, used_ids)
        cells.append(cell)
    source["cells"] = cells
    return source


def dumps(
    document: NotebookDocument | Mapping[str, Any],
    *,
    profile: str | None = None,
    indent: int | None = 1,
) -> str:
    try:
        result = json.dumps(
            _normalized(document, profile=profile),
            ensure_ascii=False,
            indent=indent,
            sort_keys=True,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        if isinstance(exc, ValueError) and str(exc).startswith("profile must"):
            raise
        raise NotebookWriteError(f"cannot serialize notebook: {exc}") from exc
    IPYNB_DEFAULT_LIMITS.enforce("max_output_bytes", len(result.encode("utf-8")))
    return result


def dump(
    document: NotebookDocument | Mapping[str, Any],
    destination: Destination,
    *,
    profile: str | None = None,
    indent: int | None = 1,
) -> None:
    text = dumps(document, profile=profile, indent=indent) + "\n"
    if hasattr(destination, "write"):
        try:
            written = destination.write(text)
        except (OSError, UnicodeError) as exc:
            raise NotebookWriteError(f"cannot write notebook: {exc}") from exc
        if written is not None and written != len(text):
            raise NotebookWriteError("notebook destination accepted a partial write")
        return
    path = Path(destination)
    try:
        path.write_text(text, encoding="utf-8", newline="\n")
    except (OSError, UnicodeError) as exc:
        raise NotebookWriteError(f"cannot write notebook to {path}: {exc}") from exc


def write_ipynb(
    model: NotebookDocument | Mapping[str, Any],
    dest: Destination | None = None,
) -> str:
    try:
        normalized = _legacy_normalized(model)
        text = json.dumps(
            normalized,
            ensure_ascii=False,
            indent=1,
            sort_keys=True,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise NotebookWriteError(f"cannot serialize notebook: {exc}") from exc
    IPYNB_DEFAULT_LIMITS.enforce("max_output_bytes", len(text.encode("utf-8")))
    if dest is not None:
        dump(normalized, dest)
    return text


def get_cell_count(model: NotebookDocument | Mapping[str, Any]) -> int:
    return len(_as_mapping(model).get("cells", []))


def get_code_cells(
    model: NotebookDocument | Mapping[str, Any],
) -> list[dict[str, Any]]:
    return [
        cell
        for cell in _as_mapping(model).get("cells", [])
        if isinstance(cell, dict) and cell.get("cell_type") == "code"
    ]


def get_markdown_cells(
    model: NotebookDocument | Mapping[str, Any],
) -> list[dict[str, Any]]:
    return [
        cell
        for cell in _as_mapping(model).get("cells", [])
        if isinstance(cell, dict) and cell.get("cell_type") == "markdown"
    ]


def roundtrip(source: Source, dest: Destination) -> dict[str, Any]:
    document = load(source, mode="preservation")
    dump(document, dest, profile="declared")
    return load(dest, mode="preservation").raw


def ipynb_installed_workflow(source: Source) -> dict[str, Any]:
    document = load(source, mode="preservation")
    return {
        "format": "ipynb",
        "loaded": True,
        "nbformat": document.nbformat,
        "cell_count": document.cell_count,
        "code_cell_count": len(document.code_cells),
        "markdown_cell_count": len(document.markdown_cells),
    }
