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
import sys
import time
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


def test_negative_max_output_bytes_is_rejected_before_running_anything() -> None:
    """LIBIPYNB-Q16 Gate G2 finding: an unvalidated negative value used to
    reach truncate_utf8_text's fallback-marker slice, where Python's
    negative-index slicing fabricated marker content onto cells whose
    stdout was empty and untouched. Rejected up front instead, matching the
    sibling engine's equally strict ExecutionOptions.max_output_bytes."""
    document = _document([_code("print('should never run')")])

    with pytest.raises(ValueError, match="max_output_bytes"):
        execute_notebook(document, timeout=10, acknowledge_unsandboxed=True, max_output_bytes=-1)


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


def test_timeout_partial_output_bytes_are_decoded_into_the_report() -> None:
    """LIBIPYNB-Q44: execute_notebook decodes the raw bytes
    ``_run_driver_subprocess`` returns exactly once, uniformly, regardless
    of platform or whether the run timed out -- superseding an earlier,
    now-structurally-impossible-to-reintroduce bug where
    ``subprocess.run``'s own timeout+kill path returned ``TimeoutExpired.
    stdout`` as ``str`` on Windows but raw ``bytes`` on POSIX, and the
    then-current code silently treated the POSIX bytes case as "nothing
    captured". Mocked at the driver-subprocess seam (not subprocess.run,
    which this path no longer calls) with real driver-format bytes,
    asserting the decode still happens correctly on the timed-out path."""
    document = _document([_code("print('captured')", "a")])
    driver_line = b'{"index": 0, "stdout": "captured\\n", "error": null}\n'

    with patch(
        "libipynb.adapters.execute._run_driver_subprocess",
        return_value=(driver_line, True),
    ):
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
    """LIBIPYNB-Q16 (P0-A): a single oversized cell's stdout is truncated
    IN PLACE on its own CellExecutionResult -- it is never dropped from
    ``results`` entirely. The previous version of this test asserted
    ``report.results == ()`` as correct, codifying the confirmed bug
    (byte-slicing the combined raw stream before parsing silently discarded
    every result once one cell's own line couldn't fit); this is a
    deliberate correction of that wrong assertion, not a weakening -- the
    old assertion described the defect, not the intended contract."""
    document = _document([_code("print('x' * 5000)")])

    report = execute_notebook(
        document, timeout=10, acknowledge_unsandboxed=True, max_output_bytes=200
    )

    assert report.output_truncated is True
    assert report.output_limit_bytes == 200
    assert len(report.results) == 1
    assert report.results[0].stdout_truncated is True
    assert len(report.results[0].stdout.encode("utf-8")) <= 200


def test_output_within_max_output_bytes_is_not_truncated() -> None:
    document = _document([_code("print('short')")])

    report = execute_notebook(document, timeout=10, acknowledge_unsandboxed=True)

    assert report.output_truncated is False
    assert report.results[0].stdout == "short\n"
    assert report.results[0].stdout_truncated is False


def test_max_output_bytes_none_disables_truncation() -> None:
    document = _document([_code("print('x' * 200)")])

    report = execute_notebook(
        document, timeout=10, acknowledge_unsandboxed=True, max_output_bytes=None
    )

    assert report.output_truncated is False
    assert report.output_limit_bytes is None


def test_oversized_first_cell_does_not_erase_small_later_cells() -> None:
    """LIBIPYNB-Q16's exact motivating regression: a big cell BEFORE small
    ones must not wipe the small ones' results, reproduced directly against
    the pre-fix code (a 3-cell run returned zero results, not two)."""
    document = _document(
        [
            _code("print('x' * 5000, end='')", "big"),
            _code("print('after1', end='')", "after1"),
            _code("print('after2', end='')", "after2"),
        ]
    )

    report = execute_notebook(
        document,
        timeout=10,
        acknowledge_unsandboxed=True,
        on_error="continue",
        max_output_bytes=200,
    )

    assert len(report.results) == 3
    assert report.total_code_cells == 3
    big, after1, after2 = report.results
    assert big.stdout_truncated is True
    # Every byte of the cumulative budget was already spent by the big
    # cell -- both later cells are correctly reported (never dropped) but
    # their own stdout is truncated to nothing, and flagged as such.
    assert after1.stdout_truncated is True
    assert after2.stdout_truncated is True
    assert after1.stdout == ""
    assert after2.stdout == ""


