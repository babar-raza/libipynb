"""LIBIPYNB-P4a-1/P4b/P4c (plans/full-parity-plan.md, Gate G6 sign-off §7):
the real Jupyter-kernel-protocol execution backend.

These are real-kernel integration tests -- every test in this file launches
an actual ``ipykernel`` process via ``nbclient``/``jupyter_client`` (the
``exec`` extra). They are not mocked and not skipped by default: CI must
install the ``exec`` extra plus ``ipykernel`` for this file to prove
anything, matching this project's own stated rule that "real executor
integration tests must run with a known CI kernel... not converted to
optional skips that can never prove the feature." A missing ``exec`` extra
or missing kernel produces one clear collection-time skip (via
``pytest.importorskip``/``pytest.mark.skipif`` at module scope below), not
647 masked one.

Scope, stated precisely (mirrors the subprocess adapter's own module
docstring, which does this for its own engine):

- This backend is NOT a sandbox. Every test below runs code the test
  itself wrote -- proving *behavior*, not proving *safety*.
- ``skip_tag`` (default ``"skip-execution"``) delegates to ``nbclient``'s
  own identically-named, identically-defaulted trait -- verified directly
  against the installed ``nbclient==0.11.0`` source, not assumed.
- Fidelity strategy: only ``outputs``/``execution_count``/(optionally)
  ``metadata.execution`` are ever written back onto a deep copy of the
  original raw dict; everything else (source form, cell id, attachments,
  unknown metadata) is asserted preserved by direct equality against the
  input, not merely "not obviously broken."
"""

from __future__ import annotations

import asyncio
import threading
import time
from pathlib import Path

import pytest

pytest.importorskip("nbclient", reason="nbclient (exec extra) is not installed")
pytest.importorskip("jupyter_client", reason="jupyter_client (exec extra) is not installed")
kernelspec = pytest.importorskip(
    "jupyter_client.kernelspec", reason="jupyter_client (exec extra) is not installed"
)
if "python3" not in kernelspec.find_kernel_specs():
    pytest.skip("no ipykernel-provided 'python3' kernelspec is installed", allow_module_level=True)

from libipynb import NotebookDocument
from libipynb.errors import NotebookExecutionError
from libipynb.execution import ExecutionOptions, ExecutionResult, LocalJupyterExecutor

pytestmark = pytest.mark.timeout(120)


def _document(cells: list[dict], metadata: dict | None = None) -> NotebookDocument:
    return NotebookDocument(
        {
            "nbformat": 4,
            "nbformat_minor": 5,
            "metadata": metadata
            or {
                "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"}
            },
            "cells": cells,
        }
    )


def _code(source: str, cell_id: str = "c", *, tags: list[str] | None = None) -> dict:
    metadata: dict = {"tags": tags} if tags else {}
    return {
        "cell_type": "code",
        "id": cell_id,
        "metadata": metadata,
        "execution_count": None,
        "outputs": [],
        "source": source,
    }


def _markdown(source: str = "# hi", cell_id: str = "m") -> dict:
    return {"cell_type": "markdown", "id": cell_id, "metadata": {}, "source": source}


def _raw(source: str = "raw text", cell_id: str = "r") -> dict:
    return {"cell_type": "raw", "id": cell_id, "metadata": {}, "source": source}


@pytest.fixture
def executor() -> LocalJupyterExecutor:
    return LocalJupyterExecutor()


def _opts(**overrides: object) -> ExecutionOptions:
    base: dict[str, object] = {"acknowledge_unsandboxed": True, "cell_timeout": 30}
    base.update(overrides)
    return ExecutionOptions(**base)  # type: ignore[arg-type]


# ── Opt-in gate: not a sandbox, must be acknowledged explicitly ────────────


def test_execute_refuses_without_acknowledgment(executor: LocalJupyterExecutor) -> None:
    document = _document([_code("print('should never run')")])

    with pytest.raises(NotebookExecutionError, match="sandbox"):
        executor.execute(document)


def test_execute_runs_once_acknowledged(executor: LocalJupyterExecutor) -> None:
    document = _document([_code("print('ran')")])

    result = executor.execute(document, options=_opts())

    assert result.cell_records[0].outputs[0]["text"] == "ran\n"


# ── Missing optional dependency: structured, not a bare ImportError ────────


def test_local_jupyter_executor_reports_missing_dependency_structurally() -> None:
    import sys as _sys
    from unittest.mock import patch

    with patch.dict(
        _sys.modules, {"nbclient": None, "jupyter_client": None, "nbclient.exceptions": None}
    ):
        from libipynb.execution.exceptions import MissingExecutionDependencyError

        with pytest.raises(MissingExecutionDependencyError, match="libipynb\\[exec\\]"):
            LocalJupyterExecutor()


# ── Successful execution / output fidelity ──────────────────────────────────


def test_stdout_is_captured_as_a_stream_output(executor: LocalJupyterExecutor) -> None:
    document = _document([_code("print('hello')")])

    result = executor.execute(document, options=_opts())

    outputs = result.cell_records[0].outputs
    assert outputs == ({"output_type": "stream", "name": "stdout", "text": "hello\n"},)


def test_stderr_is_captured_as_a_stream_output(executor: LocalJupyterExecutor) -> None:
    document = _document([_code("import sys; print('oops', file=sys.stderr)")])

    result = executor.execute(document, options=_opts())

    outputs = result.cell_records[0].outputs
    assert outputs[0]["output_type"] == "stream"
    assert outputs[0]["name"] == "stderr"
    assert outputs[0]["text"] == "oops\n"


def test_execute_result_output_and_execution_count(executor: LocalJupyterExecutor) -> None:
    document = _document([_code("21 * 2")])

    result = executor.execute(document, options=_opts())

    record = result.cell_records[0]
    assert record.execution_count == 1
    assert record.outputs[0]["output_type"] == "execute_result"
    assert record.outputs[0]["data"]["text/plain"] == "42"
    assert result.notebook.cells[0]["execution_count"] == 1


