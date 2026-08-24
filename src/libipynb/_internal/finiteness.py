"""LIBIPYNB-Q18 (P0-C): shared, dependency-free recursive non-finite-float
scanner -- lives in ``_internal`` for the same reason as
:mod:`libipynb._internal.paths`/:mod:`libipynb._internal.text`: both
``codec.reader`` (``probe()``) and ``validation.rules`` (``validate_model()``)
need it, and ``validation`` already imports from ``codec``
(``validator.py`` imports ``load``/``Source`` from ``codec.reader``), so
``codec`` importing back from ``validation`` would be circular.

Motivation: Python's ``json`` module, by default, silently accepts the
non-standard ``NaN``/``Infinity``/``-Infinity`` constants (via
``parse_constant``) and produces ``float('nan')``/``float('inf')``/
``float('-inf')`` -- legal Python values, but not legal JSON, and rejected
by this project's own writer (``allow_nan=False``). Without this scanner, a
notebook containing one of these constants could load in strict mode
(``codec.reader``'s own ``parse_constant`` hook only rejects it at the
JSON-*text* parsing stage, not for an already-constructed Python mapping
handed to ``validate()`` directly), report as valid via ``validate()``, and
report as a matched IPYNB via ``probe()`` -- then fail unrecoverably at
``dumps()``. This scanner closes the gap for both entry points: an
already-constructed mapping (not just JSON text) and a preservation-mode-
loaded document (``probe()`` deliberately tolerates other imperfections but
must not call a non-finite-constant-carrying document a valid IPYNB).
"""

from __future__ import annotations

import math
from collections.abc import Iterator, Mapping


def find_non_finite_floats(
    value: object, path: tuple[str | int, ...] = ()
) -> Iterator[tuple[str | int, ...]]:
    """Yield the path to every non-finite (``NaN``/``inf``/``-inf``) float
    found anywhere in *value*, recursing through mappings and lists at any
    depth -- notebook metadata, cell metadata, output metadata, MIME data,
    and nested structures within any of those are all just dict/list
    nesting from this function's point of view, so one recursive walk
    covers all of them."""
    if isinstance(value, bool):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            yield path
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            yield from find_non_finite_floats(item, (*path, str(key)))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from find_non_finite_floats(item, (*path, index))


__all__ = ["find_non_finite_floats"]
