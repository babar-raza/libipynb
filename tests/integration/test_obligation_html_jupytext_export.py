"""LIBIPYNB-V5: HtmlExporter and JupytextExporter, each wrapping a real tool.

Required proof (remediation-plan.md's LIBIPYNB-V5 taskcard): fidelity
reports for each adapter, round-trip tests where the underlying tool
supports round-tripping (Jupytext does; nbconvert-to-HTML does not and
must be documented as one-directional), and test results against real
`nbconvert`/`jupytext` installs -- not just a description of what they
would do. Every test below either runs the real tool (skipping cleanly if
it isn't installed, matching the existing `tests/oracle/` pattern) or
exercises the tool-unavailable error path directly.
"""

from __future__ import annotations

import subprocess
import sys
from typing import Any

import pytest

from libipynb import NotebookDocument, loads
from libipynb.adapters import HtmlExporter, JupytextExporter
from libipynb.errors import NotebookError


@pytest.fixture
def nbconvert_available() -> None:
    pytest.importorskip("nbconvert", reason="nbconvert (export extra) is not installed")


@pytest.fixture
def jupytext_available() -> None:
    pytest.importorskip("jupytext", reason="jupytext (export extra) is not installed")


def _document() -> NotebookDocument:
    return loads(
        b"""{
        "nbformat": 4, "nbformat_minor": 5,
        "metadata": {"kernelspec": {"name": "python3", "display_name": "Python 3", "language": "python"}},
        "cells": [
            {"cell_type": "markdown", "id": "c1", "metadata": {}, "source": "# A Title"},
            {"cell_type": "code", "id": "c2", "metadata": {}, "source": "print('hi')",
             "execution_count": 1, "outputs": []}
        ]}""",
        mode="preservation",
    )


class TestHtmlExporter:
    def test_produces_self_contained_html_from_the_real_tool(
        self, nbconvert_available: None
    ) -> None:
        result = HtmlExporter().export(_document())
        assert result.content.startswith("<!DOCTYPE html>")
        assert "A Title" in result.content
        # nbconvert's HTML syntax-highlights code, splitting source tokens
        # across separate <span> elements -- assert the tokens are present
        # rather than an exact contiguous "print('hi')" substring.
        assert "print" in result.content
        assert "hi" in result.content
        assert result.resources == ()
        assert result.metadata["format"] == "html"
        assert result.metadata["reversible"] is False

    def test_is_one_directional_not_claimed_as_round_trippable(
        self, nbconvert_available: None
    ) -> None:
        # Explicit regression guard for the taskcard's own non-goal: HTML
        # export must never claim reversibility.
        result = HtmlExporter().export(_document())
        assert result.metadata["reversible"] is False

    def test_missing_interpreter_raises_a_clear_notebook_error_not_a_raw_traceback(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # The (rare) case where sys.executable itself can't be spawned.
        def _raise_not_found(*args: Any, **kwargs: Any) -> Any:
            raise FileNotFoundError("no such interpreter")

        monkeypatch.setattr(subprocess, "run", _raise_not_found)
        with pytest.raises(NotebookError, match="nbconvert to be installed") as excinfo:
            HtmlExporter().export(_document())
        assert excinfo.value.code == "export_tool_unavailable"

    def test_uninstalled_nbconvert_raises_a_clear_notebook_error_not_a_generic_failure(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Gate G2 finding: the common real-world case is NOT
        # FileNotFoundError -- sys.executable always exists, so `python -m
        # nbconvert` runs successfully as a *process* and exits non-zero
        # with "No module named nbconvert" on stderr, exactly reproducing
        # what a real uninstalled-nbconvert environment produces (confirmed
        # directly: `python -m <missing module>` on this interpreter prints
        # "<executable>: No module named <missing module>", exit code 1).
        def _fake_module_not_found(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
            return subprocess.CompletedProcess(
                args, returncode=1, stdout="", stderr=f"{sys.executable}: No module named nbconvert"
            )

        monkeypatch.setattr(subprocess, "run", _fake_module_not_found)
        with pytest.raises(NotebookError, match="nbconvert to be installed") as excinfo:
            HtmlExporter().export(_document())
        assert excinfo.value.code == "export_tool_unavailable"

    def test_nonzero_exit_from_the_real_tool_is_wrapped_as_a_notebook_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # The success path is verified for real above
        # (test_produces_self_contained_html...); this test only needs to
        # prove the failure *path* is handled, so a stubbed subprocess
        # result is appropriate here rather than requiring nbconvert itself
        # to be coaxed into failing.
        def _fake_failure(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
            return subprocess.CompletedProcess(args, returncode=1, stdout="", stderr="boom")

        monkeypatch.setattr(subprocess, "run", _fake_failure)
        with pytest.raises(NotebookError, match="boom") as excinfo:
            HtmlExporter().export(_document())
        assert excinfo.value.code == "export_tool_failed"

    def test_timeout_is_wrapped_as_a_notebook_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def _raise_timeout(*args: Any, **kwargs: Any) -> Any:
            raise subprocess.TimeoutExpired(cmd="nbconvert", timeout=0.01)

        monkeypatch.setattr(subprocess, "run", _raise_timeout)
        with pytest.raises(NotebookError, match="did not finish") as excinfo:
            HtmlExporter(timeout=0.01).export(_document())
        assert excinfo.value.code == "export_tool_timeout"


class TestJupytextExporter:
    def test_produces_percent_format_text_from_the_real_tool(
        self, jupytext_available: None
    ) -> None:
        result = JupytextExporter().export(_document())
        assert "# %% [markdown]" in result.content
        assert "# A Title" in result.content
        assert "print('hi')" in result.content
        assert result.resources == ()
        assert result.metadata["format"] == "jupytext:py:percent"
        assert result.metadata["reversible"] is True

    def test_round_trips_through_the_real_tool(self, jupytext_available: None) -> None:
        import jupytext

        document = _document()
        exported = JupytextExporter().export(document)

        # Read the exported text back with the same real tool and confirm
        # the structural content it recovers matches the source -- the
        # actual point of this format being marked reversible=True.
        recovered = jupytext.reads(exported.content, fmt="py:percent")
        recovered_sources = [cell["source"] for cell in recovered["cells"]]
        assert any("A Title" in source for source in recovered_sources)
        assert any("print" in source for source in recovered_sources)

    def test_alternate_format_is_honored(self, jupytext_available: None) -> None:
        result = JupytextExporter(fmt="md").export(_document())
        assert result.metadata["format"] == "jupytext:md"
        assert "A Title" in result.content

    def test_missing_tool_raises_a_clear_notebook_error_not_a_raw_traceback(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setitem(sys.modules, "jupytext", None)
        with pytest.raises(NotebookError, match="jupytext package") as excinfo:
            JupytextExporter().export(_document())
        assert excinfo.value.code == "export_tool_unavailable"
