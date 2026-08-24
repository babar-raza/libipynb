"""LIBIPYNB-Q43: locks the shared recursive-immutability helper's location
and behavior in place -- `model.diff`/`model.metadata` depend on
`libipynb._internal.immutable.deep_freeze`/`deep_thaw` existing at this
exact import path.

Gate G2 finding this module exists to close: a single-level
`types.MappingProxyType` wrap only blocks mutating the *top* level of a
mapping -- `proxy["a"]` still returns whatever nested dict/list was stored
there, unwrapped and just as mutable as before. A frozen dataclass field
protected only by a shallow MappingProxyType wrap still let
`instance._field["nested"]["key"] = "evil"` succeed."""

from __future__ import annotations

from types import MappingProxyType

import pytest

from libipynb._internal.immutable import deep_freeze, deep_thaw


def test_top_level_dict_is_wrapped_and_rejects_item_assignment() -> None:
    frozen = deep_freeze({"a": 1})
    assert isinstance(frozen, MappingProxyType)
    with pytest.raises(TypeError):
        frozen["a"] = 2  # type: ignore[index]


def test_nested_dict_inside_a_dict_is_also_frozen() -> None:
    """The exact gap a shallow MappingProxyType wrap misses."""
    frozen = deep_freeze({"outer": {"inner": "value"}})
    assert isinstance(frozen["outer"], MappingProxyType)
    with pytest.raises(TypeError):
        frozen["outer"]["inner"] = "TAMPERED"  # type: ignore[index]


def test_deeply_nested_structure_is_frozen_at_every_level() -> None:
    frozen = deep_freeze({"a": {"b": {"c": [1, {"d": "leaf"}]}}})
    assert isinstance(frozen["a"], MappingProxyType)
    assert isinstance(frozen["a"]["b"], MappingProxyType)
    assert isinstance(frozen["a"]["b"]["c"], tuple)
    assert isinstance(frozen["a"]["b"]["c"][1], MappingProxyType)
    with pytest.raises(TypeError):
        frozen["a"]["b"]["c"][1]["d"] = "TAMPERED"  # type: ignore[index]


def test_list_is_converted_to_tuple_and_rejects_item_assignment() -> None:
    frozen = deep_freeze({"items": [1, 2, 3]})
    assert isinstance(frozen["items"], tuple)
    with pytest.raises(TypeError):
        frozen["items"][0] = 99  # type: ignore[index]


def test_list_of_dicts_each_get_frozen() -> None:
    frozen = deep_freeze({"cells": [{"source": "x"}, {"source": "y"}]})
    for cell in frozen["cells"]:
        assert isinstance(cell, MappingProxyType)
        with pytest.raises(TypeError):
            cell["source"] = "TAMPERED"  # type: ignore[index]


def test_primitives_pass_through_unchanged() -> None:
    assert deep_freeze("x") == "x"
    assert deep_freeze(1) == 1
    assert deep_freeze(1.5) == 1.5
    assert deep_freeze(True) is True
    assert deep_freeze(None) is None


def test_freezing_does_not_mutate_the_original_input() -> None:
    original = {"a": {"b": 1}}
    deep_freeze(original)
    assert original == {"a": {"b": 1}}
    original["a"]["b"] = 2  # original remains a plain, mutable dict
    assert original == {"a": {"b": 2}}


def test_thaw_reverses_freeze_into_a_genuinely_mutable_copy() -> None:
    original = {"a": {"b": [1, 2, {"c": "leaf"}]}}
    frozen = deep_freeze(original)
    thawed = deep_thaw(frozen)

    assert thawed == original
    assert isinstance(thawed, dict)
    assert isinstance(thawed["a"], dict)
    assert isinstance(thawed["a"]["b"], list)
    assert isinstance(thawed["a"]["b"][2], dict)

    # Genuinely mutable -- no TypeError, and does not affect the frozen original.
    thawed["a"]["b"][2]["c"] = "changed"
    assert thawed["a"]["b"][2]["c"] == "changed"
    assert frozen["a"]["b"][2]["c"] == "leaf"


def test_thaw_of_an_unfrozen_value_is_a_no_op_passthrough() -> None:
    assert deep_thaw("x") == "x"
    assert deep_thaw(1) == 1
    assert deep_thaw(None) is None
