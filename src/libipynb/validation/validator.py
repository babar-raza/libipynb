"""Profile-aware structural and semantic validation for nbformat 4.x."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..codec.reader import Source, load
from ..diagnostics import ValidationResult as ValidationReport
from ..errors import NotebookError, NotebookValidationError
from ..errors import NotebookResourceLimitError as ResourceLimitError
from ..model import NotebookDocument
from ..security.limits import NotebookResourceLimits as ResourceLimits
from ..security.limits import effective_limits, enforce_structure
from .rules import (
    KNOWN_CELL_TYPES,
    KNOWN_OUTPUT_TYPES,
    diagnostic,
    select_profile,
    validate_model,
)
from .schema import schema_diagnostics

VALID_CELL_TYPES = KNOWN_CELL_TYPES
VALID_OUTPUT_TYPES = KNOWN_OUTPUT_TYPES


def _mapping(
    value: NotebookDocument | Mapping[str, Any] | Source,
    *,
    limits: ResourceLimits | None,
) -> Mapping[str, Any]:
    if isinstance(value, NotebookDocument):
        return value.raw
    if isinstance(value, Mapping):
        return value
    return load(value, mode="preservation", limits=limits).raw


def validate(
    value: NotebookDocument | Mapping[str, Any] | Source,
    *,
    profile: str | None = None,
    limits: ResourceLimits | None = None,
) -> ValidationReport:
    """Validate using the declared, current, or an explicit nbformat profile.

    The default is ``declared``. A future 4.x minor uses the 4.5 structural
    baseline and reports forward-compatible constructs as warnings. The
    ``current`` profile requires an exact 4.5 declaration.
    """

    try:
        selected_limits = effective_limits(limits)
        model = _mapping(value, limits=selected_limits)
        enforce_structure(model, selected_limits)
    except ResourceLimitError as exc:
        return ValidationReport([diagnostic("IPYNB_RESOURCE_LIMIT", str(exc), ())])
    except UnicodeEncodeError as exc:
        # LIBIPYNB-Q6: UnicodeEncodeError (raised by enforce_structure's
        # UTF-8 byte-size accounting on a lone/unpaired UTF-16 surrogate)
        # IS a ValueError subclass, so this was already being caught by the
        # broad except below -- but only by accident, surfacing as the
        # generic IPYNB_PARSE code. Given its own explicit clause here
        # (checked before the broad ValueError catch, since Python tries
        # except clauses in source order) for a correctly-labeled
        # diagnostic instead.
        return ValidationReport([diagnostic("IPYNB_INVALID_SURROGATE", str(exc), ())])
    except (NotebookError, OSError, TypeError, ValueError) as exc:
        return ValidationReport([diagnostic("IPYNB_PARSE", str(exc), ())])

    selected, diagnostics = select_profile(model, profile)
    if not selected.allow_forward:
        diagnostics.extend(schema_diagnostics(model, minor=selected.expected_minor))
    diagnostics.extend(validate_model(model, selected))
    return ValidationReport(diagnostics)


def validate_notebook_schema(model: Mapping[str, Any]) -> list[str]:
    return [item.message for item in validate(model).errors]


def validate_notebook(model: Mapping[str, Any]) -> None:
    errors = validate_notebook_schema(model)
    if errors:
        raise NotebookValidationError("; ".join(errors))
