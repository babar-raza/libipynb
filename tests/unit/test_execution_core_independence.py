"""LIBIPYNB-P4a-1 (plans/full-parity-plan.md, Gate G6 sign-off §7): the
package-level half of "importing the core package without execution
dependencies installed must continue to work."

tests/unit/test_import_boundary.py already proves the *module-level*
half statically (an AST scan: no ``src/libipynb`` file imports
``nbclient``/``jupyter_client`` outside the one scoped exception). This
file proves the *runtime* half: with ``nbclient``/``jupyter_client``
genuinely unable to import (simulated via ``sys.modules`` entries set to
``None``, which the import system treats as "this name cannot be
imported" -- the same technique already used by
test_obligation_jupyter_execution_adapter.py's own missing-dependency
test), ``libipynb`` and ``libipynb.execution`` still import and their
non-kernel API surface still works; only actually constructing
``LocalJupyterExecutor`` fails, structurally.
"""

from __future__ import annotations

import importlib
import sys
from unittest.mock import patch

import pytest


def _reimport_with_backend_hidden() -> tuple[object, object]:
    """Force a fresh import of libipynb.execution and libipynb.adapters.
    jupyter_execute with nbclient/jupyter_client hidden, so this test does
    not rely on either module never having been imported earlier in the
    same test session (which nbclient/jupyter_client have, elsewhere in
    this suite -- Python caches modules in sys.modules by default)."""
    for name in ("libipynb.execution", "libipynb.adapters.jupyter_execute"):
        sys.modules.pop(name, None)
    execution = importlib.import_module("libipynb.execution")
    jupyter_execute = importlib.import_module("libipynb.adapters.jupyter_execute")
    return execution, jupyter_execute


def test_libipynb_execution_imports_without_nbclient_installed() -> None:
    with patch.dict(sys.modules, {"nbclient": None, "jupyter_client": None, "nbformat": None}):
        execution, _ = _reimport_with_backend_hidden()

    assert hasattr(execution, "ExecutionOptions")
    assert hasattr(execution, "ExecutionResult")
    assert hasattr(execution, "NotebookExecutor")
    assert hasattr(execution, "LocalJupyterExecutor")

    # Re-import cleanly afterward so later tests in the same process see
    # the real, fully-functional modules again, not the hidden-dependency
    # versions this test forced.
    for name in ("libipynb.execution", "libipynb.adapters.jupyter_execute"):
        sys.modules.pop(name, None)
    importlib.import_module("libipynb.execution")


def test_execution_options_and_results_need_no_backend_at_all() -> None:
    """These are pure dataclasses -- constructing them must never touch
    nbclient/jupyter_client/nbformat, with or without the extra installed."""
    with patch.dict(sys.modules, {"nbclient": None, "jupyter_client": None, "nbformat": None}):
        execution, _ = _reimport_with_backend_hidden()
        options = execution.ExecutionOptions(cell_timeout=5.0, stop_on_error=False)
        assert options.cell_timeout == 5.0
        assert options.stop_on_error is False

    for name in ("libipynb.execution", "libipynb.adapters.jupyter_execute"):
        sys.modules.pop(name, None)
    importlib.import_module("libipynb.execution")


def test_local_jupyter_executor_construction_fails_structurally_without_the_extra() -> None:
    with patch.dict(sys.modules, {"nbclient": None, "jupyter_client": None, "nbformat": None}):
        execution, _ = _reimport_with_backend_hidden()
        with pytest.raises(execution.MissingExecutionDependencyError, match=r"libipynb\[exec\]"):
            execution.LocalJupyterExecutor()

    for name in ("libipynb.execution", "libipynb.adapters.jupyter_execute"):
        sys.modules.pop(name, None)
    importlib.import_module("libipynb.execution")


def test_core_libipynb_never_imports_execution_at_all() -> None:
    """libipynb/__init__.py's own source must never reference the execution
    package. A live runtime check (``hasattr(libipynb, "execution")``) is
    NOT a valid proxy for this: Python's import machinery binds a submodule
    as an attribute of its parent package the moment that submodule is
    imported *anywhere* in the process (e.g. by another test file's own
    ``from libipynb.execution import ...``), regardless of whether
    ``libipynb/__init__.py`` itself did the importing -- so this is a
    static source check instead, immune to import-order side effects from
    the rest of the test session."""
    import ast
    from pathlib import Path

    init_path = Path(__file__).resolve().parents[2] / "src" / "libipynb" / "__init__.py"
    tree = ast.parse(init_path.read_text(encoding="utf-8"))
    imported_names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_names.add(node.module.split(".")[0])
            if node.level == 1:  # from .X import ... (relative, this package)
                imported_names.add(node.module)

    assert "execution" not in imported_names
    assert "adapters" not in imported_names
