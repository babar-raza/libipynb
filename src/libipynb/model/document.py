"""Pure Jupyter Notebook model objects; this module performs no I/O."""

from __future__ import annotations

from collections.abc import Iterable
from copy import deepcopy
from typing import TYPE_CHECKING, Any, ClassVar, cast

from .lifecycle import NotebookVersion, RecoveryAction

if TYPE_CHECKING:
    from .cleanup import ChangeReport, CleanupPolicy


class MimeBundle:
    """Typed, non-I/O view over a notebook MIME bundle."""

    def __init__(self, data: dict[str, Any]) -> None:
        self._data = data

    @property
    def mime_types(self) -> tuple[str, ...]:
        return tuple(self._data)

    def __getitem__(self, mime_type: str) -> Any:
        return self._data[mime_type]

    def get(self, mime_type: str, default: Any = None) -> Any:
        return self._data.get(mime_type, default)

    def to_dict(self) -> dict[str, Any]:
        return deepcopy(self._data)


class Cell:
    spec_qname: ClassVar[str] = "ipynb:cell"

    def __init__(self, data: dict[str, Any]) -> None:
        self._data = data

    @property
    def cell_type(self) -> str:
        return str(self._data.get("cell_type", "raw"))

    @property
    def id(self) -> str | None:
        value = self._data.get("id")
        return value if isinstance(value, str) else None

    @property
    def source(self) -> str:
        """Return the logical source text, independent of JSON representation."""
        value = self.raw_source
        return value if isinstance(value, str) else "".join(value)

    @property
    def raw_source(self) -> str | list[str]:
        """Return a defensive copy of the original string or string-list form."""
        value = self._data.get("source", "")
        if isinstance(value, str):
            return value
        if isinstance(value, list) and all(isinstance(item, str) for item in value):
            return list(value)
        return ""

    @property
    def metadata(self) -> dict[str, Any]:
        return dict(self._data.get("metadata", {}))

    @property
    def outputs(self) -> list[dict[str, Any]]:
        return list(self._data.get("outputs", []))

    @property
    def attachments(self) -> dict[str, Any]:
        return deepcopy(self._data.get("attachments", {}))

    @property
    def tags(self) -> tuple[str, ...]:
        value = self._data.get("metadata", {}).get("tags", [])
        if not isinstance(value, list):
            return ()
        return tuple(item for item in value if isinstance(item, str))

    @property
    def preservation_only(self) -> bool:
        return False

    @property
    def output_objects(self) -> list[NotebookOutput]:
        return []

    def to_dict(self) -> dict[str, Any]:
        return deepcopy(self._data)


class MarkdownCell(Cell):
    pass


class RawCell(Cell):
    pass


class CodeCell(Cell):
    @property
    def execution_count(self) -> int | None:
        value = self._data.get("execution_count")
        return value if isinstance(value, int) and not isinstance(value, bool) else None

    @property
    def output_objects(self) -> list[NotebookOutput]:
        values = self._data.get("outputs", [])
        if not isinstance(values, list):
            return []
        return [output_from_dict(value) for value in values if isinstance(value, dict)]


class UnknownCell(Cell):
    @property
    def preservation_only(self) -> bool:
        return True


class NotebookOutput:
    spec_qname: ClassVar[str] = "ipynb:output"

    def __init__(self, data: dict[str, Any]) -> None:
        self._data = data

    @property
    def output_type(self) -> str:
        return str(self._data.get("output_type", ""))

    @property
    def data(self) -> dict[str, Any]:
        return deepcopy(self._data.get("data", {}))

    @property
    def mime_bundle(self) -> MimeBundle:
        value = self._data.get("data", {})
        return MimeBundle(value if isinstance(value, dict) else {})

    @property
    def preservation_only(self) -> bool:
        return False

    def get_representation(self, mime_type: str) -> Any:
        return self._data.get("data", {}).get(mime_type)

    def add_representation(self, mime_type: str, value: Any) -> None:
        self._data.setdefault("data", {})[mime_type] = value

    def remove_representation(self, mime_type: str) -> bool:
        bundle = self._data.get("data")
        if isinstance(bundle, dict) and mime_type in bundle:
            del bundle[mime_type]
            return True
        return False

    def to_dict(self) -> dict[str, Any]:
        return deepcopy(self._data)


class StreamOutput(NotebookOutput):
    pass


class DisplayDataOutput(NotebookOutput):
    pass


class ExecuteResultOutput(NotebookOutput):
    pass


class ErrorOutput(NotebookOutput):
    pass


class UnknownOutput(NotebookOutput):
    @property
    def preservation_only(self) -> bool:
        return True


CELL_TYPES: dict[str, type[Cell]] = {
    "markdown": MarkdownCell,
    "raw": RawCell,
    "code": CodeCell,
}
OUTPUT_TYPES: dict[str, type[NotebookOutput]] = {
    "stream": StreamOutput,
    "display_data": DisplayDataOutput,
    "execute_result": ExecuteResultOutput,
    "error": ErrorOutput,
}


def cell_from_dict(data: dict[str, Any]) -> Cell:
    return CELL_TYPES.get(str(data.get("cell_type")), UnknownCell)(data)


