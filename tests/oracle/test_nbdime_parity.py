"""LIBIPYNB-P3c Gate G8: real oracle comparison against installed `nbdime`.

This is the sub-task every P3c status note in plans/full-parity-plan.md
explicitly flagged as skipped "because no oracle tools are installed on
this machine" -- now that `nbdime` is installed (`libipynb[oracle]`), this
file runs the actual comparison.

**Major finding, discovered by directly running real `nbmerge`, not
assumed:** real nbdime's DEFAULT merge strategy ("inline") splices literal
git-style conflict markers (`<<<<<<< local` / `=======` / `>>>>>>> remote`)
directly into a conflicted cell's `source` field. This is precisely the
practice `model/merge.py`'s own docstring calls an "outright prohibition,"
reasoning that embedding such markers into executable source "would
silently turn a merge conflict into a syntax error at best and a foreign
string literal at worst." This test proves, with the real reference tool,
that the divergence is real and libipynb's stricter behavior is a
deliberate, evidenced design choice -- not an assumption or an oversight.

A second, subtler finding: nbdime's `--merge-strategy use-base` avoids
marker-splicing (resolves silently to the base's value, matching one half
of libipynb's own behavior) but does so by NOT reporting a conflict at all
(exit code 0, no warning) -- silently resolving rather than surfacing that
a decision was made. libipynb's `merge_notebooks()` combines the safe
*value* choice (never splice, fall back to base) with `nbmerge --merge-
strategy inline`'s *reporting* behavior (always surface the conflict via
`MergeReport.conflicts`, exit 1) -- a third, evidenced position distinct
from either of nbdime's own two strategies compared here.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from libipynb import NotebookDocument, merge_notebooks


def _notebook(source: str, *, cell_id: str = "alpha") -> dict[str, Any]:
    return {
        "nbformat": 4,
        "nbformat_minor": 5,
        "metadata": {},
        "cells": [
            {
                "cell_type": "code",
                "id": cell_id,
                "metadata": {},
                "execution_count": None,
                "outputs": [],
                "source": source,
            }
        ],
    }


def _write(path: Path, notebook: dict[str, Any]) -> Path:
    path.write_text(json.dumps(notebook), encoding="utf-8")
    return path


def _run_real_nbmerge(
    base: Path, local: Path, remote: Path, out: Path, *, extra_args: list[str] | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "nbdime",
            "merge",
            str(base),
            str(local),
            str(remote),
            "--out",
            str(out),
            *(extra_args or []),
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )


def test_no_conflict_merge_agrees_with_real_nbdime(nbdime_available, tmp_path: Path) -> None:
    base = _write(tmp_path / "base.ipynb", _notebook("x = 1"))
    local = _write(tmp_path / "local.ipynb", _notebook("x = 2"))
    remote = _write(tmp_path / "remote.ipynb", _notebook("x = 1"))
    out = tmp_path / "merged.ipynb"

    real = _run_real_nbmerge(base, local, remote, out)
    assert real.returncode == 0, f"real nbdime reported an unexpected conflict: {real.stderr}"
    real_merged = json.loads(out.read_text(encoding="utf-8"))

    result = merge_notebooks(
        NotebookDocument(_notebook("x = 1")),
        NotebookDocument(_notebook("x = 2")),
        NotebookDocument(_notebook("x = 1")),
    )
    assert not result.report.has_conflicts

    assert real_merged["cells"][0]["source"] == ["x = 2"]
    assert result.merged.raw["cells"][0]["source"] == "x = 2"


def test_real_nbdime_default_strategy_splices_conflict_markers_libipynb_never_does(
    nbdime_available, tmp_path: Path
) -> None:
    base = _write(tmp_path / "base.ipynb", _notebook("x = 1"))
    local = _write(tmp_path / "local.ipynb", _notebook("x = 2"))
    remote = _write(tmp_path / "remote.ipynb", _notebook("x = 3"))
    out = tmp_path / "merged.ipynb"

    real = _run_real_nbmerge(base, local, remote, out)
    assert real.returncode == 1, "expected real nbdime to report a conflict (default strategy)"
    real_merged = json.loads(out.read_text(encoding="utf-8"))
    real_source = real_merged["cells"][0]["source"]
    real_text = "".join(real_source) if isinstance(real_source, list) else real_source

    assert "<<<<<<<" in real_text and ">>>>>>>" in real_text, (
        "if real nbdime's default strategy ever stops splicing conflict markers, "
        "this test and this module's docstring need updating, not silently left stale"
    )

    result = merge_notebooks(
        NotebookDocument(_notebook("x = 1")),
        NotebookDocument(_notebook("x = 2")),
        NotebookDocument(_notebook("x = 3")),
    )
    assert result.report.has_conflicts
    libipynb_source = result.merged.raw["cells"][0]["source"]
    assert "<<<<<<<" not in libipynb_source
    assert ">>>>>>>" not in libipynb_source
    assert libipynb_source == "x = 1", "libipynb must fall back to base's value, never a marker"


def test_real_nbdime_use_base_strategy_resolves_silently_libipynb_always_reports(
    nbdime_available, tmp_path: Path
) -> None:
    """The subtler finding: nbdime's own marker-free strategy achieves the
    same VALUE outcome as libipynb (base wins) but by suppressing the
    conflict signal entirely (exit 0), unlike libipynb which always
    surfaces it via MergeReport regardless of the value chosen."""
    base = _write(tmp_path / "base.ipynb", _notebook("x = 1"))
    local = _write(tmp_path / "local.ipynb", _notebook("x = 2"))
    remote = _write(tmp_path / "remote.ipynb", _notebook("x = 3"))
    out = tmp_path / "merged.ipynb"

    real = _run_real_nbmerge(base, local, remote, out, extra_args=["--merge-strategy", "use-base"])
    assert real.returncode == 0, (
        "if real nbdime's use-base strategy ever starts reporting a nonzero exit "
        "for a resolved conflict, this test needs updating"
    )
    real_merged = json.loads(out.read_text(encoding="utf-8"))
    assert real_merged["cells"][0]["source"] == ["x = 1"]

    result = merge_notebooks(
        NotebookDocument(_notebook("x = 1")),
        NotebookDocument(_notebook("x = 2")),
        NotebookDocument(_notebook("x = 3")),
    )
    assert result.merged.raw["cells"][0]["source"] == "x = 1"  # same value as nbdime's use-base
    assert result.report.has_conflicts, (
        "libipynb must still surface this as a conflict even though the resolved "
        "value matches nbdime's silent use-base strategy -- the point of "
        "MergeReport is that a caller can find out a decision was made"
    )
