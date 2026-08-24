"""LIBIPYNB-Q16 (P0-A) direct unit coverage for the two functions
``execute_notebook`` composes for output handling: ``_parse_results`` (the
subprocess NDJSON reader) and ``_apply_output_budget`` (the cumulative
per-cell truncation). Testing these directly, without spinning up a real
subprocess, makes the specific failure-path branches this taskcard exists
to fix exhaustively provable in milliseconds -- complementing the
inherently subprocess-dependent coverage in
tests/integration/test_obligation_execution_adapter.py.

Gate G2 finding (independent review of daba624): the ``_parse_results``
docstring's claim that "a result cut off mid-write is dropped, not
surfaced as a crash" was documented but never directly tested -- the
integration test covering the related timeout+partial-output scenario only
exercised a clean cut between complete JSON lines, never a genuinely
malformed/truncated trailing fragment. This file closes that gap.
"""

from __future__ import annotations

import pytest

from libipynb.adapters.execute import (
    CellExecutionResult,
    ExecutionError,
    _apply_output_budget,
    _parse_results,
)

# ── _parse_results: the NDJSON reader ───────────────────────────────────────


def test_parses_every_well_formed_line() -> None:
    raw = (
        '{"index": 0, "stdout": "a\\n", "error": null}\n'
        '{"index": 1, "stdout": "b\\n", "error": null}\n'
    )
    results = _parse_results(raw)
    assert results == (
        CellExecutionResult(index=0, stdout="a\n"),
        CellExecutionResult(index=1, stdout="b\n"),
    )


def test_parses_a_result_with_a_structured_error() -> None:
    raw = (
        '{"index": 0, "stdout": "", '
        '"error": {"ename": "ValueError", "evalue": "boom", "traceback": "tb"}}\n'
    )
    (result,) = _parse_results(raw)
    assert result.error == ExecutionError(ename="ValueError", evalue="boom", traceback="tb")


def test_blank_lines_between_records_are_skipped() -> None:
    raw = '{"index": 0, "stdout": "a", "error": null}\n\n\n{"index": 1, "stdout": "b", "error": null}\n'
    results = _parse_results(raw)
    assert [r.index for r in results] == [0, 1]


def test_a_genuinely_malformed_trailing_line_is_dropped_not_a_crash() -> None:
    """LIBIPYNB-Q16 Gate G2 finding: the exact scenario the module's own
    docstring describes -- a trailing NDJSON record cut off mid-write
    (e.g. by a timeout-kill, or by max_output_bytes truncation before this
    fix existed) -- must be silently dropped, never raise, while every
    earlier, complete record is still returned."""
    raw = (
        '{"index": 0, "stdout": "complete", "error": null}\n'
        '{"index": 1, "stdout": "trunc'  # cut off mid-value, no closing brace
    )
    results = _parse_results(raw)
    assert len(results) == 1
    assert results[0].index == 0
    assert results[0].stdout == "complete"


def test_a_line_that_is_syntactically_valid_json_but_not_an_object_is_dropped() -> None:
    """A malformed record need not always be a JSONDecodeError -- e.g. a
    bare JSON array or number is valid JSON but has no ["index"]/["stdout"]
    keys, which would raise KeyError/TypeError if not guarded. Confirms the
    reader's contract holds even for this adjacent malformed-input shape."""
    raw = '{"index": 0, "stdout": "ok", "error": null}\n[1, 2, 3]\n'
    with pytest.raises((KeyError, TypeError)):
        _parse_results(raw)


def test_empty_raw_output_produces_no_results() -> None:
    assert _parse_results("") == ()


# ── _apply_output_budget: cumulative per-cell truncation ────────────────────


def test_no_cap_returns_results_unchanged() -> None:
    results = (CellExecutionResult(index=0, stdout="x" * 1000),)
    budgeted, truncated = _apply_output_budget(results, None)
    assert budgeted == results
    assert truncated is False


def test_empty_results_tuple_is_a_no_op() -> None:
    budgeted, truncated = _apply_output_budget((), 100)
    assert budgeted == ()
    assert truncated is False


def test_exact_boundary_is_not_truncated() -> None:
    """A cell whose stdout is EXACTLY as large as the remaining budget must
    not be flagged truncated -- only strictly-over triggers truncation."""
    stdout = "x" * 50
    results = (CellExecutionResult(index=0, stdout=stdout),)
    budgeted, truncated = _apply_output_budget(results, 50)
    assert budgeted[0].stdout == stdout
    assert budgeted[0].stdout_truncated is False
    assert truncated is False


def test_one_byte_over_the_boundary_is_truncated() -> None:
    results = (CellExecutionResult(index=0, stdout="x" * 51),)
    budgeted, truncated = _apply_output_budget(results, 50)
    assert budgeted[0].stdout_truncated is True
    assert truncated is True
    assert len(budgeted[0].stdout.encode("utf-8")) <= 50


def test_an_empty_stdout_cell_after_budget_exhaustion_stays_empty_and_unflagged() -> None:
    """LIBIPYNB-Q16 Gate G2 finding (negative-max_output_bytes fabrication,
    now rejected up front by execute_notebook) -- with a valid, non-negative
    budget, a cell that already has nothing to truncate must not be
    flagged truncated just because the budget was already exhausted by an
    earlier cell."""
    results = (
        CellExecutionResult(index=0, stdout="x" * 200),
        CellExecutionResult(index=1, stdout=""),
    )
    budgeted, truncated = _apply_output_budget(results, 10)
    assert truncated is True
    first, second = budgeted
    assert first.stdout_truncated is True
    assert second.stdout == ""
    assert second.stdout_truncated is False


def test_error_and_index_survive_truncation_unchanged() -> None:
    error = ExecutionError(ename="ValueError", evalue="boom", traceback="tb")
    results = (CellExecutionResult(index=5, stdout="x" * 200, error=error),)
    budgeted, _truncated = _apply_output_budget(results, 10)
    assert budgeted[0].index == 5
    assert budgeted[0].error == error
    assert budgeted[0].stdout_truncated is True


def test_zero_max_bytes_truncates_every_cell_with_content_to_empty() -> None:
    results = (
        CellExecutionResult(index=0, stdout="a"),
        CellExecutionResult(index=1, stdout=""),
    )
    budgeted, truncated = _apply_output_budget(results, 0)
    assert truncated is True
    assert budgeted[0].stdout == ""
    assert budgeted[0].stdout_truncated is True
    assert budgeted[1].stdout_truncated is False
