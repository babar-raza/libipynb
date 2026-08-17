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
    HtmlExporter,
    JupytextExporter,
    MarkdownExporter,
    PythonScriptExporter,
)
from .jupyter_execute import LocalJupyterExecutor

__all__ = [
    "AncillaryResource",
    "CellExecutionResult",
    "ExecutionError",
    "ExecutionReport",
    "ExportAdapter",
    "ExportResult",
    "HtmlExporter",
    "JupytextExporter",
    "LocalJupyterExecutor",
    "MarkdownExporter",
    "PythonScriptExporter",
    "execute_notebook",
]
