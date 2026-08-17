"""Opt-in notebook execution through a real, local Jupyter kernel.

LIBIPYNB-P4a-1/P4b/P4c (plans/full-parity-plan.md, Gate G6 sign-off §7):
this package is the public surface for kernel-protocol execution -- a
second, opt-in execution backend alongside the pre-existing, still-default
subprocess adapter (:mod:`libipynb.adapters.execute`). Nothing in this
package is imported by ``libipynb``'s top-level ``__init__``, by
``codec``/``model``/``validation``, or by the subprocess adapter --
importing the core package, or the existing subprocess `execute_notebook`,
never requires Jupyter kernel-protocol dependencies to be installed
(``tests/unit/test_import_boundary.py`` enforces the module-level half of
this; ``tests/unit/test_execution_core_independence.py`` enforces the
package-level half).

Requires the ``exec`` extra for the actual backend to run:

    pip install "libipynb[exec]"

Importing ``libipynb.execution`` itself never requires ``nbclient``/
``jupyter_client`` to be installed -- only *instantiating*
:class:`~libipynb.adapters.jupyter_execute.LocalJupyterExecutor` does, and
that failure is a structured :class:`MissingExecutionDependencyError`
naming the extra to install, not a bare ``ImportError`` deep in a call
stack.

Security posture (must not be misread as more than it is): this is a
**trusted local execution** capability, not a sandbox. The kernel runs
with the permissions of its own process -- it can read/write files, start
processes, use the network, and inspect environment variables to the same
extent the calling user could. ``ExecutionOptions.cell_timeout``/
``interrupt_on_timeout`` are operational controls against a hung cell, not
an isolation boundary; disabling stdin (permanently, in the installed
``nbclient`` backend -- see :mod:`libipynb.adapters.jupyter_execute`)
reduces interactive blocking, not attacker capability. Never execute a
notebook you do not already trust with this executor. True untrusted
execution needs an external isolation boundary (container, VM, or a
purpose-built remote execution service) implementing the
:class:`NotebookExecutor` protocol below -- this package defines that
protocol precisely so such a backend can be added later without changing
the public contract, not so one ships today.
"""

from __future__ import annotations

from ..adapters.jupyter_execute import LocalJupyterExecutor
from .exceptions import ExecutionBackendError, MissingExecutionDependencyError
from .options import ExecutionOptions
from .protocol import NotebookExecutor
from .results import (
    CellExecutionRecord,
    ExecutionCellError,
    ExecutionEvent,
    ExecutionResult,
)

__all__ = [
    "CellExecutionRecord",
    "ExecutionBackendError",
    "ExecutionCellError",
    "ExecutionEvent",
    "ExecutionOptions",
    "ExecutionResult",
    "LocalJupyterExecutor",
    "MissingExecutionDependencyError",
    "NotebookExecutor",
]