def test_multiple_mime_representations_are_preserved(executor: LocalJupyterExecutor) -> None:
    document = _document(
        [
            _code(
                "class R:\n"
                "    def _repr_html_(self):\n"
                "        return '<b>bold</b>'\n"
                "    def __repr__(self):\n"
                "        return 'plain-repr'\n"
                "R()"
            )
        ]
    )

    result = executor.execute(document, options=_opts())

    data = result.cell_records[0].outputs[0]["data"]
    assert data["text/html"] == "<b>bold</b>"
    assert data["text/plain"] == "plain-repr"


def test_display_data_output(executor: LocalJupyterExecutor) -> None:
    document = _document(
        [_code("from IPython.display import display, HTML\ndisplay(HTML('<i>hi</i>'))")]
    )

    result = executor.execute(document, options=_opts())

    outputs = result.cell_records[0].outputs
    assert outputs[0]["output_type"] == "display_data"
    assert outputs[0]["data"]["text/html"] == "<i>hi</i>"


def test_state_persists_across_cells_sharing_a_kernel(executor: LocalJupyterExecutor) -> None:
    document = _document([_code("x = 21", "a"), _code("print(x * 2)", "b")])

    result = executor.execute(document, options=_opts())

    assert result.cell_records[1].outputs[0]["text"] == "42\n"


def test_unicode_output_round_trips(executor: LocalJupyterExecutor) -> None:
    document = _document([_code("print('héllo wörld 日本語 🎉')")])

    result = executor.execute(document, options=_opts())

    assert result.cell_records[0].outputs[0]["text"] == "héllo wörld 日本語 🎉\n"


def test_empty_code_cell_produces_no_outputs(executor: LocalJupyterExecutor) -> None:
    document = _document([_code("")])

    result = executor.execute(document, options=_opts())

    record = result.cell_records[0]
    assert record.outputs == ()
    assert record.execution_count is None


def test_multiple_outputs_in_one_cell_are_all_captured(executor: LocalJupyterExecutor) -> None:
    document = _document([_code("print('one')\nprint('two')\n3 + 3")])

    result = executor.execute(document, options=_opts())

    outputs = result.cell_records[0].outputs
    assert len(outputs) == 2
    assert outputs[0]["output_type"] == "stream"
    assert outputs[0]["text"] == "one\ntwo\n"
    assert outputs[1]["output_type"] == "execute_result"
    assert outputs[1]["data"]["text/plain"] == "6"


def test_clear_output_removes_prior_output_within_the_same_cell(
    executor: LocalJupyterExecutor,
) -> None:
    document = _document(
        [_code("from IPython.display import clear_output\nprint('shown')\nclear_output()")]
    )

    result = executor.execute(document, options=_opts())

    assert result.cell_records[0].outputs == ()


# ── Non-code cells: never executed, never mutated ───────────────────────────


def test_markdown_and_raw_cells_are_not_executed(executor: LocalJupyterExecutor) -> None:
    document = _document([_markdown("# Title"), _raw("plain text"), _code("print('code ran')")])

    result = executor.execute(document, options=_opts())

    assert result.cell_records[0].executed is False
    assert result.cell_records[1].executed is False
    assert result.cell_records[2].outputs[0]["text"] == "code ran\n"
    assert result.notebook.cells[0] == document.cells[0]
    assert result.notebook.cells[1] == document.cells[1]


# ── Skip-tagged cells: never sent to the kernel, outputs untouched ──────────


def test_skip_tagged_cell_is_never_executed_and_keeps_its_prior_outputs(
    executor: LocalJupyterExecutor,
) -> None:
    stale_output = {"output_type": "stream", "name": "stdout", "text": "stale\n"}
    skipped = _code("print('should not run')", "skip1", tags=["skip-execution"])
    skipped["outputs"] = [stale_output]
    skipped["execution_count"] = 7
    document = _document([skipped, _code("x = 1", "run1")])

    result = executor.execute(document, options=_opts())

    record = result.cell_records[0]
    assert record.skipped is True
    assert record.executed is False
    assert record.outputs == (stale_output,)
    assert record.execution_count == 7
    assert result.notebook.cells[0]["outputs"] == [stale_output]


def test_custom_skip_tag_is_honored(executor: LocalJupyterExecutor) -> None:
    document = _document(
        [_code("print('should not run')", "s", tags=["dont-run"]), _code("print('runs')", "r")]
    )

    result = executor.execute(document, options=_opts(skip_tag="dont-run"))

    assert result.cell_records[0].skipped is True
    assert result.cell_records[1].outputs[0]["text"] == "runs\n"


# ── Structural fidelity: cell id, unknown metadata, source form ────────────


def test_cell_ids_and_unknown_metadata_are_preserved(executor: LocalJupyterExecutor) -> None:
    cell = _code("42", "keep-this-id")
    cell["metadata"]["some_unknown_extension_field"] = {"nested": ["a", "b"]}
    document = _document([cell])

    result = executor.execute(document, options=_opts())

    executed_cell = result.notebook.cells[0]
    assert executed_cell["id"] == "keep-this-id"
    assert executed_cell["metadata"]["some_unknown_extension_field"] == {"nested": ["a", "b"]}


def test_notebook_level_unknown_metadata_is_preserved(executor: LocalJupyterExecutor) -> None:
    document = _document(
        [_code("1")],
        metadata={
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
            "custom_project_field": {"team": "libipynb"},
        },
    )

    result = executor.execute(document, options=_opts())

    assert result.notebook.metadata["custom_project_field"] == {"team": "libipynb"}


def test_list_of_lines_source_form_is_preserved_unchanged_and_actually_executes(
    executor: LocalJupyterExecutor,
) -> None:
    """LIBIPYNB-Q1 regression: the standard on-disk Jupyter source form
    (list-of-lines, ~40% of this project's own fixtures per the forensic
    audit) must both round-trip unchanged in the result AND actually
    execute -- the prior version of this test only checked the former,
    which is exactly the blind spot that let the execution engine ship
    completely unable to run this input (AttributeError: 'list' object has
    no attribute 'strip', deep inside nbclient, misreported as a generic
    kernel_death_error)."""
    cell = _code(["print(1)\n", "print(2)"], "c")
    document = _document([cell])

    result = executor.execute(document, options=_opts())

    # Preservation (the only thing the old, weak test checked):
    assert result.notebook.cells[0]["source"] == ["print(1)\n", "print(2)"]
    # Execution actually happened -- absent before this fix:
    assert result.completed is True
    assert result.kernel_death_error is None
    assert result.kernel_launch_error is None
    record = result.cell_records[0]
    assert record.executed is True
    assert record.error is None
    assert record.outputs[0]["text"] == "1\n2\n"


