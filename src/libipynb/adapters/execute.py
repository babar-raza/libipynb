"""Opt-in notebook execution, isolated from the core codec.

IPYNB-EXEC-001: "Keep execution in an opt-in adapter with kernel selection,
timeouts, error policy, and isolation boundary; return a structured
execution report; never execute during load/validate/diff/save."

The second half of that obligation -- that load/validate/diff/save never
execute cell code -- is proven separately in
tests/integration/test_obligation_core_path_no_execution.py with a CPython
audit hook, and holds independently of this module: nothing in
codec/reader, codec/writer, validation, or model/diff imports this file.

Scope of "kernel selection" here: this adapter runs Python-family kernels
only, via a real OS subprocess (isolation boundary) -- not the Jupyter
kernel wire protocol (ZMQ-based `jupyter_client`), which would add a heavy
dependency this dependency-minimal codec package does not otherwise need.
A notebook declaring a non-Python `language_info`/`kernelspec` is refused
with NotebookExecutionError naming the declared language, rather than silently
executed as Python or silently skipped -- selection means choosing AND
validating which interpreter runs the cells, not merely picking one.

Scope of "timeouts": one overall wall-clock budget for the whole run, not a
per-cell budget. `subprocess.run(..., timeout=...)` is the well-tested,
cross-platform primitive this relies on; per-cell timeouts would need a
persistent bidirectional protocol with its own tricky cross-platform
readline-with-timeout problem, deliberately not attempted here.

State persists across cells within one execution (a later cell can use a
name a previous cell defined), matching real notebook semantics -- all
cells run inside a single subprocess and a single namespace, not one
subprocess per cell.
"""

from __future__ import annotations

import contextlib
import json
import os
import queue
import signal
import subprocess
import sys
import tempfile
import threading
from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Any

from .._internal.text import truncate_utf8_text
from ..errors import NotebookExecutionError
from ..model.document import NotebookDocument

#: Environment variables kept by default when ``isolate_env=True`` -- just
#: enough for the interpreter itself to start on each platform (PATH,
#: temp-directory, and the Windows-specific variables cmd/CreateProcess
#: need). Everything else (API keys, tokens, unrelated app config) the
#: calling process happens to have set is NOT passed through. Pass
#: ``extra_env=`` to add anything a specific notebook genuinely needs.
_MINIMAL_ENV_KEYS = (
    "PATH",
    "TEMP",
    "TMP",
    "HOME",
    "SYSTEMROOT",
    "SYSTEMDRIVE",
    "PATHEXT",
    "COMSPEC",
    "LANG",
    "LC_ALL",
)


def _minimal_env(extra_env: dict[str, str] | None) -> dict[str, str]:
    kept = {key: os.environ[key] for key in _MINIMAL_ENV_KEYS if key in os.environ}
    if extra_env:
        kept.update(extra_env)
    return kept


def _memory_limit_preexec_fn(max_memory_bytes: int) -> Callable[[], None] | None:
    """A ``preexec_fn`` enforcing an address-space cap via ``RLIMIT_AS`` --
    POSIX only. ``subprocess.Popen`` raises ``ValueError`` if ``preexec_fn``
    is passed at all on Windows (not merely a no-op there), so callers must
    not pass one on that platform; Windows memory limiting needs the Job
    Objects API instead, not implemented here -- see LIBIPYNB-V4 in
    plans/remediation-plan.md for that follow-up scope decision.
    """
    if sys.platform == "win32":
        return None

    def _set_limit() -> None:
        import resource

        resource.setrlimit(resource.RLIMIT_AS, (max_memory_bytes, max_memory_bytes))

    return _set_limit


#: Runs inside the child subprocess. Reads a JSON request from stdin
#: (sources: list[str], on_error: "stop"|"continue"), executes each source
#: in one shared namespace, and writes one JSON result line per attempted
#: cell to stdout as it goes -- flushed immediately, so a result already
#: produced survives even if a later cell times out and the process is
#: killed (subprocess.TimeoutExpired.stdout carries whatever was captured
#: before the kill).
_DRIVER_SCRIPT = r"""
import contextlib, io, json, sys, traceback

def main():
    request = json.loads(sys.stdin.read())
    sources = request["sources"]
    on_error = request["on_error"]
    namespace = {}
    for index, source in enumerate(sources):
        buffer = io.StringIO()
        error = None
        try:
            with contextlib.redirect_stdout(buffer):
                exec(compile(source, "<cell %d>" % index, "exec"), namespace)
        except BaseException as exc:
            error = {
                "ename": type(exc).__name__,
                "evalue": str(exc),
                "traceback": traceback.format_exc(),
            }
        sys.stdout.write(json.dumps(
            {"index": index, "stdout": buffer.getvalue(), "error": error}
        ) + "\n")
        sys.stdout.flush()
        if error is not None and on_error == "stop":
            break

main()
"""


