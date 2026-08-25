"""Regression control for LIBIPYNB-Q2's independent per-cell timeout
watchdog (see adapters/jupyter_execute.py's ``_Tracker`` docstring for the
full design rationale): a ``threading.Timer``-based mechanism that
observes, independently of nbclient's own exception shape, whether a cell
exceeded its ``cell_timeout`` budget -- necessary because nbclient raises no
exception at all for a genuine timeout under ``interrupt_on_timeout=True``.

This file tests the *lock-ordering invariant* directly -- whichever of
``_on_watchdog_fire``/``on_cell_executed`` "wins" the race for a given cell
index must produce the correct, race-condition-free outcome regardless of
order. Calling both methods synchronously and directly (never spinning up a
real ``threading.Timer``) makes this specific invariant exhaustively
provable in milliseconds, independent of the inherently timing-dependent
real-kernel coverage in
tests/integration/test_obligation_jupyter_execution_adapter.py.
"""

from __future__ import annotations

import time
from types import SimpleNamespace

from libipynb import NotebookDocument
from libipynb.adapters.jupyter_execute import _finish, _TotalTimeoutExceeded, _Tracker
from libipynb.execution import ExecutionOptions


def _tracker(**overrides: object) -> _Tracker:
    base: dict[str, object] = {
        "on_event": None,
        "cell_timeout": 1.0,
        "interrupt_on_timeout": True,
        "total_timeout": None,
    }
    base.update(overrides)
    return _Tracker(**base)  # type: ignore[arg-type]


def _one_code_cell_document() -> NotebookDocument:
    return NotebookDocument(
        {
            "nbformat": 4,
            "nbformat_minor": 5,
            "metadata": {},
            "cells": [
                {
                    "cell_type": "code",
                    "id": "c",
                    "metadata": {},
                    "execution_count": None,
                    "outputs": [],
                    "source": "...",
                }
            ],
        }
    )


def test_cell_finishing_before_the_watchdog_fires_is_never_flagged() -> None:
    tracker = _tracker()
    tracker.on_cell_executed({"id": "a"}, 0)
    tracker._on_watchdog_fire(0)  # simulated late/stale fire
    assert tracker.watchdog_timed_out == set()


def test_the_watchdog_firing_before_the_cell_finishes_is_flagged() -> None:
    tracker = _tracker()
    tracker._on_watchdog_fire(0)
    assert tracker.watchdog_timed_out == {0}
    # the cell finishing afterward (e.g. nbclient's own interrupt-and-
    # continue path eventually completing the cell) must not retroactively
    # clear the watchdog's own independent finding.
    tracker.on_cell_executed({"id": "a"}, 0)
    assert tracker.watchdog_timed_out == {0}


def test_an_error_on_the_same_cell_after_a_watchdog_fire_does_not_clear_it() -> None:
    tracker = _tracker()
    tracker._on_watchdog_fire(0)
    tracker.on_cell_executed({"id": "a"}, 0)
    tracker.on_cell_error(
        {"id": "a"},
        0,
        {"content": {"ename": "KeyboardInterrupt", "evalue": "", "traceback": []}},
    )
    assert tracker.watchdog_timed_out == {0}


def test_watchdog_state_is_independent_per_cell_index() -> None:
    tracker = _tracker()
    tracker.on_cell_executed({"id": "a"}, 0)
    tracker._on_watchdog_fire(1)
    assert tracker.watchdog_timed_out == {1}


def test_cancel_pending_timer_is_a_safe_no_op_when_nothing_is_pending() -> None:
    tracker = _tracker()
    tracker.cancel_pending_timer()
    tracker.cancel_pending_timer()  # idempotent, must not raise either time


def test_total_timeout_raises_before_the_first_cell_when_already_exhausted() -> None:
    tracker = _tracker(total_timeout=0.01)
    time.sleep(0.02)
    try:
        tracker.on_cell_start({"id": "a"}, 0)
    except _TotalTimeoutExceeded:
        pass
    else:
        raise AssertionError("expected _TotalTimeoutExceeded to be raised")
    assert tracker.reached == [], "a cell that raised on_cell_start must not be recorded as reached"


