"""LIBIPYNB-P2: CLI `normalize` nbstripout-parity behavior.

Covers the CLI-layer opinionated default (notebook-level signature/widgets,
cell-level ExecuteTime/collapsed/execution/heading_collapsed/hidden/
scrolled), the --keep-output/--keep-count/--extra-keys/--keep-metadata-keys
flags, [tool.libipynb.normalize] config-file support, stdin ('-') support
for git-filter use, and the --install/--uninstall/--status git integration
(exercised only against scratch git repos created for the test, never the
real repository -- per plans/full-parity-plan.md's own safety requirement).
"""

from __future__ import annotations

import io
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from libipynb.cli.main import main

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
VALID = FIXTURES / "valid"

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git is not on PATH")


def _write_notebook(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "nbformat": 4,
                "nbformat_minor": 5,
                "metadata": {
                    "signature": "sha256:abc",
                    "widgets": {"state": {}},
                    "custom_notebook_key": "keep me",
                },
                "cells": [
                    {
                        "cell_type": "code",
                        "id": "cell-0",
                        "metadata": {
                            "ExecuteTime": {"start_time": "x"},
                            "custom_cell_key": "keep me too",
                        },
                        "execution_count": 4,
                        "outputs": [{"output_type": "stream", "name": "stdout", "text": "hi"}],
                        "source": "print('hi')",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )


class TestDefaultNbstripoutCompatibleStripping:
    def test_default_strips_nbstripout_keys_but_not_custom_keys(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        src = tmp_path / "in.ipynb"
        dest = tmp_path / "out.ipynb"
        _write_notebook(src)
        assert main(["normalize", str(src), "-o", str(dest)]) == 0
        out = json.loads(dest.read_text(encoding="utf-8"))
        assert "signature" not in out["metadata"]
        assert "widgets" not in out["metadata"]
        assert out["metadata"]["custom_notebook_key"] == "keep me"
        cell = out["cells"][0]
        assert "ExecuteTime" not in cell["metadata"]
        assert cell["metadata"]["custom_cell_key"] == "keep me too"
        assert cell["outputs"] == []
        assert cell["execution_count"] is None


class TestKeepFlags:
    def test_keep_output_preserves_outputs(self, tmp_path: Path) -> None:
        src = tmp_path / "in.ipynb"
        dest = tmp_path / "out.ipynb"
        _write_notebook(src)
        assert main(["normalize", str(src), "--keep-output", "-o", str(dest)]) == 0
        out = json.loads(dest.read_text(encoding="utf-8"))
        assert out["cells"][0]["outputs"] != []

    def test_keep_count_preserves_execution_count(self, tmp_path: Path) -> None:
        src = tmp_path / "in.ipynb"
        dest = tmp_path / "out.ipynb"
        _write_notebook(src)
        assert main(["normalize", str(src), "--keep-count", "-o", str(dest)]) == 0
        out = json.loads(dest.read_text(encoding="utf-8"))
        assert out["cells"][0]["execution_count"] == 4

    def test_extra_keys_strips_additional_notebook_and_cell_keys(self, tmp_path: Path) -> None:
        src = tmp_path / "in.ipynb"
        dest = tmp_path / "out.ipynb"
        _write_notebook(src)
        assert (
            main(
                [
                    "normalize",
                    str(src),
                    "--extra-keys",
                    "metadata.custom_notebook_key",
                    "cell.metadata.custom_cell_key",
                    "-o",
                    str(dest),
                ]
            )
            == 0
        )
        out = json.loads(dest.read_text(encoding="utf-8"))
        assert "custom_notebook_key" not in out["metadata"]
        assert "custom_cell_key" not in out["cells"][0]["metadata"]

    def test_keep_metadata_keys_exempts_a_default_key(self, tmp_path: Path) -> None:
        src = tmp_path / "in.ipynb"
        dest = tmp_path / "out.ipynb"
        _write_notebook(src)
        assert (
            main(
                [
                    "normalize",
                    str(src),
                    "--keep-metadata-keys",
                    "metadata.widgets",
                    "-o",
                    str(dest),
                ]
            )
            == 0
        )
        out = json.loads(dest.read_text(encoding="utf-8"))
        assert "widgets" in out["metadata"]
        # unrelated defaults still apply
        assert "signature" not in out["metadata"]


class TestConfigFile:
    def test_pyproject_toml_extra_keys_and_keep_metadata_keys_are_applied(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        src = tmp_path / "in.ipynb"
        dest = tmp_path / "out.ipynb"
        _write_notebook(src)
        (tmp_path / "pyproject.toml").write_text(
            """
[tool.libipynb.normalize]
extra_keys = ["metadata.custom_notebook_key"]
keep_metadata_keys = ["metadata.widgets"]
""",
            encoding="utf-8",
        )
        monkeypatch.chdir(tmp_path)
        assert main(["normalize", str(src), "-o", str(dest)]) == 0
        out = json.loads(dest.read_text(encoding="utf-8"))
        assert "custom_notebook_key" not in out["metadata"]  # config extra_keys
        assert "widgets" in out["metadata"]  # config keep_metadata_keys
        assert "signature" not in out["metadata"]  # untouched default still strips

    def test_config_alone_with_no_cli_flag_still_takes_effect(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        src = tmp_path / "in.ipynb"
        dest = tmp_path / "out.ipynb"
        _write_notebook(src)
        (tmp_path / "pyproject.toml").write_text(
            """
[tool.libipynb.normalize]
keep_output = true
""",
            encoding="utf-8",
        )
        monkeypatch.chdir(tmp_path)
        assert main(["normalize", str(src), "-o", str(dest)]) == 0
        out = json.loads(dest.read_text(encoding="utf-8"))
        assert out["cells"][0]["outputs"] != []

    def test_cli_extra_keys_overrides_a_config_keep_metadata_keys_for_the_same_key(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Gate G2 finding: the first implementation applied every source's
        `keep_metadata_keys` after every source's `extra_keys` as one merged
        pass, so a config `keep_metadata_keys` always won over a CLI
        `--extra-keys` for the same key, regardless of which one actually
        came from the higher-precedence source (CLI). This is the direct
        regression test for that bug: config says keep `signature`, CLI
        explicitly asks to strip it anyway -- CLI must win."""
        src = tmp_path / "in.ipynb"
        dest = tmp_path / "out.ipynb"
        _write_notebook(src)
        (tmp_path / "pyproject.toml").write_text(
            """
[tool.libipynb.normalize]
keep_metadata_keys = ["metadata.signature"]
""",
            encoding="utf-8",
        )
        monkeypatch.chdir(tmp_path)
        assert (
            main(
                [
                    "normalize",
                    str(src),
                    "--extra-keys",
                    "metadata.signature",
                    "-o",
                    str(dest),
                ]
            )
            == 0
        )
        out = json.loads(dest.read_text(encoding="utf-8"))
        assert "signature" not in out["metadata"], (
            "CLI --extra-keys must override a config keep_metadata_keys for the same key"
        )

    def test_cli_keep_metadata_keys_overrides_a_config_extra_keys_for_the_same_key(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The symmetric case: config strips a custom key, CLI explicitly
        asks to keep it -- CLI must win here too."""
        src = tmp_path / "in.ipynb"
        dest = tmp_path / "out.ipynb"
        _write_notebook(src)
        (tmp_path / "pyproject.toml").write_text(
            """
[tool.libipynb.normalize]
extra_keys = ["metadata.custom_notebook_key"]
""",
            encoding="utf-8",
        )
        monkeypatch.chdir(tmp_path)
        assert (
            main(
                [
                    "normalize",
                    str(src),
                    "--keep-metadata-keys",
                    "metadata.custom_notebook_key",
                    "-o",
                    str(dest),
                ]
            )
            == 0
        )
        out = json.loads(dest.read_text(encoding="utf-8"))
        assert out["metadata"]["custom_notebook_key"] == "keep me"


class TestMalformedInputProducesCleanErrors:
    """Gate G2 finding: a bad --extra-keys/--keep-metadata-keys value or a
    malformed [tool.libipynb.normalize] config previously crashed with a raw
    Python traceback instead of the structured JSON-to-stderr error every
    other CLI failure path uses."""

    def test_bad_extra_keys_syntax_from_cli_is_a_clean_error_not_a_traceback(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        src = tmp_path / "in.ipynb"
        _write_notebook(src)
        code = main(["normalize", str(src), "--extra-keys", "not-a-valid-path"])
        assert code == 2
        err = capsys.readouterr().err
        payload = json.loads(err)
        assert "metadata path" in payload["error"]

    def test_non_list_extra_keys_in_config_is_a_clean_error_not_a_crash(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        src = tmp_path / "in.ipynb"
        _write_notebook(src)
        (tmp_path / "pyproject.toml").write_text(
            """
[tool.libipynb.normalize]
extra_keys = "metadata.foo"
""",
            encoding="utf-8",
        )
        monkeypatch.chdir(tmp_path)
        code = main(["normalize", str(src)])
        assert code == 2
        payload = json.loads(capsys.readouterr().err)
        assert "extra_keys" in payload["error"]
        assert "list of strings" in payload["error"]

    def test_non_bool_keep_output_in_config_is_a_clean_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        src = tmp_path / "in.ipynb"
        _write_notebook(src)
        (tmp_path / "pyproject.toml").write_text(
            """
[tool.libipynb.normalize]
keep_output = "yes"
""",
            encoding="utf-8",
        )
        monkeypatch.chdir(tmp_path)
        code = main(["normalize", str(src)])
        assert code == 2
        payload = json.loads(capsys.readouterr().err)
        assert "keep_output" in payload["error"]
        assert "boolean" in payload["error"]


class TestStdinFilterUse:
    def test_dash_reads_from_stdin_and_writes_to_stdout(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        notebook = {
            "nbformat": 4,
            "nbformat_minor": 5,
            "metadata": {"signature": "x"},
            "cells": [],
        }
        monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(notebook)))
        assert main(["normalize", "-"]) == 0
        captured = capsys.readouterr()
        out = json.loads(captured.out)
        assert "signature" not in out["metadata"]


class TestMissingSource:
    def test_missing_source_without_install_flags_is_an_error(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert main(["normalize"]) == 2


def _init_scratch_repo(path: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=path, check=True)


class TestGitFilterIntegration:
    def test_install_status_uninstall_round_trip_repo_local(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _init_scratch_repo(tmp_path)
        monkeypatch.chdir(tmp_path)

        assert main(["normalize", "--status"]) == 1  # not installed yet

        assert main(["normalize", "--install"]) == 0
        attributes = (tmp_path / ".git" / "info" / "attributes").read_text(encoding="utf-8")
        assert "*.ipynb filter=libipynb" in attributes
        clean = subprocess.run(
            ["git", "config", "--get", "filter.libipynb.clean"],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            check=True,
        )
        # Invokes the same interpreter directly (see main.py's
        # _FILTER_PYTHON_SNIPPET docstring) rather than a bare "libipynb"
        # command, so it works regardless of PATH state in whatever shell
        # git spawns the filter through.
        assert "libipynb.cli" in clean.stdout
        assert sys.executable.replace("\\", "/") in clean.stdout.replace("\\", "/")

        assert main(["normalize", "--status"]) == 0

        assert main(["normalize", "--uninstall"]) == 0
        assert main(["normalize", "--status"]) == 1
        clean_after = subprocess.run(
            ["git", "config", "--get", "filter.libipynb.clean"],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            check=False,
        )
        assert clean_after.returncode != 0

    def test_install_with_versioned_attributes_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _init_scratch_repo(tmp_path)
        monkeypatch.chdir(tmp_path)
        assert main(["normalize", "--install", "--attributes", ".gitattributes"]) == 0
        assert "*.ipynb filter=libipynb" in (tmp_path / ".gitattributes").read_text(
            encoding="utf-8"
        )

    def test_install_is_idempotent(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        _init_scratch_repo(tmp_path)
        monkeypatch.chdir(tmp_path)
        assert main(["normalize", "--install"]) == 0
        assert main(["normalize", "--install"]) == 0
        attributes = (tmp_path / ".git" / "info" / "attributes").read_text(encoding="utf-8")
        assert attributes.count("*.ipynb filter=libipynb") == 1

    def test_install_outside_a_git_repo_fails_cleanly(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(tmp_path)  # not a git repo
        assert main(["normalize", "--install"]) == 1

    def test_install_and_uninstall_together_is_a_clean_error_not_silent_install(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _init_scratch_repo(tmp_path)
        monkeypatch.chdir(tmp_path)
        code = main(["normalize", "--install", "--uninstall"])
        assert code == 2
        payload = json.loads(capsys.readouterr().err)
        assert "mutually exclusive" in payload["error"]
        assert main(["normalize", "--status"]) == 1  # confirms nothing was installed

    def test_global_and_attributes_together_is_a_clean_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _init_scratch_repo(tmp_path)
        monkeypatch.chdir(tmp_path)
        code = main(["normalize", "--install", "--global", "--attributes", ".gitattributes"])
        assert code == 2
        payload = json.loads(capsys.readouterr().err)
        assert "mutually exclusive" in payload["error"]

    def test_uninstall_cleans_up_a_versioned_attributes_file_regardless_of_scope_flag(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Gate G2 finding: installing with --attributes .gitattributes (no
        --global) then uninstalling with a mismatched scope must still find
        and clean up the versioned file -- attribute files are location-
        based, not scope-based."""
        _init_scratch_repo(tmp_path)
        monkeypatch.chdir(tmp_path)
        assert main(["normalize", "--install", "--attributes", ".gitattributes"]) == 0
        assert "*.ipynb filter=libipynb" in (tmp_path / ".gitattributes").read_text(
            encoding="utf-8"
        )
        assert main(["normalize", "--uninstall"]) == 0
        remaining = (tmp_path / ".gitattributes").read_text(encoding="utf-8")
        assert "*.ipynb filter=libipynb" not in remaining

    def test_a_failing_filter_aborts_git_add_instead_of_staging_the_raw_notebook(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """LIBIPYNB-P2 Gate G2 finding: `filter.libipynb.required` must be
        `true` (matching nbstripout's own install() exactly), or a filter
        that fails for any reason (stale venv path, moved interpreter,
        ImportError) silently stages the raw, unstripped notebook instead of
        aborting -- defeating the whole feature on its most likely real-world
        failure mode."""
        _init_scratch_repo(tmp_path)
        monkeypatch.chdir(tmp_path)
        assert main(["normalize", "--install"]) == 0

        # Simulate a broken filter (e.g. the recorded interpreter path no
        # longer exists) by pointing the clean command at something that
        # always fails, without touching `required`.
        subprocess.run(
            ["git", "config", "filter.libipynb.clean", "false"],
            cwd=tmp_path,
            check=True,
        )

        notebook_path = tmp_path / "notebook.ipynb"
        _write_notebook(notebook_path)
        add_result = subprocess.run(
            ["git", "add", "notebook.ipynb"],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            check=False,
        )
        assert add_result.returncode != 0, (
            "git add succeeded despite a failing clean filter -- the filter is "
            "failing OPEN (required=false) instead of aborting the add"
        )
        status = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            check=True,
        )
        assert "notebook.ipynb" not in status.stdout or "??" in status.stdout, (
            "notebook.ipynb must not be staged after a failing required filter"
        )

    def test_end_to_end_git_add_actually_strips_outputs(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The real acceptance criterion: a genuine `git add` on a real repo
        with the filter installed must invoke libipynb, not pass the file
        through untouched."""
        _init_scratch_repo(tmp_path)
        monkeypatch.chdir(tmp_path)
        assert main(["normalize", "--install"]) == 0

        notebook_path = tmp_path / "notebook.ipynb"
        _write_notebook(notebook_path)

        subprocess.run(["git", "add", "notebook.ipynb"], cwd=tmp_path, check=True)
        show = subprocess.run(
            ["git", "show", ":notebook.ipynb"],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            check=True,
        )
        staged = json.loads(show.stdout)
        assert "signature" not in staged["metadata"], (
            "git add did not invoke the libipynb clean filter -- staged blob "
            "still has the raw, unstripped notebook"
        )
        # The working-tree file itself must be untouched (clean filters only
        # affect what's staged/committed, never the file on disk).
        working_tree = json.loads(notebook_path.read_text(encoding="utf-8"))
        assert "signature" in working_tree["metadata"]
