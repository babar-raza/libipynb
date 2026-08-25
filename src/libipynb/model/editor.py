"""Stable-ID cell collection editing with atomic change reports."""

from __future__ import annotations

import re
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import dataclass, replace
from enum import Enum
from typing import Any, cast

from .._internal.immutable import deep_freeze
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
            # LIBIPYNB-Q43 Gate-G2 round-2 review finding: `deepcopy` only
            # broke aliasing to the constructor's input, not later
            # mutation of the field itself -- see FieldChange's identical
            # fix in model.diff. `self.metadata` is already typed as
            # `Mapping`, so freezing it in place is not an API-widening
            # change here (unlike a `dict`-typed field would be).
            object.__setattr__(self, "metadata", deep_freeze(dict(self.metadata)))

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
    before: Mapping[str, Any] | None
    after: Mapping[str, Any] | None

    def __post_init__(self) -> None:
        # LIBIPYNB-Q43 Gate-G2 round-2 review finding: `deepcopy` only
        # broke aliasing to the constructor's input, not later mutation of
        # the field itself -- see model.diff.FieldChange's identical fix.
        # Widened from `dict[str, Any] | None` to `Mapping[str, Any] |
        # None` to match what `deep_freeze` actually returns (a
        # `MappingProxyType`, not a `dict`); every construction call site
        # in this module still passes a plain `dict`, which is a valid
        # `Mapping`, so this is not a behavior change for any caller.
        object.__setattr__(self, "before", deep_freeze(self.before))
        object.__setattr__(self, "after", deep_freeze(self.after))


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
            raise ValueError(f"cell at index {position} is missing a stable non-empty ID")
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
            key in value and _metadata_contains(value[key], item) for key, item in expected.items()
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
    return query.source_text is None or query.source_text in _source_text(cell)


