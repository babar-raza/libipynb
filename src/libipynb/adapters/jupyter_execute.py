"""Real Jupyter-kernel-protocol execution backend (LIBIPYNB-P4a-1/P4b/P4c).

plans/full-parity-plan.md Gate G6 sign-off (§7, 2026-08-17): this module is
the maintainer-authorized, opt-in second execution backend alongside the
pre-existing, still-default subprocess adapter (:mod:`libipynb.adapters.
execute`). Neither replaces the other -- see that module's own docstring
and this plan's §9 ("why P4 is 'add an engine,' not 'replace the engine'").

Backend choice (mission's Option A vs. B vs. C, decided here, not deferred):
``nbclient`` (Option A) over hand-rolling the Jupyter messaging protocol
directly against ``jupyter_client`` (Option B). ``nbclient`` already
implements the full ``execute_request``/``execute_reply``/iopub cycle,
busy/idle tracking, parent-message correlation, ``clear_output``, display-
id updates, per-cell and kernel-startup timeouts with interrupt-on-timeout,
and structured exceptions for the failure modes this module needs
(``CellExecutionError``, ``CellTimeoutError``, ``DeadKernelError``) --
verified directly against the installed ``nbclient==0.11.0`` source in this
environment's own ``.venv`` (not assumed from memory, per this project's own
evidence-over-recollection discipline), not merely from its README. Hand-
rolling that protocol (Option B) would duplicate a well-tested, actively
maintained implementation for no fidelity gain and a large, ongoing
protocol-maintenance burden -- rejected. A sandboxed/remote backend (Option
C) is deliberately out of scope for *this* module; ``libipynb.execution.
protocol.NotebookExecutor`` exists precisely so such a backend could be
added later as a sibling to this one without changing the public contract.

This module is never imported by ``libipynb``'s top-level ``__init__``, nor
by anything under ``codec``/``model``/``validation``, nor at module level by
anything that imports ``nbclient``/``jupyter_client``/``nbformat`` outside
function bodies here -- ``tests/unit/test_import_boundary.py`` carries a
narrow, self-testing exception scoped to exactly this one file (mirroring
the existing ``subprocess``-import allowlist pattern in
``tests/integration/test_obligation_security_baseline.py``).

Fidelity strategy: rather than round-tripping the whole notebook through
``nbformat.writes()`` (which would risk nbformat's own writer normalizing
``source`` from a string to a list-of-lines -- a real, already-documented
divergence found for a *different* reference tool, ``nbstripout``, in this
project's own oracle-comparison work), this module builds a transformed
*execution copy* of the document's raw dict, executes that copy through
``nbclient``, and then harvests only ``outputs``/``execution_count``
(and, if ``record_timing`` is enabled, ``metadata.execution``) back onto a
deep copy of the *original* raw dict, cell-by-cell, by index. Every other
key -- ``source`` in whatever form it was read, cell ``id``, attachments,
unknown extension metadata, notebook-level metadata -- is never touched and
therefore cannot be lost or reshaped by this module.

One exception, scoped to the execution copy only (LIBIPYNB-Q1): list-of-lines
``source`` -- the standard on-disk Jupyter form -- is joined into a plain
string on the execution copy before handing it to ``nbformat.from_dict()``,
because nbclient itself requires ``cell.source`` to support ``.strip()``.
This never touches the original ``document.raw``/the harvested result's
``source`` field, which stays exactly as read, per the fidelity guarantee
above.

Cancellation determinism (``execute_async`` only -- there is no equivalent
concept for the synchronous ``execute()``, which has no enclosing
``asyncio.Task`` a caller could cancel): the installed ``nbclient==0.11.0``
has its own internal race between an external cancellation and its
watchdog-driven dead-kernel detection -- ``async_execute_cell`` contains
``except asyncio.CancelledError: raise DeadKernelError("Kernel died") from
None`` around one specific internal ``await``
(``self.task_poll_for_reply``), on the assumption that only nbclient's own
watchdog task can cancel it. That assumption is false once an *external*
caller cancels the task wrapping the whole ``execute_async()`` call:
whether the resulting ``CancelledError`` lands on that exact ``await`` (and
gets silently converted to ``DeadKernelError``) or somewhere else (and
propagates normally) depends purely on event-loop scheduling timing --
confirmed by direct, repeated reproduction: the identical test surfaced
``asyncio.CancelledError`` on most runs and a completed ``ExecutionResult``
with ``kernel_death_error`` set on others, non-deterministically, with no
code change in between. Left alone, that non-determinism leaks straight
through this module's own public contract, making "except
asyncio.CancelledError" unreliable for any caller of ``execute_async()``.

Fixed by consulting the task's own cancellation bookkeeping
(``Task.cancelling()``, Python 3.11+ -- this project's floor) instead of
pattern-matching on whichever exception nbclient's race happens to
produce: see ``_is_requested_cancellation`` and its call site in
``execute_async`` below. This does not fix nbclient's own internal bug --
it cannot, from outside -- it guarantees this module's own contract is
deterministic regardless: cancelling the task always raises
``asyncio.CancelledError`` to the caller, never a normal result. If a
future ``nbclient`` release changes this internal behavior, this code
remains correct (the extra check is simply never triggered) but this
specific finding becomes stale documentation, not a live bug -- flagged
here rather than left to be silently rediscovered.
"""

from __future__ import annotations

import copy
import threading
import time
from typing import TYPE_CHECKING, Any

from .._internal.text import truncate_utf8_text
from ..errors import NotebookExecutionError
from ..model.document import NotebookDocument

# LIBIPYNB-Q2b: reuses (does not duplicate) the subprocess adapter's own
# already-tested process-tree kill logic for the hard-kill escalation
# below. Safe at module level, unlike an `..execution` import (see the
# NOTE below): `.execute` is a *sibling* submodule of this one within
# `adapters`, is pure-stdlib, and itself imports nothing from
# `jupyter_execute`/`..execution` -- no cycle, and importing it never
# requires nbclient/jupyter_client to be installed (confirmed by
# tests/unit/test_execution_core_independence.py, which hides those
# modules and still expects this file to import cleanly).
from .execute import _kill_process_tree

