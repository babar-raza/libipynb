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

import pytest

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


def test_a_self_referential_structure_fails_bounded_rather_than_hanging_forever() -> None:
    """Second-review Gate G2 finding (on the tuple/RecursionError repair
    itself): a cyclic Python structure hung this function indefinitely --
    unreachable through validate()/probe() (JSON cannot express a cycle,
    and validate()'s own enforce_structure guard trips on any real cycle
    first), but a real regression relative to the original recursive
    version, which at least raised a bounded, catchable RecursionError.
    Must now fail with a clear, bounded RecursionError instead of hanging."""
    cyclic: dict[str, object] = {}
    cyclic["self"] = cyclic

    with pytest.raises(RecursionError, match="find_non_finite_floats"):
        list(find_non_finite_floats(cyclic))


def test_a_legitimately_deep_but_within_bound_structure_still_works() -> None:
    """LIBIPYNB-Q18 Gate G2 finding: the original recursive implementation
    raised an uncaught RecursionError at ~1000 levels (Python's default
    recursion limit) -- fixed via an explicit-stack iterative walk. 500
    levels comfortably exceeds security.limits.NotebookResourceLimits' own
    default max_nesting_depth (64, what actually bounds the two real call
    sites) while staying under this scanner's own _MAX_DEPTH backstop
    (1000), proving depth alone -- short of that backstop -- is handled
    correctly by the iterative rewrite. Calling this function directly (not
    through validate(), whose own enforce_structure call would bound depth
    first and mask whether this fix actually works)."""
    nested: dict[str, object] = {"n": float("nan")}
    for _ in range(500):
        nested = {"child": nested}
    found = list(find_non_finite_floats(nested))
    assert len(found) == 1
    assert found[0][-1] == "n"
    assert math.isfinite(1.0)  # sanity: math module itself still usable after the deep walk


def test_depth_beyond_the_backstop_fails_bounded_rather_than_hanging_or_crashing() -> None:
    """Second-review Gate G2 finding: a first draft of the cycle-safety fix
    capped total VISITED NODES rather than depth, and broke a genuinely
    legitimate, wide-but-shallow 4,000-cell notebook fixture elsewhere in
    this project's own test suite (tens of thousands of total nodes, only
    ~6-8 levels deep) while a cap loose enough not to break that turned a
    cyclic input's bounded-failure path into a many-minutes-long hang
    before it even raised. Bounding by depth instead catches this case
    (and a cycle, which always manifests as unboundedly growing depth in
    this traversal) without any width-related false positive."""
    nested: dict[str, object] = {"n": float("nan")}
    for _ in range(5_000):
        nested = {"child": nested}
    with pytest.raises(RecursionError, match="find_non_finite_floats"):
        list(find_non_finite_floats(nested))


def test_a_wide_but_shallow_structure_with_many_nodes_is_unaffected_by_the_depth_backstop() -> None:
    """The exact regression class the first draft of the cycle-safety fix
    introduced: many total nodes (thousands), shallow depth (a handful of
    levels) -- must not trip the depth backstop just because it visits a
    lot of nodes."""
    wide = {f"key-{i}": {"nested": i, "value": 1.5} for i in range(10_000)}
    assert list(find_non_finite_floats(wide)) == []
