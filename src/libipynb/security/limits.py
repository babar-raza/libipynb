"""Notebook-specific resource-limit policy."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, fields
from typing import Any

from ..errors import NotebookResourceLimitError


@dataclass(frozen=True, slots=True)
class NotebookResourceLimits:
    """Finite processing limits for notebook operations."""

    max_input_bytes: int = 64 * 1024 * 1024
    max_output_bytes: int = 512 * 1024 * 1024
    max_decompressed_bytes: int = 2 * 1024 * 1024 * 1024
    #: LIBIPYNB-Q7: raised from 100_000 -- the old default rejected a
    #: legitimate, nbformat-valid ~4 MiB/150,000-line single-cell notebook
    #: that the official nbformat.validate() accepts without complaint
    #: (enforce_structure counts every JSON array element cumulatively
    #: across the whole document, so one large source line-array consumed
    #: the entire old budget). 2,000,000 gives ~13x headroom over that
    #: confirmed repro while staying two-plus orders of magnitude below
    #: where enforce_structure's own traversal cost becomes noticeable. A
    #: byte-proportional formula was considered and rejected: enforce_
    #: structure's DFS-stack traversal counts a container's entries BEFORE
    #: its child strings are popped and contribute to decoded_bytes, so an
    #: "entries-per-decoded-byte-so-far" check would spuriously reject the
    #: exact large-single-cell case this change exists to stop rejecting.
    #: See SECURITY.md's resource-limits section for the accepted,
    #: documented shape-dependent-protection caveat this doesn't close.
    max_entries: int = 2_000_000
    max_nesting_depth: int = 64
    #: LIBIPYNB-Q7: sanitize()'s markup scanner previously budgeted only
    #: *hazard* observations (active elements/attributes/references)
    #: against max_entries, not total tokens parsed -- a payload dense with
    #: harmless markup was fully tokenized by the pure-Python HTMLParser at
    #: proportional CPU cost with zero resource-limit engagement (measured:
    #: ~4.4s CPU for 300,000 harmless tags; linear extrapolation to the
    #: 2 GiB max_decompressed_bytes ceiling implied over 10 minutes of
    #: blocking CPU for one in-budget sanitize() call). 200_000 bounds a
    #: single scan's markup-tokenization phase to roughly single-digit
    #: seconds by default while leaving generous room for legitimate large
    #: HTML/markdown cells.
    max_scan_tokens: int = 200_000

    def __post_init__(self) -> None:
        for descriptor in fields(self):
            value = getattr(self, descriptor.name)
            if value <= 0:
                raise ValueError(f"{descriptor.name} must be greater than zero")

    def with_overrides(self, **values: int) -> NotebookResourceLimits:
        field_names = {item.name for item in fields(self)}
        unknown = set(values).difference(field_names)
        if unknown:
            raise TypeError(f"unknown resource limits: {', '.join(sorted(unknown))}")
        for name, value in values.items():
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"{name} must be an integer")
        return NotebookResourceLimits(
            **{f.name: int(values.get(f.name, getattr(self, f.name))) for f in fields(self)}
        )

    def enforce(self, name: str, actual: float) -> None:
        if not hasattr(self, name):
            raise TypeError(f"unknown resource limit: {name}")
        maximum = getattr(self, name)
        if actual > maximum:
            raise NotebookResourceLimitError(
                f"{name} exceeded: {actual} > {maximum}",
                context={"limit": name, "actual": actual, "maximum": maximum},
            )


DEFAULT_RESOURCE_LIMITS = NotebookResourceLimits()

IPYNB_DEFAULT_LIMITS = DEFAULT_RESOURCE_LIMITS


def effective_limits(limits: NotebookResourceLimits | None) -> NotebookResourceLimits:
    return limits or DEFAULT_RESOURCE_LIMITS


def _utf8_size(value: str, limits: NotebookResourceLimits, current: int) -> int:
    total = current
    for offset in range(0, len(value), 64 * 1024):
        total += len(value[offset : offset + 64 * 1024].encode("utf-8"))
        limits.enforce("max_decompressed_bytes", total)
    return total


def enforce_structure(value: Any, limits: NotebookResourceLimits | None = None) -> None:
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
    limits: NotebookResourceLimits,
    *,
    mode: str = "strict",
    duplicate_keys: list[str] | None = None,
) -> Callable[[list[tuple[str, Any]]], dict[str, Any]]:
    state = {"entries": 0}

    def hook(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        state["entries"] += len(pairs)
        limits.enforce("max_entries", state["entries"])
        seen: set[str] = set()
        for key, _value in pairs:
            if key in seen:
                if mode == "strict":
                    from ..errors import NotebookParseError

                    raise NotebookParseError(
                        f"duplicate JSON key {key!r}",
                        code="IPYNB_DUPLICATE_KEY",
                        context={"key": key},
                    )
                if duplicate_keys is not None:
                    duplicate_keys.append(key)
            seen.add(key)
        return dict(pairs)

    return hook


__all__ = [
    "DEFAULT_RESOURCE_LIMITS",
    "IPYNB_DEFAULT_LIMITS",
    "NotebookResourceLimits",
    "bounded_object_pairs_hook",
    "effective_limits",
    "enforce_structure",
]
