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

import difflib
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
    #: LIBIPYNB-Q10: a notebook-level (not cell-scoped) metadata path that
    #: diverged differently on ours/theirs relative to base -- see
    #: _reconcile_notebook_metadata(). Previously such a divergence
    #: resolved silently to base's value with has_conflicts=False and zero
    #: signal anywhere.
    NOTEBOOK_METADATA = "notebook_metadata"


@dataclass(frozen=True, slots=True)
class CellConflict:
    """One point of genuine divergence between `ours` and `theirs`.

    ``cell_id`` is ``None`` for a :attr:`ConflictKind.NOTEBOOK_METADATA`
    conflict -- that category is not scoped to any single cell."""

    cell_id: str | None
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


def _synthesized_copy(document: NotebookDocument) -> NotebookDocument:
    """LIBIPYNB-Q3: an internal-use-only copy whose cells all carry stable
    ids, synthesized via the same content-hash algorithm
    ``diff_notebooks()`` already applies internally (``model.diff.
    _with_stable_cell_ids``) -- applied independently but consistently to
    base/ours/theirs, so a cell unchanged across all three gets the
    identical synthesized id in each (pure function of cell content).
    Never mutates or is derived from anything but a deep copy of the
    caller's original document."""
    from .diff import _with_stable_cell_ids

    raw = _with_stable_cell_ids(deepcopy(document.raw))
    return NotebookDocument(
        raw,
        declared_version=document.declared_version,
        detected_version=document.detected_version,
    )


def _cell_map(
    original: NotebookDocument, synthesized: NotebookDocument
) -> dict[str, dict[str, Any]]:
    """Map each (possibly synthesized) id to the cell dict from the
    ORIGINAL, unsynthesized document at the same position. A synthesized id
    is used only to LOCATE cells during reconciliation -- it is never
    written into merge output (see ``merge_notebooks``, which always
    ``deepcopy``s from these original cell dicts), so a pre-4.5 notebook's
    merged cells stay id-less exactly as before this fix."""
    result: dict[str, dict[str, Any]] = {}
    for original_cell, synthesized_cell in zip(original.cells, synthesized.cells):
        cell_id = synthesized_cell.get("id")
        if isinstance(cell_id, str) and cell_id:
            result[cell_id] = original_cell
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
            if (
                ours_fc.after == theirs_fc.after
                and ours_fc.after_present == theirs_fc.after_present
            ):
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
                        f"cell {cell_id!r} field {key!r} changed differently on each side"
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
    if (only_ours_moved and theirs_change.modified) or (only_theirs_moved and ours_change.modified):
        conflicts.append(
            CellConflict(
                cell_id=cell_id,
                kind=ConflictKind.MOVE_EDIT,
                field_name=None,
                ours_value=ours_change.after_index,
                theirs_value=theirs_change.after_index,
                description=(f"cell {cell_id!r} was moved on one side and edited on the other"),
            )
        )

    return merged_cell


