"""LIBIPYNB-Q13a Gate G8: real oracle comparison against installed `nbdime diff`.

Mirrors test_nbdime_parity.py's structure exactly: `diff_notebooks()` had
merge-side oracle coverage (that file) but zero oracle-comparison coverage of
its own against real `nbdime diff` before this.

**Confirmed divergence, discovered by directly running real `nbdime diff`,
not assumed:** nbdime matches cells primarily by *content*, using id only as
a tiebreaker -- renaming a cell's id while leaving its source untouched is
reported by real nbdime as a single `replace` patch on that cell's `id`
field. `diff_notebooks()` matches strictly by cell id (`model/diff.py`'s own
documented design, LIBIPYNB-Q3's stable-id-synthesis fix included), so the
identical scenario is reported as one cell removed (old id) and one cell
added (new id) -- never a same-cell "id changed" modification. Both are
internally consistent; this test proves the divergence is real, evidenced,
and worth documenting rather than assumed or left as a surprise for a
caller expecting nbdime-like content-matching.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from libipynb import NotebookDocument, diff_notebooks


def _notebook(cells: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "nbformat": 4,
        "nbformat_minor": 5,
        "metadata": {},
        "cells": cells,
    }


def _code_cell(cell_id: str, source: str) -> dict[str, Any]:
    return {
        "cell_type": "code",
        "id": cell_id,
        "metadata": {},
        "execution_count": None,
        "outputs": [],
        "source": source,
    }


def _write(path: Path, notebook: dict[str, Any]) -> Path:
    path.write_text(json.dumps(notebook), encoding="utf-8")
    return path


def _run_real_nbdime_diff(base: Path, remote: Path, out: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "nbdime", "diff", str(base), str(remote), "--out", str(out)],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )


def test_an_added_removed_and_modified_cell_scenario_agrees_with_real_nbdime(
    nbdime_available, tmp_path: Path
) -> None:
    base = _write(
        tmp_path / "base.ipynb",
        _notebook([_code_cell("kept", "x = 1"), _code_cell("dropped", "y = 1")]),
    )
    remote = _write(
        tmp_path / "remote.ipynb",
        _notebook([_code_cell("kept", "x = 2"), _code_cell("new", "z = 1")]),
    )
    out = tmp_path / "diff.json"

    real = _run_real_nbdime_diff(base, remote, out)
    assert real.returncode == 0, f"real nbdime diff failed unexpectedly: {real.stderr}"
    real_diff = json.loads(out.read_text(encoding="utf-8"))
    assert real_diff, "real nbdime must report a non-empty diff for this scenario"

    result = diff_notebooks(
        NotebookDocument(json.loads(base.read_text(encoding="utf-8"))),
        NotebookDocument(json.loads(remote.read_text(encoding="utf-8"))),
    )
    changes_by_id = {change.cell_id: change for change in result.cell_changes}

    assert changes_by_id["kept"].modified
    assert changes_by_id["dropped"].removed
    assert changes_by_id["new"].added
    assert result.has_changes


def test_an_unmodified_notebook_agrees_with_real_nbdime_as_no_change(
    nbdime_available, tmp_path: Path
) -> None:
    notebook = _notebook([_code_cell("stable", "x = 1")])
    base = _write(tmp_path / "base.ipynb", notebook)
    remote = _write(tmp_path / "remote.ipynb", notebook)
    out = tmp_path / "diff.json"

    real = _run_real_nbdime_diff(base, remote, out)
    assert real.returncode == 0
    real_diff = json.loads(out.read_text(encoding="utf-8"))
    assert real_diff == [], "real nbdime must report an empty diff for an identical notebook"

    result = diff_notebooks(NotebookDocument(notebook), NotebookDocument(notebook))
    assert not result.has_changes


def test_known_divergence_nbdime_matches_by_content_diff_notebooks_matches_strictly_by_id(
    nbdime_available, tmp_path: Path
) -> None:
    """The documented divergence: only the cell id changes, source stays
    identical. Real nbdime reports this as a single `replace` on the `id`
    field of the same matched cell. diff_notebooks() reports it as a
    remove (old id) plus an add (new id) -- confirmed against the real
    tool, not assumed, exactly like test_nbdime_parity.py's own two
    known-divergence tests document the merge-side equivalents."""
    base = _write(tmp_path / "base.ipynb", _notebook([_code_cell("same-content", "y = 1")]))
    remote = _write(tmp_path / "remote.ipynb", _notebook([_code_cell("renamed-id", "y = 1")]))
    out = tmp_path / "diff.json"

    real = _run_real_nbdime_diff(base, remote, out)
    assert real.returncode == 0
    real_diff = json.loads(out.read_text(encoding="utf-8"))
    # Real nbdime: one `patch` on `cells`, containing one `patch` on cell 0,
    # containing exactly one `replace` on the `id` field -- never a
    # remove+add pair for what it considers the same (content-matched) cell.
    cell_patch = real_diff[0]["diff"][0]
    assert cell_patch["op"] == "patch"
    (id_op,) = cell_patch["diff"]
    assert id_op == {"op": "replace", "key": "id", "value": "renamed-id"}, (
        "if real nbdime's content-matching behavior for this scenario ever changes, "
        "this test and this module's docstring need updating, not silently left stale"
    )

    result = diff_notebooks(
        NotebookDocument(json.loads(base.read_text(encoding="utf-8"))),
        NotebookDocument(json.loads(remote.read_text(encoding="utf-8"))),
    )
    changes_by_id = {change.cell_id: change for change in result.cell_changes}
    assert set(changes_by_id) == {"same-content", "renamed-id"}
    assert changes_by_id["same-content"].removed
    assert changes_by_id["renamed-id"].added
    # Neither half is ever reported as an in-place "modified" cell the way
    # real nbdime's single content-matched patch would suggest.
    assert not changes_by_id["same-content"].modified
    assert not changes_by_id["renamed-id"].modified
