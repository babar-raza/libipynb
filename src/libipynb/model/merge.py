"""IPYNB-MERGE-001 -- three-way notebook merge by stable cell identity.

MUST: "Merge by stable cell identity and structure; detect move/edit,
delete/edit, output, and metadata conflicts; produce an explicit conflict
report and never hide conflicts inside executable source."

Built on `diff_notebooks` (model/diff.py), which already does the hard part:
matching cells by their stable `id` across two snapshots, classifying each
changed field, and detecting moves via longest-increasing-subsequence. A
three-way merge is two of those two-way diffs -- base-to-ours and
base-to-theirs -- reconciled cell by cell:

* unchanged on both sides -> base's cell, untouched;
* changed on exactly one side -> that side's cell;
* changed identically on both sides -> either side's cell, no conflict;
* changed differently on both sides -> a conflict, classified into one of
  the four named categories, and the base's original value is kept for
  that field pending resolution -- NEVER either side's conflicting value,
  and never a textual conflict marker spliced into `source`. Embedding
  "<<<<<<< ours" style markers into a code cell's source would silently
  turn a merge conflict into a syntax error at best and a foreign string
  literal at worst; the obligation's own "never hide conflicts inside
  executable source" is read here as an outright prohibition on marker
  splicing, not merely a caution.

Scope boundary, stated explicitly rather than silently assumed: this
reconciles CELLS only. All four named conflict categories (move/edit,
delete/edit, output, metadata) are cell-scoped in the obligation's own
phrasing. Notebook-level fields (kernelspec, language_info, nbformat) are
taken from `base` unchanged in the merge result -- top-level metadata
merging is a different, unbuilt capability, not silently folded into this
one.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from enum import Enum
from typing import Any

from .diff import CellChange, CellField, DiffPolicy, diff_notebooks
from .document import NotebookDocument


class ConflictKind(str, Enum):
    MOVE_EDIT = "move_edit"
    DELETE_EDIT = "delete_edit"
    EDIT_EDIT = "edit_edit"
    OUTPUT = "output"
    METADATA = "metadata"


@dataclass(frozen=True, slots=True)
class CellConflict:
    """One point of genuine divergence between `ours` and `theirs`."""

    cell_id: str
    kind: ConflictKind
    field_name: str | None
    ours_value: Any
    theirs_value: Any
    description: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "ours_value", deepcopy(self.ours_value))
        object.__setattr__(self, "theirs_value", deepcopy(self.theirs_value))


@dataclass(frozen=True, slots=True)
class MergeReport:
    conflicts: tuple[CellConflict, ...]

    @property
    def has_conflicts(self) -> bool:
        return bool(self.conflicts)

    def conflicts_of(self, kind: ConflictKind) -> tuple[CellConflict, ...]:
        return tuple(conflict for conflict in self.conflicts if conflict.kind is kind)


@dataclass(frozen=True, slots=True)
class MergeResult:
    """The best-effort merged document plus what it could not resolve.

    `merged` always exists (never None): every field this report does not
    flag as conflicted is a real, uncontested reconciliation. A caller must
    check `report.has_conflicts` before treating `merged` as final -- an
    unresolved field keeps its `base` value, which is a safe placeholder,
    not an implicit resolution.
    """

    merged: NotebookDocument
    report: MergeReport


def _cell_map(document: NotebookDocument) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for cell in document.cells:
        cell_id = cell.get("id")
        if isinstance(cell_id, str) and cell_id:
            result[cell_id] = cell
    return result


def _ordered_ids(*documents: NotebookDocument) -> list[str]:
    """A deterministic id order: `ours`' final order first (the merge's
    structural reference), then any id only `theirs` or `base` still has,
    in their own order. Ambiguous relative-order questions between `ours`
    and `theirs` are exactly the MOVE_EDIT conflicts this module detects
    elsewhere; this function only has to be deterministic, not "correct" in
    a sense the obligation does not define."""
    seen: set[str] = set()
    order: list[str] = []
    for document in documents:
        for cell in document.cells:
            cell_id = cell.get("id")
            if isinstance(cell_id, str) and cell_id and cell_id not in seen:
                seen.add(cell_id)
                order.append(cell_id)
    return order


def _apply_field(cell: dict[str, Any], key: str, after: Any, after_present: bool) -> None:
    if after_present:
        cell[key] = deepcopy(after)
    else:
        cell.pop(key, None)


def _conflict_kind_for_field(field: CellField) -> ConflictKind:
    if field is CellField.OUTPUTS:
        return ConflictKind.OUTPUT
    if field is CellField.METADATA:
        return ConflictKind.METADATA
    return ConflictKind.EDIT_EDIT


def _reconcile_present_cell(
    cell_id: str,
    base_cell: dict[str, Any],
    ours_change: CellChange,
    theirs_change: CellChange,
    conflicts: list[CellConflict],
) -> dict[str, Any]:
    merged_cell = deepcopy(base_cell)

    ours_fields = {fc.path[0]: fc for fc in ours_change.field_changes}
    theirs_fields = {fc.path[0]: fc for fc in theirs_change.field_changes}

    for key in sorted(set(ours_fields) | set(theirs_fields)):
        ours_fc = ours_fields.get(key)
        theirs_fc = theirs_fields.get(key)
        if ours_fc is not None and theirs_fc is not None:
            if ours_fc.after == theirs_fc.after and ours_fc.after_present == theirs_fc.after_present:
                _apply_field(merged_cell, key, ours_fc.after, ours_fc.after_present)
                continue
            conflicts.append(
                CellConflict(
                    cell_id=cell_id,
                    kind=_conflict_kind_for_field(ours_fc.field),
                    field_name=key,
                    ours_value=ours_fc.after if ours_fc.after_present else None,
                    theirs_value=theirs_fc.after if theirs_fc.after_present else None,
                    description=(
                        f"cell {cell_id!r} field {key!r} changed differently on "
                        "each side"
                    ),
                )
            )
            # Base's own value stands for a conflicted field -- never one
            # side's value chosen silently, never a marker spliced in.
        elif ours_fc is not None:
            _apply_field(merged_cell, key, ours_fc.after, ours_fc.after_present)
        else:
            assert theirs_fc is not None
            _apply_field(merged_cell, key, theirs_fc.after, theirs_fc.after_present)

    only_ours_moved = ours_change.moved and not ours_change.modified
    only_theirs_moved = theirs_change.moved and not theirs_change.modified
    if (only_ours_moved and theirs_change.modified) or (
        only_theirs_moved and ours_change.modified
    ):
        conflicts.append(
            CellConflict(
                cell_id=cell_id,
                kind=ConflictKind.MOVE_EDIT,
                field_name=None,
                ours_value=ours_change.after_index,
                theirs_value=theirs_change.after_index,
                description=(
                    f"cell {cell_id!r} was moved on one side and edited on the "
                    "other"
                ),
            )
        )

    return merged_cell


def merge_notebooks(
    base: NotebookDocument,
    ours: NotebookDocument,
    theirs: NotebookDocument,
    *,
    policy: DiffPolicy | None = None,
) -> MergeResult:
    """Three-way merge `ours` and `theirs` against their common `base`."""
    for name, document in (("base", base), ("ours", ours), ("theirs", theirs)):
        if not isinstance(document, NotebookDocument):
            raise TypeError(f"{name} must be an NotebookDocument")

    selected_policy = policy or DiffPolicy()
    ours_diff = diff_notebooks(base, ours, policy=selected_policy)
    theirs_diff = diff_notebooks(base, theirs, policy=selected_policy)

    ours_changes = {change.cell_id: change for change in ours_diff.cell_changes}
    theirs_changes = {change.cell_id: change for change in theirs_diff.cell_changes}

    base_cells = _cell_map(base)
    ours_cells = _cell_map(ours)
    theirs_cells = _cell_map(theirs)

    conflicts: list[CellConflict] = []
    merged_by_id: dict[str, dict[str, Any]] = {}

    for cell_id in _ordered_ids(ours, theirs, base):
        ours_change = ours_changes.get(cell_id)
        theirs_change = theirs_changes.get(cell_id)

        if ours_change is None and theirs_change is None:
            merged_by_id[cell_id] = deepcopy(base_cells[cell_id])
            continue

        if ours_change is None:
            assert theirs_change is not None  # ruled out by the check above
            if not theirs_change.removed:
                merged_by_id[cell_id] = deepcopy(theirs_cells[cell_id])
            continue

        if theirs_change is None:
            if not ours_change.removed:
                merged_by_id[cell_id] = deepcopy(ours_cells[cell_id])
            continue

        if ours_change.removed and theirs_change.removed:
            continue

        if ours_change.removed or theirs_change.removed:
            surviving = theirs_change if ours_change.removed else ours_change
            if surviving.modified or surviving.moved:
                surviving_cell = theirs_cells if ours_change.removed else ours_cells
                conflicts.append(
                    CellConflict(
                        cell_id=cell_id,
                        kind=ConflictKind.DELETE_EDIT,
                        field_name=None,
                        ours_value=None if ours_change.removed else surviving_cell[cell_id],
                        theirs_value=None if theirs_change.removed else surviving_cell[cell_id],
                        description=(
                            f"cell {cell_id!r} was deleted on one side and "
                            "changed on the other"
                        ),
                    )
                )
                merged_by_id[cell_id] = deepcopy(base_cells[cell_id])
            # else: an unmodified cell deleted on one side -- deletion wins,
            # no conflict.
            continue

        merged_by_id[cell_id] = _reconcile_present_cell(
            cell_id, base_cells[cell_id], ours_change, theirs_change, conflicts
        )

    merged_cells = [
        merged_by_id[cell_id]
        for cell_id in _ordered_ids(ours, theirs, base)
        if cell_id in merged_by_id
    ]
    merged_raw = deepcopy(base.raw)
    merged_raw["cells"] = merged_cells
    merged_document = NotebookDocument(
        merged_raw,
        declared_version=base.declared_version,
        detected_version=base.detected_version,
    )
    return MergeResult(merged=merged_document, report=MergeReport(conflicts=tuple(conflicts)))


__all__ = [
    "CellConflict",
    "ConflictKind",
    "MergeReport",
    "MergeResult",
    "merge_notebooks",
]
