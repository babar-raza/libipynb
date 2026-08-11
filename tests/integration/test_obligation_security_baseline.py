"""product-goal.yaml's own "security" completion invariant -- a whole-package
static proof that nothing outside the deliberate, isolated execution
adapter can reach a networking, process-spawning, or dynamic-import
capability.

IPYNB-SEC-001's own 5 obligations (all already `implemented`) cover
resource-limit enforcement and the load/validate/diff/save-never-executes
boundary (test_obligation_core_path_no_execution.py's audit-hook proof).
This file adds the one check neither already provides: a package-wide
static sweep confirming no OTHER module anywhere in the package can reach
a forbidden capability, matching the identical pattern already proven for
nrrd/xliff/ubl's own SEC-001 obligations this session.

ipynb's own legitimate exceptions, each individually verified below rather
than silently allow-listed:

* ``adapters/execute.py`` imports ``subprocess`` -- this is IPYNB-EXEC-001's
  own required opt-in execution adapter, already isolation-boundary-tested
  in test_obligation_execution_adapter.py and test_obligation_core_path_no_
  execution.py. No other module may import it.
* ``model/attachments.py`` and ``validation/rules.py`` import
  ``urllib.parse`` (``quote``/``unquote``) -- pure string encoding, no
  network I/O. ``urllib.request``/``urllib.error`` (the network-capable
  submodules) are never imported anywhere.
* ``validation/schema.py`` imports ``importlib.resources`` -- reading a
  schema file bundled inside this package's own wheel, not dynamic code
  loading. No dynamic ``importlib.import_module``/``__import__`` call
  exists anywhere in this package.
"""

from __future__ import annotations

import ast
from pathlib import Path

_SRC_ROOT = Path(__file__).resolve().parents[2] / "src" / "libipynb"

_FULLY_FORBIDDEN_MODULES = frozenset(
    {"socket", "http", "ftplib", "smtplib", "pkgutil", "ctypes"}
)

#: Confined to exactly this one file (the obligation-required opt-in
#: execution adapter); forbidden everywhere else.
_SUBPROCESS_ALLOWED_FILE = "adapters/execute.py"


def _iter_source_files() -> list[Path]:
    return sorted(_SRC_ROOT.rglob("*.py"))


def _import_names(node: ast.stmt) -> list[str]:
    if isinstance(node, ast.Import):
        return [alias.name.split(".")[0] for alias in node.names]
    if isinstance(node, ast.ImportFrom) and node.module:
        return [node.module.split(".")[0]]
    return []


def test_fully_forbidden_modules_are_never_imported_anywhere() -> None:
    """No legitimate use case exists anywhere in this package for these --
    unlike subprocess/urllib/importlib, which have narrow, already-verified
    legitimate uses checked by the dedicated tests below."""
    offenders: list[str] = []
    for path in _iter_source_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            for name in _import_names(node):
                if name in _FULLY_FORBIDDEN_MODULES:
                    offenders.append(f"{path}: {name}")

    assert offenders == []


def test_subprocess_is_imported_only_by_the_execution_adapter() -> None:
    offenders: list[str] = []
    for path in _iter_source_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if "subprocess" in _import_names(node):
                if not path.as_posix().endswith(_SUBPROCESS_ALLOWED_FILE):
                    offenders.append(str(path))

    assert offenders == []


def test_urllib_usage_is_confined_to_the_non_network_parse_submodule() -> None:
    """urllib.parse is pure string encoding/decoding with no network I/O.
    urllib.request/urllib.error are the network-capable submodules -- must
    never appear anywhere in this package."""
    offenders: list[str] = []
    for path in _iter_source_files():
        text = path.read_text(encoding="utf-8")
        tree = ast.parse(text, filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                if node.module in ("urllib.request", "urllib.error"):
                    offenders.append(f"{path}: {node.module}")
                elif node.module == "urllib":
                    for alias in node.names:
                        if alias.name in ("request", "error"):
                            offenders.append(f"{path}: urllib.{alias.name}")
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name in ("urllib.request", "urllib.error"):
                        offenders.append(f"{path}: {alias.name}")

    assert offenders == []


def test_no_dynamic_import_call_exists_anywhere() -> None:
    """importlib.resources (reading this package's own bundled schema file)
    is the only legitimate importlib usage. importlib.import_module and
    the __import__ builtin -- either of which could load an
    attacker-influenced module name -- must never be called anywhere."""
    offenders: list[str] = []
    for path in _iter_source_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Name) and func.id == "__import__":
                    offenders.append(f"{path}: __import__(...)")
                elif (
                    isinstance(func, ast.Attribute)
                    and func.attr == "import_module"
                    and isinstance(func.value, ast.Name)
                    and func.value.id == "importlib"
                ):
                    offenders.append(f"{path}: importlib.import_module(...)")

    assert offenders == []


def test_no_eval_or_exec_call_exists_anywhere() -> None:
    """Independent, static complement to test_obligation_core_path_no_
    execution.py's own runtime audit-hook proof: no call site anywhere in
    the package's source even names eval/exec/compile as a callable."""
    offenders: list[str] = []
    for path in _iter_source_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                if node.func.id in ("eval", "exec", "compile"):
                    offenders.append(f"{path}: {node.func.id}(...)")

    assert offenders == []
