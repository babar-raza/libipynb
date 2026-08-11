"""Optional ecosystem adapters.

The production chassis has no mandatory notebook-framework dependency.
"""

from .execute import (
    CellExecutionResult,
    ExecutionError,
    ExecutionReport,
    execute_notebook,
)
from .export import (
    AncillaryResource,
    ExportAdapter,
    ExportResult,
    MarkdownExporter,
    PythonScriptExporter,
)

__all__ = [
    "AncillaryResource",
    "CellExecutionResult",
    "ExecutionError",
    "ExecutionReport",
    "ExportAdapter",
    "ExportResult",
    "MarkdownExporter",
    "PythonScriptExporter",
    "execute_notebook",
]