def test_oversized_middle_cell_leaves_the_first_cell_untouched() -> None:
    document = _document(
        [
            _code("print('before', end='')", "before"),
            _code("print('x' * 5000, end='')", "big"),
        ]
    )

    report = execute_notebook(
        document,
        timeout=10,
        acknowledge_unsandboxed=True,
        on_error="continue",
        max_output_bytes=2000,
    )

    before, big = report.results
    assert before.stdout == "before"
    assert before.stdout_truncated is False
    assert big.stdout_truncated is True


def test_oversized_last_cell_leaves_earlier_cells_untouched() -> None:
    document = _document(
        [
            _code("print('one', end='')", "one"),
            _code("print('two', end='')", "two"),
            _code("print('x' * 5000, end='')", "big"),
        ]
    )

    report = execute_notebook(
        document,
        timeout=10,
        acknowledge_unsandboxed=True,
        on_error="continue",
        max_output_bytes=2000,
    )

    one, two, big = report.results
    assert one.stdout == "one"
    assert two.stdout == "two"
    assert one.stdout_truncated is False
    assert two.stdout_truncated is False
    assert big.stdout_truncated is True


def test_multiple_oversized_cells_are_each_reported_and_correctly_budgeted() -> None:
    document = _document(
        [
            _code("print('x' * 3000, end='')", "big1"),
            _code("print('y' * 3000, end='')", "big2"),
        ]
    )

    report = execute_notebook(
        document,
        timeout=10,
        acknowledge_unsandboxed=True,
        on_error="continue",
        max_output_bytes=200,
    )

    assert len(report.results) == 2
    big1, big2 = report.results
    assert big1.stdout_truncated is True
    assert len(big1.stdout.encode("utf-8")) <= 200
    assert big2.stdout_truncated is True
    # big1 alone already exhausted the cumulative budget.
    assert big2.stdout == ""


def test_unicode_output_is_truncated_at_a_utf8_byte_boundary() -> None:
    document = _document([_code("print('é' * 500, end='')")])

    report = execute_notebook(
        document, timeout=10, acknowledge_unsandboxed=True, max_output_bytes=201
    )

    result = report.results[0]
    assert result.stdout_truncated is True
    result.stdout.encode("utf-8")  # must not raise
    assert len(result.stdout.encode("utf-8")) <= 201


def test_error_result_after_an_oversized_output_is_still_reported() -> None:
    document = _document(
        [
            _code("print('x' * 3000, end='')", "big"),
            _code("raise ValueError('boom')", "errors"),
        ]
    )

    report = execute_notebook(
        document,
        timeout=10,
        acknowledge_unsandboxed=True,
        on_error="continue",
        max_output_bytes=200,
    )

    big, errored = report.results
    assert big.stdout_truncated is True
    assert errored.error is not None
    assert errored.error.evalue == "boom"


def test_on_error_stop_still_correctly_budgets_output_before_stopping() -> None:
    document = _document(
        [
            _code("print('x' * 3000, end='')", "big"),
            _code("raise ValueError('boom')", "errors"),
            _code("print('never runs', end='')", "never"),
        ]
    )

    report = execute_notebook(
        document, timeout=10, acknowledge_unsandboxed=True, on_error="stop", max_output_bytes=200
    )

    assert len(report.results) == 2
    big, errored = report.results
    assert big.stdout_truncated is True
    assert errored.error is not None


def test_on_error_continue_budgets_output_across_every_cell() -> None:
    document = _document(
        [
            _code("print('x' * 3000, end='')", "big"),
            _code("raise ValueError('boom')", "errors"),
            _code("print('still runs', end='')", "still-runs"),
        ]
    )

    report = execute_notebook(
        document,
        timeout=10,
        acknowledge_unsandboxed=True,
        on_error="continue",
        max_output_bytes=200,
    )

    assert len(report.results) == 3
    assert report.total_code_cells == 3
    _big, errored, last = report.results
    assert errored.error is not None
    # Budget was already exhausted by the big cell -- the last cell still
    # gets an explicit, correctly-flagged result, just with empty stdout.
    assert last.stdout_truncated is True
    assert last.stdout == ""


def test_extremely_small_output_limit_does_not_crash() -> None:
    document = _document([_code("print('hello world')")])

    report = execute_notebook(
        document, timeout=10, acknowledge_unsandboxed=True, max_output_bytes=1
    )

    assert report.output_truncated is True
    assert isinstance(report.results[0].stdout, str)
    assert len(report.results[0].stdout.encode("utf-8")) <= 1


