"""Tests for the CLI entry point (all 12 subcommands)."""

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

    def test_notebook_metadata_conflict_is_reported_in_cli_json(
        self, capsys: pytest.CaptureFixture[str], tmp_path: Path
    ) -> None:
        """LIBIPYNB-Q10: the new NOTEBOOK_METADATA conflict kind serializes
        correctly (including cell_id: null) and flips the CLI's exit code,
        with zero cli/main.py code changes needed -- _cmd_merge already
        iterates result.report.conflicts generically."""
        base = tmp_path / "base.ipynb"
        ours = tmp_path / "ours.ipynb"
        theirs = tmp_path / "theirs.ipynb"
        base_notebook = {
            "nbformat": 4,
            "nbformat_minor": 5,
            "metadata": {"kernelspec": {"name": "python3"}},
            "cells": [
                {
                    "cell_type": "code",
                    "id": "c",
                    "metadata": {},
                    "execution_count": None,
                    "outputs": [],
                    "source": "x = 1",
                }
            ],
        }
        base.write_text(json.dumps(base_notebook), encoding="utf-8")
        ours_notebook = json.loads(json.dumps(base_notebook))
        ours_notebook["metadata"]["kernelspec"]["name"] = "ours-kernel"
        ours.write_text(json.dumps(ours_notebook), encoding="utf-8")
        theirs_notebook = json.loads(json.dumps(base_notebook))
        theirs_notebook["metadata"]["kernelspec"]["name"] = "theirs-kernel"
        theirs.write_text(json.dumps(theirs_notebook), encoding="utf-8")

        assert main(["merge", str(base), str(ours), str(theirs)]) == 1
        ledger = json.loads(capsys.readouterr().err)
        assert ledger["has_conflicts"] is True
        kinds = {c["kind"] for c in ledger["conflicts"]}
        assert "notebook_metadata" in kinds
        nb_conflict = next(c for c in ledger["conflicts"] if c["kind"] == "notebook_metadata")
        assert nb_conflict["cell_id"] is None
        assert nb_conflict["field_name"] == "metadata.kernelspec.name"


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


def _kernel_available() -> bool:
    try:
        from jupyter_client.kernelspec import find_kernel_specs
    except ImportError:
        return False
    return "python3" in find_kernel_specs()


