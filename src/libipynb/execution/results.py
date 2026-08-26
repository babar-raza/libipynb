"""Typed results and diagnostics for kernel-backed execution."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .._internal.immutable import deep_freeze
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
    outputs: tuple[Mapping[str, Any], ...]
    error: ExecutionCellError | None
    started_at: float | None
    finished_at: float | None
    #: LIBIPYNB-Q2: ``True`` when one or more of this cell's own outputs
    #: were truncated or had a binary representation omitted because they
    #: exceeded :attr:`~.options.ExecutionOptions.max_output_bytes`. Always
    #: ``False`` when that option is ``None`` (the default).
    output_truncated: bool = False
    #: LIBIPYNB-Q17: MIME type keys (e.g. ``"image/png"``) removed entirely
    #: from an output's ``data`` bundle because they were base64-encoded
    #: binary content that exceeded the size limit -- appending a textual
    #: truncation marker to base64 data would corrupt it into invalid
    #: base64 without raising, so an oversized binary representation is
    #: dropped rather than truncated. Distinct from ``output_truncated``,
    #: which is also ``True`` for ordinary marker-appended text truncation;
    #: this field is the only signal that a binary representation was
    #: *removed*, not shortened. Always empty when no binary representation
    #: was oversized, including when ``output_truncated`` is ``True`` for a
    #: purely textual reason.
    omitted_mime_types: tuple[str, ...] = ()
    #: LIBIPYNB-Q2: ``True`` when this specific cell independently exceeded
    #: its own :attr:`~.options.ExecutionOptions.cell_timeout` budget,
    #: confirmed by this executor's own watchdog rather than solely
    #: inferred from nbclient's exception shape -- authoritative even when
    #: more than one cell in the same run each time out independently
    #: (possible under ``stop_on_error=False``), unlike
    #: :attr:`ExecutionResult.timed_out_cell_index`, which can only ever
    #: name one cell. Always ``False`` when :attr:`~.options.
    #: ExecutionOptions.cell_timeout` is ``None``.
    timed_out: bool = False

    def __post_init__(self) -> None:
        # LIBIPYNB-Q43 Gate-G2 round-3 review finding: the outer tuple was
        # already immutable, but each element was still a genuinely,
        # directly mutable dict -- `record.outputs[0]["x"] = "evil"`
        # silently corrupted every later read of the SAME instance's
        # `.outputs`, the identical mutation-after-access gap this
        # taskcard closes everywhere else. adapters/jupyter_execute.py's
        # own `copy.deepcopy(output)` when constructing this tuple already
        # breaks aliasing to `result.notebook`'s own cell outputs, but
        # never froze the copy -- deepcopy-only was never enough, per this
        # module's own already-established pattern. Not caught by either
        # of round 3's own grep patterns (`deepcopy(self\.` and
        # `object.__setattr__`): the deepcopy lives in a different file's
        # factory function, and this class previously had no
        # `__post_init__` at all.
        object.__setattr__(self, "outputs", tuple(deep_freeze(o) for o in self.outputs))

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

    LIBIPYNB-Q2: ``stopped_early`` and ``timed_out`` are **not** mutually
    exclusive -- a cell can independently both time out (confirmed by this
    executor's own watchdog) *and* cause the run to stop early (e.g. its
    own code caught the interrupt and re-raised a different error under
    ``stop_on_error=True``). Both fields being ``True`` at once describes
    two genuinely true, compatible facts about the same event, not a
    contradiction; do not "simplify" this back to mutual exclusivity.
    ``timed_out_cell_index`` names only the *first* cell (by index) that
    timed out, kept for backward compatibility and simple callers -- for
    a run where more than one cell independently timed out (possible under
    ``stop_on_error=False``), inspect each :attr:`CellExecutionRecord.
    timed_out` instead, which is never lossy.
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
    #: LIBIPYNB-Q2: ``True`` when :attr:`~.options.ExecutionOptions.
    #: total_timeout` elapsed before a subsequent cell could start -- a
    #: "soft" bound distinct from the per-cell ``timed_out``/
    #: ``timed_out_cell_index`` fields; see that option's own docstring for
    #: why this never bounds a single already-running cell.
    total_timed_out: bool = False
    #: LIBIPYNB-Q2b: ``True`` when :attr:`~.options.ExecutionOptions.
    #: hard_kill_grace_period` elapsed while a cell was still running after
    #: the watchdog's own fire point, and this executor force-killed the
    #: kernel's OS process tree directly rather than waiting indefinitely
    #: for a kernel that never responded to an interrupt. Always ``False``
    #: when ``hard_kill_grace_period`` is ``None`` (the default).
    hard_killed: bool = False

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
            and not self.total_timed_out
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