def output_from_dict(data: dict[str, Any]) -> NotebookOutput:
    return OUTPUT_TYPES.get(str(data.get("output_type")), UnknownOutput)(data)


class NotebookDocument:
    """Mutable typed view over a preservation-oriented notebook mapping."""

    spec_qname: ClassVar[str] = "ipynb:notebook"

    def __init__(
        self,
        data: dict[str, Any],
        *,
        declared_version: NotebookVersion | None = None,
        detected_version: NotebookVersion | None = None,
        recovery_actions: Iterable[RecoveryAction] = (),
    ) -> None:
        self._data = data
        inferred = NotebookVersion(
            data.get("nbformat")
            if isinstance(data.get("nbformat"), int) and not isinstance(data.get("nbformat"), bool)
            else None,
            data.get("nbformat_minor")
            if isinstance(data.get("nbformat_minor"), int)
            and not isinstance(data.get("nbformat_minor"), bool)
            else None,
        )
        self._declared_version = declared_version or inferred
        self._detected_version = detected_version or inferred
        self._recovery_actions = tuple(recovery_actions)

    @classmethod
    def from_file(cls, path: str) -> NotebookDocument:
        from ..codec.reader import load

        return load(path, mode="preservation")

    @property
    def raw(self) -> dict[str, Any]:
        return self._data

    @property
    def nbformat(self) -> int:
        return int(self._data.get("nbformat", 0))

    @property
    def nbformat_minor(self) -> int:
        return int(self._data.get("nbformat_minor", 0))

    @property
    def declared_version(self) -> NotebookVersion:
        return self._declared_version

    @property
    def detected_version(self) -> NotebookVersion:
        return self._detected_version

    @property
    def recovery_actions(self) -> tuple[RecoveryAction, ...]:
        return self._recovery_actions

    @property
    def metadata(self) -> dict[str, Any]:
        return dict(self._data.get("metadata", {}))

    @property
    def cells(self) -> list[dict[str, Any]]:
        cells = self._data.setdefault("cells", [])
        if not isinstance(cells, list):
            raise TypeError("notebook cells must be a list")
        return cast(list[dict[str, Any]], cells)

    @property
    def cell_objects(self) -> list[Cell]:
        return [cell_from_dict(cell) for cell in self.cells]

    @property
    def cell_count(self) -> int:
        return len(self.cells)

    @property
    def is_empty(self) -> bool:
        return not self.cells

    @property
    def code_cells(self) -> list[dict[str, Any]]:
        return [cell for cell in self.cells if cell.get("cell_type") == "code"]

    @property
    def markdown_cells(self) -> list[dict[str, Any]]:
        return [cell for cell in self.cells if cell.get("cell_type") == "markdown"]

    @property
    def raw_cells(self) -> list[dict[str, Any]]:
        return [cell for cell in self.cells if cell.get("cell_type") == "raw"]

    def find_cells(
        self,
        *,
        cell_id: str | None = None,
        cell_type: str | None = None,
        tag: str | None = None,
        source_text: str | None = None,
    ) -> list[Cell]:
        """Search typed cell views without exposing raw dictionary traversal."""
        matches: list[Cell] = []
        for cell in self.cell_objects:
            if cell_id is not None and cell.id != cell_id:
                continue
            if cell_type is not None and cell.cell_type != cell_type:
                continue
            if tag is not None and tag not in cell.tags:
                continue
            if source_text is not None and source_text not in cell.source:
                continue
            matches.append(cell)
        return matches

    def add_cell(
        self,
        cell_type: str = "code",
        source: str | list[str] = "",
        metadata: dict[str, Any] | None = None,
        index: int | None = None,
    ) -> dict[str, Any]:
        from ..codec.reader import ensure_cell_id

        used_ids = {cell["id"] for cell in self.cells if isinstance(cell.get("id"), str)}
        cell: dict[str, Any] = {
            "cell_type": cell_type,
            "source": source,
            "metadata": dict(metadata or {}),
        }
        if cell_type == "code":
            cell.update(outputs=[], execution_count=None)
        ensure_cell_id(cell, used_ids)
        if index is None:
            self.cells.append(cell)
        else:
            self.cells.insert(index, cell)
        return cell

    def remove_cell(self, index: int) -> dict[str, Any]:
        removed: dict[str, Any] = self.cells.pop(index)
        return removed

    def clear_outputs(self, index: int) -> dict[str, Any]:
        cell = self.cells[index]
        if cell.get("cell_type") != "code":
            raise ValueError(f"cell at index {index} is not a code cell")
        cell["outputs"] = []
        cell["execution_count"] = None
        return cell

    def cleanup(
        self,
        *,
        policy: CleanupPolicy | None = None,
        dry_run: bool = False,
    ) -> ChangeReport:
        from .cleanup import cleanup

        return cleanup(self, policy=policy, dry_run=dry_run)

    def to_dict(self) -> dict[str, Any]:
        return dict(self._data)

    def __repr__(self) -> str:
        return f"NotebookDocument(nbformat={self.nbformat}, cells={self.cell_count})"


Output = NotebookOutput
