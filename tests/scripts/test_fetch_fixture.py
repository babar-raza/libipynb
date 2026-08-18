"""Tests for scripts/fetch_fixture.py -- the real-world fixture vendoring
tool (see tests/fixtures/PROVENANCE.md's "Repeatable sourcing process").

Exercised entirely against a synthetic, temp-directory "fake repo" layout
and a mocked `_fetch` -- never a real network endpoint, per this project's
own network-fetch-authorization discipline: the tool's own test suite must
never become the unauthorized-fetch act the tool itself exists to gate.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import patch

import pytest

SCRIPT_PATH = Path(__file__).resolve().parent.parent.parent / "scripts" / "fetch_fixture.py"


def _load_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("fetch_fixture", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # Register before exec: dataclasses' own postponed-annotation resolution
    # (this file uses `from __future__ import annotations`) looks the module
    # up via sys.modules[cls.__module__] -- without this, that lookup fails.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


PROVENANCE_TEMPLATE = """# Test Fixture Provenance

### Candidate shortlist pending maintainer decision

| # | Candidate notebook | Source repo & pinned commit/tag URL | Declared license (+ LICENSE path at that pin) | Size | Structural pattern exercised | Criteria 1-5 self-check | Decision | Note/date |
|---|---|---|---|---|---|---|---|---|
{shortlist_rows}

### Vendored real-world fixtures