def test_list_of_lines_source_form_actually_executes_via_execute_async(
    executor: LocalJupyterExecutor,
) -> None:
    """Same regression as above, via the async entry point -- both call the
    same _build_client(), but this proves the fix isn't sync-path-only."""
    cell = _code(["print(3)\n", "print(4)"], "c")
    document = _document([cell])

    result = asyncio.run(executor.execute_async(document, options=_opts()))

    assert result.completed is True
    assert result.kernel_death_error is None
    record = result.cell_records[0]
    assert record.executed is True
    assert record.outputs[0]["text"] == "3\n4\n"


# ── Non-mutating default vs. in_place ───────────────────────────────────────


def test_default_execution_does_not_mutate_the_source_document(
    executor: LocalJupyterExecutor,
) -> None:
    document = _document([_code("1 + 1")])

    result = executor.execute(document, options=_opts())

    assert document.cells[0]["outputs"] == []
    assert document.cells[0]["execution_count"] is None
    assert result.notebook is not document
    assert result.notebook.cells[0]["outputs"] != []


def test_in_place_true_mutates_the_source_document_and_returns_it(
    executor: LocalJupyterExecutor,
) -> None:
    document = _document([_code("1 + 1")])

    result = executor.execute(document, options=_opts(in_place=True))

    assert result.notebook is document
    assert document.cells[0]["outputs"][0]["data"]["text/plain"] == "2"


# ── Working directory ────────────────────────────────────────────────────────


def test_working_directory_controls_the_kernel_process_cwd(
    executor: LocalJupyterExecutor, tmp_path: Path
) -> None:
    document = _document([_code("import os; print(os.getcwd())")])

    result = executor.execute(document, options=_opts(working_directory=str(tmp_path)))

    reported = result.cell_records[0].outputs[0]["text"].strip()
    assert Path(reported).resolve() == tmp_path.resolve()


def test_nonexistent_working_directory_is_rejected_before_starting_a_kernel(
    executor: LocalJupyterExecutor, tmp_path: Path
) -> None:
    document = _document([_code("pass")])
    missing = tmp_path / "does-not-exist"

    with pytest.raises(ValueError, match="working_directory"):
        executor.execute(document, options=_opts(working_directory=str(missing)))


# ── Timing metadata (opt-in) ─────────────────────────────────────────────────


def test_record_timing_false_by_default_adds_no_execution_metadata(
    executor: LocalJupyterExecutor,
) -> None:
    document = _document([_code("1")])

    result = executor.execute(document, options=_opts())

    assert "execution" not in result.notebook.cells[0].get("metadata", {})


def test_record_timing_true_adds_execution_timestamps(executor: LocalJupyterExecutor) -> None:
    document = _document([_code("1")])

    result = executor.execute(document, options=_opts(record_timing=True))

    execution_meta = result.notebook.cells[0]["metadata"]["execution"]
    assert "iopub.status.busy" in execution_meta
    assert "iopub.status.idle" in execution_meta


# ── Error handling: structural, never a raised Python exception ────────────


def test_syntax_error_is_reported_as_a_structured_cell_error(
    executor: LocalJupyterExecutor,
) -> None:
    document = _document([_code("def broken(:\n    pass")])

    result = executor.execute(document, options=_opts())

    record = result.cell_records[0]
    assert record.succeeded is False
    assert record.error is not None
    assert record.error.ename == "SyntaxError"


def test_runtime_exception_is_reported_as_a_structured_cell_error(
    executor: LocalJupyterExecutor,
) -> None:
    document = _document([_code("raise ValueError('boom')")])

    result = executor.execute(document, options=_opts())

    record = result.cell_records[0]
    assert record.error is not None
    assert record.error.ename == "ValueError"
    assert record.error.evalue == "boom"
    assert any("ValueError" in line for line in record.error.traceback)


def test_stop_on_error_true_halts_remaining_cells(executor: LocalJupyterExecutor) -> None:
    document = _document(
        [_code("raise ValueError('boom')", "a"), _code("print('should not run')", "b")]
    )

    result = executor.execute(document, options=_opts(stop_on_error=True))

    assert result.stopped_early is True
    assert result.completed is True  # stopped by policy, not killed
    assert result.cell_records[1].executed is False


def test_stop_on_error_false_runs_every_cell_regardless_of_failure(
    executor: LocalJupyterExecutor,
) -> None:
    document = _document(
        [_code("raise ValueError('boom')", "a"), _code("print('still runs')", "b")]
    )

    result = executor.execute(document, options=_opts(stop_on_error=False))

    assert result.stopped_early is False
    assert result.cell_records[0].error is not None
    assert result.cell_records[1].outputs[0]["text"] == "still runs\n"


def test_first_error_surfaces_the_earliest_failure(executor: LocalJupyterExecutor) -> None:
    document = _document([_code("print('ok')", "a"), _code("raise KeyError('missing')", "b")])

    result = executor.execute(document, options=_opts(stop_on_error=False))

    assert result.first_error is not None
    assert result.first_error.ename == "KeyError"


# ── Timeouts and interruption ────────────────────────────────────────────────


def test_interrupt_on_timeout_true_reports_the_timeout_as_a_cell_error(
    executor: LocalJupyterExecutor,
) -> None:
    """LIBIPYNB-Q2: this assertion is an intentional, evidence-driven
    correction, not a regression -- `result.timed_out` used to be `False`
    here because nbclient raises no exception at all for a genuine timeout
    under `interrupt_on_timeout=True` (verified directly against the
    installed nbclient source: `_async_handle_timeout` sends an interrupt
    and returns, never raises). The watchdog now confirms this
    independently of nbclient's own exception shape, so `timed_out` fires
    correctly here while the cell's own `KeyboardInterrupt` error (which by
    itself is NOT a reliable timeout signal -- see the module docstring)
    is still reported unchanged."""
    document = _document([_code("import time; time.sleep(10)", "a"), _code("print('after')", "b")])

    result = executor.execute(
        document, options=_opts(cell_timeout=1, interrupt_on_timeout=True, stop_on_error=False)
    )

    assert result.timed_out is True
    assert result.timed_out_cell_index == 0
    record = result.cell_records[0]
    assert record.error is not None
    assert record.error.ename == "KeyboardInterrupt"
    assert record.timed_out is True