if TYPE_CHECKING:
    from ..execution.options import ExecutionOptions
    from ..execution.results import (
        CellExecutionRecord,
        ExecutionCellError,
        ExecutionResult,
    )

# NOTE on import direction: libipynb.execution's own __init__ imports
# LocalJupyterExecutor FROM this module (so `from libipynb.execution import
# LocalJupyterExecutor` works, per this feature's public API). This module
# must therefore never import anything from `..execution` at module load
# time -- doing so would close a real circular-import loop (reproduced
# directly: `import libipynb.adapters` -> this file -> `..execution` ->
# `libipynb.adapters.jupyter_execute` again, still mid-load -> ImportError).
# Every reference to an `..execution` name below is deferred to call time
# instead (a plain `import` statement inside a function body), which is
# always safe here because by the time any of these functions actually
# *run*, module-level circular-import resolution has already finished.


# LIBIPYNB-Q2: deliberate positive skew added to the watchdog's own
# per-cell deadline, on top of nbclient's own rounded `cell_timeout`, so
# the watchdog's `threading.Timer` can only fire AFTER nbclient's own
# timeout mechanism would already be acting -- see `_Tracker.
# _start_watchdog` for the full reasoning. These constants are a reasoned
# starting point, not an empirically validated one: verified directly that
# kernel-interrupt delivery is a genuinely different code path on POSIX
# (a real OS signal, `os.killpg`) vs. Windows (a named event the kernel
# process polls for, `jupyter_client.provisioning.local_provisioner.
# LocalProvisioner.send_signal`'s own Windows branch) -- their relative
# latency has not been measured on either platform. A too-small skew risks
# a false positive (reporting a timeout that did not happen); a too-large
# skew only ever delays detection, never produces an incorrect result --
# the deliberately safer failure direction.
_WATCHDOG_MIN_SKEW_SECONDS = 0.25
_WATCHDOG_SKEW_FRACTION = 0.05


class _TotalTimeoutExceeded(Exception):
    """LIBIPYNB-Q2: raised from `_Tracker.on_cell_start` when
    `ExecutionOptions.total_timeout` has already elapsed before the next
    cell would start. `nbclient.util.run_hook` does not catch hook
    exceptions (verified directly against the installed nbclient source),
    so this propagates up through `NotebookClient.async_execute`'s own
    cell loop and aborts the run before that cell is sent to the kernel --
    a "soft" bound only: it never aborts a cell already in flight,
    including the last one in a run (see `ExecutionOptions.total_timeout`'s
    own docstring for why this does not close the unbounded-hang gap
    tracked separately as LIBIPYNB-Q2b)."""


def _import_backend() -> tuple[Any, Any, Any]:
    """Import nbclient/nbformat lazily, at call time, never at module load.

    Returns ``(nbclient_module, nbformat_module, exceptions_module)`` so
    callers don't each re-import.
    """
    from ..execution.exceptions import MissingExecutionDependencyError

    try:
        import nbclient
        import nbclient.exceptions as nbclient_exceptions
        import nbformat
    except ImportError as exc:
        raise MissingExecutionDependencyError(
            "LocalJupyterExecutor requires the 'exec' extra: "
            'pip install "libipynb[exec]" (needs jupyter_client and nbclient, '
            "plus at least one installed Jupyter kernel, e.g. ipykernel)."
        ) from exc
    return nbclient, nbformat, nbclient_exceptions


