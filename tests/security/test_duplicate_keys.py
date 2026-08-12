"""Duplicate JSON key detection (IPYNB_DUPLICATE_KEY).

Python's json.loads silently keeps the last value for duplicate keys,
which can hide malicious payloads. The bounded_object_pairs_hook
detects duplicates: strict mode raises NotebookParseError, while
preservation/recovery modes record a recovery action and keep the
last value (standard Python behavior).
"""

from __future__ import annotations

import json

import pytest

from libipynb import load, loads
from libipynb.errors import NotebookParseError


def _nb_json(cells_fragment: str = "[]", extra_top: str = "") -> str:
    return (
        "{"
        '"nbformat": 4, "nbformat_minor": 5, '
        '"metadata": {"language_info": {"name": "python"}}, '
        f'"cells": {cells_fragment}'
        f"{extra_top}"
        "}"
    )


def _duplicate_top_key_json() -> str:
    return (
        '{"nbformat": 4, "nbformat_minor": 5, '
        '"metadata": {}, "cells": [], "cells": []}'
    )


def _duplicate_nested_key_json() -> str:
    return (
        '{"nbformat": 4, "nbformat_minor": 5, '
        '"metadata": {"kernelspec": {"name": "python3"}, '
        '"kernelspec": {"name": "evil"}}, "cells": []}'
    )


class TestStrictModeDuplicateKeys:
    def test_duplicate_top_level_key_raises(self) -> None:
        with pytest.raises(NotebookParseError, match="duplicate JSON key") as exc_info:
            loads(_duplicate_top_key_json(), mode="strict")
        assert exc_info.value.code == "IPYNB_DUPLICATE_KEY"
        assert exc_info.value.context["key"] == "cells"

    def test_duplicate_nested_key_raises(self) -> None:
        with pytest.raises(NotebookParseError, match="duplicate JSON key"):
            loads(_duplicate_nested_key_json(), mode="strict")

    def test_no_duplicates_parses_normally(self) -> None:
        doc = loads(_nb_json(), mode="strict")
        assert doc.nbformat == 4


class TestPreservationModeDuplicateKeys:
    def test_duplicate_top_level_key_records_recovery(self) -> None:
        doc = loads(_duplicate_top_key_json(), mode="preservation")
        assert doc.nbformat == 4
        dup_actions = [a for a in doc.recovery_actions if a.code == "IPYNB_DUPLICATE_KEY"]
        assert len(dup_actions) >= 1
        assert "cells" in dup_actions[0].message

    def test_duplicate_nested_key_records_recovery(self) -> None:
        doc = loads(_duplicate_nested_key_json(), mode="preservation")
        dup_actions = [a for a in doc.recovery_actions if a.code == "IPYNB_DUPLICATE_KEY"]
        assert len(dup_actions) >= 1
        assert "kernelspec" in dup_actions[0].message


class TestRecoveryModeDuplicateKeys:
    def test_duplicate_key_records_recovery(self) -> None:
        doc = loads(_duplicate_top_key_json(), mode="recovery")
        dup_actions = [a for a in doc.recovery_actions if a.code == "IPYNB_DUPLICATE_KEY"]
        assert len(dup_actions) >= 1
