"""Regression control for a real, reproduced nbclient-internal race
(see adapters/jupyter_execute.py's execute_async docstring, and
plans/full-parity-execution-evidence.md §8/§9 for the full account):
cancelling the task wrapping ``LocalJupyterExecutor.execute_async()`` can
non-deterministically surface either ``asyncio.CancelledError`` or a
``DeadKernelError`` from nbclient, depending purely on event-loop
scheduling timing at the moment of cancellation -- because nbclient's own
``async_execute_cell`` swallows ``CancelledError`` and converts it to
``DeadKernelError`` when the cancellation happens to land on one specific
internal ``await``.

This file tests the *decision logic* libipynb uses to make its own public
contract deterministic despite that race (`_is_requested_cancellation`) --
a pure function, no kernel, no asyncio loop, milliseconds to run. This is
the fast, exhaustive half of this regression's coverage; the real-kernel
half (does the actual wiring deliver a deterministic CancelledError to a
real caller, repeatedly, under the real race) lives in
tests/integration/test_obligation_jupyter_execution_adapter.py.
"""

from __future__ import annotations

import asyncio

from libipynb.adapters.jupyter_execute import _is_requested_cancellation


def test_a_real_cancelled_error_is_always_a_requested_cancellation() -> None:
    assert _is_requested_cancellation(asyncio.CancelledError(), cancelling_count=0) is True


def test_an_unrelated_exception_with_no_cancellation_pending_is_not() -> None:
    assert _is_requested_cancellation(RuntimeError("boom"), cancelling_count=0) is False
    assert _is_requested_cancellation(ValueError("boom"), cancelling_count=0) is False


def test_the_nbclient_race_case_is_still_classified_as_cancellation() -> None:
    """The exact real-world case this function exists for: nbclient handed
    back a DeadKernelError (or any other non-CancelledError exception), but
    the task's own cancelling() counter proves a cancellation was actually
    requested and swallowed internally, not a genuine, unrelated failure."""
    dead_kernel_error = RuntimeError("Kernel died")  # stand-in; real type not needed here
    assert _is_requested_cancellation(dead_kernel_error, cancelling_count=1) is True


def test_a_genuine_unrelated_failure_during_an_unrelated_cancellation_still_counts() -> None:
    """Deliberately conservative: if cancellation was requested at all, any
    exception surfacing afterward is treated as the cancellation outcome --
    a caller who asked to abort should get an abort-shaped response, not a
    diagnosis of what else happened to be going wrong at the same moment."""
    assert _is_requested_cancellation(RuntimeError("unrelated"), cancelling_count=1) is True


def test_multiple_pending_cancellations_still_classify_correctly() -> None:
    assert _is_requested_cancellation(RuntimeError("boom"), cancelling_count=3) is True
