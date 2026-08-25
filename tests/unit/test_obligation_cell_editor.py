"""Failure-first tests for stable-ID notebook cell collection editing."""

from __future__ import annotations

import time
from collections.abc import Callable
from copy import deepcopy

import nbformat
import pytest

from libipynb import (
    NotebookDocument,
    dumps,
    edit_cells,
    loads,
)
from libipynb.model import CellEditOperation, CellEditor, CellEditReport, CellQuery


def _document() -> NotebookDocument:
    return NotebookDocument(
        {
            "nbformat": 4,
            "nbformat_minor": 5,
            "metadata": {"vendor": {"preserve": True}},
            "cells": [
                {
                    "cell_type": "code",
                    "id": "alpha",
                    "metadata": {
                        "tags": ["setup", "remove"],
                        "slideshow": {"slide_type": "slide"},
                    },
                    "source": "value = 1",
                    "execution_count": 1,
                    "outputs": [],
                },
                {
                    "cell_type": "markdown",
                    "id": "beta",
                    "metadata": {"tags": ["keep"]},
                    "source": "Explanation",
                },
                {
                    "cell_type": "raw",
                    "id": "gamma",
                    "metadata": {
                        "tags": ["remove"],
                        "format": "text/plain",
                    },
                    "source": ["raw ", "content"],
                },
            ],
        }
    )


def _valid(document: NotebookDocument) -> None:
    nbformat.validate(nbformat.from_dict(deepcopy(document.raw)))


def test_insert_move_replace_remove_are_stable_id_operations() -> None:
    document = _document()
    editor = edit_cells(document)
    vendor = deepcopy(document.raw["metadata"])
    inserted = {
        "cell_type": "markdown",
        "id": "delta",
        "metadata": {"tags": ["new"]},
        "source": "New",
    }

    insert_report = editor.insert(inserted, index=1)
    move_report = editor.move("delta", 0)
    replace_report = editor.replace(
        "delta",
        {
            "cell_type": "raw",
            "id": "ignored-by-preserve-id",
            "metadata": {"format": "text/plain"},
            "source": "replacement",
        },
    )
    remove_report = editor.remove("delta")

    assert insert_report.changes[0].operation is CellEditOperation.INSERT
    assert move_report.changes[0].operation is CellEditOperation.MOVE
    assert replace_report.changes[0].operation is CellEditOperation.REPLACE
    assert replace_report.changes[0].cell_id == "delta"
    assert remove_report.changes[0].operation is CellEditOperation.REMOVE
    assert [cell["id"] for cell in document.cells] == [
        "alpha",
        "beta",
        "gamma",
    ]
    assert document.raw["metadata"] == vendor
    assert inserted == {
        "cell_type": "markdown",
        "id": "delta",
        "metadata": {"tags": ["new"]},
        "source": "New",
    }
    _valid(document)


def test_copy_uses_deterministic_unique_ids_and_deep_copies() -> None:
    document = _document()
    editor = edit_cells(document)

    first = editor.copy("alpha")
    second = editor.copy("alpha")
    copied = document.cells[1]
    copied["metadata"]["tags"].append("copy-only")

    assert first.changes[0].cell_id == "alpha-copy"
    assert second.changes[0].cell_id == "alpha-copy-2"
    assert [cell["id"] for cell in document.cells][:3] == [
        "alpha",
        "alpha-copy-2",
        "alpha-copy",
    ]
    assert "copy-only" not in document.cells[0]["metadata"]["tags"]
    _valid(document)


def test_search_combines_id_type_tag_metadata_and_source_criteria() -> None:
    editor = edit_cells(_document())

    matches = editor.search(
        CellQuery(
            cell_type="code",
            tag="setup",
            metadata={"slideshow": {"slide_type": "slide"}},
            source_text="value",
        )
    )
    no_matches = editor.search(
        CellQuery(
            cell_id="alpha",
            metadata={"slideshow": {"slide_type": "fragment"}},
        )
    )

    assert [cell.id for cell in matches] == ["alpha"]
    assert no_matches == ()


