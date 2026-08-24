"""LIBIPYNB-Q43: shared, dependency-free recursive immutability helper --
lives in ``_internal`` for the same reason as
:mod:`libipynb._internal.paths`/:mod:`libipynb._internal.text`: more than
one layer needs it (``model.diff``, ``model.metadata``).

Motivation: a single-level ``types.MappingProxyType`` wrap only blocks
mutating the *top* level of a mapping -- ``proxy["a"]`` still returns
whatever nested ``dict``/``list`` was stored there, unwrapped and just as
mutable as before. Demonstrated live (LIBIPYNB-Q43 Gate G2 review): a
frozen dataclass field wrapped in a bare ``MappingProxyType`` still let
``instance._field["nested"]["key"] = "evil"`` succeed and silently corrupt
what a later read of that field returned -- a JSON-like notebook snapshot
is exactly this kind of multi-level structure, so shallow protection was
not actually a fix, just a narrower version of the same bug.
"""

from __future__ import annotations

from types import MappingProxyType
from typing import Any


def deep_freeze(value: Any) -> Any:
    """Recursively convert ``dict`` -> ``MappingProxyType`` (of already
    recursively-frozen values) and ``list`` -> ``tuple`` (of already
    recursively-frozen items); every other type (``str``/``int``/``float``/
    ``bool``/``None``, and anything already immutable) is returned as-is.
    Does not mutate *value* -- always builds new containers, so the
    caller's own input is never aliased by the result either."""
    if isinstance(value, dict):
        return MappingProxyType({key: deep_freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(deep_freeze(item) for item in value)
    return value


def deep_thaw(value: Any) -> Any:
    """The inverse of :func:`deep_freeze`: recursively convert
    ``MappingProxyType`` -> ``dict`` and ``tuple`` -> ``list``, producing
    an ordinary, genuinely mutable, fully independent copy a caller can
    freely modify without any risk of touching the frozen original --
    every container at every level is newly built, exactly like
    ``copy.deepcopy`` would produce, except that ``copy.deepcopy`` itself
    cannot be used directly on a ``deep_freeze``-produced structure
    (``MappingProxyType`` has no pickle/deepcopy support of its own)."""
    if isinstance(value, MappingProxyType):
        return {key: deep_thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [deep_thaw(item) for item in value]
    return value


__all__ = ["deep_freeze", "deep_thaw"]