def test_interrupt_on_timeout_false_aborts_the_whole_run(executor: LocalJupyterExecutor) -> None:
    document = _document([_code("import time; time.sleep(10)", "a"), _code("print('after')", "b")])

    result = executor.execute(document, options=_opts(cell_timeout=1, interrupt_on_timeout=False))

    assert result.timed_out is True
    assert result.timed_out_cell_index == 0
    assert result.completed is False
    assert result.cell_records[1].executed is False


def test_a_generous_timeout_does_not_interfere_with_normal_execution(
    executor: LocalJupyterExecutor,
) -> None:
    document = _document([_code("print('fine')")])

    result = executor.execute(document, options=_opts(cell_timeout=30))

    assert result.timed_out is False
    assert result.cell_records[0].outputs[0]["text"] == "fine\n"


# ── Kernel launch failure and kernel death ──────────────────────────────────


def test_missing_kernel_is_reported_structurally_not_raised(
    executor: LocalJupyterExecutor,
) -> None:
    document = _document([_code("pass")])

    result = executor.execute(
        document,
        options=_opts(kernel_name="__nonexistent_kernel__", kernel_startup_timeout=10),
    )

    assert result.kernel_launch_error is not None
    assert result.completed is False
    assert all(not r.executed for r in result.cell_records)


def test_kernel_death_mid_run_is_reported_structurally(executor: LocalJupyterExecutor) -> None:
    document = _document([_code("import os; os._exit(1)", "a"), _code("print('never')", "b")])

    result = executor.execute(document, options=_opts())

    assert result.kernel_death_error is not None
    assert result.completed is False
    assert result.cell_records[1].executed is False


# ── Interactive stdin (permanently disabled in this backend) ───────────────


def test_stdin_request_while_disabled_is_a_structured_cell_error(
    executor: LocalJupyterExecutor,
) -> None:
    document = _document([_code("input('prompt: ')")])

    result = executor.execute(document, options=_opts())

    record = result.cell_records[0]
    assert record.error is not None
    assert record.error.ename == "StdinNotImplementedError"


# ── Async execution ──────────────────────────────────────────────────────────


def test_execute_async_runs_a_notebook(executor: LocalJupyterExecutor) -> None:
    document = _document([_code("print('async hello')")])

    async def run() -> object:
        return await executor.execute_async(document, options=_opts())

    result = asyncio.run(run())

    assert result.cell_records[0].outputs[0]["text"] == "async hello\n"


def test_execute_async_cancellation_propagates_and_cleans_up_the_kernel(
    executor: LocalJupyterExecutor,
) -> None:
    """Two real, independently confirmed bugs this test guards against:

    1. nbclient's own ``async_setup_kernel`` context-manager cleanup does
       not reliably run when the enclosing task is cancelled out from under
       ``await client.async_execute()`` -- a real, reproduced kernel-process
       leak (psutil child-process tracking showed the kernel process still
       alive 15+ seconds after cancellation with no explicit cleanup).

    2. A race inside nbclient itself (``client.py``'s ``async_execute_cell``:
       ``except asyncio.CancelledError: raise DeadKernelError("Kernel died")
       from None``, on its own ``await self.task_poll_for_reply``) can
       convert an external cancellation into an unrelated-looking exception,
       non-deterministically, depending purely on event-loop scheduling
       timing at the moment ``task.cancel()`` is delivered -- confirmed by
       direct, repeated reproduction: the identical test, byte-for-byte,
       surfaced ``asyncio.CancelledError`` on most runs and a completed
       ``ExecutionResult`` with ``kernel_death_error`` set on others.

    ``LocalJupyterExecutor.execute_async`` closes both: explicit cleanup
    before re-raising (bug 1), and ``Task.cancelling()``-based
    classification (``_is_requested_cancellation``, unit-tested directly in
    tests/unit/test_jupyter_execute_cancellation.py) that makes the *public
    contract* deterministic regardless of which exception nbclient's race
    happens to surface (bug 2) -- cancelling always raises
    ``asyncio.CancelledError`` to the caller now, never a normal result.
    Run several times in a loop specifically because the race is timing-
    dependent: a single pass proves little about a race that only showed
    up some of the time before the fix."""
    import os

    import psutil

    me = psutil.Process(os.getpid())

    async def run_one_trial() -> None:
        document = _document([_code("import time; time.sleep(30)")])
        task = asyncio.ensure_future(
            executor.execute_async(document, options=_opts(cell_timeout=60))
        )
        await asyncio.sleep(2)
        assert me.children(recursive=True), "kernel process should be running by now"
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        else:
            raise AssertionError(
                "cancelling the task must always raise asyncio.CancelledError -- "
                "getting a normal return here means the nbclient race (see "
                "docstring) was not actually classified as a cancellation"
            )
        assert me.children(recursive=True) == [], "kernel process must be cleaned up"

    async def run() -> None:
        for _ in range(5):
            await run_one_trial()

    asyncio.run(run())


# ── Extra environment variables ─────────────────────────────────────────────


def test_extra_env_is_visible_to_the_kernel(executor: LocalJupyterExecutor) -> None:
    document = _document([_code("import os; print(os.environ.get('LIBIPYNB_EXTRA'))")])

    result = executor.execute(
        document, options=_opts(extra_env={"LIBIPYNB_EXTRA": "provided-explicitly"})
    )

    assert result.cell_records[0].outputs[0]["text"].strip() == "provided-explicitly"


# ── Lifecycle callback ───────────────────────────────────────────────────────


def test_on_event_receives_cell_started_and_finished_events_in_order(
    executor: LocalJupyterExecutor,
) -> None:
    from libipynb.execution import ExecutionEvent

    events: list[ExecutionEvent] = []
    document = _document([_code("1", "a"), _code("2", "b")])

    executor.execute(document, options=_opts(on_event=events.append))

    kinds_and_indices = [(e.kind, e.cell_index) for e in events]
    assert kinds_and_indices == [
        ("cell_started", 0),
        ("cell_finished", 0),
        ("cell_started", 1),
        ("cell_finished", 1),
    ]
    assert events[0].cell_id == "a"