def test_bulk_remove_has_deterministic_report_and_safe_empty_query() -> None:
    preview_document = _document()
    apply_document = _document()
    preview_editor = edit_cells(preview_document)
    apply_editor = edit_cells(apply_document)
    before = deepcopy(preview_document.raw)
    query = CellQuery(tag="remove")

    preview = preview_editor.remove_where(query, dry_run=True)
    applied = apply_editor.remove_where(query)

    assert preview.changes == applied.changes
    assert [item.cell_id for item in applied.changes] == ["alpha", "gamma"]
    assert preview.applied is False
    assert preview_document.raw == before
    assert [cell["id"] for cell in apply_document.cells] == ["beta"]
    with pytest.raises(ValueError, match="criterion"):
        apply_editor.remove_where(CellQuery())
    with pytest.raises(ValueError, match="at least one key"):
        CellQuery(metadata={})
    _valid(apply_document)


def test_dry_run_matches_apply_and_noop_reports_are_explicit() -> None:
    preview_document = _document()
    apply_document = _document()

    preview = edit_cells(preview_document).move("gamma", 0, dry_run=True)
    applied = edit_cells(apply_document).move("gamma", 0)
    noop = edit_cells(apply_document).move("gamma", 0)

    assert preview.changes == applied.changes
    assert preview_document.cells[0]["id"] == "alpha"
    assert apply_document.cells[0]["id"] == "gamma"
    assert preview.would_change and not preview.applied
    assert applied.would_change and applied.applied
    assert not noop.would_change and not noop.applied


@pytest.mark.parametrize(
    "cell, message",
    [
        (
            {
                "cell_type": "markdown",
                "id": "alpha",
                "metadata": {},
                "source": "duplicate",
            },
            "unique",
        ),
        (
            {
                "cell_type": "code",
                "id": "delta",
                "metadata": {},
                "source": "missing fields",
            },
            "execution_count",
        ),
        (
            {
                "cell_type": "markdown",
                "id": "bad id",
                "metadata": {},
                "source": "invalid ID",
            },
            "cell ID",
        ),
    ],
)
def test_insert_rejects_invalid_or_duplicate_cells_without_mutation(
    cell: dict[str, object],
    message: str,
) -> None:
    document = _document()
    before = deepcopy(document.raw)

    with pytest.raises(ValueError, match=message):
        edit_cells(document).insert(cell)

    assert document.raw == before


def test_replace_and_bulk_failure_are_atomic() -> None:
    document = _document()
    before = deepcopy(document.raw)

    with pytest.raises(ValueError, match="outputs"):
        edit_cells(document).replace(
            "beta",
            {
                "cell_type": "code",
                "id": "beta",
                "metadata": {},
                "source": "invalid",
                "execution_count": None,
            },
        )
    assert document.raw == before

    document.cells[1]["id"] = "alpha"
    duplicated = deepcopy(document.raw)
    with pytest.raises(ValueError, match="unique"):
        edit_cells(document)
    assert document.raw == duplicated


def test_future_unknown_cells_survive_unrelated_edit_unchanged() -> None:
    document = _document()
    document.raw["nbformat_minor"] = 6
    document.cells.append(
        {
            "cell_type": "future-cell",
            "id": "future",
            "metadata": {"vendor": {"keep": True}},
            "source": "future",
            "future_payload": {"nested": [1, 2, 3]},
        }
    )
    future = deepcopy(document.cells[-1])

    edit_cells(document).move("gamma", 0)

    assert next(cell for cell in document.cells if cell["id"] == "future") == future


_EditorOperation = Callable[[CellEditor, bool], CellEditReport]


@pytest.mark.parametrize(
    "operation",
    [
        lambda editor, dry_run: editor.insert(
            {
                "cell_type": "markdown",
                "id": "delta",
                "metadata": {},
                "source": "inserted",
            },
            index=1,
            dry_run=dry_run,
        ),
        lambda editor, dry_run: editor.move(
            "gamma",
            0,
            dry_run=dry_run,
        ),
        lambda editor, dry_run: editor.copy(
            "alpha",
            dry_run=dry_run,
        ),
        lambda editor, dry_run: editor.replace(
            "beta",
            {
                "cell_type": "markdown",
                "id": "will-be-preserved",
                "metadata": {"tags": ["replacement"]},
                "source": "replaced",
            },
            dry_run=dry_run,
        ),
        lambda editor, dry_run: editor.remove(
            "gamma",
            dry_run=dry_run,
        ),
        lambda editor, dry_run: editor.remove_where(
            CellQuery(tag="remove"),
            dry_run=dry_run,
        ),
    ],
)
def test_every_mutation_dry_run_matches_apply_and_save_reload(
    operation: _EditorOperation,
) -> None:
    preview_document = _document()
    apply_document = _document()
    before = deepcopy(preview_document.raw)

    preview = operation(edit_cells(preview_document), True)
    applied = operation(edit_cells(apply_document), False)
    reloaded = loads(dumps(apply_document))

    assert preview.changes == applied.changes
    assert preview_document.raw == before
    assert reloaded.raw == apply_document.raw
    assert [cell["id"] for cell in reloaded.cells] == [cell["id"] for cell in apply_document.cells]
    _valid(reloaded)


