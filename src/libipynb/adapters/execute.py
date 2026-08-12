"""Opt-in notebook execution, isolated from the core codec.

IPYNB-EXEC-001: "Keep execution in an opt-in adapter with kernel selection,
timeouts, error policy, and isolation boundary; return a structured
execution report; never execute during load/validate/diff/save."

The second half of that obligation -- that load/validate/diff/save never
execute cell code -- is proven separately in
tests/python/ipynb/test_obligation_core_path_no_execution.py with a CPython
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
import subprocess
import sys
from dataclasses import dataclass
from typing import Any

from ..errors import NotebookExecutionError
from ..model.document import NotebookDocument

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
    results = []
    for line in raw_output.splitlines():
        if not line.strip():
            continue
        payload = json.loads(line)
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
) -> ExecutionReport:
    """Execute every code cell in one isolated subprocess and report the outcome.

    Never called by load/validate/diff/save -- this is the sole entry point
    into execution, and callers must invoke it explicitly.
    """
    if on_error not in ("stop", "continue"):
        raise ValueError("on_error must be 'stop' or 'continue'")
    resolved_kernel = _resolve_kernel(document, kernel)
    sources = [_cell_source(cell) for cell in document.code_cells]
    payload = json.dumps({"sources": sources, "on_error": on_error})
    timed_out = False
    launch_error: str | None = None
    raw_output = ""
    try:
        completed = subprocess.run(
            [resolved_kernel, "-c", _DRIVER_SCRIPT],
            input=payload,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        raw_output = completed.stdout
    except subprocess.TimeoutExpired as exc:
        raw_output = exc.stdout if isinstance(exc.stdout, str) else ""
        timed_out = True
    except OSError as exc:
        # The kernel process itself could not be started (missing
        # interpreter, not executable, etc.) -- a controlled, reported
        # outcome, not an unhandled crash out of an API that promises a
        # structured report.
        launch_error = str(exc)
    return ExecutionReport(
        results=_parse_results(raw_output),
        kernel=resolved_kernel,
        total_code_cells=len(sources),
        timed_out=timed_out,
        kernel_launch_error=launch_error,
    )


__all__ = [
    "CellExecutionResult",
    "ExecutionError",
    "ExecutionReport",
    "execute_notebook",
]