@pytest.mark.skipif(
    not _kernel_available(), reason="libipynb[exec] and an installed python3 kernel are required"
)
class TestExecute:
    """LIBIPYNB-P4c: the `libipynb execute` subcommand. Real-kernel, like
    tests/integration/test_obligation_jupyter_execution_adapter.py -- skips
    cleanly (not falsely) when the `exec` extra/a kernel isn't installed."""

    def test_execute_refuses_without_acknowledgment(
        self, capsys: pytest.CaptureFixture[str], tmp_path: Path
    ) -> None:
        notebook = tmp_path / "nb.ipynb"
        _write_notebook(notebook, sources=["1 + 1"])

        assert main(["execute", str(notebook)]) == 2
        err = json.loads(capsys.readouterr().err)
        assert "sandbox" in err["error"]

    def test_execute_to_output_file(
        self, capsys: pytest.CaptureFixture[str], tmp_path: Path
    ) -> None:
        notebook = tmp_path / "nb.ipynb"
        dest = tmp_path / "executed.ipynb"
        _write_notebook(notebook, sources=["print('hi')"])

        assert main(["execute", str(notebook), "-o", str(dest), "--acknowledge-unsandboxed"]) == 0
        ledger = json.loads(capsys.readouterr().out)
        assert ledger["succeeded"] is True
        assert ledger["executed_count"] == 1
        assert ledger["output"] == str(dest)

        executed = json.loads(dest.read_text(encoding="utf-8"))
        assert executed["cells"][0]["outputs"][0]["text"] == "hi\n"
        # Source notebook itself is never mutated by the CLI command.
        original = json.loads(notebook.read_text(encoding="utf-8"))
        assert original["cells"][0]["outputs"] == []

    def test_execute_max_output_bytes_surfaces_truncation_in_the_ledger(
        self, capsys: pytest.CaptureFixture[str], tmp_path: Path
    ) -> None:
        """LIBIPYNB-Q17 Gate G2 finding: output_truncated/omitted_mime_types
        were silently absent from the CLI ledger -- a user could lose an
        oversized image with zero visible signal. --max-output-bytes itself
        didn't exist as a CLI flag before this fix, so this is also the
        first test proving the flag is wired through end-to-end, not just
        that the ledger fields exist in isolation."""
        notebook = tmp_path / "nb.ipynb"
        dest = tmp_path / "executed.ipynb"
        _write_notebook(notebook, sources=["print('x' * 2000)"])

        assert (
            main(
                [
                    "execute",
                    str(notebook),
                    "-o",
                    str(dest),
                    "--acknowledge-unsandboxed",
                    "--max-output-bytes",
                    "100",
                ]
            )
            == 0
        )
        ledger = json.loads(capsys.readouterr().out)
        assert ledger["output_truncated"] is True
        assert ledger["cells_with_truncated_output"] == [0]
        assert ledger["cells_with_omitted_mime_types"] == {}

        executed = json.loads(dest.read_text(encoding="utf-8"))
        assert len(executed["cells"][0]["outputs"][0]["text"].encode("utf-8")) <= 100

    def test_execute_without_max_output_bytes_never_truncates(
        self, capsys: pytest.CaptureFixture[str], tmp_path: Path
    ) -> None:
        notebook = tmp_path / "nb.ipynb"
        dest = tmp_path / "executed.ipynb"
        _write_notebook(notebook, sources=["print('short')"])

        assert main(["execute", str(notebook), "-o", str(dest), "--acknowledge-unsandboxed"]) == 0
        ledger = json.loads(capsys.readouterr().out)
        assert ledger["output_truncated"] is False
        assert ledger["cells_with_truncated_output"] == []
        assert ledger["cells_with_omitted_mime_types"] == {}

    def test_execute_succeeds_on_list_of_lines_source(
        self, capsys: pytest.CaptureFixture[str], tmp_path: Path
    ) -> None:
        """LIBIPYNB-Q1 regression at the CLI layer: list-of-lines source is
        the standard on-disk Jupyter form (confirmed present in a large
        fraction of this project's own fixtures), yet `libipynb execute`
        used to crash the kernel with AttributeError on any such cell,
        reported as an opaque kernel_death_error. _write_notebook writes
        each `sources` element verbatim, so passing a list here writes a
        genuine JSON array source field, not a string."""
        notebook = tmp_path / "nb.ipynb"
        dest = tmp_path / "executed.ipynb"
        _write_notebook(notebook, sources=[["print(1)\n", "print(2)"]])  # type: ignore[list-item]

        assert main(["execute", str(notebook), "-o", str(dest), "--acknowledge-unsandboxed"]) == 0
        ledger = json.loads(capsys.readouterr().out)
        assert ledger["succeeded"] is True
        assert ledger["executed_count"] == 1

        executed = json.loads(dest.read_text(encoding="utf-8"))
        assert executed["cells"][0]["outputs"][0]["text"] == "1\n2\n"
        # Source form itself is untouched by the fix -- still a list.
        assert executed["cells"][0]["source"] == ["print(1)\n", "print(2)"]

    def test_execute_to_stdout(self, capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
        notebook = tmp_path / "nb.ipynb"
        _write_notebook(notebook, sources=["21 * 2"])

        assert main(["execute", str(notebook), "--acknowledge-unsandboxed"]) == 0
        captured = capsys.readouterr()
        ledger = json.loads(captured.err)
        assert ledger["succeeded"] is True
        assert '"text/plain": "42"' in captured.out

    def test_execute_refuses_to_overwrite_the_source_without_force(
        self, capsys: pytest.CaptureFixture[str], tmp_path: Path
    ) -> None:
        notebook = tmp_path / "nb.ipynb"
        _write_notebook(notebook, sources=["1 + 1"])

        assert (
            main(["execute", str(notebook), "-o", str(notebook), "--acknowledge-unsandboxed"]) == 2
        )
        err = json.loads(capsys.readouterr().err)
        assert "refusing to overwrite" in err["error"]

        # --force explicitly allows it.
        assert (
            main(
                [
                    "execute",
                    str(notebook),
                    "-o",
                    str(notebook),
                    "--acknowledge-unsandboxed",
                    "--force",
                ]
            )
            == 0
        )
        executed = json.loads(notebook.read_text(encoding="utf-8"))
        assert executed["cells"][0]["outputs"][0]["data"]["text/plain"] == "2"

    def test_execute_reports_a_cell_error_with_exit_code_1(
        self, capsys: pytest.CaptureFixture[str], tmp_path: Path
    ) -> None:
        notebook = tmp_path / "nb.ipynb"
        _write_notebook(notebook, sources=["raise ValueError('boom')"])

        assert main(["execute", str(notebook), "--acknowledge-unsandboxed"]) == 1
        ledger = json.loads(capsys.readouterr().err)
        assert ledger["succeeded"] is False
        assert ledger["first_error"]["ename"] == "ValueError"

    def test_execute_on_error_continue(
        self, capsys: pytest.CaptureFixture[str], tmp_path: Path
    ) -> None:
        notebook = tmp_path / "nb.ipynb"
        _write_notebook(notebook, sources=["raise ValueError('boom')", "print('still runs')"])

        assert (
            main(["execute", str(notebook), "--acknowledge-unsandboxed", "--on-error", "continue"])
            == 1
        )
        ledger = json.loads(capsys.readouterr().err)
        assert ledger["stopped_early"] is False
        assert ledger["executed_count"] == 2

    def test_execute_missing_kernel_reports_a_clean_error_not_a_traceback(
        self, capsys: pytest.CaptureFixture[str], tmp_path: Path
    ) -> None:
        notebook = tmp_path / "nb.ipynb"
        _write_notebook(notebook, sources=["pass"])

        assert (
            main(
                [
                    "execute",
                    str(notebook),
                    "--acknowledge-unsandboxed",
                    "--kernel",
                    "__nonexistent_kernel__",
                    "--kernel-startup-timeout",
                    "5",
                ]
            )
            == 1
        )
        ledger = json.loads(capsys.readouterr().err)
        assert ledger["kernel_launch_error"] is not None

    def test_execute_missing_exec_extra_is_reported_structurally(
        self, capsys: pytest.CaptureFixture[str], tmp_path: Path
    ) -> None:
        import sys
        from unittest.mock import patch

        notebook = tmp_path / "nb.ipynb"
        _write_notebook(notebook, sources=["1 + 1"])

        with patch.dict(sys.modules, {"nbclient": None, "jupyter_client": None}):
            for name in ("libipynb.execution", "libipynb.adapters.jupyter_execute"):
                sys.modules.pop(name, None)
            try:
                assert main(["execute", str(notebook), "--acknowledge-unsandboxed"]) == 2
                err = json.loads(capsys.readouterr().err)
                assert "exec" in err["error"]
            finally:
                for name in ("libipynb.execution", "libipynb.adapters.jupyter_execute"):
                    sys.modules.pop(name, None)


class TestTopLevelExceptionHandling:
    """LIBIPYNB-Q4: every plain-CLI subcommand's ordinary bad-input path
    (missing file, malformed --target, etc.) must report a clean
    {"error": ...} JSON on stderr with exit code 2 -- not a raw, multi-frame
    Python traceback. Closes publication blocker #3 from the forensic
    audit."""

    @pytest.mark.parametrize(
        "argv",
        [
            ["inspect", "does-not-exist.ipynb"],
            ["sanitize", "does-not-exist.ipynb"],
            ["upgrade", "does-not-exist.ipynb"],
            ["normalize", "does-not-exist.ipynb"],
            ["convert", "does-not-exist.ipynb", "--target", "4.5"],
            ["analytics", "does-not-exist.ipynb"],
        ],
    )
    def test_missing_file_reports_clean_json_error_not_a_traceback(
        self, argv: list[str], capsys: pytest.CaptureFixture[str]
    ) -> None:
        code = main(argv)
        assert code == 2
        err = json.loads(capsys.readouterr().err)
        assert "error" in err

    def test_validate_on_missing_file_already_reported_a_structured_diagnostic(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Not a Q4 regression case: validate() never raises for a missing/
        unreadable source -- it returns a structured IPYNB_PARSE diagnostic
        as part of its normal report (exit 1 = "invalid"), which was
        already correct before this fix. Documented here so a future
        change to validate()'s contract doesn't silently start crashing
        this path without a test catching it."""
        code = main(["validate", "does-not-exist.ipynb"])
        assert code == 1
        out = json.loads(capsys.readouterr().out)
        assert out["diagnostics"][0]["code"] == "IPYNB_PARSE"

    def test_diff_on_missing_file_reports_clean_json_error(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        code = main(["diff", "does-not-exist.ipynb", str(VALID / "minimal.ipynb")])
        assert code == 2
        err = json.loads(capsys.readouterr().err)
        assert "error" in err

    def test_merge_on_missing_file_reports_clean_json_error(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        code = main(
            [
                "merge",
                "does-not-exist.ipynb",
                str(VALID / "minimal.ipynb"),
                str(VALID / "minimal.ipynb"),
            ]
        )
        assert code == 2
        err = json.loads(capsys.readouterr().err)
        assert "error" in err

    def test_convert_malformed_target_reports_clean_json_error(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        code = main(["convert", str(VALID / "minimal.ipynb"), "--target", "not-a-version"])
        assert code == 2
        err = json.loads(capsys.readouterr().err)
        assert "error" in err

    def test_convert_downgrade_without_accept_loss_reports_clean_json_error(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        notebook = tmp_path / "nb.ipynb"
        _write_notebook(notebook, sources=["1 + 1"])
        # Upgrade to 4.5 first so a downgrade to 4.4 has real losses (cell ids).
        assert main(["upgrade", str(notebook), "-o", str(notebook)]) == 0

        code = main(["convert", str(notebook), "--target", "4.4"])
        assert code == 2
        err = json.loads(capsys.readouterr().err)
        assert "error" in err


class TestModuleInvocation:
    def test_python_dash_m_libipynb_cli_probe_works(self) -> None:
        import subprocess
        import sys

        result = subprocess.run(
            [sys.executable, "-m", "libipynb.cli", "probe", str(VALID / "minimal.ipynb")],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr
        assert json.loads(result.stdout)["matched"] is True