# ── LIBIPYNB-Q15a: batch() ───────────────────────────────────────────────────


def _large_notebook(cell_count: int) -> NotebookDocument:
    cells = [
        {
            "cell_type": "code",
            "id": f"cell-{i}",
            "metadata": {},
            "source": f"x = {i}",
            "execution_count": None,
            "outputs": [],
        }
        for i in range(cell_count)
    ]
    return NotebookDocument({"nbformat": 4, "nbformat_minor": 5, "metadata": {}, "cells": cells})


def test_batch_edits_commit_atomically_as_a_single_change() -> None:
    document = _document()
    editor = edit_cells(document)

    with editor.batch() as batch:
        batch.insert(
            {"cell_type": "markdown", "id": "delta", "metadata": {}, "source": "new"}, index=1
        )
        batch.remove("gamma")
        batch.move("beta", 0)

    assert batch.report is not None
    assert batch.report.applied is True
    assert len(batch.report.changes) == 3
    assert [cell["id"] for cell in document.cells] == ["beta", "alpha", "delta"]
    _valid(document)


def test_batch_changes_property_reflects_accumulated_edits_before_commit() -> None:
    document = _document()
    editor = edit_cells(document)

    with editor.batch() as batch:
        assert batch.changes == ()
        batch.remove("gamma")
        assert len(batch.changes) == 1
        batch.remove("beta")
        assert len(batch.changes) == 2
        # Nothing committed to the real document until the `with` block exits.
        assert [cell["id"] for cell in document.cells] == ["alpha", "beta", "gamma"]

    assert [cell["id"] for cell in document.cells] == ["alpha"]


def test_batch_dry_run_validates_but_does_not_commit() -> None:
    document = _document()
    before = deepcopy(document.raw)
    editor = edit_cells(document)

    with editor.batch(dry_run=True) as batch:
        batch.remove("alpha")
        batch.remove("gamma")

    assert batch.report is not None
    assert batch.report.would_change is True
    assert batch.report.applied is False
    assert document.raw == before


def test_batch_raises_and_leaves_the_document_untouched_when_the_final_state_is_invalid() -> None:
    """The atomicity guarantee this card exists to preserve: `remove("gamma")`
    succeeds against the batch's own working copy, but the second accumulated
    edit makes the notebook AS A WHOLE invalid (a dangling attachment
    reference -- a cross-field defect only the deferred, whole-notebook
    validate() at batch-exit catches, not either individual call). Neither
    edit may leak into the real document."""
    document = _document()
    before = deepcopy(document.raw)
    editor = edit_cells(document)

    with pytest.raises(ValueError, match="cell edit would invalidate"), editor.batch() as batch:
        batch.remove("gamma")
        batch.insert(
            {
                "cell_type": "markdown",
                "id": "dangling",
                "metadata": {},
                "source": "![missing](attachment:missing.png)",
            }
        )

    assert document.raw == before, "a partially-valid batch must never leak into the real document"


def test_batch_never_commits_when_the_with_block_itself_raises() -> None:
    document = _document()
    before = deepcopy(document.raw)
    editor = edit_cells(document)

    class _Boom(Exception):
        pass

    with pytest.raises(_Boom), editor.batch() as batch:
        batch.remove("alpha")
        raise _Boom("caller's own code failed mid-batch")

    assert document.raw == before


def test_batch_result_matches_the_equivalent_sequential_single_calls() -> None:
    sequential_document = _document()
    sequential_editor = edit_cells(sequential_document)
    sequential_editor.remove("gamma")
    sequential_editor.move("beta", 0)

    batch_document = _document()
    batch_editor = edit_cells(batch_document)
    with batch_editor.batch() as batch:
        batch.remove("gamma")
        batch.move("beta", 0)

    assert sequential_document.raw == batch_document.raw
    reloaded = loads(dumps(batch_document))
    assert reloaded.raw == batch_document.raw
    _valid(reloaded)


