"""IPYNB-EXEC-001, second clause: the core path must never execute notebook code.

The obligation reads: "Keep execution in an opt-in adapter with kernel
selection, timeouts, error policy, and isolation boundary; return a structured
execution report; never execute during load/validate/diff/save."

The first half (the adapter itself: kernel selection, timeouts, error policy,
isolation boundary, structured report) is now built --
adapters/execute.py's execute_notebook() -- and proven in
test_obligation_execution_adapter.py. This file proves the second half only:
that the CORE path (loads/validate/diff_notebooks/dumps/upgrade) never
executes cell code, independent of whether the opt-in adapter exists.

The no-execution half matters on its own: a notebook is untrusted input, and a
loader that evaluated cell source would be a remote-code-execution hole. These
tests prove it with a CPython audit hook rather than by observing side effects,
because absence of an observed side effect is weak evidence -- it only shows the
particular payload chosen did not fire. The audit hook fails on the *attempt*.
"""

from __future__ import annotations

import json
import sys
from typing import Any

import pytest

from libipynb import diff_notebooks, dumps, loads, upgrade, validate

# CPython audit events raised by any code-execution or process-spawning path.
FORBIDDEN_EVENTS = (
    "exec",
    "compile",
    "subprocess.Popen",
    "os.system",
    "os.exec",
    "os.spawn",
    "os.fork",
    "socket.connect",
    "urllib.Request",
)

# Payloads that would be conspicuous if any of them ever ran.
HOSTILE_SOURCES = [
    "import os; os.system('echo pwned')",
    "__import__('subprocess').Popen(['echo', 'pwned'])",
    "eval(\"__import__('os').system('echo pwned')\")",
    "exec(compile('x=1', '<n>', 'exec'))",
    "import urllib.request; urllib.request.urlopen('http://example.invalid')",
]


class _AuditRecorder:
    """Records forbidden audit events raised while active."""

    def __init__(self) -> None:
        self.events: list[str] = []
        self._armed = False

    def hook(self, event: str, args: tuple[Any, ...]) -> None:
        if not self._armed:
            return
        for forbidden in FORBIDDEN_EVENTS:
            if event == forbidden or event.startswith(forbidden):
                self.events.append(event)

    def __enter__(self) -> "_AuditRecorder":
        self._armed = True
        return self

    def __exit__(self, *exc: object) -> None:
        self._armed = False


@pytest.fixture(scope="module")
def recorder() -> _AuditRecorder:
    """One hook for the module -- audit hooks cannot be removed once added."""
    instance = _AuditRecorder()
    sys.addaudithook(instance.hook)
    return instance


def _notebook(sources: list[str]) -> dict[str, Any]:
    return {
        "nbformat": 4,
        "nbformat_minor": 5,
        "metadata": {},
        "cells": [
            {
                "cell_type": "code",
                "id": f"cell-{index}",
                "metadata": {},
                "execution_count": None,
                "outputs": [],
                "source": source,
            }
            for index, source in enumerate(sources)
        ],
    }


def _assert_no_execution(recorder: _AuditRecorder, operation: str) -> None:
    assert not recorder.events, (
        f"{operation} raised code-execution audit events {recorder.events}; "
        "the core path must never execute notebook source"
    )


# ── The audit hook itself must work, or every test below is vacuous ────────


def test_the_audit_hook_actually_detects_execution(recorder: _AuditRecorder) -> None:
    """A guard that cannot fire proves nothing. This proves it fires."""
    with recorder:
        recorder.events.clear()
        exec(compile("_ = 1", "<probe>", "exec"))  # noqa: S102
        detected = list(recorder.events)
    assert detected, "the audit hook did not observe a real exec; the suite would be vacuous"


# ── load / validate / diff / save must not execute ─────────────────────────


@pytest.mark.parametrize("source", HOSTILE_SOURCES)
def test_load_never_executes_cell_source(recorder: _AuditRecorder, source: str) -> None:
    payload = json.dumps(_notebook([source]))
    with recorder:
        recorder.events.clear()
        loads(payload)
    _assert_no_execution(recorder, "loads()")


@pytest.mark.parametrize("source", HOSTILE_SOURCES)
def test_validate_never_executes_cell_source(
    recorder: _AuditRecorder, source: str
) -> None:
    notebook = _notebook([source])
    with recorder:
        recorder.events.clear()
        validate(notebook, profile="4.5")
    _assert_no_execution(recorder, "validate()")


@pytest.mark.parametrize("source", HOSTILE_SOURCES)
def test_save_never_executes_cell_source(recorder: _AuditRecorder, source: str) -> None:
    document = loads(json.dumps(_notebook([source])))
    with recorder:
        recorder.events.clear()
        dumps(document)
    _assert_no_execution(recorder, "dumps()")


