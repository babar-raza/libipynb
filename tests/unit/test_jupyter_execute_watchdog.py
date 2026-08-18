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

from libipynb.adapters.jupyter_execute import _TotalTimeoutExceeded, _Tracker


def _tracker(**overrides: object) -> _Tracker:
    base: dict[str, object] = {
        "on_event": None,
        "cell_timeout": 1.0,
        "interrupt_on_timeout": True,
        "total_timeout": None,
    }
    base.update(overrides)
    return _Tracker(**base)  # type: ignore[arg-type]


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
