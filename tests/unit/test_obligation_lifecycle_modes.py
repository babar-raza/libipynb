"""Failure-first lifecycle, preservation, and explicit-upgrade obligations."""

from __future__ import annotations

import json

import nbformat
import pytest

from libipynb import (
    NotebookParseError,
    NotebookWriteError,
    dumps,
    load,
    loads,
    upgrade,
)
from libipynb.errors import NotebookResourceLimitError
from libipynb.model import downgrade, plan_downgrade
from libipynb.security import IPYNB_DEFAULT_LIMITS


def _notebook(*, minor: int = 4, cell: dict[str, object] | None = None) -> str:
    return json.dumps(
        {
            "nbformat": 4,
            "nbformat_minor": minor,
            "metadata": {},
            "cells": [] if cell is None else [cell],
        },
        ensure_ascii=False,
    )


def test_preservation_mode_does_not_synthesize_absent_values_or_ids() -> None:
    source = {
        "nbformat": 4,
        "nbformat_minor": 4,
        "vendor": {"unicode": "λ", "number": 9007199254740991},
        "cells": [{"cell_type": "markdown", "source": "", "metadata": {}}],
    }

    document = loads(json.dumps(source, ensure_ascii=False), mode="preservation")

    assert document.raw == source
    assert "metadata" not in document.raw
    assert "id" not in document.cells[0]
    assert json.loads(dumps(document, profile="declared")) == source


def test_strict_mode_rejects_incomplete_current_document_with_diagnostic() -> None:
    source = _notebook(
        minor=5,
        cell={"cell_type": "markdown", "source": "", "metadata": {}},
    )

    with pytest.raises(NotebookParseError) as raised:
        loads(source, mode="strict")

    assert raised.value.code == "IPYNB_CELL_ID"
    assert raised.value.context["path"] == ("cells", 0, "id")


def test_recovery_mode_is_deterministic_and_reports_every_synthesized_value() -> None:
    source = json.dumps(
        {
            "nbformat": 4,
            "cells": [{"cell_type": "code"}],
        }
    )

    first = loads(source, mode="recovery")
    second = loads(source, mode="recovery")

    assert (
        first.raw
        == second.raw
        == {
            "nbformat": 4,
            "nbformat_minor": 0,
            "metadata": {},
            "cells": [
                {
                    "cell_type": "code",
                    "metadata": {},
                    "source": "",
                    "outputs": [],
                    "execution_count": None,
                }
            ],
        }
    )
    assert [action.code for action in first.recovery_actions] == [
        "IPYNB_RECOVER_MINOR",
        "IPYNB_RECOVER_METADATA",
        "IPYNB_RECOVER_CELL_METADATA",
        "IPYNB_RECOVER_CELL_SOURCE",
        "IPYNB_RECOVER_OUTPUTS",
        "IPYNB_RECOVER_EXECUTION_COUNT",
    ]
    assert first.recovery_actions == second.recovery_actions
    assert first.declared_version.major == 4
    assert first.declared_version.minor is None
    assert first.detected_version.as_tuple() == (4, 0)


def test_explicit_upgrade_is_the_only_production_path_that_generates_ids() -> None:
    source = loads(
        _notebook(
            minor=4,
            cell={"cell_type": "markdown", "source": "hello", "metadata": {}},
        ),
        mode="strict",
    )

    with pytest.raises(NotebookWriteError, match="explicit upgrade"):
        dumps(source)

    conversion = upgrade(source, target="4.5")
    upgraded = conversion.document
    assert upgraded.declared_version.as_tuple() == (4, 5)
    assert upgraded.detected_version.as_tuple() == (4, 5)
    assert upgraded.cells[0]["id"]
    assert conversion.id_rewrites[0].cell_index == 0
    assert conversion.id_rewrites[0].old_id is None
    assert conversion.id_rewrites[0].new_id == upgraded.cells[0]["id"]
    assert [entry.code for entry in conversion.actions] == [
        "IPYNB_UPGRADE_VERSION",
        "IPYNB_UPGRADE_CELL_ID",
    ]
    nbformat.validate(nbformat.from_dict(upgraded.raw))
    assert dumps(upgraded) == dumps(upgraded)


def test_lossless_and_normalized_output_are_an_explicit_caller_choice() -> None:
    document = loads(
        _notebook(minor=4, cell={"cell_type": "markdown", "source": "text", "metadata": {}}),
        mode="preservation",
    )

    with pytest.raises(NotebookWriteError, match="explicit upgrade"):
        dumps(document)

    lossless = json.loads(dumps(document, profile="declared"))
    assert lossless == document.raw
    assert lossless["nbformat_minor"] == 4

    upgraded = upgrade(document, target="4.5").document
    normalized = json.loads(dumps(upgraded))
    assert normalized["nbformat_minor"] == 5
    assert normalized != document.raw