# ── Round-trip: executed document is valid nbformat and reloadable ─────────


def test_executed_document_round_trips_through_dump_and_load(
    executor: LocalJupyterExecutor, tmp_path: Path
) -> None:
    from libipynb import dump, load, validate

    document = _document([_markdown(), _code("print('hi')", "c1")])

    result = executor.execute(document, options=_opts())

    report = validate(result.notebook.raw)
    assert report.is_valid, [d.message for d in report]

    out_path = tmp_path / "executed.ipynb"
    dump(result.notebook, out_path, profile="declared")
    reloaded = load(out_path, mode="preservation")
    assert reloaded.cells[1]["outputs"][0]["text"] == "hi\n"


# ── LIBIPYNB-Q2: safety/fidelity hardening ──────────────────────────────────


def test_synchronous_execute_cancels_a_pending_watchdog_timer_before_propagating_keyboard_interrupt(
    executor: LocalJupyterExecutor,
) -> None:
    """Found by an independent Gate G2 review of the watchdog redesign:
    execute()'s deliberately-uncaught KeyboardInterrupt/SystemExit path
    used to skip _finish() -- and therefore its unconditional
    cancel_pending_timer() call -- entirely, potentially leaving an armed
    watchdog timer running past the call's return (bounded, harmless, but
    real). Simulates a timer genuinely being armed via the real
    `on_cell_execute` hook nbclient itself calls, at the exact moment the
    interrupt fires, then asserts no timer thread survives."""
    from unittest.mock import patch

    document = _document([_code("1 + 1")])

    def _raise_after_arming_watchdog(self: object, **_kwargs: object) -> None:
        self.on_cell_execute(cell={"id": "a"}, cell_index=0)  # type: ignore[attr-defined]
        raise KeyboardInterrupt("simulated ctrl-c mid-cell")

    before = set(threading.enumerate())
    with (
        patch(
            "nbclient.NotebookClient.execute",
            side_effect=_raise_after_arming_watchdog,
            autospec=True,
        ),
        pytest.raises(KeyboardInterrupt),
    ):
        executor.execute(document, options=_opts(cell_timeout=1))
    assert _extra_threads_after(before) == set()


def test_synchronous_execute_propagates_keyboard_interrupt(
    executor: LocalJupyterExecutor,
) -> None:
    """Previously `execute()` caught `BaseException`, silently swallowing
    KeyboardInterrupt/SystemExit -- a caller's own Ctrl+C could not
    interrupt a hung synchronous execute() call. Confirmed by monkeypatching
    the real nbclient.NotebookClient.execute to raise KeyboardInterrupt,
    exactly as the forensic audit's own reproduction did."""
    from unittest.mock import patch

    document = _document([_code("1 + 1")])

    with (
        patch("nbclient.NotebookClient.execute", side_effect=KeyboardInterrupt("simulated ctrl-c")),
        pytest.raises(KeyboardInterrupt),
    ):
        executor.execute(document, options=_opts())


def test_cell_execution_record_outputs_are_independently_mutable_from_the_notebook(
    executor: LocalJupyterExecutor,
) -> None:
    """Previously CellExecutionRecord.outputs shared mutable nested dict
    objects with result.notebook's own cell outputs -- mutating one
    silently corrupted the other despite CellExecutionRecord being
    declared frozen=True."""
    document = _document([_code("print('hello')")])

    result = executor.execute(document, options=_opts())

    record_output = result.cell_records[0].outputs[0]
    notebook_output = result.notebook.cells[0]["outputs"][0]
    assert record_output is not notebook_output, "must not be the same object"
    record_output["text"] = "MUTATED"
    assert notebook_output["text"] != "MUTATED", (
        "mutating CellExecutionRecord.outputs must not corrupt result.notebook"
    )


def test_cancellation_unregisters_nbclients_own_atexit_cleanup_hook(
    executor: LocalJupyterExecutor,
) -> None:
    """Previously the cancellation-cleanup path never called
    atexit.unregister(client._cleanup_kernel), leaving nbclient's own
    atexit-registered hook (and the strong reference it holds) alive for
    the rest of the process -- producing a noisy, uncatchable
    "AssertionError" traceback at interpreter exit."""
    import atexit
    from unittest.mock import patch

    from nbclient import NotebookClient

    def _is_cleanup_kernel_hook(fn: object) -> bool:
        # nbclient assigns `_cleanup_kernel = run_sync(_async_cleanup_kernel)`
        # as a class attribute; jupyter_core's `run_sync()` returns a bare
        # closure literally named `wrapped` (no `functools.wraps`), so
        # identifying it by name alone would also match unrelated
        # `run_sync`-wrapped callables -- narrow to ones bound to a
        # `NotebookClient` instance specifically.
        return getattr(fn, "__name__", None) == "wrapped" and isinstance(
            getattr(fn, "__self__", None), NotebookClient
        )

    async def run() -> None:
        document = _document([_code("import time; time.sleep(30)")])
        task = asyncio.ensure_future(
            executor.execute_async(document, options=_opts(cell_timeout=60))
        )
        await asyncio.sleep(2)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    with (
        patch.object(atexit, "register", wraps=atexit.register) as register_spy,
        patch.object(atexit, "unregister", wraps=atexit.unregister) as unregister_spy,
    ):
        asyncio.run(run())

    registered = [
        call.args[0]
        for call in register_spy.call_args_list
        if call.args and _is_cleanup_kernel_hook(call.args[0])
    ]
    unregistered = [
        call.args[0]
        for call in unregister_spy.call_args_list
        if call.args and _is_cleanup_kernel_hook(call.args[0])
    ]

    assert registered, (
        "expected nbclient to register its own _cleanup_kernel atexit hook during execution"
    )
    assert any(r == u for r in registered for u in unregistered), (
        "cancellation cleanup must call atexit.unregister(client._cleanup_kernel) "
        "to release nbclient's own hook after a cancelled execute_async() call"
    )


