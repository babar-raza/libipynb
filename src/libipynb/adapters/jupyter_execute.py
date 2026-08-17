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
import time
from typing import TYPE_CHECKING, Any

from ..errors import NotebookExecutionError
from ..model.document import NotebookDocument

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
        try:
            client.execute(**start_kwargs)
        except BaseException as exc:  # noqa: BLE001 -- classified below, never re-raised bare
            return _finish(document, resolved, nb_node, tracker, client, nbclient_exc, exc)
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
    (``on_cell_start``/``on_cell_executed``/``on_cell_error``) -- the only
    way to learn *which* cell was active when a run stops early or times
    out, since ``CellExecutionError``/``CellTimeoutError`` carry a message
    but not a cell index."""

    def __init__(self, on_event: Any) -> None:
        self.reached: list[int] = []
        self.finished: set[int] = set()
        self.timing: dict[int, list[float | None]] = {}
        self.errors: dict[int, ExecutionCellError] = {}
        self._on_event = on_event

    def _emit(self, kind: str, cell: dict[str, Any], cell_index: int) -> None:
        if self._on_event is not None:
            from ..execution.results import ExecutionEvent

            self._on_event(ExecutionEvent(kind=kind, cell_index=cell_index, cell_id=cell.get("id")))

    def on_cell_start(self, cell: dict[str, Any], cell_index: int, **_kw: Any) -> None:
        self.reached.append(cell_index)
        self.timing[cell_index] = [time.time(), None]
        self._emit("cell_started", cell, cell_index)

    def on_cell_executed(self, cell: dict[str, Any], cell_index: int, **_kw: Any) -> None:
        self.finished.add(cell_index)
        entry = self.timing.setdefault(cell_index, [None, None])
        entry[1] = time.time()
        self._emit("cell_finished", cell, cell_index)

    def on_cell_error(self, cell: dict[str, Any], cell_index: int, execute_reply: Any) -> None:
        from ..execution.results import ExecutionCellError

        content = execute_reply["content"]
        self.errors[cell_index] = ExecutionCellError(
            ename=str(content.get("ename", "")),
            evalue=str(content.get("evalue", "")),
            traceback=tuple(content.get("traceback", []) or []),
        )


def _build_client(
    document: NotebookDocument,
    options: ExecutionOptions,
    nbclient_mod: Any,
    nbformat_mod: Any,
) -> tuple[Any, Any, _Tracker]:
    nb_dict = copy.deepcopy(document.raw)
    nb_node = nbformat_mod.from_dict(nb_dict)

    tracker = _Tracker(options.on_event)
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
        on_cell_executed=tracker.on_cell_executed,
        on_cell_error=tracker.on_cell_error,
    )
    # nbclient forwards unrecognized execute()/async_execute() kwargs to
    # jupyter_client's start_kernel(); stash for the call site instead of a
    # NotebookClient trait (there isn't one for extra Popen env).
    client._libipynb_extra_start_kwargs = kwargs
    return client, nb_node, tracker


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

    started_at = min((t[0] for t in tracker.timing.values() if t[0] is not None), default=None)
    finished_at = time.time()

    timed_out = False
    timed_out_cell_index: int | None = None
    stopped_early = False
    kernel_launch_error: str | None = None
    kernel_death_error: str | None = None

    if exc is not None:
        if isinstance(exc, nbclient_exc.CellTimeoutError):
            timed_out = True
            timed_out_cell_index = tracker.reached[-1] if tracker.reached else None
        elif isinstance(exc, nbclient_exc.CellExecutionError):
            stopped_early = True
        elif isinstance(exc, nbclient_exc.DeadKernelError):
            kernel_death_error = str(exc)
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
                    outputs=tuple(orig_cell.get("outputs", []) or []),
                    error=None,
                    started_at=timing[0],
                    finished_at=timing[1],
                )
            )
            continue

        exec_cell = executed_cells[index]
        new_outputs = [dict(output) for output in exec_cell.get("outputs", []) or []]
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
                outputs=tuple(new_outputs),
                error=tracker.errors.get(index),
                started_at=timing[0],
                finished_at=timing[1],
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
    )


__all__ = ["LocalJupyterExecutor"]
