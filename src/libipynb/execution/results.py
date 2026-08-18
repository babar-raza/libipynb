"""Typed results and diagnostics for kernel-backed execution."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..model.document import NotebookDocument


@dataclass(frozen=True, slots=True)
class ExecutionCellError:
    """One cell's raised exception, captured structurally (mirrors the
    subprocess adapter's ``ExecutionError`` shape, extended with the
    kernel protocol's own multi-line ``traceback`` list instead of one
    pre-formatted string)."""

    ename: str
    evalue: str
    traceback: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CellExecutionRecord:
    """One cell's outcome within a single execution run.

    Emitted for every cell in the notebook, including markdown/raw cells
    (``executed=False``, ``skipped=False``) and cells never reached
    because an earlier cell stopped the run (``executed=False``,
    ``skipped=False`` -- distinguishable from a *tagged* skip, which is
    ``skipped=True``, by checking ``ExecutionResult.stopped_early``/
    ``timed_out_cell_index`` for whether the run halted before this
    index).
    """

    index: int
    cell_id: str | None
    cell_type: str
    executed: bool
    skipped: bool
    execution_count: int | None
    outputs: tuple[dict[str, Any], ...]
    error: ExecutionCellError | None
    started_at: float | None
    finished_at: float | None
    #: LIBIPYNB-Q2: ``True`` when one or more of this cell's own outputs
    #: were truncated because they exceeded
    #: :attr:`~.options.ExecutionOptions.max_output_bytes`. Always
    #: ``False`` when that option is ``None`` (the default).
    output_truncated: bool = False

    @property
    def succeeded(self) -> bool:
        return self.executed and self.error is None

    @property
    def duration_seconds(self) -> float | None:
        if self.started_at is None or self.finished_at is None:
            return None
        return self.finished_at - self.started_at


@dataclass(frozen=True, slots=True)
class ExecutionEvent:
    """One lifecycle event, delivered to ``ExecutionOptions.on_event`` as
    the run progresses -- for progress bars/logging, not control flow."""

    kind: str
    cell_index: int | None = None
    cell_id: str | None = None


@dataclass(frozen=True, slots=True)
class ExecutionResult:
    """Structured outcome of one :class:`~.protocol.NotebookExecutor` run.

    ``notebook`` is the executed document -- a fresh copy by default, or
    the same object passed in when ``ExecutionOptions.in_place=True``
    (see that option's docstring). Always present and always a valid
    :class:`~libipynb.model.document.NotebookDocument`, even when the run
    stopped early or timed out -- cells reached before the stopping point
    carry real outputs; cells never reached are byte-identical to the
    input.
    """

    notebook: NotebookDocument
    cell_records: tuple[CellExecutionRecord, ...]
    kernel_name: str
    started_at: float
    finished_at: float
    timed_out: bool
    timed_out_cell_index: int | None
    stopped_early: bool
    kernel_launch_error: str | None
    kernel_death_error: str | None

    @property
    def duration_seconds(self) -> float:
        return self.finished_at - self.started_at

    @property
    def completed(self) -> bool:
        """False when the run was killed by a timeout, could not launch a
        kernel, or the kernel died mid-run. Stopping early because a cell
        errored under ``stop_on_error=True`` is a policy outcome, not an
        incompletion -- the executor did exactly what was asked."""
        return (
            not self.timed_out
            and self.kernel_launch_error is None
            and self.kernel_death_error is None
        )

    @property
    def succeeded(self) -> bool:
        return self.completed and self.first_error is None

    @property
    def first_error(self) -> ExecutionCellError | None:
        for record in self.cell_records:
            if record.error is not None:
                return record.error
        return None
