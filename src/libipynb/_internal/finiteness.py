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
    found anywhere in *value*, walking through mappings, lists, and tuples
    at any depth -- notebook metadata, cell metadata, output metadata, MIME
    data, and nested structures within any of those are all just container
    nesting from this function's point of view, so one walk covers all of
    them.

    Gate G2 finding (independent review of d7ad2ef): the original version
    recursed through ``Mapping``/``list`` only, silently missing a ``tuple``
    anywhere in the structure -- a live, reproducible instance of exactly
    the "``validate()`` says valid, ``dumps()`` fails" contract this whole
    scanner exists to close, since a ``tuple`` is a realistic shape for a
    hand-constructed document handed to ``validate()`` directly (the
    scanner's own primary motivation -- see the module docstring). Also
    switched from Python-call-stack recursion to an explicit stack: the
    recursive version raised an uncaught ``RecursionError`` on adversarially
    deep input (confirmed at ~1000 levels, Python's default recursion
    limit) with no depth guard of its own, unlike this project's other
    untrusted-depth traversal (``security.limits.enforce_structure``, which
    is deliberately iterative for the same reason). The two current call
    sites (``validate()``, ``probe()``) both already run ``enforce_structure``
    first, which bounds depth before this function ever runs -- but this
    function has no such precondition documented or enforced of its own,
    so a future direct caller would silently inherit the crash risk.
    """
    stack: list[tuple[object, tuple[str | int, ...]]] = [(value, path)]
    while stack:
        current, current_path = stack.pop()
        if isinstance(current, bool):
            continue
        if isinstance(current, float):
            if not math.isfinite(current):
                yield current_path
            continue
        if isinstance(current, Mapping):
            for key, item in current.items():
                stack.append((item, (*current_path, str(key))))
        elif isinstance(current, (list, tuple)):
            for index, item in enumerate(current):
                stack.append((item, (*current_path, index)))


__all__ = ["find_non_finite_floats"]
