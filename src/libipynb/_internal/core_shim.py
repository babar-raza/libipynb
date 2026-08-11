"""Temporary bridge providing the 9 format_factory.core symbols consumed by IPYNB.

This module is internal, never public API, and will be deleted once library-owned
types replace it (TC-S4-001-05).
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from enum import StrEnum
from typing import Any, Iterable, Iterator, Mapping


class FormatFactoryError(Exception):
    """Base class for public failures."""

    code = "format_factory_error"

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code or type(self).code
        self.context = dict(context or {})

    def __str__(self) -> str:
        return self.message


class ResourceLimitError(FormatFactoryError):
    """Processing would exceed a configured resource limit."""

    code = "resource_limit_exceeded"


@dataclass(frozen=True, slots=True)
class ResourceLimits:
    """Finite processing limits."""

    max_input_bytes: int = 512 * 1024 * 1024
    max_output_bytes: int = 512 * 1024 * 1024
    max_header_bytes: int = 16 * 1024 * 1024
    max_decompressed_bytes: int = 2 * 1024 * 1024 * 1024
    max_compression_ratio: float = 100.0
    max_entries: int = 100_000
    max_nesting_depth: int = 128
    max_xml_nodes: int = 5_000_000
    max_tensor_count: int = 1_000_000

    def __post_init__(self) -> None:
        for descriptor in fields(self):
            value = getattr(self, descriptor.name)
            if value <= 0:
                raise ValueError(f"{descriptor.name} must be greater than zero")

    def with_overrides(self, **values: int | float) -> "ResourceLimits":
        field_names = {item.name for item in fields(self)}
        unknown = set(values).difference(field_names)
        if unknown:
            raise TypeError(f"unknown resource limits: {', '.join(sorted(unknown))}")
        for name, value in values.items():
            if name == "max_compression_ratio":
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    raise TypeError(f"{name} must be numeric")
            elif isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"{name} must be an integer")
        return ResourceLimits(
            max_input_bytes=int(values.get("max_input_bytes", self.max_input_bytes)),
            max_output_bytes=int(values.get("max_output_bytes", self.max_output_bytes)),
            max_header_bytes=int(values.get("max_header_bytes", self.max_header_bytes)),
            max_decompressed_bytes=int(
                values.get("max_decompressed_bytes", self.max_decompressed_bytes)
            ),
            max_compression_ratio=float(
                values.get("max_compression_ratio", self.max_compression_ratio)
            ),
            max_entries=int(values.get("max_entries", self.max_entries)),
            max_nesting_depth=int(
                values.get("max_nesting_depth", self.max_nesting_depth)
            ),
            max_xml_nodes=int(values.get("max_xml_nodes", self.max_xml_nodes)),
            max_tensor_count=int(
                values.get("max_tensor_count", self.max_tensor_count)
            ),
        )

    def enforce(self, name: str, actual: int | float) -> None:
        if not hasattr(self, name):
            raise TypeError(f"unknown resource limit: {name}")
        maximum = getattr(self, name)
        if actual > maximum:
            raise ResourceLimitError(
                f"{name} exceeded: {actual} > {maximum}",
                context={"limit": name, "actual": actual, "maximum": maximum},
            )


DEFAULT_LIMITS = ResourceLimits()


class Severity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    FATAL = "fatal"


@dataclass(frozen=True, slots=True)
class SourceLocation:
    """Location in a byte stream, text document, or logical object path."""

    byte_offset: int | None = None
    line: int | None = None
    column: int | None = None
    path: tuple[str | int, ...] = ()

    def __post_init__(self) -> None:
        for name in ("byte_offset", "line", "column"):
            value = getattr(self, name)
            if value is not None and value < 0:
                raise ValueError(f"{name} must be non-negative")


@dataclass(frozen=True, slots=True)
class Diagnostic:
    code: str
    message: str
    severity: Severity = Severity.ERROR
    location: SourceLocation | None = None
    details: Mapping[str, str | int | float | bool | None] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.code.strip():
            raise ValueError("diagnostic code must not be empty")
        if not self.message.strip():
            raise ValueError("diagnostic message must not be empty")
        object.__setattr__(self, "details", dict(self.details))


@dataclass(frozen=True, slots=True)
class ValidationReport:
    """A deterministic, immutable sequence of validation diagnostics."""

    diagnostics: tuple[Diagnostic, ...] = ()

    def __init__(self, diagnostics: Iterable[Diagnostic] = ()) -> None:
        object.__setattr__(self, "diagnostics", tuple(diagnostics))

    @property
    def is_valid(self) -> bool:
        return not any(
            item.severity in {Severity.ERROR, Severity.FATAL}
            for item in self.diagnostics
        )

    @property
    def errors(self) -> tuple[Diagnostic, ...]:
        return tuple(
            item
            for item in self.diagnostics
            if item.severity in {Severity.ERROR, Severity.FATAL}
        )

    def __bool__(self) -> bool:
        return self.is_valid

    def __iter__(self) -> Iterator[Diagnostic]:
        return iter(self.diagnostics)

    def extend(self, diagnostics: Iterable[Diagnostic]) -> "ValidationReport":
        return ValidationReport((*self.diagnostics, *diagnostics))


@dataclass(frozen=True, slots=True)
class ProbeResult:
    matched: bool
    confidence: float
    format_id: str
    profile: str | None = None
    reason: str = ""

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0.0 and 1.0")
        if not self.format_id:
            raise ValueError("format_id must not be empty")

    def __bool__(self) -> bool:
        return self.matched


__all__ = [
    "FormatFactoryError",
    "ResourceLimitError",
    "ResourceLimits",
    "DEFAULT_LIMITS",
    "ProbeResult",
    "Diagnostic",
    "Severity",
    "SourceLocation",
    "ValidationReport",
]
