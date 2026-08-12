"""Reference-safe attachment mutations with deterministic reports."""

from __future__ import annotations

import re
from copy import deepcopy
from dataclasses import dataclass
from enum import Enum
from typing import Any
from urllib.parse import quote, unquote

from .document import NotebookDocument

_ATTACHMENT_REFERENCE = re.compile(r"attachment:([^\s)\]}>\"']+)")


class AttachmentReferencePolicy(str, Enum):
    REFUSE = "refuse"
    LEAVE_DANGLING = "leave_dangling"


@dataclass(frozen=True, slots=True)
class AttachmentChange:
    operation: str
    path: tuple[str | int, ...]
    before: Any
    after: Any
    references: int
    dangling_references: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "before", deepcopy(self.before))
        object.__setattr__(self, "after", deepcopy(self.after))


@dataclass(frozen=True, slots=True)
class AttachmentReport:
    changes: tuple[AttachmentChange, ...]
    would_change: bool
    applied: bool

    @property
    def count(self) -> int:
        return len(self.changes)


def _json_value(value: object) -> bool:
    if value is None or isinstance(value, (str, int, float, bool)):
        return True
    if isinstance(value, list):
        return all(_json_value(item) for item in value)
    if isinstance(value, dict):
        return all(isinstance(key, str) and _json_value(item) for key, item in value.items())
    return False


def _validate_name(name: str) -> None:
    if not isinstance(name, str) or not name:
        raise ValueError("attachment name must be a non-empty string")
    if any(ord(character) < 32 or ord(character) == 127 for character in name):
        raise ValueError("attachment name must not contain control characters")