def test_batched_edits_are_meaningfully_cheaper_than_the_same_edits_one_call_at_a_time() -> None:
    """Gate G1: measured, not claimed. Each individual mutation call pays a
    fresh deepcopy + full validate() of the whole notebook; a batch pays for
    exactly one of each regardless of edit count. On a 4,000-cell notebook,
    N=20 real (would-change) edits done one call at a time must cost
    meaningfully more than the same 20 edits accumulated in one batch."""
    cell_count = 4000
    edit_count = 20

    sequential_document = _large_notebook(cell_count)
    sequential_editor = edit_cells(sequential_document)
    start = time.perf_counter()
    for i in range(edit_count):
        sequential_editor.replace(
            f"cell-{i}",
            {
                "cell_type": "code",
                "id": f"cell-{i}",
                "metadata": {},
                "source": f"x = {i} + 1",
                "execution_count": None,
                "outputs": [],
            },
        )
    sequential_elapsed = time.perf_counter() - start

    batch_document = _large_notebook(cell_count)
    batch_editor = edit_cells(batch_document)
    start = time.perf_counter()
    with batch_editor.batch() as batch:
        for i in range(edit_count):
            batch.replace(
                f"cell-{i}",
                {
                    "cell_type": "code",
                    "id": f"cell-{i}",
                    "metadata": {},
                    "source": f"x = {i} + 1",
                    "execution_count": None,
                    "outputs": [],
                },
            )
    batch_elapsed = time.perf_counter() - start

    assert batch.report is not None and batch.report.applied
    assert sequential_document.raw == batch_document.raw

    # The batched path does 1 deepcopy + 1 validate instead of 20 of each --
    # a wide margin (not a tight ratio assertion, to avoid CI flakiness) is
    # enough to prove the architectural difference is real.
    assert batch_elapsed < sequential_elapsed / 3, (
        f"batched edits ({batch_elapsed:.3f}s) should be meaningfully cheaper than "
        f"{edit_count} sequential single-call edits ({sequential_elapsed:.3f}s) on a "
        f"{cell_count}-cell notebook"
    )


class TestQ43CellEditMutationAfterAccessDoesNotChangeLaterReads:
    """LIBIPYNB-Q43 Gate-G2 round-2 review finding: `CellEdit.before`/
    `.after` and `CellQuery.metadata` had the identical gap `NotebookDiff.
    _target_snapshot` was fixed for (see test_obligation_structure_diff.py)
    -- `deepcopy` in `__post_init__` only broke aliasing to the
    constructor's input, not later mutation of the field itself. Found
    live during round 2's own investigation, not part of round 1's
    original 4 findings."""

    def test_remove_change_before_rejects_item_assignment(self) -> None:
        document = _document()
        report = edit_cells(document).remove("alpha")
        change = report.changes[0]

        with pytest.raises(TypeError):
            change.before["metadata"]["tags"] = []  # type: ignore[index]
        assert change.before["metadata"]["tags"] == ("setup", "remove")
        assert change.after is None

    def test_insert_change_after_rejects_item_assignment(self) -> None:
        document = _document()
        report = edit_cells(document).insert(
            {
                "cell_type": "markdown",
                "id": "delta",
                "metadata": {"tags": ["new"]},
                "source": "New",
            },
            index=1,
        )
        change = report.changes[0]

        with pytest.raises(TypeError):
            change.after["metadata"]["tags"] = []  # type: ignore[index]
        assert change.after["metadata"]["tags"] == ("new",)

    def test_cell_query_metadata_rejects_item_assignment(self) -> None:
        query = CellQuery(metadata={"slideshow": {"slide_type": "slide"}})

        with pytest.raises(TypeError):
            query.metadata["slideshow"] = {}  # type: ignore[index]
        with pytest.raises(TypeError):
            query.metadata["slideshow"]["slide_type"] = "TAMPERED"  # type: ignore[index]

        document = _document()
        (found,) = edit_cells(document).search(query)
        assert found.metadata["slideshow"]["slide_type"] == "slide"


def _document_without_ids(nbformat_minor: int) -> NotebookDocument:
    """The `_document()` fixture's shape, minus every `id` -- a cell `id`
    is not a valid property before nbformat 4.5, so this is what a real
    4.0-4.4 notebook's cells actually look like."""
    return NotebookDocument(
        {
            "nbformat": 4,
            "nbformat_minor": nbformat_minor,
            "metadata": {"vendor": {"preserve": True}},
            "cells": [
                {
                    "cell_type": "code",
                    "metadata": {"tags": ["setup", "remove"]},
                    "source": "value = 1",
                    "execution_count": 1,
                    "outputs": [],
                },
                {
                    "cell_type": "markdown",
                    "metadata": {"tags": ["keep"]},
                    "source": "Explanation",
                },
                {
                    "cell_type": "raw",
                    "metadata": {"tags": ["remove"], "format": "text/plain"},
                    "source": ["raw ", "content"],
                },
            ],
        }
    )