@dataclass(frozen=True, slots=True)
class ExecutionError:
    """A cell's raised exception, captured structurally."""

    ename: str
    evalue: str
    traceback: str


@dataclass(frozen=True, slots=True)
class CellExecutionResult:
    """One code cell's execution outcome."""

    index: int
    stdout: str
    error: ExecutionError | None = None
    #: LIBIPYNB-Q16: ``True`` when this cell's own ``stdout`` was shortened
    #: because the run's cumulative captured output reached
    #: ``max_output_bytes``. Always ``False`` when that option is ``None``.
    stdout_truncated: bool = False

    @property
    def succeeded(self) -> bool:
        return self.error is None


@dataclass(frozen=True, slots=True)
class ExecutionReport:
    """Structured outcome of a full notebook execution run."""

    results: tuple[CellExecutionResult, ...]
    kernel: str
    total_code_cells: int
    timed_out: bool = False
    kernel_launch_error: str | None = None
    #: Run-provenance fields (LIBIPYNB-V4): what isolation was actually
    #: applied to this specific run, not just what the API allows asking
    #: for -- e.g. memory_limit_bytes is None whenever a limit was
    #: requested but this platform can't enforce one (Windows), not only
    #: when no limit was requested at all.
    work_dir: str | None = None
    memory_limit_bytes: int | None = None
    output_limit_bytes: int | None = None
    output_truncated: bool = False

    @property
    def completed(self) -> bool:
        """False when the run was killed mid-flight by the timeout, or the
        kernel process could not be launched at all.

        Stopping early because a cell errored under on_error="stop" is a
        policy outcome, not an incompletion -- the adapter did exactly what
        was asked. Only a timeout or a launch failure means the run did not
        reach a controlled end.
        """
        return not self.timed_out and self.kernel_launch_error is None

    @property
    def all_cells_ran(self) -> bool:
        return len(self.results) == self.total_code_cells

    @property
    def first_error(self) -> ExecutionError | None:
        for result in self.results:
            if result.error is not None:
                return result.error
        return None


def _resolve_kernel(document: NotebookDocument, kernel: str | None) -> str:
    if kernel is not None:
        return kernel
    metadata = document.metadata
    language = metadata.get("language_info", {}).get("name") or metadata.get("kernelspec", {}).get(
        "language"
    )
    if language is not None and language != "python":
        raise NotebookExecutionError(
            f"notebook declares kernel language {language!r}; this adapter "
            "only executes Python-family kernels -- pass an explicit "
            "kernel= interpreter path to override"
        )
    return sys.executable


def _cell_source(cell: dict[str, Any]) -> str:
    value = cell.get("source", "")
    return value if isinstance(value, str) else "".join(value)


def _parse_results(raw_output: str) -> tuple[CellExecutionResult, ...]:
    """Parse the driver's newline-delimited JSON result stream.

    LIBIPYNB-Q16: always called on the full, untruncated ``raw_output`` --
    ``max_output_bytes`` is applied afterwards, per already-parsed cell
    result, by :func:`_apply_output_budget` below, never by byte-slicing
    this combined stream before it is split into records. Byte-slicing
    first was the confirmed bug: a single oversized cell's line, cut off
    mid-write by the slice, silently dropped every later cell's already-
    complete, unrelated result along with it (reproduced directly: a
    3-cell run with one oversized cell and a small max_output_bytes
    returned zero parsed results, not two).

    A trailing line can still be incomplete for a genuinely unrelated
    reason -- a timeout-kill severing the subprocess mid-write, which
    predates ``max_output_bytes`` entirely. That's the same situation the
    driver's own contract already accepted: a result already flushed is
    kept; a result cut off mid-write is dropped, not surfaced as a crash.
    """
    results = []
    for line in raw_output.splitlines():
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        error = None
        if payload["error"] is not None:
            error = ExecutionError(**payload["error"])
        results.append(
            CellExecutionResult(index=payload["index"], stdout=payload["stdout"], error=error)
        )
    return tuple(results)


