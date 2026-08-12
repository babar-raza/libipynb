"""Tests for the CLI entry point (all 8 subcommands)."""

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

    def test_write_to_output(
        self, capsys: pytest.CaptureFixture[str], tmp_path: Path
    ) -> None:
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

    def test_upgrade(
        self, capsys: pytest.CaptureFixture[str], tmp_path: Path
    ) -> None:
        dest = tmp_path / "upgraded.ipynb"
        assert (
            main([
                "convert",
                str(VALID / "nbformat-4-0.ipynb"),
                "--target",
                "4.5",
                "-o",
                str(dest),
            ])
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
            main([
                "convert",
                str(VALID / "minimal.ipynb"),
                "--target",
                "4.0",
                "--accept-loss",
                "-o",
                str(dest),
            ])
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