class LocalJupyterExecutor:
    """Runs a notebook through a real, locally installed Jupyter kernel via
    ``nbclient``. See :mod:`libipynb.execution` for the security posture
    (trusted local execution, not a sandbox) and the full option/result
    contract.

    Requires the ``exec`` extra: ``pip install "libipynb[exec]"``. Raises
    :class:`~libipynb.execution.exceptions.MissingExecutionDependencyError`
    at construction time -- not on first use, and not a bare
    ``ImportError`` -- if the extra is not installed, so the failure is
    immediate, structured, and actionable.
    """

    def __init__(self) -> None:
        _import_backend()

    def execute(
        self,
        document: NotebookDocument,
        *,
        options: ExecutionOptions | None = None,
    ) -> ExecutionResult:
        from ..execution.options import ExecutionOptions as _Options

        resolved = options or _Options()
        _check_preflight(resolved)
        nbclient_mod, nbformat_mod, nbclient_exc = _import_backend()
        client, nb_node, tracker = _build_client(document, resolved, nbclient_mod, nbformat_mod)
        start_kwargs = client._libipynb_extra_start_kwargs
        # LIBIPYNB-Q2: this used to catch `BaseException`, silently
        # swallowing KeyboardInterrupt/SystemExit -- confirmed live: a
        # caller's own Ctrl+C could not interrupt a hung synchronous
        # execute() call, because the interrupt was routed into _finish()
        # and returned as a structured (completed=False) result instead of
        # propagating. _finish()'s own classification below already has a
        # catch-all "unrecognized failure mode" branch for any Exception
        # subtype it doesn't specifically name, so narrowing to `except
        # Exception` loses no other behavior. Contrast with
        # execute_async() above, whose `except BaseException` IS
        # deliberate and must not be narrowed the same way: it specifically
        # needs to observe `asyncio.CancelledError` (a BaseException
        # subclass) to run its own documented cancellation-cleanup path.
        try:
            client.execute(**start_kwargs)
        except Exception as exc:  # noqa: BLE001 -- classified below, never re-raised bare
            return _finish(document, resolved, nb_node, tracker, client, nbclient_exc, exc)
        except BaseException:
            # LIBIPYNB-Q2: KeyboardInterrupt/SystemExit deliberately
            # propagate past this method (see comment above) without ever
            # reaching _finish() -- cancel any still-armed watchdog timer
            # explicitly here, mirroring execute_async's own cancellation-
            # branch cleanup, so this BaseException exit path can never
            # leave a timer un-cancelled either. Found by an independent
            # Gate G2 review of this design: without this, a watchdog timer
            # armed for the cell in flight when the interrupt arrives would
            # stay un-cancelled until it harmlessly self-fires against an
            # already-orphaned _Tracker (bounded by cell_timeout+skew, no
            # resource leak) -- low severity, but a real, previously-
            # untested gap, not merely a hypothetical one.
            tracker.cancel_pending_timer()
            raise
        return _finish(document, resolved, nb_node, tracker, client, nbclient_exc, None)

    async def execute_async(
        self,
        document: NotebookDocument,
        *,
        options: ExecutionOptions | None = None,
    ) -> ExecutionResult:
        from ..execution.options import ExecutionOptions as _Options

        resolved = options or _Options()
        _check_preflight(resolved)
        nbclient_mod, nbformat_mod, nbclient_exc = _import_backend()
        client, nb_node, tracker = _build_client(document, resolved, nbclient_mod, nbformat_mod)
        start_kwargs = client._libipynb_extra_start_kwargs
        try:
            await client.async_execute(**start_kwargs)
        except BaseException as exc:
            import asyncio

            current_task = asyncio.current_task()
            cancelling_count = current_task.cancelling() if current_task is not None else 0
            if _is_requested_cancellation(exc, cancelling_count):
                # This task's own cancellation was requested -- guaranteed
                # deterministic from here, regardless of which exception
                # nbclient happened to surface. See module docstring
                # "Cancellation determinism" for the full account of why
                # `isinstance(exc, asyncio.CancelledError)` alone is not
                # sufficient: nbclient's own async_execute_cell has an
                # internal `except asyncio.CancelledError: raise
                # DeadKernelError(...) from None` around one specific await
                # (`self.task_poll_for_reply`) that assumes it can only be
                # cancelled by nbclient's own internal watchdog task -- a
                # false assumption once an external caller cancels the
                # enclosing task, which non-deterministically converts our
                # cancellation into an unrelated-looking exception depending
                # purely on event-loop scheduling timing (confirmed by
                # direct, repeated reproduction: the identical test
                # surfaced CancelledError on most runs and a completed
                # ExecutionResult with kernel_death_error set on others).
                # `Task.cancelling()` (Python 3.11+) sidesteps the race
                # entirely by asking the task's own bookkeeping "was I
                # cancelled" instead of pattern-matching on nbclient's
                # exception shape, so this module's own public contract is
                # deterministic even when the dependency it wraps is not.
                #
                # LIBIPYNB-Q2: this branch never reaches `_finish()` (it
                # raises directly below), so the watchdog's own cleanup
                # must happen here explicitly -- `_finish()` is not the
                # only exit path a pending timer needs to be cancelled on.
                tracker.cancel_pending_timer()
                #
                # The kernel must be shut down before that guaranteed
                # CancelledError propagates: verified directly that
                # nbclient's own async_setup_kernel context-manager
                # `finally` clause does NOT reliably run its kernel teardown
                # when the enclosing task is cancelled out from under
                # `await client.async_execute()` -- a real, reproduced
                # kernel-process leak (confirmed via psutil child-process
                # tracking: the kernel and its interrupt-event helper
                # process were still alive 15+ seconds after cancellation
                # with no manual cleanup). Cleaning up explicitly here,
                # before re-raising, closes that gap regardless of whether
                # nbclient's own path also runs.
                if client.km is not None:
                    try:
                        await client._async_cleanup_kernel()
                    except Exception:  # noqa: BLE001, S110 -- best-effort; must never mask CancelledError
                        pass
                    finally:
                        # LIBIPYNB-Q2: nbclient's own async_setup_kernel
                        # registers atexit.register(self._cleanup_kernel)
                        # (see module docstring above) and only unregisters
                        # it in its own successful-teardown finally/signal
                        # paths -- neither of which we go through here.
                        # Left unregistered, this hook (and the strong
                        # reference it holds to the kernel manager) stays
                        # alive for the rest of the process, producing a
                        # noisy, uncatchable "Exception ignored in atexit
                        # callback ... AssertionError" traceback at
                        # interpreter exit and accumulating on a
                        # long-running host that performs many cancelled
                        # executions. Per CPython's own atexit docs,
                        # unregister() silently no-ops if the callable was
                        # never registered or already removed, so this is
                        # always safe to call unconditionally here.
                        import atexit

                        atexit.unregister(client._cleanup_kernel)
                if isinstance(exc, asyncio.CancelledError):
                    raise
                # nbclient swallowed the real CancelledError (see above) --
                # synthesize one so this module's own contract holds
                # ("cancel the task, always get CancelledError"), keeping
                # what nbclient actually raised visible via __cause__ for
                # diagnosis rather than discarding it the way nbclient's own
                # `from None` does.
                raise asyncio.CancelledError() from exc
            return _finish(document, resolved, nb_node, tracker, client, nbclient_exc, exc)
        return _finish(document, resolved, nb_node, tracker, client, nbclient_exc, None)


def _is_requested_cancellation(exc: BaseException, cancelling_count: int) -> bool:
    """True if *exc* should be treated as this task's own requested
    cancellation having been delivered somewhere in the call chain --
    either because *exc* directly is ``asyncio.CancelledError``, or because
    the enclosing task's own cancellation counter (``Task.cancelling()``,
    Python 3.11+) is nonzero even though *exc* is something else entirely.
    The second case is real, not hypothetical: see ``execute_async``'s own
    call site for the exact nbclient-internal race that produces it. A
    pure, dependency-free function so this specific decision is unit-
    testable in milliseconds, independent of the real-kernel wiring around
    it -- the regression control for a race that is otherwise expensive and
    inherently unreliable to reproduce on demand.
    """
    import asyncio

    return isinstance(exc, asyncio.CancelledError) or cancelling_count > 0


