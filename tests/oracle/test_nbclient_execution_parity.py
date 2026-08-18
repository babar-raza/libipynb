"""LIBIPYNB-P4a-1 Gate G8: real oracle comparison against installed
`nbconvert --execute` (which itself delegates to `nbclient`, the same
library `LocalJupyterExecutor` uses -- so this test compares against the
reference *tool users actually invoke*, not just the shared underlying
engine, matching the same "compare against the real CLI/tool" discipline
already used by test_nbstripout_parity.py/test_nbdime_parity.py).

Only deterministic cells are compared (fixed print statements, fixed
arithmetic) -- consistent with this project's own oracle/determinism
policy (plans/full-parity-plan.md "Oracle and determinism policy"):
execution is not byte-deterministic in general (timestamps, object ids,
generated identifiers), so this test does not claim byte-identical output
for arbitrary code, only agreement on the outputs a real notebook author
would expect to be identical, and structural agreement (valid nbformat,
execution counts assigned) on the executed notebook as a whole.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from libipynb import NotebookDocument, validate
from libipynb.execution import ExecutionOptions, LocalJupyterExecutor


def _as_text(value: object) -> str:
    """Normalize nbformat's string-vs-list-of-lines text representation --
    real nbconvert's output (round-tripped through nbformat's own writer)
    uses the list form; LocalJupyterExecutor deliberately never round-trips
    through nbformat's writer (see adapters/jupyter_execute.py's module
    docstring: "Fidelity strategy"), so it carries whatever raw form the
    kernel protocol produced. Both are valid nbformat text fields -- the
    exact same already-documented divergence found for nbstripout in
    test_nbstripout_parity.py, not a new one."""
    return "".join(value) if isinstance(value, list) else str(value)


def _fixture_notebook() -> dict:
    return {
        "nbformat": 4,
        "nbformat_minor": 5,
        "metadata": {
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"}
        },
        "cells": [
            {
                "cell_type": "code",
                "id": "a",
                "metadata": {},
                "execution_count": None,
                "outputs": [],
                "source": "x = 21",
            },
            {
                "cell_type": "code",
                "id": "b",
                "metadata": {},
                "execution_count": None,
                "outputs": [],
                "source": "print('oracle fixture:', x * 2)",
            },
            {
                "cell_type": "code",
                "id": "c",
                "metadata": {},
                "execution_count": None,
                "outputs": [],
                "source": "x + 1",
            },
        ],
    }


def _run_real_nbconvert_execute(source: Path, out_dir: Path) -> dict:
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "nbconvert",
            "--to",
            "notebook",
            "--execute",
            "--output-dir",
            str(out_dir),
            str(source),
        ],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert completed.returncode == 0, f"real nbconvert --execute failed: {completed.stderr}"
    [executed_path] = list(out_dir.glob("*.ipynb"))
    return json.loads(executed_path.read_text(encoding="utf-8"))


def test_deterministic_cell_outputs_agree_with_real_nbconvert_execute(
    nbconvert_available, nbclient_available, tmp_path: Path
) -> None:
    fixture = _fixture_notebook()
    source_path = tmp_path / "fixture.ipynb"
    source_path.write_text(json.dumps(fixture), encoding="utf-8")
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    real_executed = _run_real_nbconvert_execute(source_path, out_dir)

    result = LocalJupyterExecutor().execute(
        NotebookDocument(fixture), options=ExecutionOptions(acknowledge_unsandboxed=True)
    )

    real_cell_b_text = "".join(real_executed["cells"][1]["outputs"][0]["text"])
    libipynb_cell_b_text = result.cell_records[1].outputs[0]["text"]
    assert real_cell_b_text == libipynb_cell_b_text == "oracle fixture: 42\n"

    real_cell_c_data = _as_text(real_executed["cells"][2]["outputs"][0]["data"]["text/plain"])
    libipynb_cell_c_data = _as_text(result.cell_records[2].outputs[0]["data"]["text/plain"])
    assert real_cell_c_data == libipynb_cell_c_data == "22"

    # execution_count sequencing agrees (both engines run the same 3 code
    # cells, in order, in one shared kernel session).
    assert [c["execution_count"] for c in real_executed["cells"]] == [1, 2, 3]
    assert [r.execution_count for r in result.cell_records] == [1, 2, 3]

    # The libipynb-executed document is itself schema-valid nbformat, same
    # bar real nbconvert's own output must clear.
    report = validate(result.notebook.raw)
    assert report.is_valid, [d.message for d in report]


def _list_source_fixture_notebook() -> dict:
    """LIBIPYNB-Q1 Gate G8: same shape as _fixture_notebook() above, but with
    every code cell's source as a list-of-lines -- the standard on-disk
    Jupyter form real nbconvert/jupyter always produce, and the exact input
    shape LocalJupyterExecutor previously crashed on unconditionally
    (AttributeError: 'list' object has no attribute 'strip', deep inside
    nbclient). Extends the existing string-source-only oracle comparison
    above to list-source input for the first time."""
    return {
        "nbformat": 4,
        "nbformat_minor": 5,
        "metadata": {
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"}
        },
        "cells": [
            {
                "cell_type": "code",
                "id": "a",
                "metadata": {},
                "execution_count": None,
                "outputs": [],
                "source": ["x = 21\n"],
            },
            {
                "cell_type": "code",
                "id": "b",
                "metadata": {},
                "execution_count": None,
                "outputs": [],
                "source": ["y = x * 2\n", "print('oracle fixture:', y)"],
            },
            {
                "cell_type": "code",
                "id": "c",
                "metadata": {},
                "execution_count": None,
                "outputs": [],
                "source": ["x + 1"],
            },
        ],
    }


def test_list_of_lines_source_executes_and_agrees_with_real_nbconvert_execute(
    nbconvert_available, nbclient_available, tmp_path: Path
) -> None:
    fixture = _list_source_fixture_notebook()
    source_path = tmp_path / "list-source-fixture.ipynb"
    source_path.write_text(json.dumps(fixture), encoding="utf-8")
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    real_executed = _run_real_nbconvert_execute(source_path, out_dir)

    result = LocalJupyterExecutor().execute(
        NotebookDocument(fixture), options=ExecutionOptions(acknowledge_unsandboxed=True)
    )

    # The confirmed pre-fix failure mode: kernel_death_error set, nothing
    # executed. Assert the positive outcome directly, not just "no crash".
    assert result.completed is True
    assert result.kernel_death_error is None
    assert all(record.executed for record in result.cell_records)

    real_cell_b_text = "".join(real_executed["cells"][1]["outputs"][0]["text"])
    libipynb_cell_b_text = result.cell_records[1].outputs[0]["text"]
    assert real_cell_b_text == libipynb_cell_b_text == "oracle fixture: 42\n"

    real_cell_c_data = _as_text(real_executed["cells"][2]["outputs"][0]["data"]["text/plain"])
    libipynb_cell_c_data = _as_text(result.cell_records[2].outputs[0]["data"]["text/plain"])
    assert real_cell_c_data == libipynb_cell_c_data == "22"

    assert [c["execution_count"] for c in real_executed["cells"]] == [1, 2, 3]
    assert [r.execution_count for r in result.cell_records] == [1, 2, 3]

    # Source form itself is untouched by the fix -- the executed result's
    # source is still a list, same shape as the input (the fidelity
    # guarantee the module docstring makes -- only the execution COPY is
    # normalized, never the harvested result).
    assert result.notebook.cells[1]["source"] == ["y = x * 2\n", "print('oracle fixture:', y)"]
