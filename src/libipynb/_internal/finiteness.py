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

#: Second-review Gate G2 finding (on e0d7874, the tuple/RecursionError
#: repair itself): a self-referential Python structure (``d = {}; d["x"] =
#: d``) hangs this function forever -- a real, if unreachable-through-real-
#: call-sites (JSON parsing cannot express a cycle; validate()'s own
#: enforce_structure guard trips on any real cycle first), regression
#: relative to the original recursive version, which at least raised a
#: bounded, catchable RecursionError. Bounded by *depth* (path length),
#: not total node count -- a first draft capped total visited nodes
#: instead and broke on a genuinely legitimate, wide-but-shallow 4,000-cell
#: notebook fixture elsewhere in this project's own test suite (tens of
#: thousands of total nodes, but only ~6-8 levels deep), while a cap large
#: enough not to break that turned a cyclic input's bounded-failure path
#: into a many-minutes-long hang before it even raised (path -- the
#: growing tuple threaded through every call -- is copied in full on every
#: level via ``(*path, key)``, an existing, pre-this-fix cost, so total
#: work across a long CHAIN is O(depth^2), but a wide document's cost stays
#: close to O(total_nodes x depth) regardless of how many nodes it has, as
#: long as depth stays small). A cycle in this traversal always manifests
#: as unboundedly growing depth (each revisit extends the path by one
#: element), so bounding depth catches both a pathological chain and a
#: cycle without penalizing width at all. 1,000 is comfortably beyond
#: ``security.limits.NotebookResourceLimits``' own default
#: ``max_nesting_depth`` (64) -- generous for a direct caller with a
#: custom higher limit -- while keeping even the worst case a few
#: milliseconds (measured).
_MAX_DEPTH = 1000


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

    Raises ``RecursionError`` (matching the exception type the pre-fix
    recursive version would have raised for merely-deep, non-cyclic input)
    if the walk's path exceeds :data:`_MAX_DEPTH` levels -- the practical
    backstop against a self-referential structure hanging this function
    forever (an explicit stack has no other built-in protection against
    that), which also transitively bounds pathologically deep legitimate
    input without penalizing a document that is merely *wide* (many
    siblings, shallow nesting), however many total nodes it has.
    """
    stack: list[tuple[object, tuple[str | int, ...]]] = [(value, path)]
    while stack:
        current, current_path = stack.pop()
        if len(current_path) > _MAX_DEPTH:
            raise RecursionError(
                f"find_non_finite_floats exceeded {_MAX_DEPTH} levels of nesting -- "
                "the input is either implausibly deep or contains a reference cycle"
            )
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
