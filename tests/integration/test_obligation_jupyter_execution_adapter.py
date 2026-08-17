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
from libipynb.execution import ExecutionOptions, LocalJupyterExecutor

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


def test_list_of_lines_source_form_is_preserved_unchanged(executor: LocalJupyterExecutor) -> None:
    cell = _code(["print(1)\n", "print(2)"], "c")
    document = _document([cell])

    result = executor.execute(document, options=_opts())

    assert result.notebook.cells[0]["source"] == ["print(1)\n", "print(2)"]


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
    document = _document([_code("import time; time.sleep(10)", "a"), _code("print('after')", "b")])

    result = executor.execute(
        document, options=_opts(cell_timeout=1, interrupt_on_timeout=True, stop_on_error=False)
    )

    assert result.timed_out is False
    record = result.cell_records[0]
    assert record.error is not None
    assert record.error.ename == "KeyboardInterrupt"


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
    """Verified directly (this environment) that nbclient's own cleanup path
    does not reliably run on task cancellation -- a real, reproduced kernel-
    process leak (psutil child-process tracking showed the kernel process
    still alive 15+ seconds after cancellation with no explicit cleanup).
    ``LocalJupyterExecutor.execute_async`` closes that gap itself.

    A second, independently confirmed real race lives inside ``nbclient``
    itself (``client.py``'s ``async_execute_cell``:
    ``except asyncio.CancelledError: raise DeadKernelError("Kernel died")
    from None``, on its own ``await self.task_poll_for_reply``) -- if the
    external cancellation happens to land while control is suspended at
    *that specific* await point, nbclient converts it into a
    ``DeadKernelError`` instead of letting ``CancelledError`` propagate,
    discarding the cancellation entirely. Reproduced directly, repeatedly,
    in this environment: the exact same test, byte-for-byte, surfaces
    ``asyncio.CancelledError`` most runs and a normal ``ExecutionResult``
    with ``kernel_death_error`` set on others, non-deterministically. Both
    outcomes are handled correctly by this module (the kernel is shut down
    either way -- via this module's own explicit cleanup in the
    ``CancelledError`` case, or via ``nbclient``'s own ordinary
    ``async_setup_kernel`` teardown in the ``DeadKernelError`` case, since
    that is a regular exception, not a cancellation). This test therefore
    asserts the invariant that actually always holds -- no leaked kernel
    process, no hang -- rather than one single non-deterministic exception
    shape."""
    import os

    import psutil

    document = _document([_code("import time; time.sleep(30)")])
    me = psutil.Process(os.getpid())

    async def run() -> None:
        task = asyncio.ensure_future(
            executor.execute_async(document, options=_opts(cell_timeout=60))
        )
        await asyncio.sleep(2)
        assert me.children(recursive=True), "kernel process should be running by now"
        task.cancel()
        try:
            result = await task
        except asyncio.CancelledError:
            pass
        else:
            assert result.kernel_death_error is not None, (
                "if await task did not raise CancelledError, the only legitimate "
                "reason (see docstring) is nbclient's own internal cancel/dead-"
                "kernel race -- anything else is a real bug"
            )
        assert me.children(recursive=True) == [], "kernel process must be cleaned up"

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
