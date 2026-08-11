"""Failure-first tests for planned, loss-audited nbformat conversion."""

from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import replace

import nbformat
import pytest
from libipynb import (
    ConversionDisposition,
    IpynbDocument,
    IpynbValidationError,
    downgrade,
    dumps,
    loads,
    plan_downgrade,
    upgrade,
)


def _current_notebook() -> IpynbDocument:
    return IpynbDocument(
        {
            "nbformat": 4,
            "nbformat_minor": 5,
            "metadata": {
                "title": "Conversion vector",
                "authors": [{"name": "Format Factory"}],
                "vendor.root": {"keep": True},
            },
            "cells": [
                {
                    "cell_type": "code",
                    "id": "cell-one",
                    "metadata": {
                        "jupyter": {
                            "source_hidden": True,
                            "vendor": "keep",
                        },
                        "execution": {
                            "iopub.status.busy": "2026-07-26T00:00:00Z",
                            "vendor": "keep",
                        },
                        "vendor.cell": {"keep": True},
                    },
                    "source": "value = 1",
                    "execution_count": 1,
                    "outputs": [],
                },
                {
                    "cell_type": "markdown",
                    "id": "cell-two",
                    "metadata": {},
                    "source": "text",
                },
            ],
        }
    )


def _validate_official(document: IpynbDocument, minor: int) -> None:
    nbformat.validate(
        nbformat.from_dict(document.raw),
        version=4,
        version_minor=minor,
    )


def test_downgrade_plan_reports_loss_and_preserved_extensions() -> None:
    document = _current_notebook()
    before = deepcopy(document.raw)

    first = plan_downgrade(document, target="4.0")
    second = plan_downgrade(document, target="nbformat-4.0")

    assert first == second
    assert first.source_version.as_tuple() == (4, 5)
    assert first.target_version.as_tuple() == (4, 0)
    assert first.requires_loss_acceptance
    assert not first.blockers
    assert {issue.code for issue in first.losses} == {
        "IPYNB_DOWNGRADE_CELL_ID_REMOVED"
    }
    assert {issue.path for issue in first.losses} == {
        ("cells", 0, "id"),
        ("cells", 1, "id"),
    }
    assert {
        issue.code for issue in first.preserved_extensions
    } == {
        "IPYNB_DOWNGRADE_EXECUTION_METADATA_EXTENSION",
        "IPYNB_DOWNGRADE_JUPYTER_METADATA_EXTENSION",
        "IPYNB_DOWNGRADE_NOTEBOOK_METADATA_EXTENSION",
    }
    assert all(
        issue.disposition is ConversionDisposition.PRESERVE_AS_EXTENSION
        for issue in first.preserved_extensions
    )
    assert document.raw == before


def test_lossy_downgrade_requires_explicit_acceptance() -> None:
    document = _current_notebook()
    plan = plan_downgrade(document, target="4.4")
    before = deepcopy(document.raw)

    with pytest.raises(IpynbValidationError) as raised:
        downgrade(document, plan=plan)

    assert raised.value.code == "IPYNB_DOWNGRADE_LOSS_NOT_ACCEPTED"
    assert raised.value.context["loss_count"] == 2
    assert document.raw == before


@pytest.mark.parametrize("target_minor", range(5))
def test_accepted_downgrade_is_valid_for_every_supported_older_minor(
    target_minor: int,
) -> None:
    document = _current_notebook()
    plan = plan_downgrade(document, target=f"4.{target_minor}")

    result = downgrade(document, plan=plan, accept_loss=True)

    assert result.document is not document
    assert result.document.declared_version.as_tuple() == (4, target_minor)
    assert result.document.detected_version.as_tuple() == (4, target_minor)
    assert all("id" not in cell for cell in result.document.cells)
    assert result.document.raw["metadata"]["title"] == "Conversion vector"
    assert result.document.cells[0]["metadata"]["jupyter"]["vendor"] == "keep"
    assert (
        result.document.cells[0]["metadata"]["execution"]["vendor"]
        == "keep"
    )
    assert result.issues == plan.issues
    assert result.losses == plan.losses
    assert [action.code for action in result.actions] == [
        "IPYNB_DOWNGRADE_VERSION",
        "IPYNB_DOWNGRADE_CELL_ID",
        "IPYNB_DOWNGRADE_CELL_ID",
    ]
    _validate_official(result.document, target_minor)
    reloaded = loads(
        dumps(result.document, profile="declared"),
        mode="strict",
    )
    assert reloaded.raw == result.document.raw


