"""Stable-identity notebook diffing and preconditioned patch application."""

from __future__ import annotations

import hashlib
import json
from bisect import bisect_left
from copy import deepcopy
from dataclasses import dataclass
from enum import Enum
from typing import Any

from .document import NotebookDocument


class CellField(str, Enum):
    CELL_TYPE = "cell_type"
    SOURCE = "source"
    METADATA = "metadata"
    ATTACHMENTS = "attachments"
    EXECUTION_COUNT = "execution_count"
    OUTPUTS = "outputs"
    OTHER = "other"


class PatchPreconditionError(ValueError):
    """Raised when a patch is applied to a different logical base."""


@dataclass(frozen=True, slots=True)
class DiffPolicy:
    """Fields excluded from comparison and preserved from the patch base."""

    ignore_outputs: bool = False
    ignore_execution_counts: bool = False
    ignored_metadata_keys: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.ignore_outputs, bool):
            raise TypeError("ignore_outputs must be a bool")
        if not isinstance(self.ignore_execution_counts, bool):
            raise TypeError("ignore_execution_counts must be a bool")
        if not isinstance(self.ignored_metadata_keys, tuple):
            raise TypeError("ignored_metadata_keys must be a tuple")
        for key in self.ignored_metadata_keys:
            if not isinstance(key, str) or not key:
                raise ValueError("ignored_metadata_keys must contain non-empty strings")
        object.__setattr__(
            self,
            "ignored_metadata_keys",
            tuple(sorted(set(self.ignored_metadata_keys))),
        )


@dataclass(frozen=True, slots=True)
class FieldChange:
    field: CellField
    path: tuple[str, ...]
    before: Any
    after: Any
    before_present: bool = True
    after_present: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "before", deepcopy(self.before))
        object.__setattr__(self, "after", deepcopy(self.after))


@dataclass(frozen=True, slots=True)
class NotebookFieldChange:
    path: tuple[str, ...]
    before: Any
    after: Any
    before_present: bool = True
    after_present: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "before", deepcopy(self.before))
        object.__setattr__(self, "after", deepcopy(self.after))


@dataclass(frozen=True, slots=True)
class CellChange:
    cell_id: str
    before_index: int | None
    after_index: int | None
    moved: bool = False
    field_changes: tuple[FieldChange, ...] = ()

    @property
    def added(self) -> bool:
        return self.before_index is None

    @property
    def removed(self) -> bool:
        return self.after_index is None

    @property
    def modified(self) -> bool:
        return bool(self.field_changes)


@dataclass(frozen=True, slots=True)
class NotebookPatch:
    """A complete target snapshot guarded by a policy-aware base digest."""

    base_fingerprint: str
    policy: DiffPolicy
    _target_snapshot: dict[str, Any]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "_target_snapshot",
            deepcopy(self._target_snapshot),
        )

    @property
    def target_snapshot(self) -> dict[str, Any]:
        return deepcopy(self._target_snapshot)

    def apply(
        self,
        document: NotebookDocument,
    ) -> NotebookDocument:
        """Apply atomically after checking the logical-base precondition."""
        if not isinstance(document, NotebookDocument):
            raise TypeError("document must be an NotebookDocument")
        actual = _fingerprint(document.raw, self.policy)
        if actual != self.base_fingerprint:
            raise PatchPreconditionError(
                "notebook patch precondition failed: "
                f"expected {self.base_fingerprint}, got {actual}"
            )

        target = deepcopy(self._target_snapshot)
        _restore_ignored_values(document.raw, target, self.policy)
        return NotebookDocument(target)


@dataclass(frozen=True, slots=True)
class NotebookDiff:
    """Deterministic structural changes plus an applicable patch target."""

    base_fingerprint: str
    policy: DiffPolicy
    notebook_changes: tuple[NotebookFieldChange, ...]
    cell_changes: tuple[CellChange, ...]
    _target_snapshot: dict[str, Any]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "_target_snapshot",
            deepcopy(self._target_snapshot),
        )

    @property
    def has_changes(self) -> bool:
        return bool(self.notebook_changes or self.cell_changes)

    def to_patch(self) -> NotebookPatch:
        return NotebookPatch(
            base_fingerprint=self.base_fingerprint,
            policy=self.policy,
            _target_snapshot=self._target_snapshot,
        )


