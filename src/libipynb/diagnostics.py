"""Validation diagnostic types for notebook processing."""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass, field
from enum import StrEnum

from ._internal.immutable import deep_freeze


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
        # LIBIPYNB-Q43 Gate-G2 round-3 review finding: `dict(self.details)`
        # broke aliasing to the constructor's input but left `details`
        # a genuinely, directly mutable plain dict for the lifetime of
        # this otherwise-frozen instance -- the identical
        # mutation-after-access gap this taskcard closes everywhere else,
        # missed by round 3's own repair despite that same commit
        # explicitly re-examining this exact field: reasoning that no
        # in-repo caller constructs a non-empty `details=` overlooked that
        # `Diagnostic` is a public, top-level-exported, documented
        # dataclass any external caller can construct directly (see
        # README.md's "typed Diagnostic objects"), not merely
        # internal-reachability-gated. `details`'s declared value type is
        # primitive-only (str/int/float/bool/None, no nested containers),
        # so `deep_freeze` only needs to act at this one level here -- but
        # doing exactly that, via the same shared helper everywhere else,
        # is more consistent than special-casing a manual top-level-only
        # freeze.
        object.__setattr__(self, "details", deep_freeze(dict(self.details)))


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
