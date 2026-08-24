"""Papermill-style parameter injection with deterministic, previewable results.

LIBIPYNB-Q35 (`plans/publication-readiness-plan-2026-08-24.md` Phase 3). The
tag convention (``parameters`` / ``injected-parameters``) and the notebook
metadata provenance location (``metadata.papermill.parameters``) both match
real Papermill exactly -- confirmed by reading its actual source
(``papermill/parameterize.py``, ``papermill/translators.py``) rather than
assumed, so a notebook produced by either tool is a normal input to the
other. Two deliberate, documented divergences from Papermill's own real
behavior, not oversights:

- **Python-only.** Real Papermill dispatches to a per-language
  ``Translator`` (R, Julia, Scala, ...); this module only implements the
  Python one. Injecting into a notebook whose declared kernel language is
  not Python (or unset) raises :class:`UnsupportedLanguageError` rather
  than silently guessing or defaulting to Python code that the kernel
  cannot actually run.
- **Explicit type rejection, not silent stringification.** Real
  Papermill's ``Translator.translate()`` falls through to
  ``translate_escaped_str`` -- i.e. ``str(val)`` wrapped in quotes -- for
  *any* value type it doesn't recognize (confirmed by reading
  ``Translator.translate``). This module instead raises
  :class:`UnsupportedParameterTypeError` for anything outside
  ``str``/``bool``/``int``/``float``/``None``/``list``/``dict`` (of the
  same, recursively) -- matching this project's established preference for
  explicit, typed failure over silent best-effort coercion (the same
  posture ``codec.reader``'s strict mode and ``security.limits`` already
  take elsewhere in this codebase).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from .document import NotebookDocument

#: Matches Papermill's own tag convention exactly (confirmed directly
#: against papermill/parameterize.py and papermill/utils.py) -- a
#: notebook tagged this way is already meaningful input to either tool.
PARAMETERS_TAG = "parameters"
INJECTED_PARAMETERS_TAG = "injected-parameters"

_SUPPORTED_SCALAR_TYPES = (str, bool, int, float, type(None))


class UnsupportedParameterTypeError(TypeError):
    """A parameter value's type has no defined Python source translation.

    Deliberate divergence from real Papermill, which silently
    stringifies unrecognized types instead -- see this module's docstring.
    """


class UnsupportedLanguageError(ValueError):
    """The target notebook's kernel language is not Python.

    LIBIPYNB-Q35 implements Python-only injection; see this module's
    docstring for why unsupported languages fail loudly instead of
    guessing.
    """


@dataclass(frozen=True, slots=True)
class InjectedParameter:
    """One name/value pair recorded as part of an injection."""

    name: str
    value: Any


@dataclass(frozen=True, slots=True)
class ParameterInjectionReport:
    """Where and how an injection happened -- returned for both real and
    ``dry_run`` calls, so a caller can preview the effect identically to
    how it would actually land."""

    parameters: tuple[InjectedParameter, ...]
    injected_cell_index: int
    replaced_existing_injection: bool
    parameters_cell_found: bool
    source: str


def _validate_parameter_value(value: object, *, path: str) -> None:
    if isinstance(value, _SUPPORTED_SCALAR_TYPES):
        return
    if isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _validate_parameter_value(item, path=f"{path}[{index}]")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise UnsupportedParameterTypeError(
                    f"{path}: dict keys must be strings, got {type(key).__name__}"
                )
            _validate_parameter_value(item, path=f"{path}[{key!r}]")
        return
    raise UnsupportedParameterTypeError(
        f"{path}: unsupported parameter value type {type(value).__name__} "
        "(supported: str, bool, int, float, None, list, dict -- recursively, of the same)"
    )


def _translate_python_str(value: str) -> str:
    # Matches PythonTranslator.translate_escaped_str exactly (confirmed
    # directly, including that it always double-quotes -- Python's own
    # repr() would single-quote unless the string itself contains a
    # single quote, a real, oracle-verified divergence caught by directly
    # comparing generated source against real papermill's own output for
    # the same parameters, not assumed to already match).
    escaped = value.encode("unicode_escape").decode("utf-8")
    escaped = escaped.replace('"', r"\"")
    return f'"{escaped}"'


def _translate_python_value(value: object) -> str:
    if value is None:
        return "None"
    if isinstance(value, bool):
        return "True" if value else "False"
    if isinstance(value, str):
        return _translate_python_str(value)
    if isinstance(value, float):
        # Matches PythonTranslator.translate_float exactly (confirmed
        # directly): repr() alone would emit "nan"/"inf", neither of which
        # is valid standalone Python source.
        if math.isnan(value):
            return "float('nan')"
        if math.isinf(value):
            return "float('-inf')" if value < 0 else "float('inf')"
        return repr(value)
    if isinstance(value, int):
        return repr(value)
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(_translate_python_value(item) for item in value) + "]"
    if isinstance(value, dict):
        pairs = ", ".join(
            f"{_translate_python_value(key)}: {_translate_python_value(item)}"
            for key, item in value.items()
        )
        return "{" + pairs + "}"
    raise UnsupportedParameterTypeError(f"unsupported parameter value type {type(value).__name__}")


def _codify_python(parameters: dict[str, Any], *, comment: str) -> str:
    lines = [f"# {comment}"] if comment else []
    for name, value in parameters.items():
        lines.append(f"{name} = {_translate_python_value(value)}")
    return "\n".join(lines) + "\n"


def _tagged_cell_index(document: NotebookDocument, tag: str) -> int:
    for index, cell in enumerate(document.cells):
        tags = cell.get("metadata", {}).get("tags")
        if isinstance(tags, list) and tag in tags:
            return index
    return -1


def find_parameters_cell_index(document: NotebookDocument) -> int:
    """Index of the first cell tagged ``"parameters"``, or -1 if none."""
    return _tagged_cell_index(document, PARAMETERS_TAG)


def find_injected_parameters_cell_index(document: NotebookDocument) -> int:
    """Index of the first cell tagged ``"injected-parameters"``, or -1 if none."""
    return _tagged_cell_index(document, INJECTED_PARAMETERS_TAG)


def _notebook_language(document: NotebookDocument) -> str | None:
    metadata = document.raw.get("metadata", {})
    language_info = metadata.get("language_info")
    if isinstance(language_info, dict) and isinstance(language_info.get("name"), str):
        return str(language_info["name"])
    kernelspec = metadata.get("kernelspec")
    if isinstance(kernelspec, dict) and isinstance(kernelspec.get("language"), str):
        return str(kernelspec["language"])
    return None


def inject_parameters(
    document: NotebookDocument,
    parameters: dict[str, Any],
    *,
    comment: str = "Parameters",
    dry_run: bool = False,
) -> ParameterInjectionReport:
    """Insert a code cell assigning ``parameters``, Papermill-style.

    Placement mirrors real Papermill exactly: replaces an existing cell
    tagged ``"injected-parameters"`` if one exists; otherwise inserts
    immediately after the first cell tagged ``"parameters"``; otherwise
    inserts at the top of the notebook (undeclared-parameters-cell case --
    real Papermill logs a warning and proceeds identically; this returns
    ``parameters_cell_found=False`` in the report so a caller can decide
    whether that is acceptable, rather than only a log line).

    Raises :class:`UnsupportedLanguageError` if the notebook's declared
    kernel language is set and is not Python, and
    :class:`UnsupportedParameterTypeError` if any parameter value (or a
    value nested inside a list/dict parameter) is not one of
    ``str``/``bool``/``int``/``float``/``None``/``list``/``dict``.
    """
    if not isinstance(document, NotebookDocument):
        raise TypeError("document must be a NotebookDocument")
    if not isinstance(parameters, dict) or not all(isinstance(key, str) for key in parameters):
        raise TypeError("parameters must be a dict[str, ...]")
    for name, value in parameters.items():
        _validate_parameter_value(value, path=name)

    language = _notebook_language(document)
    if language is not None and language != "python":
        raise UnsupportedLanguageError(
            f"LIBIPYNB-Q35 supports Python-only parameter injection; this notebook's "
            f"declared kernel language is {language!r}"
        )

    source = _codify_python(parameters, comment=comment)

    injected_index = find_injected_parameters_cell_index(document)
    params_index = find_parameters_cell_index(document)
    replaced = injected_index >= 0

    if replaced:
        target_index = injected_index
    elif params_index >= 0:
        target_index = params_index + 1
    else:
        target_index = 0

    if not dry_run:
        if replaced:
            document.remove_cell(target_index)
        document.add_cell(
            cell_type="code",
            source=source,
            metadata={"tags": [INJECTED_PARAMETERS_TAG]},
            index=target_index,
        )
        metadata = document.raw.setdefault("metadata", {})
        papermill_metadata = metadata.setdefault("papermill", {})
        papermill_metadata["parameters"] = dict(parameters)

    return ParameterInjectionReport(
        parameters=tuple(InjectedParameter(name, value) for name, value in parameters.items()),
        injected_cell_index=target_index,
        replaced_existing_injection=replaced,
        parameters_cell_found=params_index >= 0,
        source=source,
    )
