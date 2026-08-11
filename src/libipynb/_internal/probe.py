"""Notebook format probe result."""

from __future__ import annotations

from dataclasses import dataclass


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
