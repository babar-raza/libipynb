"""LIBIPYNB-P3c: git diff/merge driver integration.

Covers the internal `_git-diff-driver`/`_git-merge-driver` commands (git's
own invocation contract, gitattributes(5)), the `diff --install-git`/
`--uninstall-git`/`--git-status` wrapper, and a real end-to-end proof that
`git diff`/`git merge` on a real scratch repository actually invoke
libipynb rather than falling back to git's default binary-file handling.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from libipynb.cli.main import main

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git is not on PATH")


def _write_notebook(path: Path, *, sources: list[str]) -> None:
    path.write_text(
        json.dumps(
            {
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
        ),
        encoding="utf-8",
    )


class TestInternalDiffDriverCommand:
    def test_prints_a_hunk_for_a_changed_cell(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        old_file = tmp_path / "old.ipynb"
        new_file = tmp_path / "new.ipynb"
        _write_notebook(old_file, sources=["x = 1\n"])
        _write_notebook(new_file, sources=["x = 2\n"])
        code = main(
            [
                "_git-diff-driver",
                "notebook.ipynb",
                str(old_file),
                "hex1",
                "100644",
                str(new_file),
                "hex2",
                "100644",
            ]
        )
        assert code == 0
        out = capsys.readouterr().out
        assert "--- a/notebook.ipynb" in out
        assert "-x = 1" in out
        assert "+x = 2" in out

    def test_missing_old_file_is_treated_as_empty_notebook(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        new_file = tmp_path / "new.ipynb"
        _write_notebook(new_file, sources=["x = 1\n"])
        missing = tmp_path / "does-not-exist.ipynb"
        code = main(
            [
                "_git-diff-driver",
                "notebook.ipynb",
                str(missing),
                "0000000",
                "000000",
                str(new_file),
                "hex2",
                "100644",
            ]
        )
        assert code == 0
        out = capsys.readouterr().out
        assert "added" in out

    def test_internal_error_shows_no_diff_and_never_fails_the_driver(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """LIBIPYNB-Q4: git's diff-driver protocol has no "fall back to
        default diff" state once a driver is configured -- a nonzero exit
        here is fatal to the WHOLE `git diff` invocation, confirmed by the
        forensic audit's own live repro. An internal error (here: duplicate
        cell ids, which loads fine but makes diff_notebooks() raise) must
        still exit 0 and show a clean "no diff" note, never propagate."""
        old_file = tmp_path / "old.ipynb"
        new_file = tmp_path / "new.ipynb"
        duplicate_ids = json.dumps(
            {
                "nbformat": 4,
                "nbformat_minor": 5,
                "metadata": {},
                "cells": [
                    {
                        "cell_type": "code",
                        "id": "dup",
                        "metadata": {},
                        "execution_count": None,
                        "outputs": [],
                        "source": "x = 1",
                    },
                    {
                        "cell_type": "code",
                        "id": "dup",
                        "metadata": {},
                        "execution_count": None,
                        "outputs": [],
                        "source": "y = 2",
                    },
                ],
            }
        )
        old_file.write_text(duplicate_ids, encoding="utf-8")
        _write_notebook(new_file, sources=["x = 1\n"])

        code = main(
            [
                "_git-diff-driver",
                "notebook.ipynb",
                str(old_file),
                "hex1",
                "100644",
                str(new_file),
                "hex2",
                "100644",
            ]
        )

        assert code == 0, "an internal error must never propagate a nonzero exit to git"
        captured = capsys.readouterr()
        assert "no diff" in captured.out.lower() or "no diff" in captured.err.lower()

    def test_identical_notebooks_report_no_structural_changes(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        old_file = tmp_path / "old.ipynb"
        new_file = tmp_path / "new.ipynb"
        _write_notebook(old_file, sources=["x = 1\n"])
        _write_notebook(new_file, sources=["x = 1\n"])
        code = main(
            [
                "_git-diff-driver",
                "notebook.ipynb",
                str(old_file),
                "hex1",
                "100644",
                str(new_file),
                "hex1",
                "100644",
            ]
        )
        assert code == 0
        assert "(no structural changes)" in capsys.readouterr().out


class TestInternalMergeDriverCommand:
    def test_no_conflict_merge_overwrites_ours_and_returns_0(self, tmp_path: Path) -> None:
        ancestor = tmp_path / "ancestor.ipynb"
        ours = tmp_path / "ours.ipynb"
        theirs = tmp_path / "theirs.ipynb"
        _write_notebook(ancestor, sources=["x = 1"])
        _write_notebook(ours, sources=["x = 2"])
        _write_notebook(theirs, sources=["x = 1"])
        code = main(["_git-merge-driver", str(ancestor), str(ours), str(theirs), "notebook.ipynb"])
        assert code == 0
        merged = json.loads(ours.read_text(encoding="utf-8"))
        assert merged["cells"][0]["source"] == "x = 2"

    def test_conflicting_merge_overwrites_ours_with_ancestor_value_and_returns_1(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        ancestor = tmp_path / "ancestor.ipynb"
        ours = tmp_path / "ours.ipynb"
        theirs = tmp_path / "theirs.ipynb"
        _write_notebook(ancestor, sources=["x = 1"])
        _write_notebook(ours, sources=["x = 2"])
        _write_notebook(theirs, sources=["x = 3"])
        code = main(["_git-merge-driver", str(ancestor), str(ours), str(theirs), "notebook.ipynb"])
        assert code == 1
        merged = json.loads(ours.read_text(encoding="utf-8"))
        assert merged["cells"][0]["source"] == "x = 1"
        assert "conflict" in capsys.readouterr().err.lower()

    def test_internal_error_leaves_ours_untouched_and_returns_1(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """LIBIPYNB-Q4: git's merge-driver protocol is binary (0=clean,
        nonzero=needs manual attention) -- an internal error (here:
        duplicate cell ids, which load fine but make merge_notebooks()
        raise) must report via the same nonzero-exit convention, and %A
        (args.ours) must be left completely untouched, never corrupted."""
        ancestor = tmp_path / "ancestor.ipynb"
        ours = tmp_path / "ours.ipynb"
        theirs = tmp_path / "theirs.ipynb"
        duplicate_ids = json.dumps(
            {
                "nbformat": 4,
                "nbformat_minor": 5,
                "metadata": {},
                "cells": [
                    {
                        "cell_type": "code",
                        "id": "dup",
                        "metadata": {},
                        "execution_count": None,
                        "outputs": [],
                        "source": "x = 1",
                    },
                    {
                        "cell_type": "code",
                        "id": "dup",
                        "metadata": {},
                        "execution_count": None,
                        "outputs": [],
                        "source": "y = 2",
                    },
                ],
            }
        )
        ancestor.write_text(duplicate_ids, encoding="utf-8")
        _write_notebook(ours, sources=["x = 1"])
        _write_notebook(theirs, sources=["x = 1"])
        original_ours_text = ours.read_text(encoding="utf-8")

        code = main(["_git-merge-driver", str(ancestor), str(ours), str(theirs), "notebook.ipynb"])

        assert code == 1
        assert ours.read_text(encoding="utf-8") == original_ours_text
        assert "unresolved" in capsys.readouterr().err.lower()


def _init_scratch_repo(path: Path) -> None:
    # Explicit -b master (Gate G2 finding): this suite's own
    # test_git_merge_invokes_libipynb_for_a_conflict later runs a literal
    # `git merge master`, which would fail on any machine configured with
    # init.defaultBranch=main instead of git's old default -- pinning the
    # branch name here makes the test deterministic across environments
    # rather than dependent on the runner's global git config.
    subprocess.run(["git", "init", "-q", "-b", "master"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=path, check=True)


class TestInstallUninstallStatus:
    def test_round_trip(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        _init_scratch_repo(tmp_path)
        monkeypatch.chdir(tmp_path)

        assert main(["diff", "--git-status"]) == 1

        assert main(["diff", "--install-git"]) == 0
        attributes = (tmp_path / ".git" / "info" / "attributes").read_text(encoding="utf-8")
        assert "*.ipynb diff=libipynb merge=libipynb" in attributes
        diff_cmd = subprocess.run(
            ["git", "config", "--get", "diff.libipynb.command"],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            check=True,
        )
        assert "_git-diff-driver" in diff_cmd.stdout
        merge_cmd = subprocess.run(
            ["git", "config", "--get", "merge.libipynb.driver"],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            check=True,
        )
        assert "_git-merge-driver" in merge_cmd.stdout
        assert "%O %A %B %P" in merge_cmd.stdout

        assert main(["diff", "--git-status"]) == 0

        assert main(["diff", "--uninstall-git"]) == 0
        assert main(["diff", "--git-status"]) == 1


class TestEndToEndGitDiffAndMerge:
    def test_git_diff_invokes_libipynb_and_shows_a_cell_hunk(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _init_scratch_repo(tmp_path)
        monkeypatch.chdir(tmp_path)
        assert main(["diff", "--install-git"]) == 0

        notebook = tmp_path / "notebook.ipynb"
        _write_notebook(notebook, sources=["x = 1\n"])
        subprocess.run(["git", "add", "notebook.ipynb"], cwd=tmp_path, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "initial"], cwd=tmp_path, check=True)

        _write_notebook(notebook, sources=["x = 2\n"])
        result = subprocess.run(
            ["git", "diff"], cwd=tmp_path, capture_output=True, text=True, check=True
        )
        assert "-x = 1" in result.stdout, (
            "git diff did not invoke the libipynb diff driver -- got git's own default "
            f"diff output instead:\n{result.stdout}"
        )
        assert "+x = 2" in result.stdout

    def test_git_merge_invokes_libipynb_for_a_conflict(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _init_scratch_repo(tmp_path)
        monkeypatch.chdir(tmp_path)
        assert main(["diff", "--install-git"]) == 0

        notebook = tmp_path / "notebook.ipynb"
        _write_notebook(notebook, sources=["x = 1"])
        subprocess.run(["git", "add", "notebook.ipynb"], cwd=tmp_path, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "base"], cwd=tmp_path, check=True)
        subprocess.run(["git", "branch", "feature"], cwd=tmp_path, check=True)

        _write_notebook(notebook, sources=["x = 2"])
        subprocess.run(["git", "add", "notebook.ipynb"], cwd=tmp_path, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "main change"], cwd=tmp_path, check=True)

        subprocess.run(["git", "checkout", "-q", "feature"], cwd=tmp_path, check=True)
        _write_notebook(notebook, sources=["x = 3"])
        subprocess.run(["git", "add", "notebook.ipynb"], cwd=tmp_path, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "feature change"], cwd=tmp_path, check=True)

        merge_result = subprocess.run(
            ["git", "merge", "master"], cwd=tmp_path, capture_output=True, text=True, check=False
        )
        assert merge_result.returncode != 0, "expected a conflicted merge"
        merged_content = json.loads(notebook.read_text(encoding="utf-8"))
        # A real git conflict-marker merge would have left "<<<<<<<" in the
        # file and made it invalid JSON entirely -- proving libipynb's
        # driver ran, not git's default merge strategy.
        assert merged_content["cells"][0]["source"] == "x = 1"


def _write_pre_45_notebook(path: Path, *, sources: list[str]) -> None:
    """A genuine nbformat-4.4 notebook with no cell `id` on any cell -- the
    majority-case real-world shape LIBIPYNB-Q3 fixes diff/merge for.
    Deliberately not using `_write_notebook` above, which always writes an
    explicit id."""
    path.write_text(
        json.dumps(
            {
                "nbformat": 4,
                "nbformat_minor": 4,
                "metadata": {},
                "cells": [
                    {
                        "cell_type": "code",
                        "metadata": {},
                        "execution_count": None,
                        "outputs": [],
                        "source": source,
                    }
                    for source in sources
                ],
            }
        ),
        encoding="utf-8",
    )


class TestEndToEndGitDiffOnPreNbformat45Notebooks:
    """LIBIPYNB-Q3 blocker fix, reproduced exactly as the forensic audit
    found it: real git diff/merge on a genuine pre-4.5 (no cell-id)
    notebook used to fail outright (`fatal: external diff died, stopping
    at notebook.ipynb`, exit 128) -- not a standalone-CLI-only bug, a real
    break of the git integration itself, which is this feature's entire
    reason to exist."""

    def test_git_diff_succeeds_on_a_pre_45_notebook(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _init_scratch_repo(tmp_path)
        monkeypatch.chdir(tmp_path)
        assert main(["diff", "--install-git"]) == 0

        notebook = tmp_path / "notebook.ipynb"
        _write_pre_45_notebook(notebook, sources=["x = 1\n"])
        subprocess.run(["git", "add", "notebook.ipynb"], cwd=tmp_path, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "initial"], cwd=tmp_path, check=True)

        _write_pre_45_notebook(notebook, sources=["x = 2\n"])
        result = subprocess.run(
            ["git", "diff"], cwd=tmp_path, capture_output=True, text=True, check=False
        )
        assert result.returncode == 0, (
            "git diff must not fail on a pre-4.5 (no cell-id) notebook -- got "
            f"exit {result.returncode}, stderr:\n{result.stderr}"
        )
        # A changed id-less cell is honestly reported as a synthesized-id
        # remove+add (an accepted, documented limitation of content-hash
        # identity for cells with no stable id -- see model/diff.py's
        # _with_stable_cell_ids docstring), not a line-level "-x = 1"/
        # "+x = 2" hunk the way an id-bearing (4.5) notebook would be. The
        # bar this test proves is the actual blocker fix: git diff exits 0
        # and shows *something*, instead of `fatal: external diff died`.
        assert "added" in result.stdout
        assert "removed" in result.stdout

    def test_git_merge_succeeds_cleanly_on_a_genuinely_divergent_pre_45_notebook(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A real (non-fast-forward) 3-way merge: master and feature each
        commit a NON-overlapping change after branching, forcing git to
        actually invoke the merge driver rather than fast-forwarding."""
        _init_scratch_repo(tmp_path)
        monkeypatch.chdir(tmp_path)
        assert main(["diff", "--install-git"]) == 0

        notebook = tmp_path / "notebook.ipynb"
        _write_pre_45_notebook(notebook, sources=["x = 1"])
        subprocess.run(["git", "add", "notebook.ipynb"], cwd=tmp_path, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "base"], cwd=tmp_path, check=True)
        subprocess.run(["git", "branch", "feature"], cwd=tmp_path, check=True)

        # master: add a second, unrelated cell.
        _write_pre_45_notebook(notebook, sources=["x = 1", "y = 2"])
        subprocess.run(["git", "add", "notebook.ipynb"], cwd=tmp_path, check=True)
        subprocess.run(
            ["git", "commit", "-q", "-m", "master adds a cell"], cwd=tmp_path, check=True
        )

        # feature: modify the first cell instead (non-overlapping with master's change).
        subprocess.run(["git", "checkout", "-q", "feature"], cwd=tmp_path, check=True)
        _write_pre_45_notebook(notebook, sources=["x = 100"])
        subprocess.run(["git", "add", "notebook.ipynb"], cwd=tmp_path, check=True)
        subprocess.run(
            ["git", "commit", "-q", "-m", "feature edits a cell"], cwd=tmp_path, check=True
        )

        subprocess.run(["git", "checkout", "-q", "master"], cwd=tmp_path, check=True)
        merge_result = subprocess.run(
            ["git", "merge", "feature"], cwd=tmp_path, capture_output=True, text=True, check=False
        )
        assert merge_result.returncode == 0, (
            "git merge must not fail on a pre-4.5 (no cell-id) notebook for a "
            f"genuinely divergent, non-conflicting 3-way merge -- got exit "
            f"{merge_result.returncode}, stderr:\n{merge_result.stderr}"
        )
        merged_content = json.loads(notebook.read_text(encoding="utf-8"))
        sources = [cell["source"] for cell in merged_content["cells"]]
        assert "x = 100" in sources
        assert "y = 2" in sources
