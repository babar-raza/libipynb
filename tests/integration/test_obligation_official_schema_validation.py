"""Failure-first differential tests for exact official nbformat schemas."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from copy import deepcopy
from importlib import resources
from typing import Any

import nbformat
import pytest
from libipynb import (
    NotebookParseError,
    loads,
    validate,
)
from libipynb.security import IPYNB_DEFAULT_LIMITS
from libipynb.validation.schema import (
    SCHEMA_DIGESTS,
    SCHEMA_SOURCE_VERSION,
    canonical_schema_digest,
    schema_diagnostics,
)

Notebook = dict[str, Any]
Mutation = Callable[[Notebook], None]


def _notebook(minor: int = 5) -> Notebook:
    cell: Notebook = {
        "cell_type": "code",
        "metadata": {},
        "source": "value = 1",
        "execution_count": None,
        "outputs": [],
    }
    if minor >= 5:
        cell["id"] = "cell-one"
    return {
        "nbformat": 4,
        "nbformat_minor": minor,
        "metadata": {},
        "cells": [cell],
    }


def _official_errors(value: Notebook, minor: int) -> list[Exception]:
    return list(
        nbformat.validator.iter_validate(
            nbformat.from_dict(value),
            version=4,
            version_minor=minor,
        )
    )


def _add_top_extra(value: Notebook) -> None:
    value["unexpected"] = True


def _add_cell_extra(value: Notebook) -> None:
    value["cells"][0]["unexpected"] = True


def _malform_kernelspec(value: Notebook) -> None:
    value["metadata"]["kernelspec"] = {"display_name": "Python"}


def _malform_language_info(value: Notebook) -> None:
    value["metadata"]["language_info"] = "python"


def _empty_metadata_name(value: Notebook) -> None:
    value["cells"][0]["metadata"]["name"] = ""


def _malform_collapsed(value: Notebook) -> None:
    value["cells"][0]["metadata"]["collapsed"] = "yes"


def _negative_execution_count(value: Notebook) -> None:
    value["cells"][0]["execution_count"] = -1


def _add_stream_extra(value: Notebook) -> None:
    value["cells"][0]["outputs"].append(
        {
            "output_type": "stream",
            "name": "stdout",
            "text": "",
            "unexpected": True,
        }
    )


def _add_display_extra(value: Notebook) -> None:
    value["cells"][0]["outputs"].append(
        {
            "output_type": "display_data",
            "data": {},
            "metadata": {},
            "unexpected": True,
        }
    )


def _remove_execution_count(value: Notebook) -> None:
    del value["cells"][0]["execution_count"]


def _remove_outputs(value: Notebook) -> None:
    del value["cells"][0]["outputs"]


@pytest.mark.parametrize(
    "mutation",
    [
        _add_top_extra,
        _add_cell_extra,
        _malform_kernelspec,
        _malform_language_info,
        _empty_metadata_name,
        _malform_collapsed,
        _negative_execution_count,
        _add_stream_extra,
        _add_display_extra,
        _remove_execution_count,
        _remove_outputs,
    ],
    ids=lambda function: function.__name__,
)
def test_factory_rejects_every_official_schema_rejection(
    mutation: Mutation,
) -> None:
    value = _notebook()
    mutation(value)

    assert _official_errors(value, 5)
    assert not validate(value, profile="4.5").is_valid


@pytest.mark.parametrize("minor", range(6))
def test_exact_supported_minor_schema_accepts_valid_document(minor: int) -> None:
    value = _notebook(minor)

    assert not _official_errors(value, minor)
    assert validate(value, profile=f"4.{minor}").is_valid


@pytest.mark.parametrize("minor", [1, 2, 3, 4, 5])
def test_schema_diagnostics_enforce_the_minor_version_floor(minor: int) -> None:
    """"the nbformat_minor field has a minimum equal to that schema's minor
    number" -- each pinned schema declares nbformat_minor's own JSON Schema
    "minimum" as its own minor, so a document that under-declares its minor
    is rejected by the very schema it claims to satisfy."""
    value = _notebook(minor)
    value["nbformat_minor"] = minor - 1

    errors = schema_diagnostics(value, minor=minor)

    assert any(error.code == "IPYNB_SCHEMA_MINIMUM" for error in errors)
    assert any(
        error.location is not None and error.location.path == ("nbformat_minor",)
        for error in errors
    )


def test_schema_diagnostics_expose_stable_codes_and_precise_paths() -> None:
    value = _notebook()
    _add_top_extra(value)
    _negative_execution_count(value)
    _malform_kernelspec(value)
    report = validate(value, profile="4.5")
    by_code = {}
    for item in report.errors:
        by_code.setdefault(item.code, set()).add(
            item.location.path if item.location is not None else ()
        )

    assert ("unexpected",) in by_code["IPYNB_SCHEMA_ADDITIONALPROPERTIES"]
    assert (
        "cells",
        0,
        "execution_count",
    ) in by_code["IPYNB_SCHEMA_MINIMUM"]
    assert (
        "metadata",
        "kernelspec",
        "name",
    ) in by_code["IPYNB_SCHEMA_REQUIRED"]


def test_strict_load_rejects_official_schema_error_at_parse_boundary() -> None:
    value = _notebook()
    _add_cell_extra(value)

    with pytest.raises(NotebookParseError) as raised:
        loads(json.dumps(value))

    assert raised.value.code == "IPYNB_SCHEMA_ADDITIONALPROPERTIES"
    assert raised.value.context["path"] == ("cells", 0, "unexpected")


def test_mapping_validation_is_bounded_before_schema_recursion() -> None:
    value = _notebook()
    cycle: Notebook = {}
    cycle["self"] = cycle
    value["metadata"]["cycle"] = cycle
    limits = IPYNB_DEFAULT_LIMITS.with_overrides(max_entries=32)

    report = validate(value, profile="4.5", limits=limits)

    assert not report.is_valid
    assert report.errors[0].code == "IPYNB_RESOURCE_LIMIT"


def test_vendored_schema_bundle_has_pinned_exact_digests() -> None:
    """The vendored bundle must be the pinned official content.

    Compares the CANONICAL digest (line endings normalized to LF), not the raw
    byte digest this originally asserted. The raw comparison encoded a
    platform dependency rather than an integrity property: on a Windows
    checkout git rewrites LF to CRLF, so every vendored schema mismatched and
    none would load, while the identical source passed on Linux. See
    TC-FF6-IPYNB-SCHEMA-DIGEST-001. Content integrity is unchanged -- any
    difference beyond line endings still fails, as
    test_obligation_schema_digest_encoding.py asserts directly.
    """
    assert SCHEMA_SOURCE_VERSION == "nbformat-5.10.4"
    root = resources.files("libipynb.validation").joinpath(
        "schemas"
    )

    for minor, expected in SCHEMA_DIGESTS.items():
        payload = root.joinpath(
            f"nbformat.v4.{minor}.schema.json"
        ).read_bytes()
        assert canonical_schema_digest(payload) == expected