def _check_preflight(options: ExecutionOptions) -> None:
    if not options.acknowledge_unsandboxed:
        raise NotebookExecutionError(
            "LocalJupyterExecutor is not a sandbox: the kernel runs with this "
            "process's own permissions -- it can read/write files, start "
            "processes, use the network, and inspect environment variables. "
            "cell_timeout/interrupt_on_timeout are operational controls, not "
            "an isolation boundary. Pass acknowledge_unsandboxed=True to "
            "confirm you trust the notebook being executed."
        )
    if options.working_directory is not None:
        from pathlib import Path

        path = Path(options.working_directory)
        if not path.is_dir():
            raise ValueError(
                f"working_directory {options.working_directory!r} does not exist "
                "or is not a directory"
            )


class _Tracker:
    """Accumulates per-cell lifecycle state via nbclient's own hooks
    (``on_cell_start``/``on_cell_execute``/``on_cell_executed``/
    ``on_cell_error``) -- the only way to learn *which* cell was active
    when a run stops early or times out, since ``CellExecutionError``/
    ``CellTimeoutError`` carry a message but not a cell index.

    LIBIPYNB-Q2: also runs an independent, libipynb-owned per-cell watchdog
    (``threading.Timer``) alongside nbclient's own timeout handling, purely
    to OBSERVE whether a cell's wall-clock budget was exceeded -- it never
    sends any protocol message or otherwise touches the kernel itself. This
    exists because nbclient raises no exception at all for a genuine
    per-cell timeout when ``interrupt_on_timeout=True`` (the default): see
    the module docstring's own account of nbclient's internal behavior.
    All watchdog state is guarded by ``self._lock`` and is instance-scoped
    -- a fresh ``_Tracker`` is built per ``execute()``/``execute_async()``
    call (see ``_build_client``), so this state can never leak across
    concurrent or sequential runs as long as it stays on the instance.

    LIBIPYNB-Q2b: when ``hard_kill_grace_period`` is set, this is no longer
    purely observational for a cell that never finishes -- the watchdog's
    own fire (``_on_watchdog_fire``) chains a SECOND ``threading.Timer``
    (reusing the same ``self._active_timer``/``self._active_timer_index``
    slot, so the existing cancellation paths below already cancel it too),
    and if that second timer also fires, ``_on_hard_kill_fire`` force-kills
    the kernel's OS process tree directly. Live-reproduced (LIBIPYNB-Q2b
    evidence): with only the observational watchdog, a kernel that ignores
    SIGINT hangs the whole run indefinitely; the interrupt nbclient already
    sent at the watchdog's own fire point never gets anywhere for a
    genuinely uninterruptible kernel, so escalating past it is the only way
    to ever unblock the caller.

    The watchdog timer is started from ``on_cell_execute`` (fired only for
    a cell about to actually be sent to the kernel), not ``on_cell_start``
    (fired unconditionally for every cell, including markdown/raw cells,
    empty-source cells, and skip-tagged cells -- none of which ever reach
    ``on_cell_executed``/``on_cell_error``, verified directly against
    nbclient's own ``async_execute_cell``). Starting the timer from
    ``on_cell_start`` instead would leak a timer for every such cell, since
    nothing would ever cancel it.
    """

    def __init__(
        self,
        on_event: Any,
        *,
        cell_timeout: float | None = None,
        interrupt_on_timeout: bool = True,
        total_timeout: float | None = None,
        hard_kill_grace_period: float | None = None,
    ) -> None:
        self.reached: list[int] = []
        self.finished: set[int] = set()
        self.timing: dict[int, list[float | None]] = {}
        self.errors: dict[int, ExecutionCellError] = {}
        self._on_event = on_event

        self._cell_timeout = cell_timeout
        self._interrupt_on_timeout = interrupt_on_timeout
        self._total_timeout = total_timeout
        self._run_started_at = time.monotonic()

        self._lock = threading.Lock()
        self._active_timer: threading.Timer | None = None
        self._active_timer_index: int | None = None
        self.watchdog_timed_out: set[int] = set()

        # LIBIPYNB-Q2b
        self._hard_kill_grace_period = hard_kill_grace_period
        self._client: Any = None
        self.hard_killed = False

    def set_client(self, client: Any) -> None:
        """Called from ``_build_client`` right after the ``NotebookClient``
        is constructed. Cannot be a constructor argument: this ``_Tracker``
        must exist before ``NotebookClient`` does, since its hooks
        (``on_cell_execute`` etc.) are passed into that very constructor
        call. By the time any timer built from this instance could
        possibly fire, a cell is already executing, which means the kernel
        has already started and ``client.km``/``.provisioner`` are already
        populated -- so no readiness check is needed here or at fire time."""
        self._client = client

    def _emit(self, kind: str, cell: dict[str, Any], cell_index: int) -> None:
        if self._on_event is not None:
            from ..execution.results import ExecutionEvent

            self._on_event(ExecutionEvent(kind=kind, cell_index=cell_index, cell_id=cell.get("id")))

    def on_cell_start(self, cell: dict[str, Any], cell_index: int, **_kw: Any) -> None:
        if self._total_timeout is not None and (
            time.monotonic() - self._run_started_at > self._total_timeout
        ):
            raise _TotalTimeoutExceeded(
                f"total_timeout ({self._total_timeout}s) exceeded before cell "
                f"{cell_index} could start"
            )
        self.reached.append(cell_index)
        self.timing[cell_index] = [time.time(), None]
        self._emit("cell_started", cell, cell_index)

    def on_cell_execute(self, cell: dict[str, Any], cell_index: int, **_kw: Any) -> None:
        # LIBIPYNB-Q2: fires only for a cell about to actually be sent to
        # the kernel -- see the class docstring for why this, not
        # `on_cell_start`, is the correct place to start the watchdog.
        if self._cell_timeout is None or not self._interrupt_on_timeout:
            # interrupt_on_timeout=False already gets a deterministic
            # CellTimeoutError straight from nbclient (see the module
            # docstring/_finish's own classification) -- running a second,
            # redundant timer there would add risk for zero benefit.
            return
        rounded = max(1, round(self._cell_timeout))
        skew = max(_WATCHDOG_MIN_SKEW_SECONDS, _WATCHDOG_SKEW_FRACTION * rounded)
        timer = threading.Timer(rounded + skew, self._on_watchdog_fire, args=(cell_index,))
        timer.daemon = True
        with self._lock:
            self._active_timer = timer
            self._active_timer_index = cell_index
        timer.start()

    def _on_watchdog_fire(self, cell_index: int) -> None:
        # Runs on the Timer's own OS thread -- never touches the kernel,
        # only this instance's own lock-guarded state (LIBIPYNB-Q2b: unless
        # hard_kill_grace_period is set, in which case it arms a second
        # timer below that -- if IT also fires -- will touch the kernel).
        hard_kill_timer: threading.Timer | None = None
        with self._lock:
            if cell_index in self.finished:
                return  # stale fire: this cell genuinely completed in time
            self.watchdog_timed_out.add(cell_index)
            if self._hard_kill_grace_period is not None:
                # Reuses the same active-timer slot the first-stage
                # watchdog just occupied (it already fired, so it's inert)
                # -- on_cell_executed's existing _cancel_timer_for and
                # every exit path's cancel_pending_timer() therefore
                # already correctly cancel THIS timer too, with no changes
                # needed to either.
                hard_kill_timer = threading.Timer(
                    self._hard_kill_grace_period, self._on_hard_kill_fire, args=(cell_index,)
                )
                hard_kill_timer.daemon = True
                self._active_timer = hard_kill_timer
                self._active_timer_index = cell_index
        if hard_kill_timer is not None:
            hard_kill_timer.start()

    def _on_hard_kill_fire(self, cell_index: int) -> None:
        # LIBIPYNB-Q2b: runs on this second Timer's own OS thread, chained
        # from _on_watchdog_fire above. By construction this only ever
        # fires when hard_kill_grace_period was set, which
        # ExecutionOptions.__post_init__ already requires cell_timeout and
        # interrupt_on_timeout=True for -- an interrupt has therefore
        # already been sent for this cell, and it STILL hasn't finished:
        # treated as genuinely uninterruptible, not a slow-but-live kernel.
        with self._lock:
            if cell_index in self.finished:
                return  # stale fire: the cell genuinely finished during the grace period
            self.hard_killed = True
        # Deliberately outside the lock: killing a process tree can be slow
        # (subprocess.run(["taskkill", ...]) on Windows) and must never
        # block on_cell_executed/cancel_pending_timer, which also take
        # self._lock, from making progress on the client's own thread.
        #
        # Gate-G2 review finding: cancel_pending_timer()'s Timer.cancel()
        # cannot rendezvous with a fire already past the `finished` check
        # above -- an execute_async cancellation racing in at almost the
        # same instant can tear down `self._client.km`/`.provisioner.
        # process` (both genuinely set to None by nbclient's own
        # _async_cleanup_kernel / jupyter_client's LocalProvisioner.wait()
        # as part of ordinary teardown) between that check and the
        # attribute chase below. getattr-chained rather than a direct
        # `self._client.km.provisioner.process` so a real, if narrow, race
        # degrades to "nothing to kill" instead of an unguarded
        # AttributeError on this Timer's own daemon thread.
        km = getattr(self._client, "km", None)
        provisioner = getattr(km, "provisioner", None)
        process = getattr(provisioner, "process", None)
        if process is not None:
            _kill_process_tree(process)

    def cancel_pending_timer(self) -> None:
        """LIBIPYNB-Q2: cancels any still-pending watchdog timer. Must be
        called on every exit path (see ``_finish`` and
        ``execute_async``'s cancellation branch) -- ``Timer.cancel()`` on
        an already-fired timer is always a safe no-op, so calling this
        unconditionally on every exit is correct, not merely defensive."""
        with self._lock:
            timer, self._active_timer = self._active_timer, None
            self._active_timer_index = None
        if timer is not None:
            timer.cancel()

    def _cancel_timer_for(self, cell_index: int) -> None:
        with self._lock:
            if self._active_timer_index != cell_index:
                return
            timer, self._active_timer = self._active_timer, None
            self._active_timer_index = None
        if timer is not None:
            timer.cancel()

    def on_cell_executed(self, cell: dict[str, Any], cell_index: int, **_kw: Any) -> None:
        with self._lock:
            self.finished.add(cell_index)
        self._cancel_timer_for(cell_index)
        entry = self.timing.setdefault(cell_index, [None, None])
        entry[1] = time.time()
        self._emit("cell_finished", cell, cell_index)

    def on_cell_error(self, cell: dict[str, Any], cell_index: int, execute_reply: Any) -> None:
        # LIBIPYNB-Q2: nbclient always calls on_cell_executed before
        # on_cell_error for the same cell (verified directly:
        # async_execute_cell calls on_cell_executed, then
        # _check_raise_for_error -> on_cell_error, in that order) -- the
        # watchdog timer for this cell is therefore already cancelled by
        # the time this runs; no separate cancellation needed here.
        from ..execution.results import ExecutionCellError

        content = execute_reply["content"]
        self.errors[cell_index] = ExecutionCellError(
            ename=str(content.get("ename", "")),
            evalue=str(content.get("evalue", "")),
            traceback=tuple(content.get("traceback", []) or []),
        )