def _find_same_position_replacement_id(
    base_ids: list[str], side_ids: list[str], removed_id: str
) -> str | None:
    """Finds the id in `side_ids` that is a genuine, UNAMBIGUOUS substitution
    for `removed_id` in `base_ids`, using a proper sequence alignment
    (`difflib.SequenceMatcher`) between the two id lists rather than raw
    index comparison. Deliberately conservative: returns a match only when
    there is exactly one possible candidate, never a "best guess" among
    several -- see the design-history note below for why guessing was tried
    and rejected as unsafe.

    LIBIPYNB-Q3 Gate G2 finding #1: an earlier version of this correlation
    compared `added_change.after_index == removed_change.before_index`
    directly -- which silently breaks the moment ANY other cell is also
    added/removed on the same side near this position, because that shifts
    every later index. Concretely: `base=[A, B]`, `ours=[new, A_edited,
    B]` -- `A`'s removal has `before_index=0`; naive index matching finds
    `new` (`after_index=0`), not `A_edited` (`after_index=1`), as the
    "replacement" -- picking an entirely unrelated cell, then silently
    dropping the real `new` cell from the merge output while letting the
    real edit through completely unconflicted.

    `SequenceMatcher`'s LCS-based alignment does not have this flaw: it
    naturally anchors on the surrounding *unchanged* ids (`B` in the
    example above) and only reports a change opcode for the span that is
    genuinely NOT shared between the two sequences -- regardless of
    unrelated insertions elsewhere. Every unique-id list (ids here are
    always unique per document, content-hash collisions included, per
    `codec.reader.ensure_cell_id`'s own collision-counter scheme) is safe
    to align this way.

    Design history, Gate G2 finding #2 (why this function does NOT attempt
    content-similarity disambiguation): `SequenceMatcher` does not always
    separate an adjacent insertion from a 1:1 replace into two opcodes --
    `base=[A, B]`, `ours=[new, A_edited, B]` produces one combined
    `('replace', 0, 1, 0, 2)` block (both `new` and `A_edited`), not an
    `insert` + `replace` pair. A first attempt at this function resolved
    such multi-candidate blocks by picking whichever candidate's own
    source text was most textually similar to the removed cell's. A
    second, separate independent review broke that: it constructed a
    genuinely new, UNRELATED inserted cell (e.g. a plausible extra
    `import` line) that happened to resemble the base cell's original
    content MORE than a substantially-rewritten TRUE edit did -- the
    similarity heuristic then confidently picked the unrelated cell as
    "the replacement," which silently dropped that unrelated cell from
    the merge output (real cell loss) and reported the wrong content in
    the resulting conflict. That is strictly worse than declining: a
    decline falls back to the well-understood, already-accepted baseline
    behavior below (both sides' real content is kept, uncontested, just
    without a conflict flagged) -- it never fabricates a plausible-looking
    but wrong answer. Given a choice between "sometimes misses a
    conflict" and "sometimes reports wrong data or loses a cell," this
    function is intentionally scoped to the former: it only ever resolves
    a case with literally one possible candidate, where no judgment call
    -- and therefore no way to be wrong -- is involved.

    Known, accepted limitation (this is the caller's own fallback, not a
    bug): any block with more than one base cell, or more than one side
    candidate, declines (returns None) and is handled by the ordinary
    delete+add path -- for an id-less cell edited differently on both
    sides in such a block, this means the divergent edits are kept
    side-by-side with no conflict flagged, the same "silent duplication"
    limitation id-less content-identity always had before this function
    existed. No data is ever lost and no wrong value is ever reported --
    only detection completeness is what varies.
    """
    try:
        removed_index = base_ids.index(removed_id)
    except ValueError:
        return None

    matcher = difflib.SequenceMatcher(a=base_ids, b=side_ids, autojunk=False)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if not (i1 <= removed_index < i2):
            continue
        if tag == "replace" and (i2 - i1) == 1 and (j2 - j1) == 1:
            return side_ids[j1]
        return None
    return None


def _reconcile_same_position_id_less_edit(
    cell_id: str,
    base_synth_ids: list[str],
    ours_synth_ids: list[str],
    theirs_synth_ids: list[str],
    ours_cells: dict[str, dict[str, Any]],
    theirs_cells: dict[str, dict[str, Any]],
    base_cell: dict[str, Any],
) -> tuple[dict[str, Any], CellConflict | None, str, str] | None:
    """LIBIPYNB-Q3: when an id-less base cell is edited DIFFERENTLY on both
    sides, content-hash synthesis gives each side's edit a different
    synthesized id (content changed -> digest changed), so plain id-based
    reconciliation sees "base cell removed on both sides" plus two
    unrelated same-position "added" cells -- and would silently keep BOTH,
    duplicating content instead of detecting a conflict. This correlates
    the genuine same-cell replacement on each side (see
    `_find_same_position_replacement_id`) and resolves them exactly like
    an EDIT_EDIT conflict: base's original value stands pending
    resolution, never either side's value chosen silently. Returns None
    when no unambiguous same-cell replacement is found on both sides (a
    genuine, non-overlapping deletion, or a still-ambiguous multi-cell
    edit block -- handled normally by the caller, i.e. as an ordinary
    delete+add with no special-cased conflict).

    Known, accepted limitation, documented rather than silently swallowed:
    resolving this way does not guarantee the conflicted cell keeps its
    exact original index in the merged output -- the same class of
    position-fidelity limitation the diff layer already accepts for
    id-less changed cells (see ``model/diff.py``'s ``_with_stable_cell_ids``
    docstring: a changed id-less cell is reported as remove+add, not
    modified-in-place, because without a stable id there is no way to tell
    "same cell, different content" from "a different cell"). What this
    function guarantees is the property that actually matters: no
    duplicated content, and a real, reported conflict -- never a silent
    merge of two divergent edits.
    """
    ours_replacement_id = _find_same_position_replacement_id(
        base_synth_ids, ours_synth_ids, cell_id
    )
    theirs_replacement_id = _find_same_position_replacement_id(
        base_synth_ids, theirs_synth_ids, cell_id
    )
    if ours_replacement_id is None or theirs_replacement_id is None:
        return None

    ours_cell = ours_cells[ours_replacement_id]
    theirs_cell = theirs_cells[theirs_replacement_id]
    if ours_cell == theirs_cell:
        return deepcopy(ours_cell), None, ours_replacement_id, theirs_replacement_id

    conflict = CellConflict(
        cell_id=cell_id,
        kind=ConflictKind.EDIT_EDIT,
        field_name=None,
        ours_value=ours_cell,
        theirs_value=theirs_cell,
        description=(
            "cell with no stable id (matched by content-hash) was edited differently on each side"
        ),
    )
    return deepcopy(base_cell), conflict, ours_replacement_id, theirs_replacement_id