def test_total_timeout_none_never_raises() -> None:
    tracker = _tracker(total_timeout=None)
    tracker.on_cell_start({"id": "a"}, 0)  # must not raise
    assert tracker.reached == [0]


def test_total_timeout_not_yet_exhausted_does_not_raise() -> None:
    tracker = _tracker(total_timeout=60.0)
    tracker.on_cell_start({"id": "a"}, 0)  # must not raise
    assert tracker.reached == [0]


# ── LIBIPYNB-Q57: _finish()'s third, timestamp-based detection path ────────
# Gate-G2 review finding: the first two detection paths (a CellTimeoutError
# exception, or this file's own watchdog above) can both miss a genuine
# timeout under real container CPU contention -- nbclient's own
# interrupt-then-report round trip can finish faster than the watchdog's
# padded fire time, and the kernel's interrupt response can surface as a
# bare KeyboardInterrupt cell error rather than CellTimeoutError. _finish()
# gained a third path that compares each cell's own recorded start/finish
# timestamps against cell_timeout, needing no live timer. Only real-kernel
# integration coverage exercised this before (inherently timing-dependent,
# per the reviewer -- "only shows up some of the time"); these two tests
# call _finish() directly with hand-set tracker.timing values, exhaustively
# provable in milliseconds, matching this file's own stated technique above
# for the sibling watchdog race. nbclient itself is never imported here --
# `_finish` only ever compares `exc` against `nbclient_exc`'s attributes via
# `isinstance`, and `exc=None` short-circuits that entirely, so a bare
# SimpleNamespace stand-in is sufficient and keeps this test free of the
# `exec` extra's real dependency.


def _stub_nbclient_exc() -> SimpleNamespace:
    return SimpleNamespace(
        CellTimeoutError=Exception, CellExecutionError=Exception, DeadKernelError=Exception
    )


def test_finish_detects_a_timeout_nbclient_itself_never_raised_for() -> None:
    """The exact scenario the fix targets: a cell that ran longer than its
    own cell_timeout budget, but nbclient raised no exception at all
    (exc=None) and the watchdog never fired either (tracker.watchdog_timed_out
    stays empty) -- both pre-existing detection paths miss this by
    construction, so only the new timestamp-comparison path can catch it."""
    tracker = _tracker(cell_timeout=1.0)
    tracker.on_cell_start({"id": "c"}, 0)
    tracker.on_cell_executed({"id": "c"}, 0)
    tracker.timing[0] = [0.0, 2.0]  # a cell that took 2s against a 1s budget

    result = _finish(
        _one_code_cell_document(),
        ExecutionOptions(acknowledge_unsandboxed=True, cell_timeout=1.0),
        {"cells": [{"outputs": [], "execution_count": 1, "metadata": {}}]},
        tracker,
        SimpleNamespace(kernel_name="python3"),
        _stub_nbclient_exc(),
        None,
    )

    assert result.timed_out is True
    assert result.timed_out_cell_index == 0
    assert result.cell_records[0].timed_out is True


def test_finish_does_not_flag_a_cell_that_finished_within_budget() -> None:
    """Negative control: same shape as the test above, but the cell's own
    recorded span is comfortably under cell_timeout -- must NOT be
    flagged, confirming the new comparison is genuinely discriminating
    and not merely always-true."""
    tracker = _tracker(cell_timeout=1.0)
    tracker.on_cell_start({"id": "c"}, 0)
    tracker.on_cell_executed({"id": "c"}, 0)
    tracker.timing[0] = [0.0, 0.1]

    result = _finish(
        _one_code_cell_document(),
        ExecutionOptions(acknowledge_unsandboxed=True, cell_timeout=1.0),
        {"cells": [{"outputs": [], "execution_count": 1, "metadata": {}}]},
        tracker,
        SimpleNamespace(kernel_name="python3"),
        _stub_nbclient_exc(),
        None,
    )

    assert result.timed_out is False
    assert result.cell_records[0].timed_out is False