def _normalize_source_for_execution(cell: dict[str, Any]) -> None:
    """nbclient calls ``cell.source.strip()`` unconditionally; unlike a real
    ``nbformat.writes()``/``reads()`` round trip, ``nbformat.from_dict()``
    does NOT coerce list-of-lines source to a string, so a list-source cell
    (the standard on-disk Jupyter form) crashes the whole run with
    AttributeError before any cell executes (LIBIPYNB-Q1). Mirrors
    ``adapters/execute.py``'s own ``_cell_source()`` helper exactly. Mutates
    only the already-deep-copied execution dict -- never ``document.raw``
    (see ``_build_client``'s ``deepcopy`` above and this module's own
    "execution copy" fidelity strategy in the module docstring)."""
    value = cell.get("source", "")
    if not isinstance(value, str):
        cell["source"] = "".join(value) if isinstance(value, list) else str(value)


def _build_client(
    document: NotebookDocument,
    options: ExecutionOptions,
    nbclient_mod: Any,
    nbformat_mod: Any,
) -> tuple[Any, Any, _Tracker]:
    nb_dict = copy.deepcopy(document.raw)
    for cell in nb_dict.get("cells", []) or []:
        if isinstance(cell, dict):
            _normalize_source_for_execution(cell)
    nb_node = nbformat_mod.from_dict(nb_dict)

    tracker = _Tracker(
        options.on_event,
        cell_timeout=options.cell_timeout,
        interrupt_on_timeout=options.interrupt_on_timeout,
        total_timeout=options.total_timeout,
        hard_kill_grace_period=options.hard_kill_grace_period,
    )
    resources: dict[str, Any] = {}
    if options.working_directory is not None:
        resources["metadata"] = {"path": options.working_directory}

    kwargs: dict[str, Any] = {}
    if options.extra_env:
        import os

        kwargs["env"] = {**os.environ, **options.extra_env}

    client = nbclient_mod.NotebookClient(
        nb_node,
        kernel_name=options.kernel_name or "",
        resources=resources,
        # nbclient's own `timeout` trait is integer-seconds only; a
        # sub-second value must not round down to 0, which nbclient treats
        # as "no timeout" (the exact opposite of what a caller asking for
        # a sub-second budget intended).
        timeout=max(1, round(options.cell_timeout)) if options.cell_timeout is not None else -1,
        startup_timeout=int(options.kernel_startup_timeout),
        allow_errors=not options.stop_on_error,
        interrupt_on_timeout=options.interrupt_on_timeout,
        skip_cells_with_tag=options.skip_tag,
        record_timing=options.record_timing,
        on_cell_start=tracker.on_cell_start,
        on_cell_execute=tracker.on_cell_execute,
        on_cell_executed=tracker.on_cell_executed,
        on_cell_error=tracker.on_cell_error,
    )
    # nbclient forwards unrecognized execute()/async_execute() kwargs to
    # jupyter_client's start_kernel(); stash for the call site instead of a
    # NotebookClient trait (there isn't one for extra Popen env).
    client._libipynb_extra_start_kwargs = kwargs
    # LIBIPYNB-Q2b: must happen before this function returns -- the hard-
    # kill escalation (if armed) needs a way to reach the kernel process,
    # and this is the only point in the whole call chain that constructs
    # `client` at all.
    tracker.set_client(client)
    return client, nb_node, tracker