def test_timeout_plus_partial_output_still_correctly_budgets_what_was_captured() -> None:
    """The pre-existing timeout+partial-output contract (an incomplete
    trailing line is dropped, not surfaced as a crash) must keep holding
    once max_output_bytes is also in play -- the two mechanisms are
    independent and must not interact badly."""
    document = _document(
        [
            _code("print('before-sleep', end='')", "before"),
            _code("import time; time.sleep(30)", "sleeper"),
        ]
    )

    report = execute_notebook(
        document, timeout=1, acknowledge_unsandboxed=True, max_output_bytes=100
    )

    assert report.timed_out is True
    # Whatever was flushed before the timeout-kill is still correctly
    # budgeted, not corrupted by the interaction of the two mechanisms.
    for result in report.results:
        assert len(result.stdout.encode("utf-8")) <= 100


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


@pytest.mark.skipif(
    sys.platform in ("win32", "darwin"),
    reason="RLIMIT_AS enforcement is reliable on Linux only (LIBIPYNB-Q64: "
    "unreliable/crashing on macOS, see test_max_memory_bytes_on_macos_"
    "refuses_rather_than_silently_crashing below)",
)
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


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS-specific refusal behavior")
def test_max_memory_bytes_on_macos_refuses_rather_than_silently_crashing() -> None:
    # LIBIPYNB-Q64: before this fix, RLIMIT_AS's unreliability on macOS
    # surfaced as an opaque subprocess.SubprocessError from inside
    # preexec_fn, not a clean, documented refusal -- confirmed via a real
    # CI failure, not a hypothetical. This must fail loudly and early
    # instead, the same way the Windows case already does.
    document = _document([_code("pass")])

    with pytest.raises(NotebookExecutionError, match="macOS"):
        execute_notebook(
            document,
            timeout=10,
            acknowledge_unsandboxed=True,
            max_memory_bytes=64 * 1024 * 1024,
        )


@pytest.mark.skipif(sys.platform == "win32", reason="RLIMIT_AS is POSIX-only")
def test_max_memory_bytes_none_does_not_limit_normal_allocation_on_posix() -> None:
    document = _document([_code("data = bytearray(1024); print(len(data))")])

    report = execute_notebook(document, timeout=10, acknowledge_unsandboxed=True)

    assert report.memory_limit_bytes is None
    assert report.results[0].stdout.strip() == "1024"


# ── LIBIPYNB-Q44: grandchild process defeats timeout + is leaked ───────────
#
# Two compounding defects, both reproduced directly (not assumed) via a
# standalone diagnostic before this test was written:
#
# 1. execute_notebook's `timeout` is meant to bound wall-clock time -- the
#    whole point of an "opt-in execution adapter" for untrusted code. But
#    subprocess.run(timeout=...)'s kill path still calls communicate() to
#    drain output, which blocks reading the pipe until EOF. If a cell
#    spawns a grandchild process without redirecting ITS OWN stdout, the
#    grandchild inherits the driver's stdout pipe handle by default (a
#    well-known subprocess gotcha, not Windows-specific: `close_fds=True`
#    only closes *unnamed* fds, never fd 1/2 themselves, on POSIX either) --
#    so the pipe has a second writer, and EOF (hence communicate()'s
#    return, hence execute_notebook's own return) does not happen until
#    that grandchild ALSO exits, regardless of the driver already having
#    been killed. Reproduced directly: `timeout=2` against a driver whose
#    only cell spawns a `time.sleep(60)` grandchild made execute_notebook
#    itself take >60s to return, not ~2s -- the caller-visible bound the
#    `timeout` parameter promises was silently violated by nothing more
#    than the executed (untrusted!) cell code spawning a subprocess.
# 2. Separately, even once execute_notebook does return, the grandchild
#    itself was never explicitly terminated -- only the direct driver
#    process was killed (subprocess.run's internal kill signals exactly
#    one PID). A process a cell spawned and left running survives as a
#    leaked/orphaned process.
#
# Both share one root cause (the timeout path never manages the whole
# process TREE, only the one direct child) and one fix.


