"""LIBIPYNB-P8: src/libipynb must never import an oracle or exec-extra tool.

plans/full-parity-plan.md's Design Philosophy (§1) and Gate G7 require that
the five reference tools used as design inspiration/test oracles
(nbformat/nbstripout/nbdime/nbconvert/papermill) and the real Jupyter
kernel-protocol libraries (jupyter_client/nbclient) never become a runtime
dependency of the core package -- they belong in the `oracle`/`exec` extras
groups and are used only from tests/oracle/ or an explicit opt-in adapter.

This is a static check (like test_obligation_core_path_no_execution.py's
`test_core_module_source_never_references_the_execution_adapter`), not a
runtime one: it parses every module under src/libipynb with `ast` and fails
if any of them imports a forbidden name, so the boundary holds even for a
module that is never executed by the test suite.

nbformat itself is intentionally NOT in this forbidden list: it is already a
declared `reference`/`test`-extra dependency used by tests/interoperability/,
and this check is about the newly-introduced oracle/exec tools, not about
re-litigating that pre-existing, already-governed exception.
"""

from __future__ import annotations

import ast
import textwrap
from pathlib import Path

# Names that may only ever appear under tests/oracle/ (oracle tools) or as
# the exec-extra's own runtime dependency inside adapters/execute.py's future
# kernel engine (LIBIPYNB-P4a-1, not yet implemented -- when it lands, this
# list's jupyter_client/nbclient entries will need a scoped, documented
# exception for that one file, not a blanket removal).
FORBIDDEN_TOP_LEVEL_MODULES = (
    "jupyter_client",
    "nbclient",
    "nbdime",
    "nbconvert",
    "papermill",
    "nbstripout",
)


def _imported_top_level_names(source: str) -> set[str]:
    """Every top-level module name a file imports, via `import x` or `from x import y`."""
    tree = ast.parse(source)
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module.split(".")[0])
    return names


def _violations(source: str) -> set[str]:
    return _imported_top_level_names(source) & set(FORBIDDEN_TOP_LEVEL_MODULES)


def _src_root() -> Path:
    return Path(__file__).resolve().parents[2] / "src" / "libipynb"


# ── The check itself must be able to fail, or it proves nothing ────────────


def test_the_checker_actually_detects_a_forbidden_import() -> None:
    """A boundary check that cannot fire proves nothing -- this proves it fires,
    permanently and re-runnably, rather than as a one-off manual demonstration
    that leaves no trace in the suite (plans/full-parity-plan.md Gate G7/P8's
    own required-work: 'proven capable of catching a real violation')."""
    hostile_source = textwrap.dedent(
        """
        import jupyter_client
        from nbdime import diff
        """
    )
    assert _violations(hostile_source) == {"jupyter_client", "nbdime"}


def test_the_checker_does_not_flag_unrelated_imports() -> None:
    benign_source = textwrap.dedent(
        """
        import json
        from collections import abc
        import jsonschema
        """
    )
    assert _violations(benign_source) == set()


def test_the_checker_flags_from_import_form_too() -> None:
    assert _violations("from papermill import execute_notebook") == {"papermill"}


# ── The real scan over src/libipynb ─────────────────────────────────────────


def test_no_source_file_imports_an_oracle_or_exec_extra_tool() -> None:
    root = _src_root()
    assert root.is_dir(), f"expected package root at {root}"
    offenders: dict[str, set[str]] = {}
    for path in root.rglob("*.py"):
        violations = _violations(path.read_text(encoding="utf-8"))
        if violations:
            offenders[str(path.relative_to(root))] = violations
    assert not offenders, (
        f"src/libipynb must never import oracle/exec-extra tools, found: {offenders}"
    )
