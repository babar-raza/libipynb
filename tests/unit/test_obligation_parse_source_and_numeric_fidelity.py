"""IPYNB-PARSE-001: the three dimensions its six MUST obligations declare.

Their shared proof requirement is "Fixtures for string vs list-of-strings
sources, unknown fields, and numeric edge values round-trip" -- three axes, all
of which must be exercised. The ledger carried two selectors against three
declared dimensions, which is the shape proof_requirement_audit_lesson exists to
catch: a matrix with an untested axis is where defects hide.

One sharpness note. A first probe compared restored metadata to the original
with `==` and reported every numeric edge preserved. That comparison cannot
detect a lost sign on negative zero, because `-0.0 == 0.0` is True in Python.
The negative-zero test below uses copysign instead. A test that cannot fail for
the defect it names is not evidence.
"""

from __future__ import annotations

import json
import math
from typing import Any

import pytest

from libipynb import dumps, loads, validate

# Values chosen to break naive JSON round-tripping: the float64 integer-exactness
# boundary, the u64 boundary, the largest finite float, the smallest subnormal,
# and a value whose repr must not be shortened.
NUMERIC_EDGES: dict[str, Any] = {
    "int_2pow53": 2**53,
    "int_2pow53_plus_one": 2**53 + 1,
    "int_u64_max": 2**64 - 1,
    "int_negative_large": -(2**53),
    "float_max": 1.7976931348623157e308,
    "float_min_subnormal": 5e-324,
    "float_epsilon": 2.220446049250313e-16,
    "float_exponent": 1e100,
    "float_repr_sensitive": 0.1 + 0.2,
    "float_many_digits": 3.141592653589793,
    "int_zero": 0,
    "float_zero": 0.0,
}


def _notebook(
    cells: list[dict[str, Any]], metadata: dict[str, Any] | None = None
) -> dict[str, Any]:
    return {
        "nbformat": 4,
        "nbformat_minor": 5,
        "metadata": metadata or {},
        "cells": cells,
    }


def _cell(**overrides: Any) -> dict[str, Any]:
    cell: dict[str, Any] = {
        "cell_type": "markdown",
        "id": "cell-one",
        "metadata": {},
        "source": "",
    }
    cell.update(overrides)
    return cell


def _roundtrip(notebook: dict[str, Any]) -> dict[str, Any]:
    return json.loads(dumps(loads(json.dumps(notebook))))


# ── Dimension 1: string vs list-of-strings sources ─────────────────────────


def test_string_source_is_valid_and_preserved_as_a_string() -> None:
    """nbformat permits either shape; neither may be silently normalized."""
    notebook = _notebook([_cell(source="line one\nline two")])
    assert validate(notebook, profile="4.5").is_valid
    restored = _roundtrip(notebook)["cells"][0]["source"]
    assert restored == "line one\nline two"
    assert isinstance(restored, str)


def test_list_source_is_valid_and_preserved_as_a_list() -> None:
    notebook = _notebook([_cell(source=["line one\n", "line two"])])
    assert validate(notebook, profile="4.5").is_valid
    restored = _roundtrip(notebook)["cells"][0]["source"]
    assert restored == ["line one\n", "line two"]
    assert isinstance(restored, list)


def test_the_two_shapes_are_not_converted_into_each_other() -> None:
    """The distinction is the whole point of the dimension: a writer that
    normalized both to one shape would pass each test above in isolation."""
    as_string = _roundtrip(_notebook([_cell(source="a\nb")]))["cells"][0]["source"]
    as_list = _roundtrip(_notebook([_cell(source=["a\n", "b"])]))["cells"][0]["source"]
    assert isinstance(as_string, str)
    assert isinstance(as_list, list)


@pytest.mark.parametrize("source", ["", [], ["single line"], "no trailing newline"])
def test_source_edge_shapes_round_trip(source: str | list[str]) -> None:
    notebook = _notebook([_cell(source=source)])
    assert validate(notebook, profile="4.5").is_valid
    assert _roundtrip(notebook)["cells"][0]["source"] == source


@pytest.mark.parametrize("cell_type", ["markdown", "raw"])
def test_both_source_shapes_work_for_every_cell_type(cell_type: str) -> None:
    for source in ("text", ["text"]):
        notebook = _notebook([_cell(cell_type=cell_type, source=source)])
        assert validate(notebook, profile="4.5").is_valid
        assert _roundtrip(notebook)["cells"][0]["source"] == source


def test_code_cell_supports_both_source_shapes() -> None:
    for source in ("print(1)", ["print(1)\n", "print(2)"]):
        notebook = _notebook(
            [_cell(cell_type="code", execution_count=None, outputs=[], source=source)]
        )
        assert validate(notebook, profile="4.5").is_valid
        assert _roundtrip(notebook)["cells"][0]["source"] == source


