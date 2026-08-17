"""LIBIPYNB-V1: pattern-based secret/PII scanning hooks.

Report-only, never mutates, never claims completeness. See
security/secrets.py's module docstring for the stated scope.
"""

from __future__ import annotations

from copy import deepcopy

import pytest

from libipynb import NotebookDocument
from libipynb.security.secrets import (
    DEFAULT_SECRET_RULES,
    SecretRule,
    SecretScope,
    scan_for_secrets,
)


def _document(cells: list[dict], metadata: dict | None = None) -> NotebookDocument:
    return NotebookDocument(
        {
            "nbformat": 4,
            "nbformat_minor": 5,
            "metadata": metadata or {},
            "cells": cells,
        }
    )


def _code_cell(source: str, cell_id: str = "c", outputs: list[dict] | None = None) -> dict:
    return {
        "cell_type": "code",
        "id": cell_id,
        "metadata": {},
        "execution_count": None,
        "outputs": outputs or [],
        "source": source,
    }


# ── Detection across every scanned scope ────────────────────────────────────


def test_aws_access_key_detected_in_source() -> None:
    document = _document([_code_cell("key = 'AKIAABCDEFGHIJKLMNOP'")])

    report = scan_for_secrets(document)

    assert report.count == 1
    finding = report.findings[0]
    assert finding.rule_id == "aws_access_key_id"
    assert finding.scope == SecretScope.SOURCE
    assert finding.path == ("cells", 0, "source")


def test_github_token_detected_in_stream_output_text() -> None:
    document = _document(
        [
            _code_cell(
                "print(token)",
                outputs=[
                    {
                        "output_type": "stream",
                        "name": "stdout",
                        "text": "token=ghp_" + "a" * 36 + "\n",
                    }
                ],
            )
        ]
    )

    report = scan_for_secrets(document)

    assert any(
        f.rule_id == "github_token" and f.scope == SecretScope.OUTPUT_TEXT for f in report.findings
    )


def test_private_key_block_detected_in_display_data_text_plain() -> None:
    document = _document(
        [
            _code_cell(
                "print(key)",
                outputs=[
                    {
                        "output_type": "display_data",
                        "data": {"text/plain": "-----BEGIN RSA PRIVATE KEY-----\nMIIB...\n"},
                        "metadata": {},
                    }
                ],
            )
        ]
    )

    report = scan_for_secrets(document)

    assert any(f.rule_id == "private_key_block" for f in report.findings)


def test_traceback_lines_are_scanned() -> None:
    document = _document(
        [
            _code_cell(
                "raise ValueError(token)",
                outputs=[
                    {
                        "output_type": "error",
                        "ename": "ValueError",
                        "evalue": "bad token",
                        "traceback": [
                            "Traceback (most recent call last):",
                            "  File x, line 1",
                            "ValueError: token=xoxb-111111111111-222222222222-abcdefghijklmnopqrstuvwx",
                        ],
                    }
                ],
            )
        ]
    )

    report = scan_for_secrets(document)

    assert any(
        f.rule_id == "slack_token" and f.scope == SecretScope.TRACEBACK for f in report.findings
    )


def test_credential_shaped_key_detected_in_metadata() -> None:
    """Metadata is structured key/value data: a value stored under a key
    like "password" is a strong signal by itself, independent of whether
    the value's content matches a regex shape (unlike source/output text,
    where "password = ..." is one string and the key is part of it)."""
    document = _document(
        [_code_cell("pass")], metadata={"papermill": {"password": "hunter2hunter2"}}
    )

    report = scan_for_secrets(document)

    assert any(
        f.rule_id == "sensitive_metadata_key" and f.scope == SecretScope.METADATA
        for f in report.findings
    )


def test_cell_metadata_is_scanned() -> None:
    document = _document(
        [
            {
                "cell_type": "code",
                "id": "c",
                "metadata": {"papermill": {"api_key": "sk-1234567890abcd"}},
                "execution_count": None,
                "outputs": [],
                "source": "pass",
            }
        ]
    )

    report = scan_for_secrets(document)

    assert any(f.path[:2] == ("cells", 0) and "metadata" in f.path for f in report.findings)


def test_url_with_embedded_credentials_detected() -> None:
    document = _document([_code_cell("url = 'https://admin:sup3rSecret@db.example.com/'")])

    report = scan_for_secrets(document)

    assert any(f.rule_id == "url_embedded_credentials" for f in report.findings)