def test_max_output_bytes_truncates_only_the_oversized_output_not_downstream_cells(
    executor: LocalJupyterExecutor,
) -> None:
    """A small cell AFTER an oversized one must still get its own correct,
    untruncated output -- the specific regression class already confirmed
    in the older subprocess engine (adapters/execute.py), which must not
    be reproduced here since truncation is applied per-output, never by
    slicing a combined byte stream."""
    document = _document(
        [
            _code("print('before', end='')", "before"),
            _code("print('x' * 1_000_000, end='')", "big"),
            _code("print('after', end='')", "after"),
        ]
    )

    result = executor.execute(document, options=_opts(stop_on_error=False, max_output_bytes=1024))

    before_record, big_record, after_record = result.cell_records
    assert before_record.outputs[0]["text"] == "before"
    assert before_record.output_truncated is False
    assert big_record.output_truncated is True
    assert len(big_record.outputs[0]["text"].encode("utf-8")) <= 1024
    # The cell AFTER the oversized one must still have run and produced its
    # own, complete, untruncated output -- not silently dropped.
    assert after_record.executed is True
    assert after_record.outputs[0]["text"] == "after"
    assert after_record.output_truncated is False


# ── LIBIPYNB-Q17: any()-short-circuit fix -- every oversized output, not ───
# ── just the first, must be handled; binary MIME must be omitted, not ──────
# ── corrupted, when oversized ───────────────────────────────────────────────


def test_two_oversized_stream_outputs_in_one_cell_are_both_truncated(
    executor: LocalJupyterExecutor,
) -> None:
    """The exact regression this fix closes: _truncate_outputs_if_needed
    previously used any(...) over a generator, which stops the moment the
    first oversized output is found -- a cell producing two independently
    oversized outputs (here: stdout and stderr, two separate stream output
    dicts) previously left the second one completely untouched."""
    document = _document(
        [
            _code(
                "import sys\nsys.stdout.write('a' * 2000)\nsys.stderr.write('b' * 2000)\n",
                "two-streams",
            )
        ]
    )

    result = executor.execute(document, options=_opts(max_output_bytes=200))

    (record,) = result.cell_records
    assert record.output_truncated is True
    stdout_output = next(o for o in record.outputs if o.get("name") == "stdout")
    stderr_output = next(o for o in record.outputs if o.get("name") == "stderr")
    assert len(stdout_output["text"].encode("utf-8")) <= 200
    assert len(stderr_output["text"].encode("utf-8")) <= 200
    # Both must actually have been shortened, not just the first one visited.
    assert len(stdout_output["text"]) < 2000
    assert len(stderr_output["text"]) < 2000


def test_mixed_stream_display_data_and_execute_result_outputs_are_all_truncated(
    executor: LocalJupyterExecutor,
) -> None:
    document = _document(
        [
            _code(
                "from IPython.display import display\n"
                "print('s' * 2000, end='')\n"
                "display({'text/plain': 'd' * 2000}, raw=True)\n"
                "'e' * 2000\n",
                "mixed",
            )
        ]
    )

    result = executor.execute(document, options=_opts(max_output_bytes=200))

    (record,) = result.cell_records
    assert record.output_truncated is True
    by_type = {o["output_type"]: o for o in record.outputs}
    assert set(by_type) == {"stream", "display_data", "execute_result"}
    assert len(by_type["stream"]["text"].encode("utf-8")) <= 200
    assert len(by_type["display_data"]["data"]["text/plain"].encode("utf-8")) <= 200
    assert len(by_type["execute_result"]["data"]["text/plain"].encode("utf-8")) <= 200


def test_multiple_oversized_mime_representations_in_one_output_are_all_truncated(
    executor: LocalJupyterExecutor,
) -> None:
    document = _document(
        [
            _code(
                "from IPython.display import display\n"
                "display({'text/plain': 'p' * 2000, 'text/html': 'h' * 2000}, raw=True)\n",
                "multi-mime",
            )
        ]
    )

    result = executor.execute(document, options=_opts(max_output_bytes=200))

    (record,) = result.cell_records
    (output,) = record.outputs
    assert len(output["data"]["text/plain"].encode("utf-8")) <= 200
    assert len(output["data"]["text/html"].encode("utf-8")) <= 200


def test_oversized_binary_mime_payload_is_omitted_not_corrupted(
    executor: LocalJupyterExecutor,
) -> None:
    """LIBIPYNB-Q17's second defect: appending a text truncation marker to
    base64 content corrupts it into invalid base64 without raising. An
    oversized binary representation must be removed entirely and reported
    via omitted_mime_types, never truncated in place."""
    document = _document(
        [
            _code(
                "from IPython.display import display\n"
                "display({'image/png': 'A' * 2000}, raw=True)\n",
                "binary",
            )
        ]
    )

    result = executor.execute(document, options=_opts(max_output_bytes=200))

    (record,) = result.cell_records
    assert record.output_truncated is True
    assert record.omitted_mime_types == ("image/png",)
    (output,) = record.outputs
    assert "image/png" not in output["data"]


def test_oversized_binary_and_text_mime_in_the_same_output_are_each_handled_correctly(
    executor: LocalJupyterExecutor,
) -> None:
    document = _document(
        [
            _code(
                "from IPython.display import display\n"
                "display({'image/png': 'A' * 2000, 'text/plain': 'p' * 2000}, raw=True)\n",
                "mixed-binary",
            )
        ]
    )

    result = executor.execute(document, options=_opts(max_output_bytes=200))

    (record,) = result.cell_records
    (output,) = record.outputs
    assert "image/png" not in output["data"]
    assert record.omitted_mime_types == ("image/png",)
    assert len(output["data"]["text/plain"].encode("utf-8")) <= 200


def test_multiple_oversized_binary_mime_representations_are_all_omitted_and_aggregated(
    executor: LocalJupyterExecutor,
) -> None:
    """LIBIPYNB-Q17 Gate G2 finding: the single-binary-omission tests above
    don't exercise omitted_mime_types aggregating across >=2 omissions in
    the same cell -- exactly the cardinality class this whole taskcard
    exists to stop missing."""
    document = _document(
        [
            _code(
                "from IPython.display import display\n"
                "display({'image/png': 'A' * 2000, 'application/pdf': 'B' * 2000}, raw=True)\n",
                "two-binary",
            )
        ]
    )

    result = executor.execute(document, options=_opts(max_output_bytes=200))

    (record,) = result.cell_records
    assert set(record.omitted_mime_types) == {"image/png", "application/pdf"}
    (output,) = record.outputs
    assert "image/png" not in output["data"]
    assert "application/pdf" not in output["data"]


