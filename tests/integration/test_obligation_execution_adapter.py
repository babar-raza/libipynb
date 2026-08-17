"""IPYNB-EXEC-001, first clause: the opt-in execution adapter itself.

MUST: "Keep execution in an opt-in adapter with kernel selection, timeouts,
error policy, and isolation boundary; return a structured execution
report."

required_tests: "Isolated-environment execution tests covering timeout,
kernel failure, and partial output."

Scope, stated plainly: this adapter runs Python-family kernels only, via a
real OS subprocess, with one overall wall-clock timeout (not per-cell). It
does not implement the Jupyter kernel wire protocol. See adapters/execute.py's
module docstring for the reasoning. The second half of the obligation (core
path never executes) is proven separately in
test_obligation_core_path_no_execution.py.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from libipynb import NotebookDocument, NotebookExecutionError
from libipynb.adapters import ExecutionReport, execute_notebook


def _document(cells: list[dict], metadata: dict | None = None) -> NotebookDocument:
    return NotebookDocument(
        {
            "nbformat": 4,
            "nbformat_minor": 5,
            "metadata": metadata or {},
            "cells": cells,
        }
    )


def _code(source: str, cell_id: str = "c") -> dict:
    return {
        "cell_type": "code",
        "id": cell_id,
        "metadata": {},
        "execution_count": None,
        "outputs": [],
        "source": source,
    }


def _markdown(source: str = "# hi") -> dict:
    return {"cell_type": "markdown", "id": "m", "metadata": {}, "source": source}


# ── Opt-in gate: not a sandbox, must be acknowledged explicitly ────────────


def test_execute_notebook_refuses_without_acknowledgment() -> None:
    """execute_notebook is not a sandbox (no CPU/memory/disk/network limits;
    the child subprocess inherits the caller's full environment). Calling it
    without explicitly acknowledging that must refuse before running
    anything, not execute first and warn after."""
    document = _document([_code("print('should never run')")])

    with pytest.raises(NotebookExecutionError, match="sandbox"):
        execute_notebook(document, timeout=10)


def test_execute_notebook_runs_once_acknowledged() -> None:
    document = _document([_code("print('ran')")])

    report = execute_notebook(document, timeout=10, acknowledge_unsandboxed=True)

    assert report.results[0].stdout == "ran\n"


# ── Isolation boundary: real subprocess, shared namespace across cells ─────


def test_execution_runs_in_a_subprocess_not_the_parent_interpreter() -> None:
    """A name defined by the adapter's driver must not leak into this
    process -- if it did, execution would not be isolated."""
    document = _document([_code("__adapter_leak_probe__ = 1")])

    execute_notebook(document, timeout=10, acknowledge_unsandboxed=True)

    assert "__adapter_leak_probe__" not in globals()


def test_state_persists_across_cells_within_one_run() -> None:
    document = _document([_code("x = 21", "a"), _code("print(x * 2)", "b")])

    report = execute_notebook(document, timeout=10, acknowledge_unsandboxed=True)

    assert report.results[1].stdout == "42\n"


def test_markdown_and_raw_cells_are_never_sent_to_the_subprocess() -> None:
    document = _document([_markdown(), _code("print('only code')", "b")])

    report = execute_notebook(document, timeout=10, acknowledge_unsandboxed=True)

    assert report.total_code_cells == 1
    assert len(report.results) == 1
    assert report.results[0].stdout == "only code\n"


# ── Structured execution report ─────────────────────────────────────────────


def test_successful_cell_reports_stdout_and_no_error() -> None:
    document = _document([_code("print('hello')")])

    report = execute_notebook(document, timeout=10, acknowledge_unsandboxed=True)

    assert isinstance(report, ExecutionReport)
    assert len(report.results) == 1
    assert report.results[0].stdout == "hello\n"
    assert report.results[0].error is None
    assert report.results[0].succeeded is True


def test_failing_cell_reports_structured_error_not_a_raised_exception() -> None:
    document = _document([_code("raise ValueError('boom')")])

    report = execute_notebook(document, timeout=10, acknowledge_unsandboxed=True)

    result = report.results[0]
    assert result.succeeded is False
    assert result.error is not None
    assert result.error.ename == "ValueError"
    assert result.error.evalue == "boom"
    assert "ValueError: boom" in result.error.traceback


def test_first_error_surfaces_the_earliest_failure() -> None:
    document = _document([_code("print('ok')", "a"), _code("raise KeyError('missing')", "b")])

    report = execute_notebook(document, timeout=10, acknowledge_unsandboxed=True)

    assert report.first_error is not None
    assert report.first_error.ename == "KeyError"


# ── Error policy ─────────────────────────────────────────────────────────────


def test_on_error_stop_halts_remaining_cells() -> None:
    document = _document(
        [
            _code("raise ValueError('boom')", "a"),
            _code("print('should not run')", "b"),
        ]
    )

    report = execute_notebook(document, timeout=10, on_error="stop", acknowledge_unsandboxed=True)

    assert len(report.results) == 1
    assert report.all_cells_ran is False
    assert report.completed is True  # stopped by policy, not killed


def test_on_error_continue_runs_every_cell_regardless_of_failure() -> None:
    document = _document(
        [
            _code("raise ValueError('boom')", "a"),
            _code("print('still runs')", "b"),
        ]
    )

    report = execute_notebook(
        document, timeout=10, on_error="continue", acknowledge_unsandboxed=True
    )

    assert report.all_cells_ran is True
    assert report.results[0].succeeded is False
    assert report.results[1].stdout == "still runs\n"


def test_invalid_on_error_value_is_rejected() -> None:
    document = _document([_code("pass")])

    with pytest.raises(ValueError, match="on_error"):
        execute_notebook(document, timeout=10, on_error="ignore", acknowledge_unsandboxed=True)


# ── Timeouts ─────────────────────────────────────────────────────────────────


def test_timeout_is_reported_structurally_not_raised() -> None:
    document = _document([_code("print('before')", "a"), _code("import time; time.sleep(5)", "b")])

    report = execute_notebook(document, timeout=1, acknowledge_unsandboxed=True)

    assert report.timed_out is True
    assert report.completed is False


def test_timeout_preserves_partial_output_from_completed_cells() -> None:
    document = _document(
        [_code("print('captured')", "a"), _code("import time; time.sleep(5)", "b")]
    )

    report = execute_notebook(document, timeout=1, acknowledge_unsandboxed=True)

    assert len(report.results) == 1
    assert report.results[0].stdout == "captured\n"


def test_timeout_partial_output_is_decoded_when_the_platform_returns_bytes() -> None:
    """subprocess.run's timeout+kill path returns TimeoutExpired.stdout as
    str on Windows (it re-invokes communicate(), which decodes) but as raw
    bytes on POSIX (no re-drain, so text=True's decoding step is never
    reached) -- confirmed by direct reproduction on Linux, where this
    silently discarded all partial output before this fix (the previous
    code's `if isinstance(exc.stdout, str) else ""` treated bytes as
    "nothing captured", turning a real timeout+partial-output case into a
    zero-results one). Mocked here with real driver-format bytes so the
    regression is caught on any platform's CI, not only by running on
    Linux."""
    document = _document([_code("print('captured')", "a")])
    driver_line = b'{"index": 0, "stdout": "captured\\n", "error": null}\n'
    timeout_error = subprocess.TimeoutExpired(cmd=["python"], timeout=1, output=driver_line)

    with patch("libipynb.adapters.execute.subprocess.run", side_effect=timeout_error):
        report = execute_notebook(document, timeout=1, acknowledge_unsandboxed=True)

    assert report.timed_out is True
    assert len(report.results) == 1
    assert report.results[0].stdout == "captured\n"


def test_a_generous_timeout_does_not_interfere_with_normal_execution() -> None:
    document = _document([_code("print('fine')")])

    report = execute_notebook(document, timeout=30, acknowledge_unsandboxed=True)

    assert report.timed_out is False
    assert report.results[0].stdout == "fine\n"


# ── Kernel selection ─────────────────────────────────────────────────────────


def test_default_kernel_is_the_current_python_interpreter() -> None:
    document = _document([_code("pass")])

    report = execute_notebook(document, timeout=10, acknowledge_unsandboxed=True)

    assert report.kernel == sys.executable


def test_declared_python_kernelspec_is_accepted() -> None:
    document = _document(
        [_code("pass")],
        metadata={"kernelspec": {"name": "python3", "language": "python"}},
    )

    report = execute_notebook(document, timeout=10, acknowledge_unsandboxed=True)

    assert report.timed_out is False


def test_non_python_kernel_is_refused_not_silently_run_as_python() -> None:
    document = _document(
        [_code("print('should never run')")],
        metadata={"kernelspec": {"name": "ir", "language": "R"}},
    )

    with pytest.raises(NotebookExecutionError, match="R"):
        execute_notebook(document, timeout=10, acknowledge_unsandboxed=True)


def test_explicit_kernel_override_bypasses_language_detection() -> None:
    document = _document(
        [_code("print('ran')")],
        metadata={"kernelspec": {"name": "ir", "language": "R"}},
    )

    report = execute_notebook(
        document, timeout=10, kernel=sys.executable, acknowledge_unsandboxed=True
    )

    assert report.kernel == sys.executable
    assert report.results[0].stdout == "ran\n"


def test_kernel_failure_is_reported_not_raised_as_an_unhandled_exception() -> None:
    """A nonexistent interpreter path is the cleanest reproducible stand-in
    for "the kernel process could not run at all" -- proving the adapter
    surfaces this as a controlled, structured outcome rather than letting
    OSError/FileNotFoundError escape uncaught."""
    document = _document([_code("pass")])

    report = execute_notebook(
        document, timeout=10, kernel="__nonexistent_interpreter__", acknowledge_unsandboxed=True
    )

    assert report.kernel_launch_error is not None
    assert report.completed is False
    assert report.results == ()


# ── LIBIPYNB-V4: cwd isolation ──────────────────────────────────────────────


def test_isolate_cwd_default_runs_in_a_fresh_temp_directory_and_cleans_up() -> None:
    document = _document([_code("import os; print(os.getcwd())")])

    report = execute_notebook(document, timeout=10, acknowledge_unsandboxed=True)

    assert report.work_dir is not None
    assert report.results[0].stdout.strip() == report.work_dir
    assert report.work_dir != os.getcwd()
    assert not Path(report.work_dir).exists(), "temp work dir must be cleaned up after the run"


def test_isolate_cwd_false_inherits_the_real_working_directory() -> None:
    document = _document([_code("import os; print(os.getcwd())")])

    report = execute_notebook(document, timeout=10, acknowledge_unsandboxed=True, isolate_cwd=False)

    assert report.work_dir is None
    assert report.results[0].stdout.strip() == os.getcwd()


# ── LIBIPYNB-V4: env isolation ──────────────────────────────────────────────


def test_isolate_env_default_strips_variables_outside_the_minimal_keep_list() -> None:
    document = _document([_code("import os; print(repr(os.environ.get('LIBIPYNB_TEST_SECRET')))")])

    with patch.dict(os.environ, {"LIBIPYNB_TEST_SECRET": "should-not-leak"}):
        report = execute_notebook(document, timeout=10, acknowledge_unsandboxed=True)

    assert report.results[0].stdout.strip() == "None"


def test_isolate_env_false_inherits_the_full_environment() -> None:
    document = _document([_code("import os; print(repr(os.environ.get('LIBIPYNB_TEST_SECRET')))")])

    with patch.dict(os.environ, {"LIBIPYNB_TEST_SECRET": "visible-when-not-isolated"}):
        report = execute_notebook(
            document, timeout=10, acknowledge_unsandboxed=True, isolate_env=False
        )

    assert report.results[0].stdout.strip() == "'visible-when-not-isolated'"


def test_extra_env_is_passed_through_even_while_isolating() -> None:
    document = _document([_code("import os; print(os.environ.get('LIBIPYNB_EXTRA'))")])

    report = execute_notebook(
        document,
        timeout=10,
        acknowledge_unsandboxed=True,
        extra_env={"LIBIPYNB_EXTRA": "provided-explicitly"},
    )

    assert report.results[0].stdout.strip() == "provided-explicitly"


# ── LIBIPYNB-V4: bounded output capture ─────────────────────────────────────


def test_output_beyond_max_output_bytes_is_truncated_and_reported() -> None:
    document = _document([_code("print('x' * 5000)")])

    report = execute_notebook(
        document, timeout=10, acknowledge_unsandboxed=True, max_output_bytes=200
    )

    assert report.output_truncated is True
    assert report.output_limit_bytes == 200
    # Truncation lands mid-record (the single 5000-char print never
    # finishes its JSON line before the 200-byte cap), so the incomplete
    # trailing record is dropped, not surfaced as a parse crash.
    assert report.results == ()


def test_output_within_max_output_bytes_is_not_truncated() -> None:
    document = _document([_code("print('short')")])

    report = execute_notebook(document, timeout=10, acknowledge_unsandboxed=True)

    assert report.output_truncated is False
    assert report.results[0].stdout == "short\n"


def test_max_output_bytes_none_disables_truncation() -> None:
    document = _document([_code("print('x' * 200)")])

    report = execute_notebook(
        document, timeout=10, acknowledge_unsandboxed=True, max_output_bytes=None
    )

    assert report.output_truncated is False
    assert report.output_limit_bytes is None


# ── LIBIPYNB-V4: memory limiting (platform-specific enforcement) ───────────


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-specific refusal behavior")
def test_max_memory_bytes_on_windows_refuses_rather_than_silently_ignoring() -> None:
    document = _document([_code("pass")])

    with pytest.raises(NotebookExecutionError, match="Windows"):
        execute_notebook(
            document,
            timeout=10,
            acknowledge_unsandboxed=True,
            max_memory_bytes=64 * 1024 * 1024,
        )


@pytest.mark.skipif(sys.platform == "win32", reason="RLIMIT_AS is POSIX-only")
def test_max_memory_bytes_is_enforced_on_posix() -> None:
    document = _document(
        [_code("data = bytearray(200 * 1024 * 1024)")]  # 200 MiB, well past the limit below
    )

    report = execute_notebook(
        document,
        timeout=10,
        acknowledge_unsandboxed=True,
        max_memory_bytes=64 * 1024 * 1024,
    )

    assert report.memory_limit_bytes == 64 * 1024 * 1024
    assert report.results[0].succeeded is False
    assert report.results[0].error is not None
    assert report.results[0].error.ename == "MemoryError"


@pytest.mark.skipif(sys.platform == "win32", reason="RLIMIT_AS is POSIX-only")
def test_max_memory_bytes_none_does_not_limit_normal_allocation_on_posix() -> None:
    document = _document([_code("data = bytearray(1024); print(len(data))")])

    report = execute_notebook(document, timeout=10, acknowledge_unsandboxed=True)

    assert report.memory_limit_bytes is None
    assert report.results[0].stdout.strip() == "1024"