def _validate_cell(
    value: Mapping[str, Any],
    *,
    notebook_minor: int,
    used_ids: set[str] | None = None,
) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError("cell must be a mapping")
    cell = deepcopy(dict(value))
    cell_id = cell.get("id")
    if notebook_minor >= 5:
        if not isinstance(cell_id, str) or not _CELL_ID.fullmatch(cell_id):
            raise ValueError("cell ID must contain 1-64 ASCII letters, digits, _ or -")
    elif not isinstance(cell_id, str) or not _CELL_ID.fullmatch(cell_id):
        # LIBIPYNB-Q66: cell `id` is not a valid nbformat cell property
        # before 4.5 -- a caller inserting into a <5 document has no real
        # id to supply and isn't required to. Assign one anyway, purely as
        # this editor's own internal, ephemeral addressing key for the
        # duration of this operation (the same content-hash algorithm
        # `codec.reader.with_stable_cell_ids` uses for diff/merge) --
        # `CellEditor._finish` strips it again before anything is
        # validated against the notebook's own <5 schema or committed.
        from ..codec.reader import ensure_cell_id  # deferred: avoid model<->codec import cycle

        ensure_cell_id(cell, used_ids if used_ids is not None else set())
    cell_type = cell.get("cell_type")
    if not isinstance(cell_type, str) or not cell_type:
        raise ValueError("cell_type must be a non-empty string")
    if cell_type not in _KNOWN_CELL_TYPES and notebook_minor <= 5:
        raise ValueError(f"unsupported current-profile cell type: {cell_type}")
    if not isinstance(cell.get("metadata"), dict):
        raise ValueError("cell metadata must be an object")  # noqa: TRY004
    source = cell.get("source")
    if not (
        isinstance(source, str)
        or (isinstance(source, list) and all(isinstance(item, str) for item in source))
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


def _select(raw: dict[str, Any], cell_id: str) -> tuple[int, dict[str, Any]]:
    if not isinstance(cell_id, str) or not cell_id:
        raise ValueError("cell_id must be a non-empty string")
    try:
        return _index(raw)[cell_id]
    except KeyError as exc:
        raise KeyError(f"cell ID not found: {cell_id}") from exc


def _new_shadow(document: NotebookDocument) -> dict[str, Any] | None:
    """The initial, ephemeral-id-carrying shadow copy for a <4.5 document
    -- ``None`` for >=4.5 documents, which need no shadow since their
    cells already carry real, persisted ids that never move underneath
    this module's id-string-addressed mutators.

    LIBIPYNB-Q66 Gate-G2 CRITICAL review finding: an earlier version of
    this mechanism recomputed ephemeral ids fresh, by re-hashing cell
    content, on *every* call -- reasoning that this was safe because
    recomputation is a pure function of content, so two calls "without an
    intervening edit" would agree. That reasoning missed the actual usage
    pattern: `CellEditor`'s own public API hands a caller an id from one
    call (e.g. `insert()`) specifically so it can be used in a *later,
    separate* call (`move()`/`copy()`/`replace()`/`remove()`) -- and
    content-hash ids are assigned by list *position* among
    content-duplicate cells. Reproduced live: two duplicate-content cells,
    capture the id of the one at position 0, `move()` it to position 1 --
    recomputing ids fresh afterward reassigns that SAME id string back to
    position 0, which is now a *different* physical cell. A caller still
    holding the original id would silently operate on the wrong cell, no
    error raised.

    Fixed by computing this shadow exactly once, then carrying it forward
    as `CellEditor` instance state (`self._shadow`), updated in place
    after every successful (non-dry-run) commit -- never re-derived from
    content after this first assignment. An id therefore stays bound to
    the same logical cell for the lifetime of one `CellEditor` instance,
    the same guarantee a real, persisted id gives a >=4.5 document.
    """
    if document.nbformat_minor >= 5:
        return None
    from ..codec.reader import with_stable_cell_ids  # deferred: avoid model<->codec import cycle

    shadow = deepcopy(document.raw)
    with_stable_cell_ids(shadow)
    return shadow


def _without_ephemeral_id(value: Mapping[str, Any] | None) -> dict[str, Any] | None:
    return None if value is None else {key: item for key, item in value.items() if key != "id"}


def _strip_ephemeral_ids_from_changes(changes: tuple[CellEdit, ...]) -> tuple[CellEdit, ...]:
    """`CellEdit.before`/`.after` are frozen (deep_freeze) snapshots, not
    live views (see `_internal/immutable.py`) -- taken at the moment each
    `_do_*` function returns, before any later strip of the committed
    document's cells could retroactively affect them. Rebuilding each
    entry here, with `id` removed before it's re-frozen, is what keeps a
    caller inspecting either `CellEditReport.changes` (post-commit) or
    `CellEditBatch.changes` (readable mid-batch, before any commit has
    happened at all -- LIBIPYNB-Q66 Gate-G2 WARNING finding: an earlier
    version only stripped the former, leaving the latter to leak the raw
    ephemeral id both mid-batch and after commit) from ever seeing an
    `id` the document's own committed state doesn't have. `cell_id` itself
    is deliberately left as the ephemeral id -- a change-tracking label
    ("which cell"), not a content snapshot, and some identifier is
    unavoidably needed to describe "which cell changed" either way.
    """
    return tuple(
        replace(
            change,
            before=_without_ephemeral_id(change.before),
            after=_without_ephemeral_id(change.after),
        )
        for change in changes
    )


# LIBIPYNB-Q15a: each mutator below implements exactly one operation's core
# logic against a caller-supplied `target` dict, with no `deepcopy`/
# `validate()`/commit of its own. `CellEditor`'s individual per-call methods
# and `CellEditBatch`'s accumulating methods both call the same function --
# one `deepcopy` per single call (as before) vs. one `deepcopy` for an
# entire batch, with identical mutation logic either way.


def _do_insert(
    target: dict[str, Any],
    cell: Mapping[str, Any],
    index: int | None,
    notebook_minor: int,
) -> CellEdit:
    values = _cells(target)
    position = len(values) if index is None else index
    if (
        not isinstance(position, int)
        or isinstance(position, bool)
        or position < 0
        or position > len(values)
    ):
        raise IndexError("insert index is outside the cell collection")
    validated = _validate_cell(cell, notebook_minor=notebook_minor, used_ids=set(_index(target)))
    cell_id = str(validated["id"])
    if cell_id in _index(target):
        raise ValueError(f"cell ID must be unique: {cell_id}")
    values.insert(position, validated)
    return CellEdit(CellEditOperation.INSERT, cell_id, None, position, None, validated)


def _do_move(target: dict[str, Any], cell_id: str, index: int) -> CellEdit | None:
    values = _cells(target)
    current_index, cell = _select(target, cell_id)
    if not isinstance(index, int) or isinstance(index, bool) or index < 0 or index >= len(values):
        raise IndexError("move index is outside the cell collection")
    if current_index == index:
        return None
    values.pop(current_index)
    values.insert(index, cell)
    return CellEdit(CellEditOperation.MOVE, cell_id, current_index, index, cell, cell)


def _do_copy(
    target: dict[str, Any],
    cell_id: str,
    index: int | None,
    new_id: str | None,
    notebook_minor: int,
) -> CellEdit:
    values = _cells(target)
    current_index, cell = _select(target, cell_id)
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
    copied = _validate_cell(copied, notebook_minor=notebook_minor)
    if selected_id in used:
        raise ValueError(f"cell ID must be unique: {selected_id}")
    values.insert(position, copied)
    return CellEdit(CellEditOperation.COPY, selected_id, None, position, None, copied)


def _do_replace(
    target: dict[str, Any],
    cell_id: str,
    cell: Mapping[str, Any],
    notebook_minor: int,
) -> CellEdit | None:
    values = _cells(target)
    position, before = _select(target, cell_id)
    replacement = deepcopy(dict(cell))
    replacement["id"] = cell_id
    replacement = _validate_cell(replacement, notebook_minor=notebook_minor)
    if before == replacement:
        return None
    values[position] = replacement
    return CellEdit(CellEditOperation.REPLACE, cell_id, position, position, before, replacement)


def _do_remove(target: dict[str, Any], cell_id: str) -> CellEdit:
    values = _cells(target)
    position, cell = _select(target, cell_id)
    values.pop(position)
    return CellEdit(CellEditOperation.REMOVE, cell_id, position, None, cell, None)


def _do_remove_where(target: dict[str, Any], query: CellQuery) -> tuple[CellEdit, ...]:
    if not isinstance(query, CellQuery):
        raise TypeError("query must be a CellQuery")
    if not query.has_criteria:
        raise ValueError("bulk removal requires at least one criterion")
    values = _cells(target)
    changes = tuple(
        CellEdit(CellEditOperation.REMOVE, str(cell["id"]), position, None, cell, None)
        for position, cell in enumerate(values)
        if _matches(cell, query)
    )
    if not changes:
        return ()
    removed = {change.cell_id for change in changes}
    target["cells"] = [cell for cell in values if cell.get("id") not in removed]
    return changes


class CellEditBatch:
    """Accumulates edits against one in-memory working copy.

    Returned by :meth:`CellEditor.batch`. Each method here mutates the same
    working copy (one `deepcopy`, taken once at batch-entry) and records a
    :class:`CellEdit`, but -- unlike :class:`CellEditor`'s own per-call
    methods -- does not validate or commit anything itself. The single
    deferred `validate()` call, and the atomic commit it guards, happen once
    in :meth:`CellEditor.batch`'s `__exit__`, after the `with` block
    completes normally. If the `with` block itself raises, `__exit__`'s
    commit step never runs and the editor's document is left untouched --
    the same atomic, all-or-nothing guarantee individual calls already had,
    now covering a whole batch for the cost of one validation instead of N.
    """

    def __init__(self, editor: CellEditor) -> None:
        self._editor = editor
        self._target = editor._working_copy()
        self._notebook_minor = editor.document.nbformat_minor
        self._changes: list[CellEdit] = []
        #: Set by `CellEditor.batch()` after a successful, validated commit
        #: (or a validated dry run) -- `None` while the batch is still open.
        self.report: CellEditReport | None = None

    @property
    def changes(self) -> tuple[CellEdit, ...]:
        changes = tuple(self._changes)
        if self._notebook_minor < 5:
            changes = _strip_ephemeral_ids_from_changes(changes)
        return changes

    def insert(self, cell: Mapping[str, Any], *, index: int | None = None) -> CellEdit:
        change = _do_insert(self._target, cell, index, self._notebook_minor)
        self._changes.append(change)
        return change

    def move(self, cell_id: str, index: int) -> CellEdit | None:
        change = _do_move(self._target, cell_id, index)
        if change is not None:
            self._changes.append(change)
        return change

    def copy(
        self,
        cell_id: str,
        *,
        index: int | None = None,
        new_id: str | None = None,
    ) -> CellEdit:
        change = _do_copy(self._target, cell_id, index, new_id, self._notebook_minor)
        self._changes.append(change)
        return change

    def replace(self, cell_id: str, cell: Mapping[str, Any]) -> CellEdit | None:
        change = _do_replace(self._target, cell_id, cell, self._notebook_minor)
        if change is not None:
            self._changes.append(change)
        return change

    def remove(self, cell_id: str) -> CellEdit:
        change = _do_remove(self._target, cell_id)
        self._changes.append(change)
        return change

    def remove_where(self, query: CellQuery) -> tuple[CellEdit, ...]:
        changes = _do_remove_where(self._target, query)
        self._changes.extend(changes)
        return changes


class CellEditor:
    """Cell collection mutations that preserve legacy index-based methods."""

    def __init__(self, document: NotebookDocument) -> None:
        if not isinstance(document, NotebookDocument):
            raise TypeError("document must be an NotebookDocument")
        self.document = document
        #: `None` for >=4.5 documents (no shadow needed -- their cells
        #: already carry real, persisted ids). For <4.5, the persistent,
        #: ephemeral-id-carrying working state this editor instance
        #: mutates and carries forward across calls -- see `_new_shadow`'s
        #: docstring for why this must be instance state, not recomputed
        #: fresh each call.
        self._shadow = _new_shadow(document)
        # Fail fast on a structurally broken document (this also no
        # longer requires ids that aren't a valid property below 4.5).
        _index(self._working_copy())

    def _working_copy(self) -> dict[str, Any]:
        """A fresh, independent copy to mutate for one operation -- from
        the persistent shadow for <4.5 documents, or directly from the
        real document for >=4.5 (whose cells already carry real ids)."""
        return deepcopy(self._shadow if self._shadow is not None else self.document.raw)

    def search(self, query: CellQuery) -> tuple[Cell, ...]:
        if not isinstance(query, CellQuery):
            raise TypeError("query must be a CellQuery")
        return tuple(
            cell_from_dict(cell) for cell in _cells(self.document.raw) if _matches(cell, query)
        )

    def insert(
        self,
        cell: Mapping[str, Any],
        *,
        index: int | None = None,
        dry_run: bool = False,
    ) -> CellEditReport:
        target = self._working_copy()
        change = _do_insert(target, cell, index, self.document.nbformat_minor)
        return self._finish(target, (change,), dry_run=dry_run)

    def move(
        self,
        cell_id: str,
        index: int,
        *,
        dry_run: bool = False,
    ) -> CellEditReport:
        target = self._working_copy()
        change = _do_move(target, cell_id, index)
        if change is None:
            return CellEditReport((), False)
        return self._finish(target, (change,), dry_run=dry_run)

    def copy(
        self,
        cell_id: str,
        *,
        index: int | None = None,
        new_id: str | None = None,
        dry_run: bool = False,
    ) -> CellEditReport:
        target = self._working_copy()
        change = _do_copy(target, cell_id, index, new_id, self.document.nbformat_minor)
        return self._finish(target, (change,), dry_run=dry_run)

    def replace(
        self,
        cell_id: str,
        cell: Mapping[str, Any],
        *,
        dry_run: bool = False,
    ) -> CellEditReport:
        target = self._working_copy()
        change = _do_replace(target, cell_id, cell, self.document.nbformat_minor)
        if change is None:
            return CellEditReport((), False)
        return self._finish(target, (change,), dry_run=dry_run)

    def remove(
        self,
        cell_id: str,
        *,
        dry_run: bool = False,
    ) -> CellEditReport:
        target = self._working_copy()
        change = _do_remove(target, cell_id)
        return self._finish(target, (change,), dry_run=dry_run)

    def remove_where(
        self,
        query: CellQuery,
        *,
        dry_run: bool = False,
    ) -> CellEditReport:
        target = self._working_copy()
        changes = _do_remove_where(target, query)
        if not changes:
            return CellEditReport((), False)
        return self._finish(target, changes, dry_run=dry_run)

    @contextmanager
    def batch(self, *, dry_run: bool = False) -> Iterator[CellEditBatch]:
        """Accumulate edits against one in-memory working copy, deferring
        the single `validate()` call (and the atomic commit it guards) to
        the end of the `with` block.

        LIBIPYNB-Q15a: every individual mutation method above pays a fresh
        `deepcopy` of the whole notebook plus a full `validate()` call, even
        under `dry_run=True` -- previewing N edits one at a time costs N
        full-notebook validations. A batch pays for exactly one of each,
        regardless of how many edits it accumulates::

            with editor.batch() as batch:
                batch.insert(cell_a)
                batch.remove("old-cell")
            # batch.report is now set; committed iff validation passed.

        If the `with` block itself raises, this commit step never runs and
        `self.document` is left completely untouched -- individual calls'
        atomic, all-or-nothing guarantee, now covering a whole batch.
        """
        working = CellEditBatch(self)
        yield working
        working.report = self._finish(working._target, tuple(working._changes), dry_run=dry_run)

    def _finish(
        self,
        target: dict[str, Any],
        changes: tuple[CellEdit, ...],
        *,
        dry_run: bool,
    ) -> CellEditReport:
        from ..validation import validate

        is_pre_v45 = self.document.nbformat_minor < 5
        committed = target
        if is_pre_v45:
            # LIBIPYNB-Q66: `target` carries ephemeral ids (from
            # `_working_copy`/`_do_*`) needed only for this operation's
            # own internal addressing. `committed` -- a separate deepcopy,
            # not `target` itself -- is what gets those ids stripped
            # (a <4.5 schema's `additionalProperties: false` would
            # otherwise reject them, exactly like `lifecycle.downgrade()`'s
            # identical strip), validated, and written into the real
            # document. `target` itself is left untouched here
            # specifically so it can become the new `self._shadow` below
            # -- still carrying its ids, ready for the next call.
            committed = deepcopy(target)
            for cell in _cells(committed):
                cell.pop("id", None)
            changes = _strip_ephemeral_ids_from_changes(changes)
        report = validate(NotebookDocument(committed))
        if not report.is_valid:
            first = report.errors[0]
            raise ValueError(f"cell edit would invalidate notebook: {first.code}: {first.message}")
        if not dry_run:
            self.document.raw.clear()
            self.document.raw.update(committed)
            if is_pre_v45:
                # Carries this operation's ids forward as the new shadow
                # -- see `_new_shadow`'s docstring for why recomputing
                # fresh from content on the next call would be wrong.
                self._shadow = target
        return CellEditReport(changes, not dry_run)


def edit_cells(document: NotebookDocument) -> CellEditor:
    return CellEditor(document)


__all__ = [
    "CellEdit",
    "CellEditBatch",
    "CellEditOperation",
    "CellEditReport",
    "CellEditor",
    "CellQuery",
    "edit_cells",
]