def _canonical_bytes(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ValueError("notebook diff requires JSON-compatible finite values") from exc


def _strip_named_key(value: Any, key: str) -> None:
    if isinstance(value, dict):
        value.pop(key, None)
        for child in value.values():
            _strip_named_key(child, key)
    elif isinstance(value, list):
        for child in value:
            _strip_named_key(child, key)


def _strip_metadata_keys(value: Any, ignored: frozenset[str]) -> None:
    if isinstance(value, dict):
        metadata = value.get("metadata")
        if isinstance(metadata, dict):
            for key in ignored:
                metadata.pop(key, None)
            _strip_metadata_keys(metadata, ignored)
        for key, child in value.items():
            if key != "metadata":
                _strip_metadata_keys(child, ignored)
    elif isinstance(value, list):
        for child in value:
            _strip_metadata_keys(child, ignored)


def _projection(
    raw: dict[str, Any],
    policy: DiffPolicy,
) -> dict[str, Any]:
    projected = deepcopy(raw)
    cells = projected.get("cells")
    if isinstance(cells, list) and policy.ignore_outputs:
        for cell in cells:
            if isinstance(cell, dict):
                cell.pop("outputs", None)
    if policy.ignore_execution_counts:
        _strip_named_key(projected, "execution_count")
    if policy.ignored_metadata_keys:
        _strip_metadata_keys(
            projected,
            frozenset(policy.ignored_metadata_keys),
        )
    return projected


def _fingerprint(raw: dict[str, Any], policy: DiffPolicy) -> str:
    return hashlib.sha256(_canonical_bytes(_projection(raw, policy))).hexdigest()


def _cell_index(
    raw: dict[str, Any],
) -> tuple[list[str], dict[str, tuple[int, dict[str, Any]]]]:
    cells = raw.get("cells")
    if not isinstance(cells, list):
        raise TypeError("notebook cells must be an array")
    order: list[str] = []
    index: dict[str, tuple[int, dict[str, Any]]] = {}
    for position, value in enumerate(cells):
        if not isinstance(value, dict):
            raise TypeError(f"cell at index {position} must be an object")
        cell_id = value.get("id")
        if not isinstance(cell_id, str) or not cell_id:
            raise ValueError(f"cell at index {position} is missing a stable non-empty ID")
        if cell_id in index:
            raise ValueError(f"cell IDs must be unique: {cell_id}")
        order.append(cell_id)
        index[cell_id] = (position, value)
    return order, index


def _cell_field(name: str) -> CellField:
    try:
        return CellField(name)
    except ValueError:
        return CellField.OTHER


def _field_changes(
    before: dict[str, Any],
    after: dict[str, Any],
) -> tuple[FieldChange, ...]:
    missing = object()
    changes: list[FieldChange] = []
    for key in sorted(set(before) | set(after)):
        if key == "id":
            continue
        left = before.get(key, missing)
        right = after.get(key, missing)
        if left != right:
            changes.append(
                FieldChange(
                    field=_cell_field(key),
                    path=(key,),
                    before=None if left is missing else left,
                    after=None if right is missing else right,
                    before_present=left is not missing,
                    after_present=right is not missing,
                )
            )
    return tuple(changes)


def _notebook_changes(
    before: dict[str, Any],
    after: dict[str, Any],
) -> tuple[NotebookFieldChange, ...]:
    missing = object()
    changes: list[NotebookFieldChange] = []
    for key in sorted((set(before) | set(after)) - {"cells"}):
        left = before.get(key, missing)
        right = after.get(key, missing)
        if left != right:
            changes.append(
                NotebookFieldChange(
                    path=(key,),
                    before=None if left is missing else left,
                    after=None if right is missing else right,
                    before_present=left is not missing,
                    after_present=right is not missing,
                )
            )
    return tuple(changes)


def _restore_execution_counts(
    current: dict[str, Any],
    target: dict[str, Any],
) -> None:
    if "execution_count" in current:
        target["execution_count"] = deepcopy(current["execution_count"])
    else:
        target.pop("execution_count", None)
    current_outputs = current.get("outputs")
    target_outputs = target.get("outputs")
    if not isinstance(current_outputs, list) or not isinstance(target_outputs, list):
        return
    for left, right in zip(current_outputs, target_outputs):
        if (
            isinstance(left, dict)
            and isinstance(right, dict)
            and left.get("output_type") == right.get("output_type")
        ):
            if "execution_count" in left:
                right["execution_count"] = deepcopy(left["execution_count"])
            else:
                right.pop("execution_count", None)


def _restore_metadata(
    current: Any,
    target: Any,
    ignored: frozenset[str],
) -> None:
    if not isinstance(current, dict) or not isinstance(target, dict):
        return
    for key in ignored:
        if key in current:
            target[key] = deepcopy(current[key])
        else:
            target.pop(key, None)
    for key in (set(current) & set(target)) - ignored:
        left = current[key]
        right = target[key]
        if isinstance(left, dict) and isinstance(right, dict):
            _restore_metadata(left, right, ignored)
        elif isinstance(left, list) and isinstance(right, list):
            for left_item, right_item in zip(left, right):
                _restore_metadata(left_item, right_item, ignored)


def _restore_metadata_tree(
    current: Any,
    target: Any,
    ignored: frozenset[str],
) -> None:
    if isinstance(current, dict) and isinstance(target, dict):
        left_metadata = current.get("metadata")
        right_metadata = target.get("metadata")
        if isinstance(left_metadata, dict) and isinstance(right_metadata, dict):
            _restore_metadata(left_metadata, right_metadata, ignored)
        for key in set(current) & set(target):
            if key != "metadata":
                _restore_metadata_tree(current[key], target[key], ignored)
    elif isinstance(current, list) and isinstance(target, list):
        for left, right in zip(current, target):
            _restore_metadata_tree(left, right, ignored)


def _restore_ignored_values(
    current: dict[str, Any],
    target: dict[str, Any],
    policy: DiffPolicy,
) -> None:
    _, current_cells = _cell_index(current)
    _, target_cells = _cell_index(target)

    if policy.ignored_metadata_keys:
        ignored = frozenset(policy.ignored_metadata_keys)
        current_metadata = current.get("metadata")
        target_metadata = target.get("metadata")
        if isinstance(current_metadata, dict) and isinstance(target_metadata, dict):
            _restore_metadata(current_metadata, target_metadata, ignored)
    else:
        ignored = frozenset()

    for cell_id in set(current_cells) & set(target_cells):
        left = current_cells[cell_id][1]
        right = target_cells[cell_id][1]
        if left.get("cell_type") != right.get("cell_type"):
            continue
        if policy.ignore_outputs:
            if "outputs" in left:
                right["outputs"] = deepcopy(left["outputs"])
            else:
                right.pop("outputs", None)
        if policy.ignore_execution_counts:
            _restore_execution_counts(left, right)
        if ignored:
            _restore_metadata_tree(left, right, ignored)


def _moved_cell_ids(
    left_order: list[str],
    right_order: list[str],
) -> set[str]:
    """Return the minimum deterministic set outside the common subsequence."""
    right_positions = {cell_id: position for position, cell_id in enumerate(right_order)}
    common_left = [cell_id for cell_id in left_order if cell_id in right_positions]
    if not common_left:
        return set()

    sequence = [right_positions[cell_id] for cell_id in common_left]
    tail_values: list[int] = []
    tail_indices: list[int] = []
    predecessors = [-1] * len(sequence)
    for index, value in enumerate(sequence):
        position = bisect_left(tail_values, value)
        if position:
            predecessors[index] = tail_indices[position - 1]
        if position == len(tail_values):
            tail_values.append(value)
            tail_indices.append(index)
        else:
            tail_values[position] = value
            tail_indices[position] = index

    retained: set[str] = set()
    cursor = tail_indices[-1]
    while cursor >= 0:
        retained.add(common_left[cursor])
        cursor = predecessors[cursor]
    return set(common_left) - retained


def diff_notebooks(
    before: NotebookDocument,
    after: NotebookDocument,
    *,
    policy: DiffPolicy | None = None,
) -> NotebookDiff:
    """Compare notebooks by cell ID and build a preconditioned patch."""
    if not isinstance(before, NotebookDocument):
        raise TypeError("before must be an NotebookDocument")
    if not isinstance(after, NotebookDocument):
        raise TypeError("after must be an NotebookDocument")
    selected_policy = policy or DiffPolicy()
    if not isinstance(selected_policy, DiffPolicy):
        raise TypeError("policy must be a DiffPolicy")

    _canonical_bytes(before.raw)
    _canonical_bytes(after.raw)
    left = _projection(before.raw, selected_policy)
    right = _projection(after.raw, selected_policy)
    left_order, left_index = _cell_index(left)
    right_order, right_index = _cell_index(right)
    moved_ids = _moved_cell_ids(left_order, right_order)

    cell_changes: list[CellChange] = []
    for cell_id in right_order + [value for value in left_order if value not in right_index]:
        left_item = left_index.get(cell_id)
        right_item = right_index.get(cell_id)
        before_index = left_item[0] if left_item is not None else None
        after_index = right_item[0] if right_item is not None else None
        fields = (
            _field_changes(left_item[1], right_item[1])
            if left_item is not None and right_item is not None
            else ()
        )
        change = CellChange(
            cell_id=cell_id,
            before_index=before_index,
            after_index=after_index,
            moved=cell_id in moved_ids,
            field_changes=fields,
        )
        if change.added or change.removed or change.moved or change.modified:
            cell_changes.append(change)

    return NotebookDiff(
        base_fingerprint=hashlib.sha256(_canonical_bytes(left)).hexdigest(),
        policy=selected_policy,
        notebook_changes=_notebook_changes(left, right),
        cell_changes=tuple(cell_changes),
        _target_snapshot=after.raw,
    )


__all__ = [
    "CellChange",
    "CellField",
    "DiffPolicy",
    "FieldChange",
    "NotebookDiff",
    "NotebookFieldChange",
    "NotebookPatch",
    "PatchPreconditionError",
    "diff_notebooks",
]