# ── Dimension 2: unknown fields ────────────────────────────────────────────


def test_unknown_notebook_metadata_is_preserved() -> None:
    notebook = _notebook([_cell()], metadata={"x-vendor": {"nested": [1, {"k": "v"}]}})
    assert _roundtrip(notebook)["metadata"]["x-vendor"] == {"nested": [1, {"k": "v"}]}


def test_unknown_cell_metadata_is_preserved() -> None:
    notebook = _notebook([_cell(metadata={"x-tool": {"state": "kept"}})])
    assert _roundtrip(notebook)["cells"][0]["metadata"]["x-tool"] == {"state": "kept"}


def test_unknown_metadata_survives_two_round_trips() -> None:
    """Idempotence: a field kept once but dropped on the second pass is worse
    than one dropped immediately, because it survives a shallow test."""
    notebook = _notebook([_cell()], metadata={"x-vendor": {"deep": {"a": [1, 2]}}})
    once = _roundtrip(notebook)
    twice = _roundtrip(once)
    assert twice["metadata"]["x-vendor"] == {"deep": {"a": [1, 2]}}
    assert once == twice


def test_unknown_metadata_key_ordering_does_not_affect_content() -> None:
    forward = _notebook([_cell()], metadata={"a-first": 1, "z-last": 2})
    reverse = _notebook([_cell()], metadata={"z-last": 2, "a-first": 1})
    assert _roundtrip(forward)["metadata"] == _roundtrip(reverse)["metadata"]


# ── Dimension 3: numeric edge values ───────────────────────────────────────


@pytest.mark.parametrize("name,value", sorted(NUMERIC_EDGES.items()))
def test_numeric_edge_value_round_trips_exactly(name: str, value: Any) -> None:
    notebook = _notebook([_cell()], metadata={"x-num": {name: value}})
    restored = _roundtrip(notebook)["metadata"]["x-num"][name]
    assert restored == value
    assert type(restored) is type(value), "int must not become float, or vice versa"


def test_negative_zero_keeps_its_sign() -> None:
    """`-0.0 == 0.0` is True, so an equality check cannot see this defect.

    A first probe of these edges used `==` and reported everything preserved;
    it could not have detected a lost sign. copysign can.
    """
    notebook = _notebook([_cell()], metadata={"x-num": {"negative_zero": -0.0}})
    restored = _roundtrip(notebook)["metadata"]["x-num"]["negative_zero"]
    assert math.copysign(1.0, restored) == -1.0


def test_large_integers_do_not_degrade_to_float() -> None:
    """2**53 + 1 is not representable as a float64; a float round-trip loses it."""
    notebook = _notebook([_cell()], metadata={"x-num": {"n": 2**53 + 1}})
    restored = _roundtrip(notebook)["metadata"]["x-num"]["n"]
    assert restored == 2**53 + 1
    assert isinstance(restored, int)


def test_all_numeric_edges_survive_together_and_idempotently() -> None:
    notebook = _notebook([_cell()], metadata={"x-num": dict(NUMERIC_EDGES)})
    once = _roundtrip(notebook)
    twice = _roundtrip(once)
    assert once["metadata"]["x-num"] == NUMERIC_EDGES
    assert once == twice


def test_execution_count_is_an_integer_not_a_float_after_roundtrip() -> None:
    notebook = _notebook([_cell(cell_type="code", execution_count=7, outputs=[], source="x")])
    restored = _roundtrip(notebook)["cells"][0]["execution_count"]
    assert restored == 7
    assert isinstance(restored, int)


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_numbers_fail_closed_rather_than_emitting_invalid_json(
    bad: float,
) -> None:
    """NaN and Infinity are not valid JSON. Emitting them would produce a file
    no conforming reader could load."""
    from libipynb import NotebookWriteError

    document = loads(json.dumps(_notebook([_cell()])))
    document.raw["metadata"]["x-num"] = {"bad": bad}
    with pytest.raises(NotebookWriteError):
        dumps(document)


# ── All three dimensions in one fixture ────────────────────────────────────


def test_full_matrix_notebook_round_trips_and_validates() -> None:
    notebook = _notebook(
        [
            _cell(source="string form", metadata={"x-cell": {"kept": True}}),
            _cell(id="cell-two", source=["list\n", "form"]),
        ],
        metadata={"x-vendor": {"nested": [1, 2]}, "x-num": dict(NUMERIC_EDGES)},
    )
    assert validate(notebook, profile="4.5").is_valid
    restored = _roundtrip(notebook)
    assert restored["cells"][0]["source"] == "string form"
    assert restored["cells"][1]["source"] == ["list\n", "form"]
    assert restored["cells"][0]["metadata"]["x-cell"] == {"kept": True}
    assert restored["metadata"]["x-num"] == NUMERIC_EDGES
