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


class _FakeProcess:
    """Stands in for the real subprocess.Popen `client.km.provisioner.
    process` at fire time -- `_kill_process_tree` (imported from
    adapters/execute.py) only ever touches `.pid`/`.kill()` on it, both
    provided here, so no real OS process is involved in these tests."""

    def __init__(self, pid: int = 999_999) -> None:
        self.pid = pid
        self.killed = False

    def kill(self) -> None:
        self.killed = True


def _fake_client(process: _FakeProcess) -> SimpleNamespace:
    return SimpleNamespace(km=SimpleNamespace(provisioner=SimpleNamespace(process=process)))


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


# ── LIBIPYNB-Q2b: hard-kill escalation ──────────────────────────────────────
# Same technique as the watchdog race tests above: `_on_watchdog_fire`/
# `_on_hard_kill_fire` are called directly and synchronously, never via a
# real threading.Timer wait, so the lock-ordering invariants below are
# exhaustively provable in milliseconds. `_kill_process_tree` (imported
# from adapters/execute.py, unchanged by this taskcard) is exercised for
# real against a `_FakeProcess` stand-in -- no real kernel is involved.


def test_watchdog_fire_arms_a_hard_kill_timer_when_grace_period_is_set() -> None:
    tracker = _tracker(hard_kill_grace_period=5.0)
    tracker._on_watchdog_fire(0)
    assert tracker.watchdog_timed_out == {0}
    assert tracker._active_timer is not None
    assert tracker._active_timer_index == 0
    tracker._active_timer.cancel()  # never let the real 5s timer actually fire in this test


def test_watchdog_fire_does_not_arm_a_hard_kill_timer_when_grace_period_is_none() -> None:
    tracker = _tracker(hard_kill_grace_period=None)
    tracker._on_watchdog_fire(0)
    assert tracker.watchdog_timed_out == {0}
    assert tracker._active_timer is None


def test_watchdog_fire_does_not_arm_a_hard_kill_timer_for_a_stale_fire() -> None:
    """A cell that already finished before the (stale) watchdog fire must
    not arm a hard-kill timer either -- the existing `finished` check
    short-circuits before the new arming logic runs."""
    tracker = _tracker(hard_kill_grace_period=5.0)
    tracker.on_cell_executed({"id": "a"}, 0)
    tracker._on_watchdog_fire(0)
    assert tracker._active_timer is None


def test_hard_kill_fire_kills_the_kernel_process_and_sets_hard_killed() -> None:
    process = _FakeProcess()
    tracker = _tracker(hard_kill_grace_period=5.0)
    tracker.set_client(_fake_client(process))

    tracker._on_hard_kill_fire(0)

    assert tracker.hard_killed is True
    assert process.killed is True


def test_hard_kill_fire_is_a_stale_no_op_if_the_cell_already_finished() -> None:
    """The cell completed during the grace period (e.g. nbclient's own
    interrupt eventually succeeded) -- must not kill a live, already-
    reused kernel process."""
    process = _FakeProcess()
    tracker = _tracker(hard_kill_grace_period=5.0)
    tracker.set_client(_fake_client(process))
    tracker.on_cell_executed({"id": "a"}, 0)

    tracker._on_hard_kill_fire(0)

    assert tracker.hard_killed is False
    assert process.killed is False


def test_hard_kill_fire_does_not_raise_if_the_client_was_never_set() -> None:
    """Defensive-only: set_client is always called by _build_client before
    any cell can execute, so this should never happen in practice -- but
    _on_hard_kill_fire must degrade to "nothing to kill" rather than crash
    this Timer's own daemon thread if it somehow did."""
    tracker = _tracker(hard_kill_grace_period=5.0)

    tracker._on_hard_kill_fire(0)  # must not raise

    assert tracker.hard_killed is True


def test_hard_kill_fire_does_not_raise_if_the_kernel_manager_was_torn_down() -> None:
    """Gate-G2 review finding: an execute_async cancellation racing in at
    almost the same instant as this fire can null out client.km (nbclient's
    own _async_cleanup_kernel does exactly this as part of ordinary
    teardown) -- must degrade, not raise an unguarded AttributeError."""
    tracker = _tracker(hard_kill_grace_period=5.0)
    tracker.set_client(SimpleNamespace(km=None))

    tracker._on_hard_kill_fire(0)  # must not raise

    assert tracker.hard_killed is True


def test_hard_kill_fire_does_not_raise_if_the_provisioner_process_was_torn_down() -> None:
    """Same race, one layer deeper: jupyter_client's LocalProvisioner.wait()
    sets provisioner.process = None during ordinary teardown."""
    tracker = _tracker(hard_kill_grace_period=5.0)
    tracker.set_client(
        SimpleNamespace(km=SimpleNamespace(provisioner=SimpleNamespace(process=None)))
    )

    tracker._on_hard_kill_fire(0)  # must not raise

    assert tracker.hard_killed is True


def test_hard_kill_state_is_independent_per_cell_index() -> None:
    process = _FakeProcess()
    tracker = _tracker(hard_kill_grace_period=5.0)
    tracker.set_client(_fake_client(process))
    tracker.on_cell_executed({"id": "a"}, 0)

    tracker._on_hard_kill_fire(1)  # a different cell than the one that finished

    assert tracker.hard_killed is True
    assert process.killed is True


def test_cancel_pending_timer_cancels_a_still_pending_hard_kill_timer() -> None:
    """The watchdog's own fire re-arms `_active_timer` to the hard-kill
    timer (see the class docstring); the pre-existing cancel_pending_timer
    -- called from every exit path -- must therefore already cancel it too,
    with no changes needed to cancel_pending_timer itself."""
    tracker = _tracker(hard_kill_grace_period=5.0)
    tracker._on_watchdog_fire(0)
    hard_kill_timer = tracker._active_timer
    assert hard_kill_timer is not None

    tracker.cancel_pending_timer()

    assert hard_kill_timer.finished.is_set() is True
    assert tracker._active_timer is None


def test_finish_surfaces_tracker_hard_killed_on_the_result() -> None:
    tracker = _tracker(cell_timeout=1.0, hard_kill_grace_period=2.0)
    tracker.set_client(_fake_client(_FakeProcess()))
    tracker.on_cell_start({"id": "c"}, 0)
    tracker._on_watchdog_fire(0)
    tracker._on_hard_kill_fire(0)

    result = _finish(
        _one_code_cell_document(),
        ExecutionOptions(
            acknowledge_unsandboxed=True, cell_timeout=1.0, hard_kill_grace_period=2.0
        ),
        {"cells": [{"outputs": [], "execution_count": None, "metadata": {}}]},
        tracker,
        SimpleNamespace(kernel_name="python3"),
        _stub_nbclient_exc(),
        None,
    )

    assert result.hard_killed is True


def test_finish_reports_hard_killed_false_when_no_escalation_happened() -> None:
    tracker = _tracker(cell_timeout=1.0, hard_kill_grace_period=2.0)
    tracker.on_cell_start({"id": "c"}, 0)
    tracker.on_cell_executed({"id": "c"}, 0)

    result = _finish(
        _one_code_cell_document(),
        ExecutionOptions(
            acknowledge_unsandboxed=True, cell_timeout=1.0, hard_kill_grace_period=2.0
        ),
        {"cells": [{"outputs": [], "execution_count": 1, "metadata": {}}]},
        tracker,
        SimpleNamespace(kernel_name="python3"),
        _stub_nbclient_exc(),
        None,
    )

    assert result.hard_killed is False


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