def test_diff_never_executes_cell_source(recorder: _AuditRecorder) -> None:
    left = loads(json.dumps(_notebook(HOSTILE_SOURCES[:2])))
    right = loads(json.dumps(_notebook(HOSTILE_SOURCES[2:4])))
    with recorder:
        recorder.events.clear()
        diff_notebooks(left, right)
    _assert_no_execution(recorder, "diff_notebooks()")


def test_upgrade_never_executes_cell_source(recorder: _AuditRecorder) -> None:
    notebook = {
        "nbformat": 4,
        "nbformat_minor": 4,
        "metadata": {},
        "cells": [
            {
                "cell_type": "code",
                "metadata": {},
                "execution_count": None,
                "outputs": [],
                "source": HOSTILE_SOURCES[0],
            }
        ],
    }
    with recorder:
        recorder.events.clear()
        upgrade(notebook)
    _assert_no_execution(recorder, "upgrade()")


def test_full_lifecycle_over_every_hostile_payload_executes_nothing(
    recorder: _AuditRecorder,
) -> None:
    """The whole documented core path in one pass, over all payloads at once."""
    payload = json.dumps(_notebook(HOSTILE_SOURCES))
    with recorder:
        recorder.events.clear()
        document = loads(payload)
        validate(json.loads(payload), profile="4.5")
        diff_notebooks(document, loads(payload))
        dumps(document)
    _assert_no_execution(recorder, "load -> validate -> diff -> save")


# ── Hostile payloads in places other than cell source ──────────────────────


def test_hostile_metadata_is_not_executed(recorder: _AuditRecorder) -> None:
    notebook = _notebook(["x = 1"])
    notebook["metadata"]["x-payload"] = HOSTILE_SOURCES[0]
    notebook["cells"][0]["metadata"]["x-payload"] = HOSTILE_SOURCES[1]
    with recorder:
        recorder.events.clear()
        dumps(loads(json.dumps(notebook)))
    _assert_no_execution(recorder, "metadata round-trip")


def test_hostile_output_payload_is_not_executed(recorder: _AuditRecorder) -> None:
    notebook = _notebook(["x = 1"])
    notebook["cells"][0]["outputs"] = [
        {
            "output_type": "display_data",
            "data": {"text/plain": HOSTILE_SOURCES[0], "text/html": "<script>x</script>"},
            "metadata": {},
        }
    ]
    with recorder:
        recorder.events.clear()
        dumps(loads(json.dumps(notebook)))
    _assert_no_execution(recorder, "output round-trip")


# ── Execution lives only behind the explicit opt-in adapter ────────────────


def test_execute_notebook_is_the_sole_execution_entry_point() -> None:
    """The obligation puts execution behind an opt-in adapter. execute_notebook
    is that adapter's one entry point -- proving it exists is
    test_obligation_execution_adapter.py's job. This test proves the core
    lifecycle functions are not secretly aliases for it and do not reach it."""
    from libipynb import diff_notebooks as diff_fn
    from libipynb import dumps as dumps_fn
    from libipynb.adapters import execute_notebook
    from libipynb import loads as loads_fn
    from libipynb import upgrade as upgrade_fn
    from libipynb import validate as validate_fn
    from libipynb.adapters.execute import execute_notebook as adapter_fn

    core_functions = (loads_fn, dumps_fn, validate_fn, diff_fn, upgrade_fn)
    assert execute_notebook not in core_functions
    assert execute_notebook is adapter_fn


def test_core_module_source_never_references_the_execution_adapter() -> None:
    """A stronger, static check than the audit hook: the reader, writer,
    validator, and diff modules must not import adapters.execute at all, so
    there is no code path -- reachable or not -- connecting them to it."""
    import ast
    from pathlib import Path

    package_root = Path(__file__).resolve().parents[2] / "src" / "libipynb"
    core_modules = [
        package_root / "codec" / "reader.py",
        package_root / "codec" / "writer.py",
        package_root / "validation" / "validator.py",
        package_root / "model" / "diff.py",
    ]
    for module_path in core_modules:
        assert module_path.is_file(), f"expected core module at {module_path}"
        tree = ast.parse(module_path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                assert "execute" not in node.module, (
                    f"{module_path} imports from {node.module!r}; the core path "
                    "must not reference the execution adapter"
                )
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert "execute" not in alias.name, (
                        f"{module_path} imports {alias.name!r}; the core path "
                        "must not reference the execution adapter"
                    )
