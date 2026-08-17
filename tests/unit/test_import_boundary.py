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

LIBIPYNB-P4a-1 (plans/full-parity-plan.md Gate G6 sign-off, §7): the kernel-
protocol execution engine has landed in adapters/jupyter_execute.py, so this
file now carries the scoped, documented exception this module's own comment
anticipated -- `jupyter_client`/`nbclient` (and, for the same reason,
`nbformat`, needed to build the execution-time notebook representation
`nbclient` expects) may appear ONLY in that one file, mirroring the exact
allowlist-with-self-test pattern already proven for `subprocess` in
tests/integration/test_obligation_security_baseline.py. `nbdime`/
`nbconvert`/`papermill`/`nbstripout` remain forbidden everywhere, with no
exception -- the kernel backend does not need them.
"""

from __future__ import annotations

import ast
import textwrap
from pathlib import Path

# Names forbidden everywhere in src/libipynb, no exceptions.
FORBIDDEN_TOP_LEVEL_MODULES = (
    "jupyter_client",
    "nbclient",
    "nbdime",
    "nbconvert",
    "papermill",
    "nbstripout",
)

#: Confined to exactly this one file -- the opt-in kernel-protocol execution
#: backend (LIBIPYNB-P4a-1). `nbformat` is not in FORBIDDEN_TOP_LEVEL_MODULES
#: at all (see module docstring), so it needs no entry here; it is listed in
#: _KERNEL_BACKEND_ALLOWED_MODULES only for documentation symmetry with the
#: two that are.
_KERNEL_BACKEND_ALLOWED_FILE = "adapters/jupyter_execute.py"
_KERNEL_BACKEND_ALLOWED_MODULES = frozenset({"jupyter_client", "nbclient"})


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


def _violations(source: str, *, path: str | None = None) -> set[str]:
    found = _imported_top_level_names(source) & set(FORBIDDEN_TOP_LEVEL_MODULES)
    if path is not None and path.replace("\\", "/").endswith(_KERNEL_BACKEND_ALLOWED_FILE):
        found -= _KERNEL_BACKEND_ALLOWED_MODULES
    return found


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


# ── The scoped jupyter_execute.py exception must be narrow, not a loophole ──


def test_jupyter_client_and_nbclient_are_still_flagged_outside_the_allowed_file() -> None:
    """The exception is keyed on the *file path*, not just the module name --
    the same hostile import in any other file must still be caught."""
    hostile_source = "import nbclient\nimport jupyter_client\n"
    assert _violations(hostile_source, path="src/libipynb/model/document.py") == {
        "nbclient",
        "jupyter_client",
    }
    assert _violations(hostile_source, path="src/libipynb/adapters/execute.py") == {
        "nbclient",
        "jupyter_client",
    }


def test_jupyter_client_and_nbclient_are_allowed_only_in_the_kernel_backend_file() -> None:
    hostile_source = "import nbclient\nimport jupyter_client\n"
    assert _violations(hostile_source, path="src/libipynb/adapters/jupyter_execute.py") == set()


def test_the_kernel_backend_exception_does_not_widen_to_other_forbidden_tools() -> None:
    """Even inside the one allowed file, nbdime/nbconvert/papermill/nbstripout
    must still be flagged -- the exception is scoped to exactly two names."""
    hostile_source = "import nbdime\nimport nbconvert\nimport papermill\nimport nbstripout\n"
    assert _violations(hostile_source, path="src/libipynb/adapters/jupyter_execute.py") == {
        "nbdime",
        "nbconvert",
        "papermill",
        "nbstripout",
    }


# ── The real scan over src/libipynb ─────────────────────────────────────────


def test_no_source_file_imports_an_oracle_or_exec_extra_tool() -> None:
    root = _src_root()
    assert root.is_dir(), f"expected package root at {root}"
    offenders: dict[str, set[str]] = {}
    for path in root.rglob("*.py"):
        violations = _violations(path.read_text(encoding="utf-8"), path=str(path))
        if violations:
            offenders[str(path.relative_to(root))] = violations
    assert not offenders, (
        f"src/libipynb must never import oracle/exec-extra tools, found: {offenders}"
    )