class TestTimeoutIsNotDefeatedByASpawnedGrandchild:
    def test_execute_notebook_returns_promptly_even_if_a_cell_spawns_a_long_lived_process(
        self,
    ) -> None:
        """The primary, most important invariant: wall-clock time to get a
        result back is actually bounded by `timeout`, regardless of what
        the executed cell code spawns. A grandchild sleeping for 20s must
        not make a `timeout=1` call take anywhere near that long."""
        document = _document(
            [
                _code(
                    "import subprocess, sys\n"
                    "child = subprocess.Popen(\n"
                    "    [sys.executable, '-c', 'import time; time.sleep(20)']\n"
                    ")\n"
                    "print(child.pid)\n",
                    "spawn",
                ),
                _code("import time; time.sleep(30)", "hang"),
            ]
        )

        t0 = time.monotonic()
        report = execute_notebook(document, timeout=1, acknowledge_unsandboxed=True)
        elapsed = time.monotonic() - t0

        assert report.timed_out is True
        # Generous margin over the 1s timeout for process-spawn/kill
        # overhead -- but decisively less than the grandchild's own 20s
        # lifetime, so this can only pass if the grandchild's lifetime
        # genuinely did not gate the return.
        assert elapsed < 10.0, (
            f"execute_notebook took {elapsed:.1f}s to return with timeout=1 -- "
            "a spawned grandchild process defeated the timeout bound "
            "(LIBIPYNB-Q44)"
        )

    def test_a_process_spawned_by_a_cell_does_not_survive_a_timeout_kill(self) -> None:
        psutil = pytest.importorskip("psutil")

        document = _document(
            [
                _code(
                    "import subprocess, sys\n"
                    "child = subprocess.Popen(\n"
                    "    [sys.executable, '-c', 'import time; time.sleep(20)']\n"
                    ")\n"
                    "print(child.pid)\n",
                    "spawn",
                ),
                _code("import time; time.sleep(30)", "hang"),
            ]
        )

        report = execute_notebook(document, timeout=1, acknowledge_unsandboxed=True)

        assert report.timed_out is True
        assert len(report.results) == 1, "the spawning cell's own result must have flushed"
        child_pid = int(report.results[0].stdout.strip())

        # Give the OS a brief, bounded grace period to finish tearing the
        # process down -- psutil.Process(pid) can still resolve a just-killed
        # PID for a short window before it's fully reaped. The grandchild's
        # own 20s sleep is long enough that reaching this point via natural
        # exit (rather than actual cleanup) would already contradict the
        # companion test's <10s bound -- this test still checks cleanup
        # directly and independently, without relying on that ordering.
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            try:
                child = psutil.Process(child_pid)
                if child.status() == psutil.STATUS_ZOMBIE:
                    break
            except psutil.NoSuchProcess:
                break
            time.sleep(0.2)
        else:
            pytest.fail(
                f"grandchild process {child_pid} was still running "
                f"{deadline - time.monotonic():.1f}s past the timeout-kill -- "
                "execute_notebook's timeout path only killed the direct "
                "driver subprocess, not processes the executed cell code "
                "itself spawned (LIBIPYNB-Q44)"
            )


# ── LIBIPYNB-Q44 Gate-G2 review finding (MAJOR): stdin write also unbounded ─
#
# The first fix moved stdout draining to a background thread but left
# ``process.stdin.write(payload)`` synchronous on the main thread, before
# ``process.wait(timeout=...)`` is ever reached -- the exact same failure
# shape on the write side that the read side was just fixed for. A payload
# larger than the OS pipe buffer (~64KB), combined with a driver that
# hasn't started reading stdin yet (slow interpreter startup, antivirus
# scan-on-spawn, system load), blocks that write with zero timeout
# protection -- and worse, the run can come back reporting
# ``timed_out=False`` even though it took far longer than requested,
# since the hang happens before the timeout-measuring wait() call is even
# reached. Reproduced directly (mirroring the independent Gate-G2 review's
# own repro): a large payload against a driver replaced with one that
# sleeps before touching stdin at all.


class TestTimeoutIsNotDefeatedByALargeStdinPayload:
    def test_execute_notebook_returns_promptly_even_with_a_slow_to_start_driver(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import libipynb.adapters.execute as execute_module

        # Sleeps well past the requested timeout before reading stdin at
        # all -- if the payload also exceeds the OS pipe buffer, a
        # synchronous stdin write on the main thread would block for
        # (most of) that sleep, regardless of `timeout`.
        slow_start_driver = "import sys, time\ntime.sleep(5)\nsys.stdin.read()\n"
        monkeypatch.setattr(execute_module, "_DRIVER_SCRIPT", slow_start_driver)

        # One cell with a source large enough to exceed any realistic OS
        # pipe buffer size once JSON-encoded as part of the request payload.
        document = _document([_code("x = 1  # " + ("a" * (2 * 1024 * 1024)))])

        t0 = time.monotonic()
        report = execute_module.execute_notebook(document, timeout=1, acknowledge_unsandboxed=True)
        elapsed = time.monotonic() - t0

        assert report.timed_out is True
        assert elapsed < 4.0, (
            f"execute_notebook took {elapsed:.1f}s to return with timeout=1 -- "
            "a large payload blocked the synchronous stdin write on the main "
            "thread, defeating the timeout before process.wait() was even "
            "reached (LIBIPYNB-Q44)"
        )
