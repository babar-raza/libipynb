"""LIBIPYNB-Q18: locks the shared non-finite-float scanner's location and
behavior in place -- both `codec.reader.probe()` and
`validation.rules.validate_model` depend on
`libipynb._internal.finiteness.find_non_finite_floats` existing at this
exact import path.

Direct unit tests, not routed through `validate()`: `validate()`'s own
`enforce_structure` call bounds nesting depth (default 64) *before* this
scanner ever runs, which would mask whether the scanner's own iterative
walk is actually safe at depth -- these tests call the scanner directly to
prove that independently of any caller's own upstream guard."""

from __future__ import annotations

import math

from libipynb._internal.finiteness import find_non_finite_floats


def test_finds_nan_at_the_top_level() -> None:
    assert list(find_non_finite_floats(float("nan"))) == [()]


def test_finds_infinity_and_negative_infinity() -> None:
    assert list(find_non_finite_floats(float("inf"))) == [()]
    assert list(find_non_finite_floats(float("-inf"))) == [()]


def test_a_finite_float_is_not_flagged() -> None:
    assert list(find_non_finite_floats(1.5)) == []


def test_a_bool_is_never_treated_as_a_float() -> None:
    """bool is a subclass of int in Python, not float -- must not be
    mistaken for a non-finite value or crash math.isfinite."""
    assert list(find_non_finite_floats(True)) == []
    assert list(find_non_finite_floats(False)) == []


def test_recurses_through_nested_dicts() -> None:
    value = {"a": {"b": {"c": float("nan")}}}
    assert list(find_non_finite_floats(value)) == [("a", "b", "c")]


def test_recurses_through_nested_lists() -> None:
    value = [1, [2, 3, [float("nan")]]]
    assert list(find_non_finite_floats(value)) == [(1, 2, 0)]


def test_recurses_through_tuples() -> None:
    """LIBIPYNB-Q18 Gate G2 CRITICAL finding: the original version missed
    this entirely."""
    value = (1, 2, float("nan"))
    assert list(find_non_finite_floats(value)) == [(2,)]


def test_recurses_through_a_tuple_nested_inside_a_dict() -> None:
    value = {"custom": (1, float("nan"), 3)}
    assert list(find_non_finite_floats(value)) == [("custom", 1)]


def test_finds_every_occurrence_not_just_the_first() -> None:
    value = {"a": float("nan"), "b": [float("inf"), 1, float("-inf")]}
    found = set(find_non_finite_floats(value))
    assert found == {("a",), ("b", 0), ("b", 2)}


def test_a_document_with_no_non_finite_values_yields_nothing() -> None:
    value = {"a": 1, "b": [1.5, "text", None, True], "c": (1, 2)}
    assert list(find_non_finite_floats(value)) == []


def test_extreme_depth_does_not_raise_recursion_error() -> None:
    """LIBIPYNB-Q18 Gate G2 finding: the original recursive implementation
    raised an uncaught RecursionError at ~1000 levels (Python's default
    recursion limit) -- fixed via an explicit-stack iterative walk. 10,000
    levels comfortably exceeds that limit; calling this function directly
    (not through validate(), whose own enforce_structure call would bound
    depth first and mask whether this fix actually works)."""
    nested: dict[str, object] = {"n": float("nan")}
    for _ in range(10_000):
        nested = {"child": nested}
    found = list(find_non_finite_floats(nested))
    assert len(found) == 1
    assert found[0][-1] == "n"
    assert math.isfinite(1.0)  # sanity: math module itself still usable after the deep walk