def _apply_output_budget(
    results: tuple[CellExecutionResult, ...], max_bytes: int | None
) -> tuple[tuple[CellExecutionResult, ...], bool]:
    """Cap the run's *cumulative* captured stdout at *max_bytes*, applied to
    already-parsed, structured per-cell results -- never to the combined
    raw stream (see :func:`_parse_results`'s docstring for why that was the
    bug). Every cell keeps its own explicit result; once the running total
    reaches the budget, each subsequent cell's own ``stdout`` is shortened
    to what remains (down to empty once the budget is exhausted) and
    flagged via ``stdout_truncated`` -- visible, not silent, data loss, and
    distinct from :mod:`libipynb.adapters.jupyter_execute`'s
    ``max_output_bytes``, which caps each output *independently* rather
    than cumulatively (documented separately on each engine's own options,
    a genuine, pre-existing difference between the two -- not something
    this fix introduces or is trying to unify).
    """
    if max_bytes is None:
        return results, False
    truncated_any = False
    remaining = max_bytes
    budgeted: list[CellExecutionResult] = []
    for result in results:
        stdout_bytes = len(result.stdout.encode("utf-8"))
        if stdout_bytes <= remaining:
            budgeted.append(result)
            remaining -= stdout_bytes
            continue
        budgeted.append(
            replace(
                result,
                stdout=truncate_utf8_text(result.stdout, remaining),
                stdout_truncated=True,
            )
        )
        truncated_any = True
        remaining = 0
    return tuple(budgeted), truncated_any


def _kill_process_tree(process: subprocess.Popen[bytes]) -> None:
    """LIBIPYNB-Q44: terminate the driver AND every process it (or code it
    ran) spawned -- ``Popen.kill()`` alone only ever signals that one PID,
    leaving anything the executed cell code itself spawned (e.g. via its
    own ``subprocess.Popen`` call) running, untouched, after the driver
    itself is gone. Best-effort: a process that already exited on its own
    between the timeout firing and this call is not an error here."""
    if sys.platform == "win32":
        # taskkill /T kills the whole process tree rooted at this PID, not
        # just the one process -- a ubiquitous, OS-provided tool (System32),
        # not a new dependency. /F forces termination without prompting.
        with contextlib.suppress(OSError, subprocess.TimeoutExpired):
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(process.pid)],
                capture_output=True,
                check=False,
                timeout=10,
            )
        # Always also try the direct kill -- taskkill failing (missing
        # binary on a stripped-down install, access-denied, ...) must not
        # leave the driver process itself alive.
        with contextlib.suppress(OSError):
            process.kill()
    else:
        # _run_driver_subprocess starts the driver in its own session
        # (start_new_session=True), making it the leader of a new process
        # group -- os.killpg signals every process in that group, not just
        # the driver, which is what actually reaches a grandchild the
        # driver's own cell code spawned.
        with contextlib.suppress(ProcessLookupError, PermissionError):
            os.killpg(os.getpgid(process.pid), signal.SIGKILL)
        with contextlib.suppress(OSError):
            process.kill()


