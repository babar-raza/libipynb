"""Notebook-specific resource-limit policy."""

from __future__ import annotations

from typing import Any, Callable

from .._internal.core_shim import DEFAULT_LIMITS, ResourceLimits

IPYNB_DEFAULT_LIMITS = DEFAULT_LIMITS.with_overrides(
    max_input_bytes=64 * 1024 * 1024,
    max_nesting_depth=64,
)


def effective_limits(limits: ResourceLimits | None) -> ResourceLimits:
    return limits or IPYNB_DEFAULT_LIMITS


def _utf8_size(value: str, limits: ResourceLimits, current: int) -> int:
    total = current
    for offset in range(0, len(value), 64 * 1024):
        total += len(value[offset : offset + 64 * 1024].encode("utf-8"))
        limits.enforce("max_decompressed_bytes", total)
    return total


def enforce_structure(value: Any, limits: ResourceLimits | None = None) -> None:
    """Bound an already-decoded JSON-like tree before recursive processing."""

    selected = effective_limits(limits)
    stack: list[tuple[Any, int]] = [(value, 0)]
    entries = 0
    decoded_bytes = 0
    while stack:
        current, depth = stack.pop()
        selected.enforce("max_nesting_depth", depth)
        if isinstance(current, dict):
            entries += len(current)
            selected.enforce("max_entries", entries)
            for key, item in current.items():
                if isinstance(key, str):
                    decoded_bytes = _utf8_size(key, selected, decoded_bytes)
                stack.append((item, depth + 1))
        elif isinstance(current, list):
            entries += len(current)
            selected.enforce("max_entries", entries)
            stack.extend((item, depth + 1) for item in current)
        elif isinstance(current, str):
            decoded_bytes = _utf8_size(current, selected, decoded_bytes)


def bounded_object_pairs_hook(
    limits: ResourceLimits,
) -> Callable[[list[tuple[str, Any]]], dict[str, Any]]:
    """Build a `json.loads(..., object_pairs_hook=...)` callback that checks
    `max_entries` DURING parsing, not after.

    `enforce_structure()` walks an already-decoded tree -- by the time it
    runs, `json.loads()` has already fully materialized every dict and list
    in memory, regardless of how oversized the result is. Confirmed
    genuinely exploitable by direct probing before this fix: a 200,000-key
    JSON object (3.3MB encoded) was fully parsed into a live Python dict in
    ~50ms before any limit check ever ran, even with max_entries=5
    configured. `json.loads()` has no hook for JSON arrays, so this can only
    guard the object (dict) half of the attack surface -- array-heavy
    payloads still materialize fully before `enforce_structure()`'s
    post-parse walk catches them, a structural limitation of the stdlib
    parser this function does not attempt to work around.

    A closure over a single running total, since `object_pairs_hook` fires
    once per JSON object as it completes (innermost first) -- the count
    accumulates across the whole document, matching `enforce_structure()`'s
    own cumulative-across-the-tree counting.
    """

    state = {"entries": 0}

    def hook(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        state["entries"] += len(pairs)
        limits.enforce("max_entries", state["entries"])
        return dict(pairs)

    return hook


__all__ = [
    "IPYNB_DEFAULT_LIMITS",
    "bounded_object_pairs_hook",
    "effective_limits",
    "enforce_structure",
]