def _flatten_metadata_paths(value: Any, prefix: tuple[str, ...] = ()) -> dict[tuple[str, ...], Any]:
    """Leaf-level (path -> value) map. Dict values recurse; anything else
    (including lists) is one opaque leaf -- matching the granularity
    _reconcile_present_cell already uses for cell fields (a changed list is
    one conflicting unit, not diffed element-by-element)."""
    if isinstance(value, dict):
        result: dict[tuple[str, ...], Any] = {}
        for key, sub in value.items():
            result.update(_flatten_metadata_paths(sub, (*prefix, key)))
        return result
    return {prefix: value}


def _reconcile_notebook_metadata(
    base_metadata: Any,
    ours_metadata: Any,
    theirs_metadata: Any,
    conflicts: list[CellConflict],
) -> None:
    """LIBIPYNB-Q10: detection-only. The merged document's top-level
    metadata still always comes from `base` (see merge_notebooks' own
    `merged_raw = deepcopy(base.raw)` below) -- this function never changes
    that, matching this module's existing base-wins-on-conflict philosophy
    and its own documented scope boundary (see module docstring). It only
    adds a machine-checkable NOTEBOOK_METADATA conflict entry when
    ours/theirs diverge from base on the SAME leaf metadata path with
    DIFFERENT resulting values -- a real three-way conflict, not a
    whole-top-level-key approximation (which would false-positive on two
    genuinely unrelated edits landing under the same top-level key, e.g.
    metadata.language_info.version vs metadata.kernelspec.name)."""
    base_leaves = _flatten_metadata_paths(base_metadata if isinstance(base_metadata, dict) else {})
    ours_leaves = _flatten_metadata_paths(ours_metadata if isinstance(ours_metadata, dict) else {})
    theirs_leaves = _flatten_metadata_paths(
        theirs_metadata if isinstance(theirs_metadata, dict) else {}
    )
    missing = object()
    for path in sorted(set(base_leaves) | set(ours_leaves) | set(theirs_leaves)):
        base_value = base_leaves.get(path, missing)
        ours_value = ours_leaves.get(path, missing)
        theirs_value = theirs_leaves.get(path, missing)
        ours_changed = ours_value != base_value
        theirs_changed = theirs_value != base_value
        if ours_changed and theirs_changed and ours_value != theirs_value:
            dotted = ".".join(path)
            conflicts.append(
                CellConflict(
                    cell_id=None,
                    kind=ConflictKind.NOTEBOOK_METADATA,
                    field_name=f"metadata.{dotted}",
                    ours_value=None if ours_value is missing else ours_value,
                    theirs_value=None if theirs_value is missing else theirs_value,
                    description=(
                        f"notebook metadata path {dotted!r} changed differently on each side"
                    ),
                )
            )


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

    # LIBIPYNB-Q3: diff_notebooks() above synthesizes stable ids internally
    # for any id-less cell (nbformat 4.0-4.4), so ours_changes/theirs_changes
    # are keyed by those synthesized ids. _cell_map must be keyed the same
    # way to correlate correctly -- computed independently here (not shared
    # state with diff_notebooks' internal calls) but deterministically
    # identical, since synthesis is a pure function of each cell's content.
    base_synth = _synthesized_copy(base)
    ours_synth = _synthesized_copy(ours)
    theirs_synth = _synthesized_copy(theirs)
    base_cells = _cell_map(base, base_synth)
    ours_cells = _cell_map(ours, ours_synth)
    theirs_cells = _cell_map(theirs, theirs_synth)
    # LIBIPYNB-Q3 Gate G2 fix: plain per-document id sequences (in each
    # document's own cell order), used only for the same-position-edit
    # correlation below via a proper sequence alignment -- see
    # `_find_same_position_replacement_id`'s own docstring for why raw
    # before_index/after_index comparison was unsound.
    base_synth_ids = [str(cell["id"]) for cell in base_synth.cells]
    ours_synth_ids = [str(cell["id"]) for cell in ours_synth.cells]
    theirs_synth_ids = [str(cell["id"]) for cell in theirs_synth.cells]

    conflicts: list[CellConflict] = []
    merged_by_id: dict[str, dict[str, Any]] = {}
    # LIBIPYNB-Q3: for an id-less base cell edited DIFFERENTLY on both sides,
    # content-hash synthesis gives each side's edit a different id (content
    # changed -> digest changed), so plain id-based reconciliation below
    # would see "base cell removed on both sides" plus two unrelated
    # same-position "added" cells and silently keep BOTH -- duplicating
    # content instead of detecting a conflict. `consumed_ids` marks each
    # side's replacement cell_id as already handled by
    # `_reconcile_same_position_id_less_edit` (called just below) so the
    # main loop doesn't also add it again.
    consumed_ids: set[str] = set()
    for cell_id, candidate_ours_change in ours_changes.items():
        candidate_theirs_change = theirs_changes.get(cell_id)
        if (
            candidate_theirs_change is None
            or not (candidate_ours_change.removed and candidate_theirs_change.removed)
            or cell_id not in base_cells
        ):
            continue
        replacement = _reconcile_same_position_id_less_edit(
            cell_id,
            base_synth_ids,
            ours_synth_ids,
            theirs_synth_ids,
            ours_cells,
            theirs_cells,
            base_cells[cell_id],
        )
        if replacement is None:
            continue
        merged_cell, replacement_conflict, ours_replacement_id, theirs_replacement_id = replacement
        merged_by_id[cell_id] = merged_cell
        if replacement_conflict is not None:
            conflicts.append(replacement_conflict)
        consumed_ids.add(ours_replacement_id)
        consumed_ids.add(theirs_replacement_id)

    for cell_id in _ordered_ids(ours_synth, theirs_synth, base_synth):
        if cell_id in consumed_ids:
            continue
        ours_change = ours_changes.get(cell_id)
        theirs_change = theirs_changes.get(cell_id)

        if cell_id in merged_by_id:
            # Already resolved by the same-position-edit pass above.
            continue

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

        if ours_change.added and theirs_change.added:
            # Neither side's diff is against a base cell -- `cell_id` was
            # never in `base` at all (both sides independently created it,
            # e.g. via deterministic/content-derived cell-ID generation).
            # base_cells[cell_id] does not exist here; reconciling against
            # a nonexistent base cell would be a KeyError, not a merge.
            ours_cell = ours_cells[cell_id]
            theirs_cell = theirs_cells[cell_id]
            if ours_cell == theirs_cell:
                merged_by_id[cell_id] = deepcopy(ours_cell)
            else:
                conflicts.append(
                    CellConflict(
                        cell_id=cell_id,
                        kind=ConflictKind.EDIT_EDIT,
                        field_name=None,
                        ours_value=ours_cell,
                        theirs_value=theirs_cell,
                        description=(
                            f"cell {cell_id!r} was added independently on both "
                            "sides with different content"
                        ),
                    )
                )
                # No base value exists to fall back on for an add/add
                # conflict -- `ours` is kept as an explicit, reported
                # placeholder (never silently treated as resolved).
                merged_by_id[cell_id] = deepcopy(ours_cell)
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
                            f"cell {cell_id!r} was deleted on one side and changed on the other"
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

    _reconcile_notebook_metadata(
        base.raw.get("metadata"), ours.raw.get("metadata"), theirs.raw.get("metadata"), conflicts
    )

    merged_cells = [
        merged_by_id[cell_id]
        for cell_id in _ordered_ids(ours_synth, theirs_synth, base_synth)
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
