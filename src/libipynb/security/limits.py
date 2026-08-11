"""Notebook-specific resource-limit policy."""

from __future__ import annotations

from dataclasses import dataclass, fields
from typing import Any, Callable

from ..errors import NotebookResourceLimitError


@dataclass(frozen=True, slots=True)
class NotebookResourceLimits:
    """Finite processing limits for notebook operations."""

    max_input_bytes: int = 64 * 1024 * 1024
    max_output_bytes: int = 512 * 1024 * 1024
    max_decompressed_bytes: int = 2 * 1024 * 1024 * 1024
    max_entries: int = 100_000
    max_nesting_depth: int = 64

    def __post_init__(self) -> None:
        for descriptor in fields(self):
            value = getattr(self, descriptor.name)
            if value <= 0:
                raise ValueError(f"{descriptor.name} must be greater than zero")

    def with_overrides(self, **values: int) -> "NotebookResourceLimits":
        field_names = {item.name for item in fields(self)}
        unknown = set(values).difference(field_names)
        if unknown:
            raise TypeError(f"unknown resource limits: {', '.join(sorted(unknown))}")
        for name, value in values.items():
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"{name} must be an integer")
        return NotebookResourceLimits(**{f.name: int(values.get(f.name, getattr(self, f.name))) for f in fields(self)})

    def enforce(self, name: str, actual: int | float) -> None:
        if not hasattr(self, name):
            raise TypeError(f"unknown resource limit: {name}")
        maximum = getattr(self, name)
        if actual > maximum:
            raise NotebookResourceLimitError(
                f"{name} exceeded: {actual} > {maximum}",
                context={"limit": name, "actual": actual, "maximum": maximum},
            )


DEFAULT_RESOURCE_LIMITS = NotebookResourceLimits()

# Transitional aliases (removed in TC-S5-001-04)
ResourceLimits = NotebookResourceLimits
DEFAULT_LIMITS = DEFAULT_RESOURCE_LIMITS
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
) -> Callable[[list[tuple[str, Any]]], dict[str, Any]]:
    state = {"entries": 0}

    def hook(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        state["entries"] += len(pairs)
        limits.enforce("max_entries", state["entries"])
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