#: MIME types nbformat represents as base64-encoded binary data, never
#: literal text -- mirrors validation/rules.py's own established convention
#: exactly (``mime_type.startswith("image/")``, with ``image/svg+xml``
#: excluded since SVG is literal XML text per the nbformat spec, not
#: base64), plus ``application/pdf``, the other common base64-shaped output
#: MIME type nbformat notebooks carry. Anything not matched here is treated
#: as literal text and marker-truncated rather than omitted.
def _is_binary_mime_type(mime_type: str) -> bool:
    folded = mime_type.casefold()
    if folded == "application/pdf":
        return True
    return folded.startswith("image/") and folded != "image/svg+xml"


def _truncate_one_output(output: dict[str, Any], max_bytes: int) -> tuple[bool, tuple[str, ...]]:
    """Truncate/omit *output*'s oversized payloads in place.

    Returns ``(changed, omitted_mime_types)``: ``changed`` is True if any
    text payload was truncated or any binary payload was omitted;
    ``omitted_mime_types`` names every MIME key removed from ``output["data"]``
    because it was binary-shaped and oversized -- LIBIPYNB-Q17: appending a
    textual truncation marker to base64 content corrupts it into invalid
    base64 without raising (the notebook stays syntactically valid JSON
    while the image/PDF data silently becomes garbage), so an oversized
    binary representation is removed entirely rather than truncated, and the
    removal is reported structurally instead of just disappearing.
    """
    changed = False
    text = output.get("text")
    if isinstance(text, str):
        if len(text.encode("utf-8")) > max_bytes:
            output["text"] = truncate_utf8_text(text, max_bytes)
            changed = True
    elif isinstance(text, list) and all(isinstance(item, str) for item in text):
        joined = "".join(text)
        if len(joined.encode("utf-8")) > max_bytes:
            output["text"] = [truncate_utf8_text(joined, max_bytes)]
            changed = True
    data = output.get("data")
    omitted: list[str] = []
    if isinstance(data, dict):
        for mime_type, payload in list(data.items()):
            if not (isinstance(payload, str) and len(payload.encode("utf-8")) > max_bytes):
                continue
            if isinstance(mime_type, str) and _is_binary_mime_type(mime_type):
                del data[mime_type]
                omitted.append(mime_type)
            else:
                data[mime_type] = truncate_utf8_text(payload, max_bytes)
            changed = True
    return changed, tuple(omitted)


