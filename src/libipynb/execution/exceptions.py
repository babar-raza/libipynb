"""Execution-specific exception types.

Deliberately small: ordinary, anticipated execution outcomes (a cell
raising, a cell timing out, a kernel that cannot start, a kernel that
dies mid-run) are reported *structurally* on :class:`~.results.
ExecutionResult`, matching the existing subprocess adapter's own
philosophy (:mod:`libipynb.adapters.execute`'s ``ExecutionReport``) of
never raising for an outcome the caller should be able to inspect and
handle programmatically. Only two situations are true exceptions here:
a missing optional dependency (nothing meaningful can be returned at
all) and the pre-flight safety acknowledgment gate (a caller-error, not
an execution outcome) -- the latter reuses the existing
``NotebookExecutionError`` directly rather than adding a redundant
subclass.
"""

from __future__ import annotations

from ..errors import NotebookExecutionError


class ExecutionBackendError(NotebookExecutionError):
    """Base class for kernel-backend errors that have no meaningful
    partial :class:`~.results.ExecutionResult` to attach to."""

    code = "execution_backend_error"


class MissingExecutionDependencyError(ExecutionBackendError):
    """Raised when a kernel-execution backend is used without its
    optional dependencies installed (``pip install "libipynb[exec]"``)."""

    code = "execution_dependency_missing"