# ── Non-goals: cleanliness is not a completeness guarantee ─────────────────


def test_clean_notebook_produces_no_findings() -> None:
    document = _document([_code_cell("print('hello world')")])

    report = scan_for_secrets(document)

    assert report.is_clean is True
    assert report.count == 0


def test_scan_never_mutates_the_document() -> None:
    document = _document([_code_cell("key = 'AKIAABCDEFGHIJKLMNOP'")])
    before = deepcopy(document.raw)

    scan_for_secrets(document)

    assert document.raw == before


# ── Redaction: the report must never carry the full secret ─────────────────


def test_finding_preview_never_contains_the_full_matched_secret() -> None:
    secret = "AKIAABCDEFGHIJKLMNOP"
    document = _document([_code_cell(f"key = '{secret}'")])

    report = scan_for_secrets(document)

    assert report.count == 1
    assert secret not in report.findings[0].preview


def test_short_matches_reveal_no_characters_or_exact_length() -> None:
    """Regression for a real leak an independent review found: an earlier
    version showed a fixed number of leading/trailing characters, which
    for any match under ~17 characters revealed most or all of it (a
    9-character url_embedded_credentials match showed 8 of 9 real
    characters). The preview must now carry zero characters of the match
    and not even its exact length (only a coarse bucket)."""
    rule = SecretRule("short_test_rule", __import__("re").compile(r"SHORT1"), "test")
    document = _document([_code_cell("x = 'SHORT1'")])

    report = scan_for_secrets(document, rules=(rule,))

    assert report.findings[0].preview == "<redacted:short>"
    assert "SHORT1" not in report.findings[0].preview
    assert "6" not in report.findings[0].preview  # exact length must not leak either


def test_nine_character_url_credential_match_does_not_leak_most_of_itself() -> None:
    """The exact scenario an independent review used to demonstrate the
    original redaction bug: 'ab://c:d@' (9 chars) previously showed 8 of
    its 9 real characters via "first 4 ... last 4"."""
    document = _document([_code_cell("u = 'ab://c:d@'")])

    report = scan_for_secrets(document)

    (finding,) = [f for f in report.findings if f.rule_id == "url_embedded_credentials"]
    # The full marker is the only thing the preview may equal -- checking
    # single letters from the 9-char match against it is meaningless,
    # since the word "redacted" itself contains common letters.
    assert finding.preview == "<redacted:short>"


def test_generic_credential_short_password_does_not_leak_via_preview() -> None:
    document = _document([_code_cell('pwd = "12345678"')])

    report = scan_for_secrets(document)

    (finding,) = [f for f in report.findings if f.rule_id == "generic_credential_assignment"]
    assert "12345678" not in finding.preview
    assert "678" not in finding.preview
    assert "1234" not in finding.preview


# ── Configurability ──────────────────────────────────────────────────────────


def test_extra_rules_extend_the_default_ruleset() -> None:
    import re

    custom = SecretRule("internal_widget_token", re.compile(r"WIDGET-[0-9]{6}"), "internal token")
    document = _document([_code_cell("t = 'WIDGET-123456'")])

    without = scan_for_secrets(document)
    with_extra = scan_for_secrets(document, extra_rules=(custom,))

    assert without.count == 0
    assert with_extra.count == 1
    assert with_extra.findings[0].rule_id == "internal_widget_token"


def test_custom_rules_replace_the_default_ruleset_when_provided() -> None:
    document = _document([_code_cell("key = 'AKIAABCDEFGHIJKLMNOP'")])

    report = scan_for_secrets(document, rules=())

    assert report.count == 0


def test_scan_metadata_false_skips_metadata_scanning() -> None:
    document = _document([_code_cell("pass")], metadata={"password": "hunter2hunter2hunter2"})

    report = scan_for_secrets(document, scan_metadata=False)

    assert report.count == 0


def test_default_ruleset_is_a_stable_public_tuple() -> None:
    assert isinstance(DEFAULT_SECRET_RULES, tuple)
    assert len(DEFAULT_SECRET_RULES) >= 8
    assert len({rule.rule_id for rule in DEFAULT_SECRET_RULES}) == len(DEFAULT_SECRET_RULES)


# ── Type safety ───────────────────────────────────────────────────────────


def test_rejects_non_notebook_document() -> None:
    with pytest.raises(TypeError):
        scan_for_secrets({"nbformat": 4})  # type: ignore[arg-type]