def _truncate_outputs_if_needed(
    outputs: list[dict[str, Any]], max_bytes: int | None
) -> tuple[bool, tuple[str, ...]]:
    """LIBIPYNB-Q2/Q17: truncate each output's own payload INDEPENDENTLY --
    never by slicing a combined byte stream across outputs/cells, which is
    the older subprocess engine's own confirmed bug (silently dropping
    every downstream cell's results once one cell's output pushed the
    shared stream past the byte cutoff). Truncating per-output here can
    only ever affect the one oversized output it is applied to.

    LIBIPYNB-Q17: must visit every output unconditionally -- the previous
    version used ``any(_truncate_one_output(...) for output in outputs)``,
    which short-circuits the moment the first oversized output is found,
    silently leaving every later oversized output in the same call
    untouched. An explicit loop has no such short-circuit: every output is
    always visited, regardless of what earlier ones returned.
    """
    if max_bytes is None:
        return False, ()
    changed = False
    all_omitted: list[str] = []
    for output in outputs:
        output_changed, omitted = _truncate_one_output(output, max_bytes)
        changed = changed or output_changed
        all_omitted.extend(omitted)
    return changed, tuple(all_omitted)


def _finish(
    original_document: NotebookDocument,
    options: ExecutionOptions,
    nb_node: Any,
    tracker: _Tracker,
    client: Any,
    nbclient_exc: Any,
    exc: BaseException | None,
) -> ExecutionResult:
    from ..execution.results import CellExecutionRecord, ExecutionResult

    # LIBIPYNB-Q2: unconditional, on every exit path through this function
    # -- correct regardless of whether a timer is actually pending
    # (`cancel_pending_timer` is a safe no-op when none is), and this is
    # the backstop for any nbclient-internal exception path that aborts a
    # cell before its own on_cell_executed/on_cell_error hook ever fires
    # (the per-cell hooks are the common-case cleanup; this is the
    # exceptional-case one).
    tracker.cancel_pending_timer()

    started_at = min((t[0] for t in tracker.timing.values() if t[0] is not None), default=None)
    finished_at = time.time()

    timed_out = False
    timed_out_cell_index: int | None = None
    stopped_early = False
    kernel_launch_error: str | None = None
    kernel_death_error: str | None = None
    total_timed_out = False

    if exc is not None:
        if isinstance(exc, nbclient_exc.CellTimeoutError):
            timed_out = True
            timed_out_cell_index = tracker.reached[-1] if tracker.reached else None
        elif isinstance(exc, nbclient_exc.CellExecutionError):
            stopped_early = True
        elif isinstance(exc, nbclient_exc.DeadKernelError):
            kernel_death_error = str(exc)
        elif isinstance(exc, _TotalTimeoutExceeded):
            total_timed_out = True
        elif not tracker.reached:
            # Nothing was ever reached: the kernel itself never came up
            # (missing kernelspec, startup_timeout exceeded, provisioner
            # failure, etc.) -- reported structurally, matching the
            # subprocess adapter's own kernel_launch_error field, rather
            # than raised, so callers handle both engines the same way.
            kernel_launch_error = str(exc)
        else:
            # An unrecognized failure mode reached at least one cell --
            # do not silently classify it as something it is not; surface
            # it via the same field a truly unknown backend failure would
            # use, with the real exception type named for diagnosis.
            kernel_death_error = f"{type(exc).__name__}: {exc}"

    # LIBIPYNB-Q2: additive, independent of the exc-classification above --
    # deliberately NOT gated on `ename == "KeyboardInterrupt"` string
    # matching, which is exactly the unreliable signal this watchdog
    # exists to replace. `stopped_early`/`timed_out` are NOT mutually
    # exclusive: a cell can genuinely both cause an early stop (its own
    # code caught the interrupt and re-raised under stop_on_error=True)
    # AND independently exceed its own budget -- both facts are kept, not
    # collapsed into one (see ExecutionResult's own docstring).
    if not timed_out and tracker.watchdog_timed_out:
        timed_out = True
        timed_out_cell_index = min(tracker.watchdog_timed_out)
    # LIBIPYNB-Q2: authoritative, non-lossy per-cell timeout evidence --
    # unlike timed_out_cell_index (which can only ever name one cell),
    # every cell independently confirmed as timed out is tracked here, so
    # a run with more than one such cell (possible under
    # stop_on_error=False) is never silently reduced to a single index.
    timed_out_cells: set[int] = set(tracker.watchdog_timed_out)
    if isinstance(exc, nbclient_exc.CellTimeoutError) and timed_out_cell_index is not None:
        timed_out_cells.add(timed_out_cell_index)
    # LIBIPYNB-Q57: a third, race-free detection path, using data already
    # collected (on_cell_start/on_cell_executed's own timestamps) rather
    # than a live race between two independently-started clocks.
    # Confirmed live under real container CPU contention: nbclient's own
    # interrupt-then-report round trip can complete FASTER than the
    # watchdog's own `rounded + skew` fire time -- on_cell_executed then
    # cancels the still-pending watchdog timer before it ever gets a
    # chance to confirm anything, and the kernel's interrupt response can
    # surface as a bare KeyboardInterrupt cell error rather than nbclient
    # re-raising its own CellTimeoutError wrapper (the exact "unreliable
    # exception-type signal" problem the watchdog above already exists to
    # route around, just manifesting as a false NEGATIVE here instead of
    # the false positive that mechanism was built for). The elapsed
    # wall-clock time a cell actually took is authoritative and race-free
    # once the cell has finished -- comparing it against nbclient's own
    # rounded timeout value (the same `rounded` _build_client passes to
    # NotebookClient's `timeout` trait) needs no live timer at all: with
    # interrupt_on_timeout=True, a cell cannot legitimately take at least
    # as long as its own budget without that budget's enforcement having
    # been triggered.
    #
    # Gate-G2 review note: `tracker.timing`'s own start point
    # (`on_cell_start`, before the execute request is even dispatched) is
    # slightly earlier than nbclient's own enforcement window (`deadline
    # = monotonic() + timeout`, started only after dispatch) -- so this
    # comparison is marginally more sensitive than nbclient's own, not
    # perfectly aligned to it. This narrows (but does not eliminate) the
    # false-positive margin the watchdog's own explicit skew provides for
    # the "quick cell, generous timeout" case; accepted as the correct
    # trade-off, since closing a real false negative here necessarily
    # costs some of that unrelated margin.
    if options.cell_timeout is not None and options.interrupt_on_timeout:
        rounded_cell_timeout = max(1, round(options.cell_timeout))
        for cell_index, (cell_started_at, cell_finished_at) in tracker.timing.items():
            if (
                cell_index not in timed_out_cells
                and cell_started_at is not None
                and cell_finished_at is not None
                and cell_finished_at - cell_started_at >= rounded_cell_timeout
            ):
                timed_out_cells.add(cell_index)
                timed_out = True
                timed_out_cell_index = (
                    cell_index
                    if timed_out_cell_index is None
                    else min(timed_out_cell_index, cell_index)
                )

    new_raw = copy.deepcopy(original_document.raw)
    records: list[CellExecutionRecord] = []
    original_cells = new_raw.get("cells", [])
    executed_cells = nb_node.get("cells", [])
    for index, orig_cell in enumerate(original_cells):
        cell_type = str(orig_cell.get("cell_type", "raw"))
        if cell_type != "code":
            records.append(
                CellExecutionRecord(
                    index=index,
                    cell_id=orig_cell.get("id"),
                    cell_type=cell_type,
                    executed=False,
                    skipped=False,
                    execution_count=None,
                    outputs=(),
                    error=None,
                    started_at=None,
                    finished_at=None,
                )
            )
            continue

        tags = orig_cell.get("metadata", {}).get("tags", [])
        is_skip_tagged = options.skip_tag in tags if isinstance(tags, list) else False
        was_executed = index in tracker.finished
        timing = tracker.timing.get(index, [None, None])

        if is_skip_tagged or not was_executed:
            records.append(
                CellExecutionRecord(
                    index=index,
                    cell_id=orig_cell.get("id"),
                    cell_type="code",
                    executed=False,
                    skipped=is_skip_tagged,
                    execution_count=orig_cell.get("execution_count"),
                    # LIBIPYNB-Q2: deep-copied -- orig_cell["outputs"]
                    # lives inside new_raw, which becomes result.notebook
                    # directly; without this, mutating a "frozen"
                    # CellExecutionRecord.outputs entry would silently
                    # corrupt result.notebook too (see the executed-cell
                    # branch's identical fix below for the full rationale).
                    outputs=tuple(
                        copy.deepcopy(output) for output in (orig_cell.get("outputs", []) or [])
                    ),
                    error=None,
                    started_at=timing[0],
                    finished_at=timing[1],
                    timed_out=index in timed_out_cells,
                )
            )
            continue

        exec_cell = executed_cells[index]
        new_outputs = [dict(output) for output in exec_cell.get("outputs", []) or []]
        # LIBIPYNB-Q2: applied before orig_cell["outputs"] is assigned, so
        # both the notebook written back onto result.notebook AND this
        # cell's CellExecutionRecord (deep-copied from the same,
        # already-truncated new_outputs below) reflect the truncation
        # consistently.
        output_truncated, omitted_mime_types = _truncate_outputs_if_needed(
            new_outputs, options.max_output_bytes
        )
        new_execution_count = exec_cell.get("execution_count")
        orig_cell["outputs"] = new_outputs
        orig_cell["execution_count"] = new_execution_count
        if options.record_timing:
            exec_metadata = exec_cell.get("metadata", {}).get("execution")
            if exec_metadata:
                orig_cell.setdefault("metadata", {})["execution"] = dict(exec_metadata)

        records.append(
            CellExecutionRecord(
                index=index,
                cell_id=orig_cell.get("id"),
                cell_type="code",
                executed=True,
                skipped=False,
                execution_count=new_execution_count,
                # LIBIPYNB-Q2: deep-copied, independently from
                # orig_cell["outputs"] = new_outputs above. `new_outputs`'s
                # own [dict(output) for ...] is only a SHALLOW per-item
                # copy -- nested values (a MIME `data` bundle, `metadata`)
                # were still shared objects between orig_cell["outputs"]
                # (which becomes part of result.notebook) and this
                # CellExecutionRecord.outputs tuple, so mutating one
                # silently corrupted the other despite CellExecutionRecord
                # being declared frozen=True. Confirmed live:
                # `result.cell_records[0].outputs[0] is
                # result.notebook.cells[0]['outputs'][0]` was True before
                # this fix.
                outputs=tuple(copy.deepcopy(output) for output in new_outputs),
                error=tracker.errors.get(index),
                started_at=timing[0],
                finished_at=timing[1],
                output_truncated=output_truncated,
                omitted_mime_types=omitted_mime_types,
                timed_out=index in timed_out_cells,
            )
        )

    if options.in_place:
        original_document.raw["cells"] = new_raw["cells"]
        result_document = original_document
    else:
        result_document = NotebookDocument(
            new_raw,
            declared_version=original_document.declared_version,
            detected_version=original_document.detected_version,
            recovery_actions=original_document.recovery_actions,
        )

    return ExecutionResult(
        notebook=result_document,
        cell_records=tuple(records),
        # client.kernel_name is nbclient's own *resolved* value -- it fills
        # in from the notebook's declared kernelspec (or jupyter_client's
        # installed default) the moment create_kernel_manager() runs, so
        # this reflects what actually launched, not just what was asked for.
        kernel_name=client.kernel_name or "(kernel default)",
        started_at=started_at if started_at is not None else finished_at,
        finished_at=finished_at,
        timed_out=timed_out,
        timed_out_cell_index=timed_out_cell_index,
        stopped_early=stopped_early,
        kernel_launch_error=kernel_launch_error,
        kernel_death_error=kernel_death_error,
        total_timed_out=total_timed_out,
        hard_killed=tracker.hard_killed,
    )


__all__ = ["LocalJupyterExecutor"]