def test_upgrade_assigns_cell_ids_for_4_5_notebooks() -> None:
    doc = load(
        _notebook(
            minor=5,
            cell={"cell_type": "markdown", "source": "legacy", "metadata": {}},
        ),
        mode="recovery",
    )
    upgraded = upgrade(doc, target="4.5")

    assert upgraded.document.raw["cells"][0]["id"]


def test_upgrade_records_orig_nbformat_minor_matching_nbformats_own_reference_behavior() -> None:
    """LIBIPYNB-Q14: nbformat.v4.convert.upgrade() unconditionally sets
    `nb.metadata.orig_nbformat_minor = from_minor` on every real version
    bump -- this provenance field was previously omitted entirely."""
    source_minor = 3
    document = loads(
        _notebook(
            minor=source_minor,
            cell={"cell_type": "markdown", "source": "hello", "metadata": {}},
        ),
        mode="strict",
    )

    upgraded = upgrade(document, target="4.5").document

    assert upgraded.raw["metadata"]["orig_nbformat_minor"] == source_minor
    nbformat.validate(nbformat.from_dict(upgraded.raw))


def test_upgrade_omits_orig_nbformat_minor_when_the_version_does_not_actually_change() -> None:
    document = loads(
        _notebook(
            minor=5,
            cell={"cell_type": "markdown", "source": "hello", "metadata": {}, "id": "cell-0"},
        ),
        mode="strict",
    )

    upgraded = upgrade(document, target="4.5").document

    assert "orig_nbformat_minor" not in upgraded.raw["metadata"]


def _deeply_nested_metadata(depth: int) -> dict[str, object]:
    node: dict[str, object] = {}
    cursor = node
    for _ in range(depth):
        cursor["x"] = {}
        cursor = cursor["x"]  # type: ignore[assignment]
    return {"nbformat": 4, "nbformat_minor": 4, "metadata": node, "cells": []}


class TestUpgradeDowngradeResourceLimits:
    """LIBIPYNB-Q5: upgrade()/plan_downgrade()/downgrade() previously called
    Python's recursive copy.deepcopy() on caller-supplied input BEFORE any
    bounded traversal ran -- an uncaught RecursionError at ~495+ levels of
    nested metadata, a trivially-triggered DoS against the same resource-
    limit guarantee validate()/load() already correctly enforce for
    identical adversarial input. upgrade() specifically enforced NO
    structural limit at all below that crash threshold."""

    def test_upgrade_rejects_deeply_nested_metadata_instead_of_recursion_error(self) -> None:
        payload = _deeply_nested_metadata(5000)

        with pytest.raises(NotebookResourceLimitError):
            upgrade(payload, target="4.5")

    def test_upgrade_is_now_bounded_well_below_the_old_crash_threshold_too(self) -> None:
        """The gap upgrade() had was worse than "crashes past ~495 levels" --
        it enforced no limit whatsoever below that. A tight custom limit
        must now reject a payload that would previously have silently
        succeeded."""
        payload = _deeply_nested_metadata(200)
        tight_limits = IPYNB_DEFAULT_LIMITS.with_overrides(max_nesting_depth=64)

        with pytest.raises(NotebookResourceLimitError, match="max_nesting_depth"):
            upgrade(payload, target="4.5", limits=tight_limits)

    def test_upgrade_honors_a_caller_supplied_looser_limit(self) -> None:
        payload = _deeply_nested_metadata(200)
        looser_limits = IPYNB_DEFAULT_LIMITS.with_overrides(max_nesting_depth=300)

        upgrade(payload, target="4.5", limits=looser_limits)  # must not raise

    def test_plan_downgrade_rejects_deeply_nested_metadata_instead_of_recursion_error(self) -> None:
        payload = _deeply_nested_metadata(5000)
        payload["nbformat_minor"] = 5

        with pytest.raises(NotebookResourceLimitError):
            plan_downgrade(payload, target="4.4")

    def test_downgrade_rejects_deeply_nested_metadata_instead_of_recursion_error(self) -> None:
        base = {"nbformat": 4, "nbformat_minor": 5, "metadata": {}, "cells": []}
        plan = plan_downgrade(base, target="4.4")

        payload = _deeply_nested_metadata(5000)
        payload["nbformat_minor"] = 5

        with pytest.raises(NotebookResourceLimitError):
            downgrade(payload, plan=plan, accept_loss=True)