def _validate_bundle(bundle: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(bundle, dict) or not bundle:
        raise ValueError("attachment MIME bundle must be a non-empty object")
    for media_type, payload in bundle.items():
        if not isinstance(media_type, str) or not media_type or "/" not in media_type:
            raise ValueError(f"invalid attachment MIME type: {media_type!r}")
        if not _json_value(payload):
            raise ValueError(f"attachment MIME payload for {media_type!r} is not JSON-compatible")
    return deepcopy(bundle)


def _source_text(cell: dict[str, Any]) -> str:
    source = cell.get("source", "")
    if isinstance(source, str):
        return source
    if isinstance(source, list) and all(isinstance(item, str) for item in source):
        return "".join(source)
    raise TypeError("cell source must be a string or string array")


def _reference_count(cell: dict[str, Any], name: str) -> int:
    return sum(
        1
        for encoded in _ATTACHMENT_REFERENCE.findall(_source_text(cell))
        if unquote(encoded) == name
    )


def _rewrite_references(
    cell: dict[str, Any],
    old_name: str,
    new_name: str,
) -> int:
    source = cell.get("source", "")
    text = _source_text(cell)
    encoded_new = quote(new_name, safe="._~-")
    replacements = 0

    def replace(match: re.Match[str]) -> str:
        nonlocal replacements
        if unquote(match.group(1)) != old_name:
            return match.group(0)
        replacements += 1
        return f"attachment:{encoded_new}"

    rewritten = _ATTACHMENT_REFERENCE.sub(replace, text)
    if replacements == 0:
        return 0
    if isinstance(source, str):
        cell["source"] = rewritten
        return replacements

    lengths = [len(item) for item in source]
    segments: list[str] = []
    offset = 0
    for length in lengths[:-1]:
        segments.append(rewritten[offset : offset + length])
        offset += length
    segments.append(rewritten[offset:])
    cell["source"] = segments
    return replacements


def _cell(
    root: dict[str, Any],
    cell_id: str,
) -> tuple[int, dict[str, Any]]:
    if not isinstance(cell_id, str) or not cell_id:
        raise ValueError("cell_id must be a non-empty string")
    cells = root.get("cells")
    if not isinstance(cells, list):
        raise TypeError("notebook cells must be an array")
    matches = [
        (index, item)
        for index, item in enumerate(cells)
        if isinstance(item, dict) and item.get("id") == cell_id
    ]
    if not matches:
        raise KeyError(f"cell ID not found: {cell_id}")
    if len(matches) > 1:
        raise ValueError(f"cell ID is not unique: {cell_id}")
    index, selected = matches[0]
    if selected.get("cell_type") not in {"markdown", "raw"}:
        raise ValueError("attachments are supported only on markdown or raw cells")
    return index, selected


def _attachments(cell: dict[str, Any]) -> dict[str, Any]:
    value = cell.get("attachments")
    if value is None:
        value = {}
        cell["attachments"] = value
    if not isinstance(value, dict):
        raise TypeError("cell attachments must be an object")
    return value


class AttachmentManager:
    """Attachment CRUD bound to stable cell IDs."""

    def __init__(self, document: NotebookDocument) -> None:
        if not isinstance(document, NotebookDocument):
            raise TypeError("document must be an NotebookDocument")
        self.document = document

    def add(
        self,
        cell_id: str,
        name: str,
        bundle: dict[str, Any],
        *,
        replace: bool = False,
        dry_run: bool = False,
    ) -> AttachmentReport:
        _validate_name(name)
        validated = _validate_bundle(bundle)
        target = deepcopy(self.document.raw)
        index, cell = _cell(target, cell_id)
        values = _attachments(cell)
        before = deepcopy(values.get(name))
        if name in values and not replace:
            raise ValueError(f"attachment already exists: {name}")
        if before == validated:
            return AttachmentReport((), False, False)
        values[name] = validated
        change = AttachmentChange(
            "add" if before is None else "replace",
            ("cells", index, "attachments", name),
            before,
            validated,
            _reference_count(cell, name),
            0,
        )
        return self._finish(target, change, dry_run=dry_run)

    def remove(
        self,
        cell_id: str,
        name: str,
        *,
        reference_policy: AttachmentReferencePolicy = (AttachmentReferencePolicy.REFUSE),
        dry_run: bool = False,
    ) -> AttachmentReport:
        _validate_name(name)
        if not isinstance(reference_policy, AttachmentReferencePolicy):
            raise TypeError("reference_policy must be an AttachmentReferencePolicy")
        target = deepcopy(self.document.raw)
        index, cell = _cell(target, cell_id)
        values = _attachments(cell)
        if name not in values:
            raise KeyError(name)
        references = _reference_count(cell, name)
        if references and reference_policy is AttachmentReferencePolicy.REFUSE:
            raise ValueError(f"attachment {name!r} is still referenced {references} time(s)")
        before = deepcopy(values[name])
        del values[name]
        change = AttachmentChange(
            "remove",
            ("cells", index, "attachments", name),
            before,
            None,
            references,
            references,
        )
        return self._finish(target, change, dry_run=dry_run)

    def rename(
        self,
        cell_id: str,
        old_name: str,
        new_name: str,
        *,
        rewrite_references: bool = True,
        dry_run: bool = False,
    ) -> AttachmentReport:
        _validate_name(old_name)
        _validate_name(new_name)
        target = deepcopy(self.document.raw)
        index, cell = _cell(target, cell_id)
        values = _attachments(cell)
        if old_name not in values:
            raise KeyError(old_name)
        if new_name in values and new_name != old_name:
            raise ValueError(f"attachment already exists: {new_name}")
        if old_name == new_name:
            return AttachmentReport((), False, False)

        bundle = deepcopy(values[old_name])
        reordered = {
            (new_name if name == old_name else name): value for name, value in values.items()
        }
        values.clear()
        values.update(reordered)
        references = _reference_count(cell, old_name)
        rewritten = _rewrite_references(cell, old_name, new_name) if rewrite_references else 0
        change = AttachmentChange(
            "rename",
            ("cells", index, "attachments", old_name),
            {old_name: bundle},
            {new_name: bundle},
            references,
            references - rewritten,
        )
        return self._finish(target, change, dry_run=dry_run)

    def _finish(
        self,
        target: dict[str, Any],
        change: AttachmentChange,
        *,
        dry_run: bool,
    ) -> AttachmentReport:
        if not dry_run:
            self.document.raw.clear()
            self.document.raw.update(target)
        return AttachmentReport((change,), True, not dry_run)


def manage_attachments(document: NotebookDocument) -> AttachmentManager:
    return AttachmentManager(document)


__all__ = [
    "AttachmentChange",
    "AttachmentManager",
    "AttachmentReferencePolicy",
    "AttachmentReport",
    "manage_attachments",
]