| Filename | Category | Source URL (pinned) | License | Retrieval date | SHA-256 | Size (bytes) | Structural pattern |
|---|---|---|---|---|---|---|---|
*(Empty until the maintainer approves a shortlist candidate and `scripts/fetch_fixture.py --commit` vendors it.)*
"""


@pytest.fixture
def fake_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    module = _load_module()
    fixtures_dir = tmp_path / "tests" / "fixtures"
    for category in module.VALID_CATEGORIES:
        (fixtures_dir / category).mkdir(parents=True)
    provenance_path = fixtures_dir / "PROVENANCE.md"

    def write_provenance(shortlist_rows: str = "") -> None:
        provenance_path.write_text(
            PROVENANCE_TEMPLATE.format(shortlist_rows=shortlist_rows), encoding="utf-8"
        )

    write_provenance()

    monkeypatch.setattr(module, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(module, "FIXTURES_DIR", fixtures_dir)
    monkeypatch.setattr(module, "PROVENANCE_PATH", provenance_path)
    monkeypatch.setattr(module, "STAGING_DIR", tmp_path / "staging")

    return module, fixtures_dir, provenance_path, write_provenance


NOTEBOOK_BYTES_A = json.dumps(
    {"nbformat": 4, "nbformat_minor": 5, "metadata": {}, "cells": []}
).encode()
NOTEBOOK_BYTES_B = json.dumps(
    {
        "nbformat": 4,
        "nbformat_minor": 5,
        "metadata": {},
        "cells": [{"cell_type": "markdown", "id": "x", "metadata": {}, "source": "hi"}],
    }
).encode()

URL = "https://example.com/repo/abc123/notebook.ipynb"
LICENSE_URL = "https://example.com/repo/abc123/LICENSE"


def _args(**overrides: str) -> list[str]:
    base = {
        "--url": URL,
        "--category": "valid",
        "--dest-name": "fetched.ipynb",
        "--license": "MIT",
        "--license-evidence-url": LICENSE_URL,
        "--pattern": "a real-world test fixture",
    }
    base.update(overrides)
    flat: list[str] = []
    for key, value in base.items():
        flat += [key, value]
    return flat


def test_dry_run_fetches_and_previews_without_writing(fake_repo, capsys) -> None:
    module, fixtures_dir, provenance_path, _ = fake_repo
    with patch.object(module, "_fetch", return_value=NOTEBOOK_BYTES_A):
        exit_code = module.main([*_args(), "--dry-run"])
    assert exit_code == 0
    assert not (fixtures_dir / "valid" / "fetched.ipynb").exists()
    assert URL not in provenance_path.read_text(encoding="utf-8")
    out = capsys.readouterr().out
    assert "DRY RUN" in out
    assert hashlib.sha256(NOTEBOOK_BYTES_A).hexdigest() in out


def test_missing_required_arg_is_rejected(fake_repo) -> None:
    module, *_ = fake_repo
    with pytest.raises(SystemExit) as exc_info:
        module.parse_args(["--category", "valid"])
    assert exc_info.value.code == 2


def test_non_https_url_is_refused(fake_repo, capsys) -> None:
    module, *_ = fake_repo
    exit_code = module.main([*_args(**{"--url": "http://example.com/x.ipynb"}), "--dry-run"])
    assert exit_code == 1
    assert "https://" in capsys.readouterr().err


def test_already_existing_dest_name_is_refused(fake_repo, capsys) -> None:
    module, fixtures_dir, *_ = fake_repo
    (fixtures_dir / "valid" / "fetched.ipynb").write_bytes(b"{}")
    exit_code = module.main([*_args(), "--dry-run"])
    assert exit_code == 2
    assert "already exists" in capsys.readouterr().err


def test_oversized_without_justification_is_refused(fake_repo, capsys) -> None:
    module, *_ = fake_repo
    with patch.object(module, "_fetch", return_value=NOTEBOOK_BYTES_A):
        exit_code = module.main([*_args(), "--max-bytes", "1", "--dry-run"])
    assert exit_code == 1
    assert "over --max-bytes" in capsys.readouterr().err


def test_oversized_with_justification_succeeds(fake_repo) -> None:
    module, *_ = fake_repo
    with patch.object(module, "_fetch", return_value=NOTEBOOK_BYTES_A):
        exit_code = module.main(
            [
                *_args(),
                "--max-bytes",
                "1",
                "--allow-oversized-with-justification",
                "test override",
                "--dry-run",
            ]
        )
    assert exit_code == 0


def test_commit_without_prior_dry_run_is_refused(fake_repo, capsys) -> None:
    module, _fixtures_dir, _provenance_path, write_provenance = fake_repo
    write_provenance(f"| 1 | test | {URL} | MIT | 1KB | test | ok | Approve | 2026-08-19 |")
    with patch.object(module, "_fetch", return_value=NOTEBOOK_BYTES_A):
        exit_code = module.main([*_args(), "--commit"])
    assert exit_code == 1
    assert "run --dry-run first" in capsys.readouterr().err


def test_commit_without_approved_row_is_refused(fake_repo, capsys) -> None:
    module, *_ = fake_repo
    with patch.object(module, "_fetch", return_value=NOTEBOOK_BYTES_A):
        module.main([*_args(), "--dry-run"])
        exit_code = module.main([*_args(), "--commit"])
    assert exit_code == 1
    assert "no Approve" in capsys.readouterr().err


def test_commit_with_reject_decision_is_refused(fake_repo, capsys) -> None:
    module, _fixtures_dir, _provenance_path, write_provenance = fake_repo
    write_provenance(f"| 1 | test | {URL} | MIT | 1KB | test | ok | Reject | too niche |")
    with patch.object(module, "_fetch", return_value=NOTEBOOK_BYTES_A):
        module.main([*_args(), "--dry-run"])
        exit_code = module.main([*_args(), "--commit"])
    assert exit_code == 1
    assert "no Approve" in capsys.readouterr().err


def test_commit_with_approved_row_and_unchanged_content_vendors_the_fixture(fake_repo) -> None:
    module, fixtures_dir, provenance_path, write_provenance = fake_repo
    write_provenance(f"| 1 | test | {URL} | MIT | 1KB | test | ok | Approve | 2026-08-19 |")
    with patch.object(module, "_fetch", return_value=NOTEBOOK_BYTES_A):
        assert module.main([*_args(), "--dry-run"]) == 0
        commit_code = module.main([*_args(), "--commit"])
    assert commit_code == 0
    vendored = fixtures_dir / "valid" / "fetched.ipynb"
    assert vendored.read_bytes() == NOTEBOOK_BYTES_A
    provenance_text = provenance_path.read_text(encoding="utf-8")
    assert URL in provenance_text
    assert hashlib.sha256(NOTEBOOK_BYTES_A).hexdigest() in provenance_text
    assert "*(Empty until the maintainer approves" not in provenance_text


def test_commit_refuses_if_content_changed_since_dry_run(fake_repo, capsys) -> None:
    module, _fixtures_dir, _provenance_path, write_provenance = fake_repo
    write_provenance(f"| 1 | test | {URL} | MIT | 1KB | test | ok | Approve | 2026-08-19 |")
    with patch.object(module, "_fetch", return_value=NOTEBOOK_BYTES_A):
        module.main([*_args(), "--dry-run"])
    with patch.object(module, "_fetch", return_value=NOTEBOOK_BYTES_B):
        exit_code = module.main([*_args(), "--commit"])
    assert exit_code == 1
    assert "changed since" in capsys.readouterr().err


def test_approve_with_substitution_names_the_substitute_url(fake_repo) -> None:
    module, fixtures_dir, _provenance_path, write_provenance = fake_repo
    original_url = "https://example.com/repo/abc123/original.ipynb"
    write_provenance(
        f"| 1 | test | {original_url} | MIT | 1KB | test | ok | "
        f"Approve-with-substitution: {URL} | maintainer preferred a different file |"
    )
    with patch.object(module, "_fetch", return_value=NOTEBOOK_BYTES_A):
        module.main([*_args(), "--dry-run"])
        commit_code = module.main([*_args(), "--commit"])
    assert commit_code == 0
    assert (fixtures_dir / "valid" / "fetched.ipynb").exists()


def test_approve_with_substitution_does_not_approve_its_own_original_url(fake_repo, capsys) -> None:
    module, _fixtures_dir, _provenance_path, write_provenance = fake_repo
    original_url = "https://example.com/repo/abc123/original.ipynb"
    write_provenance(
        f"| 1 | test | {original_url} | MIT | 1KB | test | ok | "
        f"Approve-with-substitution: {URL} | maintainer preferred a different file |"
    )
    with patch.object(module, "_fetch", return_value=NOTEBOOK_BYTES_A):
        exit_code = module.main(
            [*_args(**{"--url": original_url, "--dest-name": "other.ipynb"}), "--dry-run"]
        )
        assert exit_code == 0
        exit_code = module.main(
            [*_args(**{"--url": original_url, "--dest-name": "other.ipynb"}), "--commit"]
        )
    assert exit_code == 1
    assert "no Approve" in capsys.readouterr().err
