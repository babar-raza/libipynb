"""Typed, validated options for kernel-backed execution."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass

from .._internal.immutable import deep_freeze
from .results import ExecutionEvent


@dataclass(frozen=True, slots=True)
class ExecutionOptions:
    """Options accepted by every :class:`~.protocol.NotebookExecutor`
    backend. Every field here has stable, tested, documented semantics --
    nothing is exposed merely because the underlying kernel-protocol
    library happens to expose it.

    Security note: ``acknowledge_unsandboxed`` mirrors the existing
    subprocess adapter's own gate (:mod:`libipynb.adapters.execute`)
    exactly, including its wording -- kernel-protocol execution is not
    meaningfully more or less sandboxed than subprocess execution (both
    are OS-process isolation with no resource limits), so neither backend
    should look "safer" than it is.
    """

    #: Kernel to launch. ``None`` (default) uses the notebook's own
    #: declared ``metadata.kernelspec.name``, falling back to whatever
    #: kernel the installed ``jupyter_client`` resolves as its own
    #: default (typically ``python3``) if the notebook declares none.
    kernel_name: str | None = None

    #: Directory the kernel process starts in. ``None`` (default) means
    #: "whatever directory the calling process is already in" -- the same
    #: default ``nbclient`` itself uses. This is a *convenience* for
    #: notebooks that read/write relative paths, not an isolation
    #: boundary (contrast with the subprocess adapter's ``isolate_cwd``,
    #: which defaults to a fresh temp directory specifically to prevent
    #: casual file access next to the caller's own files -- this executor
    #: makes the opposite default tradeoff deliberately, because a kernel
    #: session commonly needs to resolve the same relative paths a human
    #: would have opened the notebook from).
    working_directory: str | None = None

    #: Per-cell wall-clock budget in seconds. ``None`` disables the
    #: per-cell timeout entirely (the kernel protocol's own per-cell
    #: model makes this meaningful, unlike the subprocess adapter's
    #: single whole-run budget).
    cell_timeout: float | None = 60.0

    #: How long to wait for the kernel process to report ready.
    kernel_startup_timeout: float = 60.0

    #: If ``True`` (default), a cell that raises stops the run -- later
    #: cells are never sent to the kernel, and
    #: ``ExecutionResult.stopped_early`` is ``True``. If ``False``, every
    #: cell runs regardless of earlier failures (matching the subprocess
    #: adapter's ``on_error="continue"``).
    stop_on_error: bool = True

    #: If ``True`` (default), a cell that exceeds ``cell_timeout`` sends
    #: an interrupt to the kernel and the timeout is reported as that
    #: cell's own error output (kernel stays alive; later cells still run
    #: unless ``stop_on_error`` then halts on that same error). If
    #: ``False``, a timeout aborts the entire run immediately
    #: (``ExecutionResult.timed_out=True``) without attempting to
    #: interrupt first.
    interrupt_on_timeout: bool = True

    #: Cell-metadata tag naming cells to never send to the kernel at all
    #: -- their existing outputs and ``execution_count`` are left
    #: completely untouched. Matches ``nbclient``'s own
    #: ``skip_cells_with_tag`` default exactly, so notebooks authored
    #: against ``nbconvert``/``papermill``'s own skip-tag convention work
    #: unchanged.
    skip_tag: str = "skip-execution"

    #: Whether per-cell start/idle timestamps are recorded into each
    #: executed cell's ``metadata.execution``. Default ``False`` --
    #: unlike ``nbclient``'s own default of ``True`` -- because wall-clock
    #: timestamps are exactly the kind of non-deterministic field this
    #: project's own oracle/determinism policy (plans/full-parity-plan.md
    #: §"Oracle and determinism policy") asks callers not to have to
    #: normalize away unless they explicitly opted in.
    record_timing: bool = False

    #: If ``False`` (default), ``execute()``/``execute_async()`` return a
    #: new, independent :class:`~libipynb.model.document.NotebookDocument`
    #: and the caller's original document is left byte-for-byte unchanged.
    #: If ``True``, the executor mutates the caller's own document in
    #: place and returns that same object.
    in_place: bool = False

    #: Must be explicitly set ``True`` or every call raises
    #: ``NotebookExecutionError`` before starting any kernel. See the
    #: module docstring: this is trusted-local execution, not a sandbox.
    acknowledge_unsandboxed: bool = False

    #: Extra environment variables merged into the kernel process's
    #: environment (which otherwise inherits this process's full
    #: environment unchanged -- there is no ``isolate_env``-equivalent
    #: filtering here; document this precisely rather than implying an
    #: isolation guarantee this executor does not provide).
    #:
    #: LIBIPYNB-Q43 Gate-G2 review finding: not copied, so this aliased
    #: whatever dict a caller passed in -- ``ExecutionOptions`` is meant
    #: to be built once and reused (that is the whole point of freezing
    #: it), so a caller mutating their own ``extra_env`` dict *after*
    #: constructing the options object silently changed what a later
    #: ``execute()`` call using the SAME options instance would see,
    #: despite ``frozen=True``. Frozen (not just copied) in
    #: ``__post_init__`` below via the same recursive helper
    #: ``model.diff``/``model.metadata`` use, for the same reason.
    extra_env: Mapping[str, str] | None = None

    #: Optional lifecycle callback, called synchronously with an
    #: :class:`~.results.ExecutionEvent` as the run progresses
    #: (``kernel_starting``, ``kernel_started``, ``cell_started``,
    #: ``cell_finished``, ``kernel_shutdown``). For progress reporting
    #: only -- exceptions raised inside it propagate and abort the run.
    on_event: Callable[[ExecutionEvent], None] | None = None

    #: LIBIPYNB-Q2: total wall-clock budget in seconds for the whole run,
    #: checked only at the start of each cell (a "soft" bound) -- if the
    #: elapsed time since the run began already exceeds this when the next
    #: cell would start, that cell (and all later cells) never runs and
    #: :attr:`~.results.ExecutionResult.total_timed_out` is set. ``None``
    #: (default) disables it. Does **not** bound a single already-running
    #: cell, including the last one in a run -- a cell that itself hangs
    #: forever is exactly as unbounded with this set as without it; that
    #: requires a hard-kill escalation this executor does not implement
    #: (tracked separately as LIBIPYNB-Q2b). Use :attr:`cell_timeout` for
    #: the closest available per-cell control.
    total_timeout: float | None = None

    #: LIBIPYNB-Q2: maximum UTF-8 byte size of a single output's own
    #: text/data payload before it is truncated and the corresponding
    #: :attr:`~.results.CellExecutionRecord.output_truncated` is set to
    #: ``True``. ``None`` (default) disables the cap entirely -- confirmed
    #: live before this field existed: a single cell producing 50MB of
    #: stdout was captured in full with no limit of any kind, a real
    #: regression in safety-knob coverage versus the older subprocess
    #: engine's own tested ``max_output_bytes``. Unlike that engine's
    #: confirmed bug (truncating a shared combined byte stream and
    #: silently losing every downstream cell's results), truncation here
    #: is applied independently to each output's own payload, so it can
    #: only ever affect the one oversized output it is applied to. This
    #: bounds what is *retained* in the returned
    #: :class:`~.results.ExecutionResult`/notebook, not peak transient
    #: memory the kernel or ``nbclient`` may hold while a single output is
    #: still streaming in -- a true streaming cap would need ``nbclient``'s
    #: semi-internal output-hook API, out of scope here.
    max_output_bytes: int | None = None

    def __post_init__(self) -> None:
        if self.cell_timeout is not None and self.cell_timeout <= 0:
            raise ValueError("cell_timeout must be positive or None")
        if self.kernel_startup_timeout <= 0:
            raise ValueError("kernel_startup_timeout must be positive")
        if not self.skip_tag:
            raise ValueError("skip_tag must be a non-empty string")
        if self.max_output_bytes is not None and self.max_output_bytes <= 0:
            raise ValueError("max_output_bytes must be positive or None")
        if self.total_timeout is not None and self.total_timeout <= 0:
            raise ValueError("total_timeout must be positive or None")
        if self.extra_env is not None:
            object.__setattr__(self, "extra_env", deep_freeze(dict(self.extra_env)))
