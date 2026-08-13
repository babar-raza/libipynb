"""Tests for the CLI entry point (all 11 subcommands)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from libipynb.cli.main import main

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
VALID = FIXTURES / "valid"
INVALID = FIXTURES / "invalid"


class TestProbe:
    def test_valid_notebook(self, capsys: pytest.CaptureFixture[str]) -> None:
        assert main(["probe", str(VALID / "minimal.ipynb")]) == 0
        out = json.loads(capsys.readouterr().out)
        assert out["matched"] is True

    def test_invalid_source(self, capsys: pytest.CaptureFixture[str]) -> None:
        assert main(["probe", str(INVALID / "not-json.ipynb")]) == 1


class TestValidate:
    def test_valid_notebook(self, capsys: pytest.CaptureFixture[str]) -> None:
        assert main(["validate", str(VALID / "minimal.ipynb")]) == 0
        out = json.loads(capsys.readouterr().out)
        assert out["valid"] is True


class TestInspect:
    def test_inspect_minimal(self, capsys: pytest.CaptureFixture[str]) -> None:
        assert main(["inspect", str(VALID / "minimal.ipynb")]) == 0
        out = json.loads(capsys.readouterr().out)
        assert out["nbformat"] == 4


class TestSanitize:
    def test_sanitize_dry_run(self, capsys: pytest.CaptureFixture[str]) -> None:
        assert main(["sanitize", str(VALID / "minimal.ipynb")]) == 0
        out = json.loads(capsys.readouterr().out)
        assert "finding_count" in out


class TestNormalize:
    def test_dry_run(self, capsys: pytest.CaptureFixture[str]) -> None:
        assert main(["normalize", str(VALID / "minimal.ipynb"), "--dry-run"]) == 0
        out = json.loads(capsys.readouterr().out)
        assert "change_count" in out

    def test_write_to_output(self, capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
        dest = tmp_path / "normalized.ipynb"
        assert main(["normalize", str(VALID / "minimal.ipynb"), "-o", str(dest)]) == 0
        assert dest.exists()
        out = json.loads(capsys.readouterr().out)
        assert out["change_count"] >= 0

    def test_stdout_output(self, capsys: pytest.CaptureFixture[str]) -> None:
        assert main(["normalize", str(VALID / "minimal.ipynb")]) == 0
        captured = capsys.readouterr()
        assert '"nbformat": 4' in captured.out


class TestConvert:
    def test_identity_conversion(self, capsys: pytest.CaptureFixture[str]) -> None:
        assert main(["convert", str(VALID / "minimal.ipynb"), "--target", "4.5"]) == 0
        out = json.loads(capsys.readouterr().out)
        assert out["direction"] == "none"

    def test_upgrade(self, capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
        dest = tmp_path / "upgraded.ipynb"
        assert (
            main(
                [
                    "convert",
                    str(VALID / "nbformat-4-0.ipynb"),
                    "--target",
                    "4.5",
                    "-o",
                    str(dest),
                ]
            )
            == 0
        )
        out = json.loads(capsys.readouterr().out)
        assert out["direction"] == "upgrade"
        assert dest.exists()

    def test_downgrade_with_accept_loss(
        self, capsys: pytest.CaptureFixture[str], tmp_path: Path
    ) -> None:
        dest = tmp_path / "downgraded.ipynb"
        assert (
            main(
                [
                    "convert",
                    str(VALID / "minimal.ipynb"),
                    "--target",
                    "4.0",
                    "--accept-loss",
                    "-o",
                    str(dest),
                ]
            )
            == 0
        )
        out = json.loads(capsys.readouterr().out)
        assert out["direction"] == "downgrade"
        assert dest.exists()


class TestUpgrade:
    def test_upgrade_to_stdout(self, capsys: pytest.CaptureFixture[str]) -> None:
        assert main(["upgrade", str(VALID / "nbformat-4-0.ipynb")]) == 0


class TestDiff:
    def test_identical_notebooks(self, capsys: pytest.CaptureFixture[str]) -> None:
        path = str(VALID / "minimal.ipynb")
        assert main(["diff", path, path]) == 0


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


class TestMerge:
    def test_no_conflict_merge(self, capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
        base = tmp_path / "base.ipynb"
        ours = tmp_path / "ours.ipynb"
        theirs = tmp_path / "theirs.ipynb"
        _write_notebook(base, sources=["x = 1"])
        _write_notebook(ours, sources=["x = 2"])
        _write_notebook(theirs, sources=["x = 1"])
        assert main(["merge", str(base), str(ours), str(theirs)]) == 0
        captured = capsys.readouterr()
        ledger = json.loads(captured.err)
        assert ledger["has_conflicts"] is False
        assert ledger["conflict_count"] == 0
        assert '"nbformat": 4' in captured.out

    def test_conflicting_merge_exits_1_and_still_writes_merged_document(
        self, capsys: pytest.CaptureFixture[str], tmp_path: Path
    ) -> None:
        base = tmp_path / "base.ipynb"
        ours = tmp_path / "ours.ipynb"
        theirs = tmp_path / "theirs.ipynb"
        _write_notebook(base, sources=["x = 1"])
        _write_notebook(ours, sources=["x = 2"])
        _write_notebook(theirs, sources=["x = 3"])
        assert main(["merge", str(base), str(ours), str(theirs)]) == 1
        captured = capsys.readouterr()
        ledger = json.loads(captured.err)
        assert ledger["has_conflicts"] is True
        assert ledger["conflict_count"] == 1
        assert ledger["conflicts"][0]["kind"] == "edit_edit"
        # base's value survives a conflict -- the merged document (still
        # written even when conflicts exist) must contain "x = 1", not
        # either side's conflicting value.
        assert '"x = 1"' in captured.out

    def test_output_to_file(self, capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
        base = tmp_path / "base.ipynb"
        ours = tmp_path / "ours.ipynb"
        theirs = tmp_path / "theirs.ipynb"
        dest = tmp_path / "merged.ipynb"
        _write_notebook(base, sources=["x = 1"])
        _write_notebook(ours, sources=["x = 2"])
        _write_notebook(theirs, sources=["x = 1"])
        assert main(["merge", str(base), str(ours), str(theirs), "-o", str(dest)]) == 0
        assert dest.exists()
        out = json.loads(capsys.readouterr().out)
        assert out["output"] == str(dest)
        assert out["has_conflicts"] is False


class TestAnalytics:
    def test_reports_all_four_metrics(self, capsys: pytest.CaptureFixture[str]) -> None:
        assert main(["analytics", str(VALID / "minimal.ipynb")]) == 0
        out = json.loads(capsys.readouterr().out)
        assert "cell_type_histogram" in out
        assert "output_type_histogram" in out
        assert "has_execution_errors" in out
        assert "average_source_length" in out


class TestTrust:
    _SECRET_ENV = "LIBIPYNB_TEST_TRUST_SECRET"

    def _set_secret(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(self._SECRET_ENV, "x" * 32)

    def test_sign_then_verify_round_trips(
        self, capsys: pytest.CaptureFixture[str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._set_secret(monkeypatch)
        notebook = tmp_path / "nb.ipynb"
        _write_notebook(notebook, sources=["x = 1"])
        store = tmp_path / "trust.db"

        assert (
            main(
                [
                    "trust",
                    str(notebook),
                    "--sign",
                    "--store",
                    str(store),
                    "--secret-env",
                    self._SECRET_ENV,
                ]
            )
            == 0
        )
        signed = json.loads(capsys.readouterr().out)
        assert signed["action"] == "sign"
        assert signed["trusted"] is True

        assert (
            main(
                [
                    "trust",
                    str(notebook),
                    "--verify",
                    "--store",
                    str(store),
                    "--secret-env",
                    self._SECRET_ENV,
                ]
            )
            == 0
        )
        verified = json.loads(capsys.readouterr().out)
        assert verified["action"] == "verify"
        assert verified["trusted"] is True
        assert verified["digest"] == signed["digest"]

    def test_verify_survives_a_separate_cli_invocation(
        self, capsys: pytest.CaptureFixture[str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Each `main()` call constructs its own fresh SqliteSignatureStore --
        # this is the actual point of LIBIPYNB-V2/V6 together: trust set by
        # one CLI invocation must be visible to a completely separate one,
        # not just within one process's lifetime.
        self._set_secret(monkeypatch)
        notebook = tmp_path / "nb.ipynb"
        _write_notebook(notebook, sources=["x = 1"])
        store = tmp_path / "trust.db"
        common_args = [str(notebook), "--store", str(store), "--secret-env", self._SECRET_ENV]

        assert main(["trust", *common_args, "--sign"]) == 0
        capsys.readouterr()

        assert main(["trust", *common_args, "--verify"]) == 0
        assert json.loads(capsys.readouterr().out)["trusted"] is True

    def test_verify_unsigned_content_is_untrusted_and_exits_1(
        self, capsys: pytest.CaptureFixture[str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._set_secret(monkeypatch)
        notebook = tmp_path / "nb.ipynb"
        _write_notebook(notebook, sources=["x = 1"])
        store = tmp_path / "trust.db"

        assert (
            main(
                [
                    "trust",
                    str(notebook),
                    "--verify",
                    "--store",
                    str(store),
                    "--secret-env",
                    self._SECRET_ENV,
                ]
            )
            == 1
        )
        out = json.loads(capsys.readouterr().out)
        assert out["trusted"] is False
        assert out["reason"] == "signature_not_found"

    def test_revoke_removes_trust(
        self, capsys: pytest.CaptureFixture[str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._set_secret(monkeypatch)
        notebook = tmp_path / "nb.ipynb"
        _write_notebook(notebook, sources=["x = 1"])
        store = tmp_path / "trust.db"
        common_args = [str(notebook), "--store", str(store), "--secret-env", self._SECRET_ENV]

        assert main(["trust", *common_args, "--sign"]) == 0
        capsys.readouterr()

        assert main(["trust", *common_args, "--revoke"]) == 0
        revoked = json.loads(capsys.readouterr().out)
        assert revoked["action"] == "revoke"
        assert revoked["revoked"] is True

        assert main(["trust", *common_args, "--verify"]) == 1
        assert json.loads(capsys.readouterr().out)["trusted"] is False

    def test_missing_secret_env_var_fails_with_a_clear_error(
        self, capsys: pytest.CaptureFixture[str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv(self._SECRET_ENV, raising=False)
        notebook = tmp_path / "nb.ipynb"
        _write_notebook(notebook, sources=["x = 1"])
        store = tmp_path / "trust.db"

        assert (
            main(
                [
                    "trust",
                    str(notebook),
                    "--sign",
                    "--store",
                    str(store),
                    "--secret-env",
                    self._SECRET_ENV,
                ]
            )
            == 2
        )
        err = json.loads(capsys.readouterr().err)
        assert self._SECRET_ENV in err["error"]

    def test_too_short_secret_fails_cleanly_not_a_raw_traceback(
        self, capsys: pytest.CaptureFixture[str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Regression test for a Gate G2 finding: HmacNotebookNotary rejects
        # secrets under 32 bytes with a ValueError, which previously
        # propagated as a raw, uncaught traceback instead of the same clean
        # JSON-error/exit-2 convention used for a missing --secret-env var.
        monkeypatch.setenv(self._SECRET_ENV, "too-short")
        notebook = tmp_path / "nb.ipynb"
        _write_notebook(notebook, sources=["x = 1"])
        store = tmp_path / "trust.db"

        assert (
            main(
                [
                    "trust",
                    str(notebook),
                    "--sign",
                    "--store",
                    str(store),
                    "--secret-env",
                    self._SECRET_ENV,
                ]
            )
            == 2
        )
        err = json.loads(capsys.readouterr().err)
        assert "32 bytes" in err["error"]
