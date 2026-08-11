"""Read-only typed metadata snapshots with exact unknown-data retention."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from .document import Cell, NotebookDocument, NotebookOutput


class MetadataShapeError(ValueError):
    """Raised when a known metadata namespace has an invalid shape."""


def _mapping(value: Any, context: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise MetadataShapeError(f"{context} metadata must be an object")
    return deepcopy(dict(value))


def _required_string(
    value: Mapping[str, Any],
    key: str,
    context: str,
) -> str:
    selected = value.get(key)
    if not isinstance(selected, str) or not selected:
        raise MetadataShapeError(
            f"{context}.{key} must be a non-empty string"
        )
    return selected


def _optional_string(
    value: Mapping[str, Any],
    key: str,
    context: str,
) -> str | None:
    selected = value.get(key)
    if selected is None:
        return None
    if not isinstance(selected, str):
        raise MetadataShapeError(f"{context}.{key} must be a string")
    return selected


def _optional_bool(
    value: Mapping[str, Any],
    key: str,
    context: str,
) -> bool | None:
    selected = value.get(key)
    if selected is None:
        return None
    if not isinstance(selected, bool):
        raise MetadataShapeError(f"{context}.{key} must be a boolean")
    return selected


def _extras(
    value: Mapping[str, Any],
    known: frozenset[str],
) -> dict[str, Any]:
    return deepcopy({key: item for key, item in value.items() if key not in known})


@dataclass(frozen=True, slots=True)
class KernelSpecMetadata:
    name: str
    display_name: str
    language: str | None
    _raw: dict[str, Any]

    @classmethod
    def from_value(cls, value: Any) -> "KernelSpecMetadata":
        raw = _mapping(value, "kernelspec")
        return cls(
            name=_required_string(raw, "name", "kernelspec"),
            display_name=_required_string(raw, "display_name", "kernelspec"),
            language=_optional_string(raw, "language", "kernelspec"),
            _raw=raw,
        )

    @property
    def extras(self) -> dict[str, Any]:
        return _extras(
            self._raw,
            frozenset({"name", "display_name", "language"}),
        )

    def to_dict(self) -> dict[str, Any]:
        return deepcopy(self._raw)


@dataclass(frozen=True, slots=True)
class LanguageInfoMetadata:
    name: str
    version: str | None
    mimetype: str | None
    file_extension: str | None
    codemirror_mode: str | dict[str, Any] | None
    pygments_lexer: str | None
    _raw: dict[str, Any]

    @classmethod
    def from_value(cls, value: Any) -> "LanguageInfoMetadata":
        raw = _mapping(value, "language_info")
        mode = raw.get("codemirror_mode")
        if mode is not None and not isinstance(mode, (str, dict)):
            raise MetadataShapeError(
                "language_info.codemirror_mode must be a string or object"
            )
        return cls(
            name=_required_string(raw, "name", "language_info"),
            version=_optional_string(raw, "version", "language_info"),
            mimetype=_optional_string(raw, "mimetype", "language_info"),
            file_extension=_optional_string(
                raw,
                "file_extension",
                "language_info",
            ),
            codemirror_mode=deepcopy(mode),
            pygments_lexer=_optional_string(
                raw,
                "pygments_lexer",
                "language_info",
            ),
            _raw=raw,
        )

    @property
    def extras(self) -> dict[str, Any]:
        return _extras(
            self._raw,
            frozenset(
                {
                    "name",
                    "version",
                    "mimetype",
                    "file_extension",
                    "codemirror_mode",
                    "pygments_lexer",
                }
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return deepcopy(self._raw)


@dataclass(frozen=True, slots=True)
class AuthorMetadata:
    """One entry of notebook metadata.authors.

    The pinned nbformat 4.2+ schema declares this item's intended shape
    under the non-standard keyword ``item`` rather than JSON Schema's
    ``items``, so a real JSON Schema validator never enforces it; ``name``
    is therefore modeled as optional here too, and every other field is
    preserved via ``extras`` rather than silently dropped.
    """

    name: str | None
    _raw: dict[str, Any]

    @classmethod
    def from_value(cls, value: Any) -> "AuthorMetadata":
        raw = _mapping(value, "author")
        return cls(
            name=_optional_string(raw, "name", "author"),
            _raw=raw,
        )

    @property
    def extras(self) -> dict[str, Any]:
        return _extras(self._raw, frozenset({"name"}))

    def to_dict(self) -> dict[str, Any]:
        return deepcopy(self._raw)


@dataclass(frozen=True, slots=True)
class JupyterCellMetadata:
    """Official Jupyter cell metadata (nbformat 4.3+): source_hidden for
    every known cell type, outputs_hidden for code cells."""

    source_hidden: bool | None
    outputs_hidden: bool | None
    _raw: dict[str, Any]

    @classmethod
    def from_value(cls, value: Any) -> "JupyterCellMetadata":
        raw = _mapping(value, "jupyter")
        return cls(
            source_hidden=_optional_bool(raw, "source_hidden", "jupyter"),
            outputs_hidden=_optional_bool(raw, "outputs_hidden", "jupyter"),
            _raw=raw,
        )

    @property
    def extras(self) -> dict[str, Any]:
        return _extras(
            self._raw,
            frozenset({"source_hidden", "outputs_hidden"}),
        )

    def to_dict(self) -> dict[str, Any]:
        return deepcopy(self._raw)


@dataclass(frozen=True, slots=True)
class SlideshowMetadata:
    slide_type: str | None
    _raw: dict[str, Any]

    @classmethod
    def from_value(cls, value: Any) -> "SlideshowMetadata":
        raw = _mapping(value, "slideshow")
        return cls(
            slide_type=_optional_string(raw, "slide_type", "slideshow"),
            _raw=raw,
        )

    @property
    def extras(self) -> dict[str, Any]:
        return _extras(self._raw, frozenset({"slide_type"}))

    def to_dict(self) -> dict[str, Any]:
        return deepcopy(self._raw)


@dataclass(frozen=True, slots=True)
class ExecutionMetadata:
    _raw: dict[str, Any]

    @classmethod
    def from_value(cls, value: Any) -> "ExecutionMetadata":
        return cls(_mapping(value, "execution"))

    def _timestamp(self, key: str) -> str | None:
        return _optional_string(self._raw, key, "execution")

    @property
    def iopub_status_busy(self) -> str | None:
        return self._timestamp("iopub.status.busy")

    @property
    def iopub_execute_input(self) -> str | None:
        return self._timestamp("iopub.execute_input")

    @property
    def shell_execute_reply(self) -> str | None:
        return self._timestamp("shell.execute_reply")

    @property
    def iopub_status_idle(self) -> str | None:
        return self._timestamp("iopub.status.idle")

    @property
    def extras(self) -> dict[str, Any]:
        return _extras(
            self._raw,
            frozenset(
                {
                    "iopub.status.busy",
                    "iopub.execute_input",
                    "shell.execute_reply",
                    "iopub.status.idle",
                }
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return deepcopy(self._raw)


@dataclass(frozen=True, slots=True)
class MimeRenderingMetadata:
    mime_type: str
    values: dict[str, Any]

    def __post_init__(self) -> None:
        object.__setattr__(self, "values", deepcopy(self.values))

    def to_dict(self) -> dict[str, Any]:
        return deepcopy(self.values)


class NotebookMetadataAdapter:
    __slots__ = ("_raw",)

    def __init__(self, document: NotebookDocument) -> None:
        if not isinstance(document, NotebookDocument):
            raise TypeError("document must be an NotebookDocument")
        self._raw = _mapping(document.raw.get("metadata"), "notebook")

    @property
    def kernelspec(self) -> KernelSpecMetadata | None:
        value = self._raw.get("kernelspec")
        return None if value is None else KernelSpecMetadata.from_value(value)

    @property
    def language_info(self) -> LanguageInfoMetadata | None:
        value = self._raw.get("language_info")
        return None if value is None else LanguageInfoMetadata.from_value(value)

    @property
    def title(self) -> str | None:
        return _optional_string(self._raw, "title", "notebook")

    @property
    def authors(self) -> tuple[AuthorMetadata, ...] | None:
        value = self._raw.get("authors")
        if value is None:
            return None
        if not isinstance(value, list):
            raise MetadataShapeError("notebook.authors must be an array")
        return tuple(AuthorMetadata.from_value(item) for item in value)

    @property
    def extras(self) -> dict[str, Any]:
        return _extras(
            self._raw,
            frozenset({"kernelspec", "language_info", "title", "authors"}),
        )

    def to_dict(self) -> dict[str, Any]:
        return deepcopy(self._raw)


class CellMetadataAdapter:
    __slots__ = ("_raw",)

    def __init__(self, cell: Cell) -> None:
        if not isinstance(cell, Cell):
            raise TypeError("cell must be a Cell")
        self._raw = _mapping(cell.to_dict().get("metadata"), "cell")

    @property
    def tags(self) -> tuple[str, ...]:
        value = self._raw.get("tags")
        if value is None:
            return ()
        if not isinstance(value, list) or not all(
            isinstance(item, str) for item in value
        ):
            raise MetadataShapeError("cell tags must be a string array")
        tags = tuple(value)
        if len(tags) != len(set(tags)):
            raise MetadataShapeError("cell tags must be unique")
        if any("," in tag for tag in tags):
            raise MetadataShapeError("cell tags must not contain commas")
        return tags

    @property
    def slideshow(self) -> SlideshowMetadata | None:
        value = self._raw.get("slideshow")
        return None if value is None else SlideshowMetadata.from_value(value)

    @property
    def execution(self) -> ExecutionMetadata | None:
        value = self._raw.get("execution")
        return None if value is None else ExecutionMetadata.from_value(value)

    @property
    def jupyter(self) -> JupyterCellMetadata | None:
        value = self._raw.get("jupyter")
        return None if value is None else JupyterCellMetadata.from_value(value)

    @property
    def extras(self) -> dict[str, Any]:
        return _extras(
            self._raw,
            frozenset({"tags", "slideshow", "execution", "jupyter"}),
        )

    def to_dict(self) -> dict[str, Any]:
        return deepcopy(self._raw)


class OutputMetadataAdapter:
    __slots__ = ("_raw",)

    def __init__(self, output: NotebookOutput) -> None:
        if not isinstance(output, NotebookOutput):
            raise TypeError("output must be a NotebookOutput")
        self._raw = _mapping(output.to_dict().get("metadata", {}), "output")

    @property
    def mime_types(self) -> tuple[str, ...]:
        return tuple(key for key in self._raw if "/" in key)

    def mime(self, mime_type: str) -> MimeRenderingMetadata | None:
        if not isinstance(mime_type, str) or "/" not in mime_type:
            raise ValueError("mime_type must be a valid MIME type string")
        value = self._raw.get(mime_type)
        if value is None:
            return None
        if not isinstance(value, Mapping):
            raise MetadataShapeError(
                f"output metadata for {mime_type} must be an object"
            )
        return MimeRenderingMetadata(mime_type, deepcopy(dict(value)))

    @property
    def extras(self) -> dict[str, Any]:
        return deepcopy(
            {key: value for key, value in self._raw.items() if "/" not in key}
        )

    def to_dict(self) -> dict[str, Any]:
        return deepcopy(self._raw)


def notebook_metadata(document: NotebookDocument) -> NotebookMetadataAdapter:
    return NotebookMetadataAdapter(document)


def cell_metadata(cell: Cell) -> CellMetadataAdapter:
    return CellMetadataAdapter(cell)


def output_metadata(output: NotebookOutput) -> OutputMetadataAdapter:
    return OutputMetadataAdapter(output)


__all__ = [
    "AuthorMetadata",
    "CellMetadataAdapter",
    "ExecutionMetadata",
    "JupyterCellMetadata",
    "KernelSpecMetadata",
    "LanguageInfoMetadata",
    "MetadataShapeError",
    "MimeRenderingMetadata",
    "NotebookMetadataAdapter",
    "OutputMetadataAdapter",
    "SlideshowMetadata",
    "cell_metadata",
    "notebook_metadata",
    "output_metadata",
]
