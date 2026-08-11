"""Stable-ID cell collection editing with atomic change reports."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
from enum import Enum
import re
from typing import Any, cast

from .document import Cell, NotebookDocument, cell_from_dict

_CELL_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_KNOWN_CELL_TYPES = frozenset({"code", "markdown", "raw"})


class CellEditOperation(str, Enum):
    INSERT = "insert"
    MOVE = "move"
    COPY = "copy"
    REPLACE = "replace"
    REMOVE = "remove"


@dataclass(frozen=True, slots=True)
class CellQuery:
    cell_id: str | None = None
    cell_type: str | None = None
    tag: str | None = None
    metadata: Mapping[str, Any] | None = None
    source_text: str | None = None

    def __post_init__(self) -> None:
        if self.metadata is not None:
            if not isinstance(self.metadata, Mapping):
                raise TypeError("metadata query must be a mapping")
            if not self.metadata:
                raise ValueError("metadata query must contain at least one key")
            object.__setattr__(self, "metadata", deepcopy(dict(self.metadata)))

    @property
    def has_criteria(self) -> bool:
        return any(
            value is not None
            for value in (
                self.cell_id,
                self.cell_type,
                self.tag,
                self.metadata,
                self.source_text,
            )
        )


@dataclass(frozen=True, slots=True)
class CellEdit:
    operation: CellEditOperation
    cell_id: str
    before_index: int | None
    after_index: int | None
    before: dict[str, Any] | None
    after: dict[str, Any] | None

    def __post_init__(self) -> None:
        object.__setattr__(self, "before", deepcopy(self.before))
        object.__setattr__(self, "after", deepcopy(self.after))


@dataclass(frozen=True, slots=True)
class CellEditReport:
    changes: tuple[CellEdit, ...]
    applied: bool

    @property
    def count(self) -> int:
        return len(self.changes)

    @property
    def would_change(self) -> bool:
        return bool(self.changes)


def _cells(raw: dict[str, Any]) -> list[dict[str, Any]]:
    value = raw.get("cells")
    if not isinstance(value, list):
        raise TypeError("notebook cells must be an array")
    for position, cell in enumerate(value):
        if not isinstance(cell, dict):
            raise TypeError(f"cell at index {position} must be an object")
    return cast(list[dict[str, Any]], value)


def _index(raw: dict[str, Any]) -> dict[str, tuple[int, dict[str, Any]]]:
    index: dict[str, tuple[int, dict[str, Any]]] = {}
    for position, cell in enumerate(_cells(raw)):
        cell_id = cell.get("id")
        if not isinstance(cell_id, str) or not cell_id:
            raise ValueError(
                f"cell at index {position} is missing a stable non-empty ID"
            )
        if not _CELL_ID.fullmatch(cell_id):
            raise ValueError(f"invalid cell ID: {cell_id!r}")
        if cell_id in index:
            raise ValueError(f"cell IDs must be unique: {cell_id}")
        index[cell_id] = (position, cell)
    return index


def _source_text(cell: Mapping[str, Any]) -> str:
    source = cell.get("source")
    if isinstance(source, str):
        return source
    if isinstance(source, list) and all(isinstance(item, str) for item in source):
        return "".join(source)
    return ""


def _metadata_contains(value: Any, expected: Any) -> bool:
    if isinstance(expected, Mapping):
        if not isinstance(value, Mapping):
            return False
        return all(
            key in value and _metadata_contains(value[key], item)
            for key, item in expected.items()
        )
    return bool(value == expected)


def _matches(cell: dict[str, Any], query: CellQuery) -> bool:
    if query.cell_id is not None and cell.get("id") != query.cell_id:
        return False
    if query.cell_type is not None and cell.get("cell_type") != query.cell_type:
        return False
    if query.tag is not None:
        metadata = cell.get("metadata")
        tags = metadata.get("tags") if isinstance(metadata, dict) else None
        if not isinstance(tags, list) or query.tag not in tags:
            return False
    if query.metadata is not None and not _metadata_contains(
        cell.get("metadata"),
        query.metadata,
    ):
        return False
    return (
        query.source_text is None
        or query.source_text in _source_text(cell)
    )


def _validate_cell(
    value: Mapping[str, Any],
    *,
    notebook_minor: int,
) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError("cell must be a mapping")
    cell = deepcopy(dict(value))
    cell_id = cell.get("id")
    if not isinstance(cell_id, str) or not _CELL_ID.fullmatch(cell_id):
        raise ValueError("cell ID must contain 1-64 ASCII letters, digits, _ or -")
    cell_type = cell.get("cell_type")
    if not isinstance(cell_type, str) or not cell_type:
        raise ValueError("cell_type must be a non-empty string")
    if cell_type not in _KNOWN_CELL_TYPES and notebook_minor <= 5:
        raise ValueError(f"unsupported current-profile cell type: {cell_type}")
    if not isinstance(cell.get("metadata"), dict):
        raise ValueError("cell metadata must be an object")
    source = cell.get("source")
    if not (
        isinstance(source, str)
        or (
            isinstance(source, list)
            and all(isinstance(item, str) for item in source)
        )
    ):
        raise ValueError("cell source must be a string or string array")
    if cell_type == "code":
        if "execution_count" not in cell:
            raise ValueError("code cell requires execution_count")
        count = cell["execution_count"]
        if count is not None and (
            not isinstance(count, int) or isinstance(count, bool) or count < 0
        ):
            raise ValueError("execution_count must be null or a non-negative integer")
        if not isinstance(cell.get("outputs"), list):
            raise ValueError("code cell outputs must be an array")
    attachments = cell.get("attachments")
    if attachments is not None and not isinstance(attachments, dict):
        raise ValueError("cell attachments must be an object")
    return cell


def _copy_id(source_id: str, used: set[str]) -> str:
    suffix = "-copy"
    candidate = f"{source_id[: 64 - len(suffix)]}{suffix}"
    number = 2
    while candidate in used:
        suffix = f"-copy-{number}"
        candidate = f"{source_id[: 64 - len(suffix)]}{suffix}"
        number += 1
    return candidate


class CellEditor:
    """Cell collection mutations that preserve legacy index-based methods."""

    def __init__(self, document: NotebookDocument) -> None:
        if not isinstance(document, NotebookDocument):
            raise TypeError("document must be an NotebookDocument")
        _index(document.raw)
        self.document = document

    def search(self, query: CellQuery) -> tuple[Cell, ...]:
        if not isinstance(query, CellQuery):
            raise TypeError("query must be a CellQuery")
        return tuple(
            cell_from_dict(cell)
            for cell in _cells(self.document.raw)
            if _matches(cell, query)
        )

    def insert(
        self,
        cell: Mapping[str, Any],
        *,
        index: int | None = None,
        dry_run: bool = False,
    ) -> CellEditReport:
        target = deepcopy(self.document.raw)
        values = _cells(target)
        position = len(values) if index is None else index
        if (
            not isinstance(position, int)
            or isinstance(position, bool)
            or position < 0
            or position > len(values)
        ):
            raise IndexError("insert index is outside the cell collection")
        validated = _validate_cell(
            cell,
            notebook_minor=self.document.nbformat_minor,
        )
        cell_id = str(validated["id"])
        if cell_id in _index(target):
            raise ValueError(f"cell ID must be unique: {cell_id}")
        values.insert(position, validated)
        change = CellEdit(
            CellEditOperation.INSERT,
            cell_id,
            None,
            position,
            None,
            validated,
        )
        return self._finish(target, (change,), dry_run=dry_run)

    def move(
        self,
        cell_id: str,
        index: int,
        *,
        dry_run: bool = False,
    ) -> CellEditReport:
        target = deepcopy(self.document.raw)
        values = _cells(target)
        current_index, cell = self._select(target, cell_id)
        if (
            not isinstance(index, int)
            or isinstance(index, bool)
            or index < 0
            or index >= len(values)
        ):
            raise IndexError("move index is outside the cell collection")
        if current_index == index:
            return CellEditReport((), False)
        values.pop(current_index)
        values.insert(index, cell)
        change = CellEdit(
            CellEditOperation.MOVE,
            cell_id,
            current_index,
            index,
            cell,
            cell,
        )
        return self._finish(target, (change,), dry_run=dry_run)

    def copy(
        self,
        cell_id: str,
        *,
        index: int | None = None,
        new_id: str | None = None,
        dry_run: bool = False,
    ) -> CellEditReport:
        target = deepcopy(self.document.raw)
        values = _cells(target)
        current_index, cell = self._select(target, cell_id)
        position = current_index + 1 if index is None else index
        if (
            not isinstance(position, int)
            or isinstance(position, bool)
            or position < 0
            or position > len(values)
        ):
            raise IndexError("copy index is outside the cell collection")
        used = set(_index(target))
        selected_id = new_id or _copy_id(cell_id, used)
        copied = deepcopy(cell)
        copied["id"] = selected_id
        copied = _validate_cell(
            copied,
            notebook_minor=self.document.nbformat_minor,
        )
        if selected_id in used:
            raise ValueError(f"cell ID must be unique: {selected_id}")
        values.insert(position, copied)
        change = CellEdit(
            CellEditOperation.COPY,
            selected_id,
            None,
            position,
            None,
            copied,
        )
        return self._finish(target, (change,), dry_run=dry_run)

    def replace(
        self,
        cell_id: str,
        cell: Mapping[str, Any],
        *,
        dry_run: bool = False,
    ) -> CellEditReport:
        target = deepcopy(self.document.raw)
        values = _cells(target)
        position, before = self._select(target, cell_id)
        replacement = deepcopy(dict(cell))
        replacement["id"] = cell_id
        replacement = _validate_cell(
            replacement,
            notebook_minor=self.document.nbformat_minor,
        )
        if before == replacement:
            return CellEditReport((), False)
        values[position] = replacement
        change = CellEdit(
            CellEditOperation.REPLACE,
            cell_id,
            position,
            position,
            before,
            replacement,
        )
        return self._finish(target, (change,), dry_run=dry_run)

    def remove(
        self,
        cell_id: str,
        *,
        dry_run: bool = False,
    ) -> CellEditReport:
        target = deepcopy(self.document.raw)
        values = _cells(target)
        position, cell = self._select(target, cell_id)
        values.pop(position)
        change = CellEdit(
            CellEditOperation.REMOVE,
            cell_id,
            position,
            None,
            cell,
            None,
        )
        return self._finish(target, (change,), dry_run=dry_run)

    def remove_where(
        self,
        query: CellQuery,
        *,
        dry_run: bool = False,
    ) -> CellEditReport:
        if not isinstance(query, CellQuery):
            raise TypeError("query must be a CellQuery")
        if not query.has_criteria:
            raise ValueError("bulk removal requires at least one criterion")
        target = deepcopy(self.document.raw)
        values = _cells(target)
        changes = tuple(
            CellEdit(
                CellEditOperation.REMOVE,
                str(cell["id"]),
                position,
                None,
                cell,
                None,
            )
            for position, cell in enumerate(values)
            if _matches(cell, query)
        )
        if not changes:
            return CellEditReport((), False)
        removed = {change.cell_id for change in changes}
        target["cells"] = [
            cell for cell in values if cell.get("id") not in removed
        ]
        return self._finish(target, changes, dry_run=dry_run)

    @staticmethod
    def _select(
        raw: dict[str, Any],
        cell_id: str,
    ) -> tuple[int, dict[str, Any]]:
        if not isinstance(cell_id, str) or not cell_id:
            raise ValueError("cell_id must be a non-empty string")
        try:
            return _index(raw)[cell_id]
        except KeyError as exc:
            raise KeyError(f"cell ID not found: {cell_id}") from exc

    def _finish(
        self,
        target: dict[str, Any],
        changes: tuple[CellEdit, ...],
        *,
        dry_run: bool,
    ) -> CellEditReport:
        from ..validation import validate

        report = validate(NotebookDocument(target))
        if not report.is_valid:
            first = report.errors[0]
            raise ValueError(
                f"cell edit would invalidate notebook: {first.code}: "
                f"{first.message}"
            )
        if not dry_run:
            self.document.raw.clear()
            self.document.raw.update(target)
        return CellEditReport(changes, not dry_run)


def edit_cells(document: NotebookDocument) -> CellEditor:
    return CellEditor(document)


__all__ = [
    "CellEdit",
    "CellEditOperation",
    "CellEditReport",
    "CellEditor",
    "CellQuery",
    "edit_cells",
]
