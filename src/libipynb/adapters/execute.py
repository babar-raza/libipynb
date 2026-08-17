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

import json
import os
import subprocess
import sys
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

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

    A trailing line can be incomplete -- not just from a timeout-kill
    (already the case before max_output_bytes existed) but now also from
    byte-boundary truncation, which has no reason to land on a record
    boundary. Either way it's the same situation the driver's own
    contract already accepted: a result already flushed is kept; a
    result cut off mid-write is dropped, not surfaced as a crash.
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
    - ``max_output_bytes`` (default 10 MiB): captured stdout is
      truncated to this size; ``ExecutionReport.output_truncated`` says
      whether that happened. This bounds what's *returned*, not
      necessarily peak memory while the OS pipe buffer fills during
      capture -- a true streaming-bounded read is a further step, not
      implemented here.
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
            completed = subprocess.run(
                [resolved_kernel, "-c", _DRIVER_SCRIPT],
                input=payload,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
                cwd=work_dir,
                env=resolved_env,
                preexec_fn=preexec_fn,
            )
            raw_output = completed.stdout
        except subprocess.TimeoutExpired as exc:
            # subprocess.run's timeout+kill path re-decodes captured output
            # to str on Windows (it re-invokes communicate() to drain,
            # which goes through the text-mode wrapper) but attaches raw
            # bytes on POSIX (no re-drain, so text=True's decoding step is
            # never reached) -- confirmed by direct reproduction against
            # this exact driver script and payload on Linux. Decoding here
            # makes partial-output capture on timeout actually
            # cross-platform instead of Windows-only.
            captured: str | bytes | None = exc.stdout
            if isinstance(captured, bytes):
                captured = captured.decode("utf-8", errors="replace")
            raw_output = captured if isinstance(captured, str) else ""
            timed_out = True
        except OSError as exc:
            # The kernel process itself could not be started (missing
            # interpreter, not executable, etc.) -- a controlled, reported
            # outcome, not an unhandled crash out of an API that promises a
            # structured report.
            launch_error = str(exc)
    finally:
        if work_dir_ctx is not None:
            work_dir_ctx.cleanup()

    output_truncated = False
    if max_output_bytes is not None and len(raw_output.encode("utf-8")) > max_output_bytes:
        raw_output = raw_output.encode("utf-8")[:max_output_bytes].decode("utf-8", errors="ignore")
        output_truncated = True

    return ExecutionReport(
        results=_parse_results(raw_output),
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