def _run_driver_subprocess(
    kernel: str,
    payload: str,
    *,
    timeout: float | None,
    cwd: str | None,
    env: dict[str, str] | None,
    preexec_fn: Callable[[], None] | None,
) -> tuple[bytes, bool]:
    """Runs the driver subprocess and returns ``(captured_stdout, timed_out)``.

    LIBIPYNB-Q44: reads the driver's stdout on a background thread instead
    of via ``subprocess.run``'s own ``communicate()``-based timeout
    handling, so a timeout-triggered kill can never block waiting for the
    pipe to reach EOF. EOF only happens once *every* process holding the
    write end of the pipe has exited -- not guaranteed to be true of the
    driver alone if the executed cell code spawned its own child process
    without redirecting that child's stdout (inheriting the driver's pipe
    handle is the *default* when a child's own stdout isn't explicitly
    redirected -- a well-known, cross-platform subprocess gotcha: POSIX's
    ``close_fds=True`` only closes *unnamed* descriptors, never fds 0/1/2
    themselves). Reproduced directly before this fix: a `timeout=2` call
    against a driver whose only cell spawned a 60s-sleeping grandchild
    made ``execute_notebook`` itself take over 60s to return -- the
    wall-clock bound the ``timeout`` parameter promises was silently
    defeated by nothing more than the executed cell code spawning a
    subprocess. See ``TestTimeoutIsNotDefeatedByASpawnedGrandchild`` in
    ``tests/integration/test_obligation_execution_adapter.py``.
    """
    popen_kwargs: dict[str, Any] = {
        "stdin": subprocess.PIPE,
        "stdout": subprocess.PIPE,
        "stderr": subprocess.STDOUT,
        "cwd": cwd,
        "env": env,
        "preexec_fn": preexec_fn,
    }
    if sys.platform == "win32":
        popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        popen_kwargs["start_new_session"] = True

    process: subprocess.Popen[bytes] = subprocess.Popen(
        [kernel, "-c", _DRIVER_SCRIPT], **popen_kwargs
    )
    assert process.stdin is not None
    assert process.stdout is not None

    chunks: queue.Queue[bytes | None] = queue.Queue()

    def _reader(stream: Any) -> None:
        # This thread is the stream's sole owner from here on -- the main
        # thread never touches process.stdout again after starting this
        # thread. Closing it here, not from the main thread, avoids a
        # cross-thread close-while-reading race: if the pipe never reaches
        # EOF (a grandchild still holds it open), this thread -- and only
        # this thread -- may still be blocked in stream.read() when
        # _run_driver_subprocess returns; it is a daemon thread, so it
        # cannot block interpreter exit, and it closes its own stream once
        # (if ever) it does unblock.
        try:
            for chunk in iter(lambda: stream.read(65536), b""):
                chunks.put(chunk)
        except (OSError, ValueError):
            pass
        finally:
            chunks.put(None)
            with contextlib.suppress(OSError):
                stream.close()

    reader_thread = threading.Thread(target=_reader, args=(process.stdout,), daemon=True)
    reader_thread.start()

    try:
        process.stdin.write(payload.encode("utf-8"))
        process.stdin.close()
    except OSError:
        pass  # driver may already have exited/failed to launch fully

    try:
        process.wait(timeout=timeout)
        timed_out = False
    except subprocess.TimeoutExpired:
        timed_out = True
        _kill_process_tree(process)
        with contextlib.suppress(subprocess.TimeoutExpired):
            process.wait(timeout=10)

    # A brief, bounded wait for the reader thread to catch up -- NOT a
    # requirement for correctness (the queue.get_nowait() drain below
    # returns whatever has already arrived regardless), just reduces the
    # chance of missing the last already-in-flight chunk. If a grandchild
    # is still holding the pipe open, this thread may never finish; it is
    # a daemon thread, so it cannot block process/interpreter exit.
    reader_thread.join(timeout=1.0)
    buffer = bytearray()
    while True:
        try:
            chunk = chunks.get_nowait()
        except queue.Empty:
            break
        if chunk is not None:
            buffer.extend(chunk)

    return bytes(buffer), timed_out


