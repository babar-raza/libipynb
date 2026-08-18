"""LIBIPYNB-Q2 characterization test: pins the exact nbclient-internal
behavior the per-cell timeout watchdog design depends on, independent of
whether libipynb's own code is exercised at all.

plans/full-parity-plan.md's own dependency-addition/oracle discipline
already requires "parity" claims to be backed by an executed comparison,
not just a description (Gate G8); this file applies the same discipline to
a claim about a *dependency's own behavior* that this project's watchdog
design (see adapters/jupyter_execute.py's ``_Tracker`` docstring) is built
on top of. ``pyproject.toml`` pins only ``nbclient>=0.10``, not an exact
version -- nothing else in this repository would otherwise notice if a
future resolved nbclient version changed the behavior asserted here,
silently invalidating the watchdog's own root-cause analysis. This test
exists to fail loudly and specifically if that ever happens, rather than
the watchdog quietly becoming redundant-but-wrong.

Deliberately placed in tests/oracle/ (the schedule-gated job,
LIBIPYNB-Q13b) rather than the always-on suite: this is a dependency-
behavior tripwire, not a per-commit regression test for libipynb's own
code -- keeping it schedule-gated keeps the fast suite fast while still
making the tripwire real.
"""

from __future__ import annotations

import asyncio

import pytest


def test_interrupt_on_timeout_true_does_not_raise_celltimeouterror(nbclient_available) -> None:
    """The single most load-bearing fact behind LIBIPYNB-Q2's watchdog: a
    genuine per-cell timeout under ``interrupt_on_timeout=True`` (nbclient's
    own default) does NOT raise ``nbclient.exceptions.CellTimeoutError`` --
    it sends a kernel interrupt and continues, reporting the timeout only
    as an ordinary cell error. If this ever changes (nbclient starts
    raising ``CellTimeoutError`` in this mode too), libipynb's watchdog
    becomes redundant, not wrong -- but the assumption this test pins would
    then be stale and worth revisiting, not silently rediscovered."""
    import nbclient
    import nbformat

    # Captured via nbclient's own on_cell_error hook (execute_reply's
    # message content) -- the exact surface libipynb's `_Tracker.
    # on_cell_error` itself depends on. Deliberately NOT asserted via
    # `cell.outputs` directly: empirically, on at least one platform the
    # interrupted cell's error is reflected there as a plain stderr stream
    # output (no `ename` key at all), not the structured `error` output
    # type -- a real, previously-unknown platform/version quirk this test
    # incidentally surfaced. The message-content path is what this
    # project's code actually relies on and is stable across that quirk.
    errors: list[dict] = []

    def _on_cell_error(cell: object, cell_index: int, execute_reply: dict) -> None:
        errors.append(execute_reply["content"])

    nb = nbformat.v4.new_notebook()
    nb.cells.append(nbformat.v4.new_code_cell("import time; time.sleep(10)"))
    # allow_errors=True mirrors libipynb's own `stop_on_error=False` usage
    # of this exact scenario (ExecutionOptions.stop_on_error maps directly
    # to `allow_errors=not stop_on_error` in _build_client) -- without it,
    # the interrupted cell's own KeyboardInterrupt error raises
    # CellExecutionError instead, a different exception this test is not
    # about.
    client = nbclient.NotebookClient(
        nb,
        timeout=1,
        interrupt_on_timeout=True,
        allow_errors=True,
        kernel_name="python3",
        on_cell_error=_on_cell_error,
    )

    # Must complete WITHOUT raising CellTimeoutError -- if it does raise,
    # that alone is the regression signal this test exists to catch.
    client.execute()

    assert errors, "expected on_cell_error to fire for the interrupted cell"
    assert errors[0]["ename"] == "KeyboardInterrupt"


def test_interrupt_on_timeout_false_does_raise_celltimeouterror(nbclient_available) -> None:
    """The complementary, already-relied-upon fact: ``interrupt_on_timeout=
    False`` DOES raise ``CellTimeoutError`` deterministically -- the path
    libipynb's own ``_finish()`` already classifies without any watchdog
    help. Pinned here alongside the ``True`` case above so both halves of
    the same nbclient API are characterized together, not just the one the
    watchdog needed to work around."""
    import nbclient
    import nbclient.exceptions
    import nbformat

    nb = nbformat.v4.new_notebook()
    nb.cells.append(nbformat.v4.new_code_cell("import time; time.sleep(10)"))
    client = nbclient.NotebookClient(
        nb, timeout=1, interrupt_on_timeout=False, kernel_name="python3"
    )

    with pytest.raises(nbclient.exceptions.CellTimeoutError):
        client.execute()


def test_synchronous_execute_manages_its_own_event_loop(nbclient_available) -> None:
    """The fact that makes LIBIPYNB-Q2's rejected Option A (a libipynb-owned
    ``threading.Timer`` replacing nbclient's own timeout trait) infeasible
    for the synchronous path: ``NotebookClient.execute()`` runs perfectly
    well from a thread with no already-running asyncio event loop -- it
    manages one internally and exposes no public handle to it for a caller
    to schedule work onto from another thread. This test proves the "no
    already-running loop needed" half directly and cheaply; the "no handle
    exposed" half is a structural absence rather than a positive behavior
    to assert here, and is instead documented in this project's own Q2
    design plan (verified there by reading ``jupyter_core.utils.run_sync``
    directly)."""
    import nbclient
    import nbformat

    with pytest.raises(RuntimeError):
        asyncio.get_running_loop()  # confirms: no loop already running in this thread

    nb = nbformat.v4.new_notebook()
    nb.cells.append(nbformat.v4.new_code_cell("1 + 1"))
    client = nbclient.NotebookClient(nb, timeout=30, kernel_name="python3")

    client.execute()  # must not raise for lack of a running event loop

    assert nb.cells[0].outputs[0]["data"]["text/plain"] == "2"
