"""Shared scaffolding for cross-tool oracle comparisons (LIBIPYNB-P7).

plans/full-parity-plan.md Gate G8 requires every "parity"/"matches <tool>"
claim to be backed by an executed comparison against the real reference
tool, not just a description. This module is that comparison's shared
infrastructure: one `pytest.importorskip`-gated fixture per tool (the exact
pattern already proven in tests/interoperability/conftest.py for nbformat),
plus one small, representative notebook builder reused across every oracle
test file so P2/P3c/P4a-1/P5a/P5b don't each reinvent fixture setup.

None of nbdime/nbconvert/papermill/nbstripout are installed in this
project's core or test dependency groups -- they live in the `oracle` extra
(pyproject.toml) and are expected to be ABSENT in most environments,
including this repo's own working `.venv` as of this writing (confirmed:
`pip list` shows none of the four installed here). Every test built on top
of this scaffolding must therefore skip cleanly, not fail, when the tool is
missing -- that is what this file's fixtures exist to guarantee.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

import pytest


@pytest.fixture
def nbstripout_available() -> None:
    pytest.importorskip("nbstripout", reason="nbstripout (oracle extra) is not installed")


@pytest.fixture
def nbdime_available() -> None:
    pytest.importorskip("nbdime", reason="nbdime (oracle extra) is not installed")


@pytest.fixture
def nbconvert_available() -> None:
    pytest.importorskip("nbconvert", reason="nbconvert (oracle extra) is not installed")


@pytest.fixture
def nbclient_available() -> None:
    pytest.importorskip("nbclient", reason="nbclient (exec extra) is not installed")


@pytest.fixture
def papermill_available() -> None:
    pytest.importorskip("papermill", reason="papermill (oracle extra) is not installed")


def _code_cell(source: str, *, outputs: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {
        "cell_type": "code",
        "id": uuid.uuid4().hex[:16],
        "metadata": {},
        "execution_count": None,
        "outputs": outputs or [],
        "source": source,
    }


def _markdown_cell(source: str) -> dict[str, Any]:
    return {
        "cell_type": "markdown",
        "id": uuid.uuid4().hex[:16],
        "metadata": {},
        "source": source,
    }


def representative_notebook() -> dict[str, Any]:
    """One small, deliberately unremarkable notebook reused across every
    oracle comparison: a markdown cell, a plain code cell with a stream
    output and a nonzero execution_count (what nbstripout/normalize should
    strip), and a second code cell with cell-level metadata worth exercising
    (ExecuteTime-shaped key, matching nbstripout's own default strip list)."""
    return {
        "nbformat": 4,
        "nbformat_minor": 5,
        "metadata": {
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
            "language_info": {"name": "python"},
        },
        "cells": [
            _markdown_cell("# Oracle fixture\n\nUsed by every cross-tool comparison test."),
            _code_cell(
                "print('hello from libipynb oracle fixture')",
                outputs=[
                    {
                        "output_type": "stream",
                        "name": "stdout",
                        "text": ["hello from libipynb oracle fixture\n"],
                    }
                ],
            ),
            {
                **_code_cell("x = 1 + 1\nx"),
                "execution_count": 3,
                "metadata": {
                    "ExecuteTime": {
                        "start_time": "2026-08-13T00:00:00",
                        "end_time": "2026-08-13T00:00:01",
                    }
                },
            },
        ],
    }


def parameterizable_notebook() -> dict[str, Any]:
    """A notebook with a papermill-style `parameters`-tagged cell, for the
    P5a/P5b parameter-injection oracle comparisons."""
    doc = representative_notebook()
    params_cell = _code_cell("alpha = 0.5\nname = 'default'")
    params_cell["metadata"]["tags"] = ["parameters"]
    doc["cells"].insert(1, params_cell)
    return doc


@pytest.fixture
def oracle_tmp_notebook(tmp_path: Path):
    """Write representative_notebook() to a temp .ipynb and return its path."""

    def _write(notebook: dict[str, Any] | None = None, name: str = "oracle-fixture.ipynb") -> Path:
        path = tmp_path / name
        path.write_text(json.dumps(notebook or representative_notebook()), encoding="utf-8")
        return path

    return _write