def test_svg_mime_is_text_truncated_not_omitted(executor: LocalJupyterExecutor) -> None:
    """image/svg+xml is literal XML text per the nbformat spec, not
    base64 -- must be marker-truncated like any other text MIME type, not
    treated as binary and removed."""
    document = _document(
        [
            _code(
                "from IPython.display import display\n"
                "display({'image/svg+xml': '<svg>' + 'x' * 2000 + '</svg>'}, raw=True)\n",
                "svg",
            )
        ]
    )

    result = executor.execute(document, options=_opts(max_output_bytes=200))

    (record,) = result.cell_records
    assert record.omitted_mime_types == ()
    (output,) = record.outputs
    assert "image/svg+xml" in output["data"]
    assert len(output["data"]["image/svg+xml"].encode("utf-8")) <= 200


def test_unicode_output_is_truncated_at_a_utf8_byte_boundary(
    executor: LocalJupyterExecutor,
) -> None:
    """A naive byte-slice can land mid-codepoint on multi-byte UTF-8
    content -- must decode cleanly (errors='ignore' on the cut boundary),
    never raise UnicodeDecodeError."""
    document = _document([_code("print('é' * 500, end='')", "unicode")])

    result = executor.execute(document, options=_opts(max_output_bytes=201))

    (record,) = result.cell_records
    assert record.output_truncated is True
    text = record.outputs[0]["text"]
    assert isinstance(text, str)
    text.encode("utf-8")  # must not raise


def test_extremely_small_output_limit_does_not_crash(executor: LocalJupyterExecutor) -> None:
    document = _document([_code("print('hello world')", "small-limit")])

    result = executor.execute(document, options=_opts(max_output_bytes=1))

    (record,) = result.cell_records
    assert record.output_truncated is True
    assert isinstance(record.outputs[0]["text"], str)


def test_notebook_remains_schema_valid_after_truncation(executor: LocalJupyterExecutor) -> None:
    from libipynb import validate

    document = _document(
        [
            _code(
                "from IPython.display import display\n"
                "print('s' * 2000, end='')\n"
                "display({'image/png': 'A' * 2000, 'text/plain': 'p' * 2000}, raw=True)\n",
                "valid-after-truncation",
            )
        ]
    )

    result = executor.execute(document, options=_opts(max_output_bytes=200))

    report = validate(result.notebook.raw)
    assert report.is_valid, [d.message for d in report]


# ── LIBIPYNB-Q2: independent per-cell/total-notebook timeout watchdog ──────


def test_a_cell_finishing_within_budget_is_never_falsely_flagged_as_timed_out(
    executor: LocalJupyterExecutor,
) -> None:
    """Watchdog race regression: run several trials specifically because
    this is a timing-dependent race between two independently-started
    clocks (nbclient's own timeout deadline and the watchdog's own
    ``threading.Timer``) -- a single pass proves little about a race that
    only shows up some of the time. The cell here reliably completes at
    roughly 60% of its budget, comfortably inside the watchdog's own skew
    margin (see ``_Tracker.on_cell_execute``)."""
    for _ in range(5):
        document = _document([_code("import time; time.sleep(0.6)")])
        result = executor.execute(document, options=_opts(cell_timeout=1))
        assert result.timed_out is False
        assert result.cell_records[0].timed_out is False


def _extra_threads_after(
    before: set[threading.Thread], timeout: float = 5.0
) -> set[threading.Thread]:
    deadline = time.monotonic() + timeout
    while True:
        extra = set(threading.enumerate()) - before
        if not extra or time.monotonic() >= deadline:
            return extra
        time.sleep(0.05)


def test_no_watchdog_timer_thread_survives_a_normal_completion(
    executor: LocalJupyterExecutor,
) -> None:
    before = set(threading.enumerate())
    document = _document([_code("1 + 1")])
    executor.execute(document, options=_opts(cell_timeout=5))
    assert _extra_threads_after(before) == set()


def test_no_watchdog_timer_thread_survives_a_timeout(executor: LocalJupyterExecutor) -> None:
    before = set(threading.enumerate())
    document = _document([_code("import time; time.sleep(10)")])
    executor.execute(
        document, options=_opts(cell_timeout=1, interrupt_on_timeout=True, stop_on_error=False)
    )
    assert _extra_threads_after(before) == set()


def test_no_watchdog_timer_thread_survives_async_cancellation(
    executor: LocalJupyterExecutor,
) -> None:
    """The exit path most likely to be missed when wiring in cleanup: the
    execute_async cancellation branch never reaches _finish(), so it must
    cancel any pending watchdog timer itself (see the module's own comment
    at that call site)."""
    before = set(threading.enumerate())

    async def run() -> None:
        document = _document([_code("import time; time.sleep(30)")])
        task = asyncio.ensure_future(
            executor.execute_async(document, options=_opts(cell_timeout=60))
        )
        await asyncio.sleep(1)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    asyncio.run(run())
    assert _extra_threads_after(before) == set()


def test_sequential_runs_do_not_leak_watchdog_state_between_calls(
    executor: LocalJupyterExecutor,
) -> None:
    timed_out_document = _document([_code("import time; time.sleep(10)")])
    executor.execute(
        timed_out_document,
        options=_opts(cell_timeout=1, interrupt_on_timeout=True, stop_on_error=False),
    )

    clean_document = _document([_code("print('fine')")])
    result = executor.execute(clean_document, options=_opts(cell_timeout=30))

    assert result.timed_out is False
    assert result.cell_records[0].timed_out is False


