"""Jupyter Notebook exception hierarchy."""

from __future__ import annotations

from typing import Any


class NotebookError(Exception):
    """Base exception for Jupyter Notebook operations."""

    code = "notebook_error"

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


class NotebookParseError(NotebookError):
    """Raised when notebook input cannot be parsed safely."""

    code = "parse_error"


class NotebookWriteError(NotebookError):
    """Raised when a notebook cannot be serialized or written."""

    code = "write_error"


class NotebookValidationError(NotebookError):
    """Raised when a notebook violates the selected profile."""

    code = "validation_error"


class NotebookSecurityError(NotebookError):
    """Raised for security constraint violations."""

    code = "security_error"


class NotebookResourceLimitError(NotebookError):
    """Processing would exceed a configured resource limit."""

    code = "resource_limit_exceeded"


class NotebookExecutionError(NotebookError):
    """Raised when the opt-in execution adapter cannot run a notebook."""

    code = "execution_error"


