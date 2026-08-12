"""Validation diagnostic types for notebook processing."""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass, field
from enum import StrEnum


class DiagnosticSeverity(StrEnum):
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
    severity: DiagnosticSeverity = DiagnosticSeverity.ERROR
    location: SourceLocation | None = None
    details: Mapping[str, str | int | float | bool | None] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.code.strip():
            raise ValueError("diagnostic code must not be empty")
        if not self.message.strip():
            raise ValueError("diagnostic message must not be empty")
        object.__setattr__(self, "details", dict(self.details))


@dataclass(frozen=True, slots=True)
class ValidationResult:
    """A deterministic, immutable sequence of validation diagnostics."""

    diagnostics: tuple[Diagnostic, ...] = ()

    def __init__(self, diagnostics: Iterable[Diagnostic] = ()) -> None:
        object.__setattr__(self, "diagnostics", tuple(diagnostics))

    @property
    def is_valid(self) -> bool:
        return not any(
            item.severity in {DiagnosticSeverity.ERROR, DiagnosticSeverity.FATAL}
            for item in self.diagnostics
        )

    @property
    def errors(self) -> tuple[Diagnostic, ...]:
        return tuple(
            item
            for item in self.diagnostics
            if item.severity in {DiagnosticSeverity.ERROR, DiagnosticSeverity.FATAL}
        )

    def __bool__(self) -> bool:
        return self.is_valid

    def __iter__(self) -> Iterator[Diagnostic]:
        return iter(self.diagnostics)

    def extend(self, diagnostics: Iterable[Diagnostic]) -> ValidationResult:
        return ValidationResult((*self.diagnostics, *diagnostics))