def test_concurrent_runs_on_separate_threads_do_not_interfere(
    executor: LocalJupyterExecutor,
) -> None:
    """Directly tests the 'lock must be instance-scoped, not accidentally
    module/class-scoped' pitfall: two real, independent executions -- one
    that should time out, one that should complete cleanly -- running
    genuinely concurrently on separate OS threads must not affect each
    other's result."""
    results: dict[str, object] = {}
    errors: list[BaseException] = []

    def run_short_timeout() -> None:
        try:
            document = _document([_code("import time; time.sleep(10)")])
            results["short"] = executor.execute(
                document,
                options=_opts(cell_timeout=1, interrupt_on_timeout=True, stop_on_error=False),
            )
        except BaseException as exc:  # noqa: BLE001 -- surfaced via `errors` below
            errors.append(exc)

    def run_generous_timeout() -> None:
        try:
            document = _document([_code("print('fine')")])
            results["generous"] = executor.execute(document, options=_opts(cell_timeout=30))
        except BaseException as exc:  # noqa: BLE001 -- surfaced via `errors` below
            errors.append(exc)

    t1 = threading.Thread(target=run_short_timeout)
    t2 = threading.Thread(target=run_generous_timeout)
    t1.start()
    t2.start()
    t1.join(timeout=90)
    t2.join(timeout=90)

    assert not errors, errors
    short_result = results["short"]
    generous_result = results["generous"]
    assert isinstance(short_result, ExecutionResult)
    assert isinstance(generous_result, ExecutionResult)
    assert short_result.timed_out is True
    assert generous_result.timed_out is False


def test_total_timeout_stops_before_a_later_cell_starts(
    executor: LocalJupyterExecutor,
) -> None:
    """A soft bound only: cell 0 is allowed to run to completion even
    though doing so pushes elapsed time past total_timeout -- the check
    only ever happens at the NEXT cell's own on_cell_start, before that
    cell is sent to the kernel."""
    document = _document(
        [
            _code("import time; time.sleep(6)", "a"),
            _code("print('never')", "b"),
        ]
    )

    # total_timeout must comfortably exceed real kernel-startup latency (so
    # cell 0 is allowed to start at all) while staying smaller than cell
    # 0's own duration (so it's genuinely exceeded before cell 1 would
    # start) -- empirically, kernel startup on this project's own test
    # machines has been observed to exceed 1s, so a generous margin is used
    # rather than the tightest value that happened to pass once.
    result = executor.execute(
        document, options=_opts(cell_timeout=30, total_timeout=5.0, stop_on_error=False)
    )

    assert result.cell_records[0].executed is True
    assert result.cell_records[1].executed is False
    assert result.total_timed_out is True
    assert result.completed is False


def test_total_timeout_does_not_abort_a_single_already_running_cell(
    executor: LocalJupyterExecutor,
) -> None:
    """Negative control proving the soft-variant limitation is real, not
    merely documented (see ExecutionOptions.total_timeout's own docstring
    and LIBIPYNB-Q2b, the tracked follow-up for a true hard bound): a
    single cell whose own duration clearly exceeds total_timeout is never
    aborted mid-flight, because there is no later cell whose on_cell_start
    would ever re-check the budget."""
    document = _document([_code("import time; time.sleep(6)")])

    # See the sibling test above for why total_timeout is set well above
    # observed kernel-startup latency, not the tightest bound that happens
    # to work on one machine.
    result = executor.execute(
        document, options=_opts(cell_timeout=30, total_timeout=5.0, stop_on_error=False)
    )

    assert result.cell_records[0].executed is True
    assert result.total_timed_out is False
    assert result.completed is True


def test_stopped_early_and_timed_out_can_both_be_true_for_the_same_run(
    executor: LocalJupyterExecutor,
) -> None:
    """A newly-reachable combined state, not a contradiction -- see
    ExecutionResult's own docstring. A cell whose own code catches the
    interrupt and does slow cleanup before re-raising a different error
    genuinely both (a) exceeds its own cell_timeout budget, confirmed
    independently by the watchdog well before the cell finishes, and
    (b) causes the run to stop early under stop_on_error=True (its own
    re-raised error is not allowed to continue past).

    The cleanup phase below retries its own sleep against a fixed wall-
    clock deadline rather than a single ``time.sleep(2)`` call: confirmed
    live (see ``_async_handle_timeout`` in the installed nbclient source,
    and this project's own design plan for the watchdog redesign) that
    nbclient resends its kernel interrupt roughly every ``cell_timeout``
    seconds for as long as the kernel reports alive, not just once -- a
    single unguarded cleanup sleep was empirically interrupted a second
    time before it could reach the ``raise``, surfacing the second
    ``KeyboardInterrupt`` instead of the intended ``RuntimeError``."""
    document = _document(
        [
            _code(
                "import time\n"
                "try:\n"
                "    time.sleep(10)\n"
                "except KeyboardInterrupt:\n"
                "    deadline = time.time() + 2\n"
                "    while time.time() < deadline:\n"
                "        try:\n"
                "            time.sleep(deadline - time.time())\n"
                "        except KeyboardInterrupt:\n"
                "            pass\n"
                "    raise RuntimeError('caught and rethrown after slow cleanup')\n",
                "a",
            ),
            _code("print('never')", "b"),
        ]
    )

    result = executor.execute(
        document, options=_opts(cell_timeout=1, interrupt_on_timeout=True, stop_on_error=True)
    )

    assert result.stopped_early is True
    assert result.timed_out is True
    assert result.timed_out_cell_index == 0
    record = result.cell_records[0]
    assert record.timed_out is True
    assert record.error is not None
    assert record.error.ename == "RuntimeError"
    assert result.cell_records[1].executed is False


def test_multiple_independently_timed_out_cells_are_each_recorded(
    executor: LocalJupyterExecutor,
) -> None:
    """timed_out_cell_index can only ever name one cell (kept for backward
    compatibility) -- under stop_on_error=False, more than one cell can
    independently time out in the same run, and each must be visible via
    its own CellExecutionRecord.timed_out, not silently dropped."""
    document = _document(
        [
            _code("import time; time.sleep(10)", "a"),
            _code("import time; time.sleep(10)", "b"),
            _code("print('after')", "c"),
        ]
    )

    result = executor.execute(
        document,
        options=_opts(cell_timeout=1, interrupt_on_timeout=True, stop_on_error=False),
    )

    assert result.timed_out is True
    assert result.timed_out_cell_index == 0
    assert result.cell_records[0].timed_out is True
    assert result.cell_records[1].timed_out is True
    assert result.cell_records[2].executed is True
    assert result.cell_records[2].timed_out is False