class TestQ66PreV45DocumentsAreEditable:
    """LIBIPYNB-Q66: `edit_cells()`/`CellEditor` previously required every
    cell to already carry a valid `id` -- unconditionally, regardless of
    the document's own declared `nbformat_minor` -- so construction itself
    raised `ValueError` on every real 4.0-4.4 fixture (cell ids only became
    mandatory at 4.5, confirmed against the vendored schemas). Reproduced
    live against all 5 real fixtures before this fix; these are the
    regression tests for it."""

    @pytest.mark.parametrize("minor", [0, 1, 2, 3, 4])
    def test_edit_cells_constructs_without_requiring_pre_existing_ids(self, minor: int) -> None:
        document = _document_without_ids(minor)

        editor = edit_cells(document)  # must not raise

        assert len(editor.search(CellQuery(cell_type="code"))) == 1

    @pytest.mark.parametrize("minor", [0, 1, 2, 3, 4])
    def test_insert_move_copy_replace_remove_work_and_leave_no_id_behind(self, minor: int) -> None:
        """LIBIPYNB-Q66 Gate-G2 CRITICAL review finding: an earlier version
        of this test only asserted `.applied`/no-`id` at each step, which
        stayed green even when a later step silently operated on the
        WRONG physical cell (reproduced live: content-identical cells'
        ephemeral ids drifted to a different cell when re-derived fresh
        from content on every call). Every assertion below now also
        checks cell *content* by position, not just outcome flags -- see
        test_ephemeral_id_stays_bound_to_the_same_physical_cell_across_
        content_duplicates below for the dedicated identity-stability
        regression test."""
        document = _document_without_ids(minor)
        editor = edit_cells(document)

        def _sources() -> list[object]:
            return [cell.get("source") for cell in document.raw["cells"]]

        insert_report = editor.insert(
            {"cell_type": "markdown", "metadata": {}, "source": "New"}, index=1
        )
        assert insert_report.applied
        assert "id" not in insert_report.changes[0].after
        assert _sources() == ["value = 1", "New", "Explanation", ["raw ", "content"]]
        new_id = insert_report.changes[0].cell_id

        assert editor.move(new_id, 0).applied
        assert _sources() == ["New", "value = 1", "Explanation", ["raw ", "content"]]

        copy_report = editor.copy(new_id)
        assert copy_report.applied
        assert "id" not in copy_report.changes[0].after
        # The copy is now content-identical to the original -- exactly
        # the scenario that broke identity tracking pre-fix.
        assert _sources() == ["New", "New", "value = 1", "Explanation", ["raw ", "content"]]

        replace_report = editor.replace(
            new_id, {"cell_type": "raw", "metadata": {}, "source": "replacement"}
        )
        assert replace_report.applied
        assert "id" not in replace_report.changes[0].after
        # `new_id` must still resolve to the ORIGINAL cell (now first),
        # not the copy created a step ago -- the copy survives untouched.
        assert _sources() == ["replacement", "New", "value = 1", "Explanation", ["raw ", "content"]]

        assert editor.remove(new_id).applied
        # The replaced-then-removed original is gone; the copy (and every
        # untouched fixture cell) survives.
        assert _sources() == ["New", "value = 1", "Explanation", ["raw ", "content"]]

        assert all("id" not in cell for cell in document.raw["cells"])
        _valid(document)  # independent oracle: the real nbformat package agrees

    @pytest.mark.parametrize("minor", [0, 1, 2, 3, 4])
    def test_ephemeral_id_stays_bound_to_the_same_physical_cell_across_content_duplicates(
        self, minor: int
    ) -> None:
        """LIBIPYNB-Q66 Gate-G2 CRITICAL review finding, dedicated
        regression test: two content-identical cells, capture an id for
        the one at position 0 (via insert(), the only way the public API
        exposes an id for a pre-existing-by-then cell), move it to
        position 1 -- the id must still resolve to the SAME physical cell
        it originally identified, not to whatever now occupies position 0.
        Reproduced live pre-fix: recomputing ephemeral ids fresh from
        content on every call reassigned the captured id back to position
        0 after the swap -- a different physical cell, no error raised."""
        document = NotebookDocument(
            {"nbformat": 4, "nbformat_minor": minor, "metadata": {}, "cells": []}
        )
        editor = edit_cells(document)
        editor.insert(
            {
                "cell_type": "code",
                "metadata": {},
                "source": "DUP",
                "execution_count": None,
                "outputs": [],
            }
        )
        first_report = editor.insert(
            {
                "cell_type": "code",
                "metadata": {},
                "source": "DUP",
                "execution_count": None,
                "outputs": [],
            },
            index=0,
        )
        # first_report's cell is now at position 0 (inserted there); the
        # first-inserted "DUP" cell is now at position 1.
        captured_id = first_report.changes[0].cell_id

        assert editor.move(captured_id, 1).applied

        replace_report = editor.replace(
            captured_id, {"cell_type": "markdown", "metadata": {}, "source": "REPLACED"}
        )
        assert replace_report.applied
        assert [cell.get("source") for cell in document.raw["cells"]] == ["DUP", "REPLACED"]

    @pytest.mark.parametrize("minor", [0, 1, 2, 3, 4])
    def test_batch_methods_direct_return_values_leave_no_id_behind(self, minor: int) -> None:
        """LIBIPYNB-Q66 Gate-G2 round-2 review finding: `CellEditBatch.
        changes` and the final committed `CellEditReport` both stripped
        ephemeral ids, but each individual batch method's own DIRECT
        return value (`batch.insert(...)`, `batch.move(...)`, etc.) did
        not -- a caller capturing that return value instead of reading
        `.changes` afterward still saw the raw ephemeral id. Reproduced
        live pre-fix for every mutating batch method before this test was
        written."""
        document = _document_without_ids(minor)
        editor = edit_cells(document)

        with editor.batch() as batch:
            insert_result = batch.insert({"cell_type": "markdown", "metadata": {}, "source": "New"})
            assert "id" not in insert_result.after
            new_id = insert_result.cell_id

            move_result = batch.move(new_id, 0)
            assert move_result is not None
            assert "id" not in move_result.before
            assert "id" not in move_result.after

            copy_result = batch.copy(new_id)
            assert "id" not in copy_result.after

            replace_result = batch.replace(
                new_id, {"cell_type": "raw", "metadata": {}, "source": "R"}
            )
            assert replace_result is not None
            assert "id" not in replace_result.before
            assert "id" not in replace_result.after

            remove_result = batch.remove(new_id)
            assert "id" not in remove_result.before

        assert all("id" not in cell for cell in document.raw["cells"])

    @pytest.mark.parametrize("minor", [0, 1, 2, 3, 4])
    def test_edits_round_trip_preserving_declared_version_and_no_id(self, minor: int) -> None:
        document = _document_without_ids(minor)
        editor = edit_cells(document)
        editor.insert(
            {
                "cell_type": "code",
                "metadata": {},
                "source": "z = 1",
                "execution_count": None,
                "outputs": [],
            }
        )

        text = dumps(document, profile="declared")
        reloaded = loads(text, mode="strict")

        assert reloaded.nbformat_minor == minor
        assert all("id" not in cell for cell in reloaded.raw["cells"])

    def test_4_5_document_behavior_is_unchanged_and_still_requires_a_valid_id(self) -> None:
        """Confirms the version gate above didn't loosen anything for
        >=4.5 documents: a caller-supplied cell for insert() must still
        carry a valid id, exactly as before this fix."""
        document = _document()
        editor = edit_cells(document)

        with pytest.raises(ValueError, match="cell ID"):
            editor.insert({"cell_type": "markdown", "metadata": {}, "source": "no id"})

    def test_real_4_0_through_4_4_fixtures_are_editable(self) -> None:
        """Live-reproduced against the actual shipped fixtures, not just a
        minimal synthetic document -- the exact files the original bug
        report reproduced against."""
        from pathlib import Path

        fixtures = Path(__file__).resolve().parent.parent / "fixtures" / "valid"
        for minor in range(5):
            document = NotebookDocument.from_file(str(fixtures / f"nbformat-4-{minor}.ipynb"))

            editor = edit_cells(document)  # must not raise
            report = editor.insert(
                {
                    "cell_type": "code",
                    "metadata": {},
                    "source": "print('ok')",
                    "execution_count": None,
                    "outputs": [],
                }
            )

            assert report.applied, minor
            _valid(document)
