"""Backend-neutral executor contract.

This is the seam a future non-local backend (a container, a VM, or a
purpose-built remote execution service -- see the module docstring of
:mod:`libipynb.execution`) would implement to plug into the same public
API without any change to calling code. Nothing in this project ships
such a backend today; this ``Protocol`` exists so that decision is not
foreclosed by :class:`~libipynb.adapters.jupyter_execute.LocalJupyterExecutor`
being the only implementation.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..model.document import NotebookDocument
from .options import ExecutionOptions
from .results import ExecutionResult


@runtime_checkable
class NotebookExecutor(Protocol):
    """Structural contract every execution backend satisfies."""

    def execute(
        self,
        document: NotebookDocument,
        *,
        options: ExecutionOptions | None = None,
    ) -> ExecutionResult:
        """Execute synchronously and return the structured result."""
        ...

    async def execute_async(
        self,
        document: NotebookDocument,
        *,
        options: ExecutionOptions | None = None,
    ) -> ExecutionResult:
        """Execute asynchronously and return the structured result."""
        ...