def execute_notebook(
    document: NotebookDocument,
    *,
    kernel: str | None = None,
    timeout: float | None = 30.0,
    on_error: str = "stop",
    acknowledge_unsandboxed: bool = False,
    isolate_cwd: bool = True,
    isolate_env: bool = True,
    extra_env: dict[str, str] | None = None,
    max_memory_bytes: int | None = None,
    max_output_bytes: int | None = 10 * 1024 * 1024,
) -> ExecutionReport:
    """Execute every code cell in one isolated subprocess and report the outcome.

    Never called by load/validate/diff/save -- this is the sole entry point
    into execution, and callers must invoke it explicitly.

    Security: this is process isolation, not a full sandbox. LIBIPYNB-V4
    narrowed the gap between those two by adding, on top of the
    subprocess boundary and wall-clock ``timeout`` that already existed:

    - ``isolate_cwd`` (default True): the subprocess runs in a fresh,
      empty temporary directory instead of the caller's working
      directory, so executed code can't casually read or overwrite files
      next to the caller's own. Removed after the run regardless of
      outcome.
    - ``isolate_env`` (default True): the subprocess gets a minimal
      environment (just enough for the interpreter to start -- PATH,
      temp-dir, locale) instead of a full copy of the caller's
      environment, so secrets/tokens/config the caller happens to have
      set are not implicitly exposed. Pass ``extra_env`` for anything a
      specific notebook genuinely needs.
    - ``max_output_bytes`` (default 10 MiB): the run's *cumulative*
      captured stdout across every cell is capped at this size --
      distinct from :mod:`libipynb.adapters.jupyter_execute`'s
      identically-named option, which caps each output independently
      rather than cumulatively; the two engines have never shared this
      exact semantic. Applied per already-parsed cell result, in cell
      order, after the full subprocess output is parsed -- never by
      slicing the combined raw stream before parsing it, which used to
      silently drop every unrelated later cell's already-complete result
      once one cell pushed the shared stream past the cutoff (LIBIPYNB-
      Q16). Every cell always gets its own ``CellExecutionResult``;
      ``CellExecutionResult.stdout_truncated`` says whether that specific
      cell's own stdout was shortened, and ``ExecutionReport.
      output_truncated`` is true iff any cell's was. This bounds what's
      *returned*, not necessarily peak memory while the OS pipe buffer
      fills during capture -- a true streaming-bounded read is a further
      step, not implemented here.
    - ``max_memory_bytes`` (default None = no limit): enforced via
      ``RLIMIT_AS`` on POSIX. **Not enforceable on Windows** -- passing
      it there raises ``NotebookExecutionError`` rather than silently
      running unlimited, since a caller who explicitly asked for a
      memory limit and silently got none is exactly the "looks safe but
      isn't" failure mode this module tries to avoid elsewhere.

    Still not covered: CPU-time limiting and network access denial --
    see LIBIPYNB-V4 in plans/remediation-plan.md for why those are
    deferred rather than half-implemented.

    Callers must pass ``acknowledge_unsandboxed=True`` to confirm they
    understand the above, or the call raises ``NotebookExecutionError``.
    """
    if not acknowledge_unsandboxed:
        raise NotebookExecutionError(
            "execute_notebook() is not a full sandbox: even with isolate_cwd/"
            "isolate_env (both default True), CPU time and network access are "
            "not limited, and a memory limit is only enforceable on POSIX. "
            "Pass acknowledge_unsandboxed=True to confirm you understand this "
            "and trust the notebook being executed."
        )
    if on_error not in ("stop", "continue"):
        raise ValueError("on_error must be 'stop' or 'continue'")
    if max_output_bytes is not None and max_output_bytes < 0:
        # LIBIPYNB-Q16 Gate G2 finding: an unvalidated negative value
        # reached truncate_utf8_text's fallback-marker slice
        # (_FALLBACK_MARKER[:max_bytes]), where Python's negative-index
        # slicing means "all but the last N bytes" rather than "first N
        # bytes" -- silently fabricating a "..." marker onto cells whose
        # own stdout was empty and untouched. Matches the sibling engine's
        # equally strict ExecutionOptions.max_output_bytes validation
        # (execution/options.py) rather than leaving this one unchecked.
        raise ValueError("max_output_bytes must be non-negative or None")
    if max_memory_bytes is not None and sys.platform == "win32":
        raise NotebookExecutionError(
            "max_memory_bytes cannot be enforced on Windows (no RLIMIT_AS-"
            "equivalent used here). Pass max_memory_bytes=None on this "
            "platform rather than proceeding without the limit silently."
        )
    resolved_kernel = _resolve_kernel(document, kernel)
    sources = [_cell_source(cell) for cell in document.code_cells]
    payload = json.dumps({"sources": sources, "on_error": on_error})
    timed_out = False
    launch_error: str | None = None
    raw_output = ""

    resolved_env = _minimal_env(extra_env) if isolate_env else None
    preexec_fn = _memory_limit_preexec_fn(max_memory_bytes) if max_memory_bytes else None
    work_dir_ctx = tempfile.TemporaryDirectory(prefix="libipynb-exec-") if isolate_cwd else None
    work_dir = work_dir_ctx.name if work_dir_ctx is not None else None
    try:
        try:
            raw_bytes, timed_out = _run_driver_subprocess(
                resolved_kernel,
                payload,
                timeout=timeout,
                cwd=work_dir,
                env=resolved_env,
                preexec_fn=preexec_fn,
            )
            raw_output = raw_bytes.decode("utf-8", errors="replace")
        except OSError as exc:
            # The kernel process itself could not be started (missing
            # interpreter, not executable, etc.) -- a controlled, reported
            # outcome, not an unhandled crash out of an API that promises a
            # structured report.
            launch_error = str(exc)
    finally:
        if work_dir_ctx is not None:
            work_dir_ctx.cleanup()

    # LIBIPYNB-Q16: parse the FULL, untruncated raw_output first -- never
    # byte-slice the combined stream before splitting it into per-cell
    # records (see _parse_results' and _apply_output_budget's own
    # docstrings for the confirmed bug this fixes). The budget is applied
    # afterwards, per already-parsed result.
    results, output_truncated = _apply_output_budget(_parse_results(raw_output), max_output_bytes)

    return ExecutionReport(
        results=results,
        kernel=resolved_kernel,
        total_code_cells=len(sources),
        timed_out=timed_out,
        kernel_launch_error=launch_error,
        work_dir=work_dir,
        memory_limit_bytes=max_memory_bytes,
        output_limit_bytes=max_output_bytes,
        output_truncated=output_truncated,
    )


__all__ = [
    "CellExecutionResult",
    "ExecutionError",
    "ExecutionReport",
    "execute_notebook",
]