def test_lossless_downgrade_preserves_later_metadata_as_extensions() -> None:
    source = _current_notebook().raw
    source["nbformat_minor"] = 4
    for cell in source["cells"]:
        cell.pop("id")
    document = IpynbDocument(source)
    plan = plan_downgrade(document, target="4.0")

    assert not plan.losses
    assert plan.preserved_extensions
    result = downgrade(document, plan=plan)

    assert result.document.raw["metadata"]["title"] == "Conversion vector"
    assert result.document.cells[0]["metadata"]["execution"]["vendor"] == "keep"
    _validate_official(result.document, 0)


def test_downgrade_plan_is_bound_to_exact_source_content() -> None:
    document = _current_notebook()
    plan = plan_downgrade(document, target="4.4")
    document.raw["metadata"]["vendor.root"]["keep"] = False

    with pytest.raises(IpynbValidationError) as raised:
        downgrade(document, plan=plan, accept_loss=True)

    assert raised.value.code == "IPYNB_DOWNGRADE_STALE_PLAN"


def test_downgrade_rejects_a_plan_with_omitted_loss_entries() -> None:
    document = _current_notebook()
    complete = plan_downgrade(document, target="4.4")
    incomplete = replace(complete, issues=())

    with pytest.raises(IpynbValidationError) as raised:
        downgrade(document, plan=incomplete, accept_loss=True)

    assert raised.value.code == "IPYNB_DOWNGRADE_PLAN_MISMATCH"


def test_future_minor_downgrade_is_reported_but_blocked() -> None:
    document = _current_notebook()
    document.raw["nbformat_minor"] = 6
    document.raw["vendor.future"] = {"unknown": True}

    plan = plan_downgrade(document, target="4.5")

    assert [issue.code for issue in plan.blockers] == [
        "IPYNB_DOWNGRADE_FUTURE_MINOR_UNSUPPORTED"
    ]
    with pytest.raises(IpynbValidationError) as raised:
        downgrade(document, plan=plan, accept_loss=True)
    assert raised.value.code == "IPYNB_DOWNGRADE_BLOCKED"


@pytest.mark.parametrize("source_minor", range(5))
def test_upgrade_from_every_supported_older_minor_validates_officially(
    source_minor: int,
) -> None:
    source = _current_notebook().raw
    source["nbformat_minor"] = source_minor
    for cell in source["cells"]:
        cell.pop("id")

    result = upgrade(source, target="4.5")

    assert result.document.declared_version.as_tuple() == (4, 5)
    assert len(result.id_rewrites) == 2
    _validate_official(result.document, 5)


@pytest.mark.parametrize("target", ["4.5", "4.6", "3.0", "invalid"])
def test_downgrade_refuses_non_older_or_unsupported_targets(
    target: str,
) -> None:
    with pytest.raises(ValueError):
        plan_downgrade(_current_notebook(), target=target)


def test_reading_a_higher_minor_preserves_unknown_future_additions() -> None:
    """"preserve unknown future additions when reading higher minors" -- this
    is a plain read, not a downgrade: nothing here is ever converted or
    saved, only loaded and inspected."""
    source = {
        "nbformat": 4,
        "nbformat_minor": 6,
        "metadata": {},
        "vendor_root": {"preserve": True},
        "cells": [
            {
                "cell_type": "future_cell",
                "id": "future",
                "metadata": {},
                "source": "future",
                "vendor": {"keep": True},
            }
        ],
    }

    document = loads(json.dumps(source), mode="preservation")

    assert document.raw == source
    assert document.declared_version.as_tuple() == (4, 6)
