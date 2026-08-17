"""Fuzz libipynb.validate() -- structure-aware, not raw bytes.

Raw-bytes fuzzing mostly exercises JSON-syntax rejection (already covered
by fuzz_parser.py) and rarely reaches deep validation logic (cell-ID rules,
MIME-bundle checks, attachment cross-references) within a bounded budget.
This target keeps a plausible notebook shape fixed and fuzzes the leaf
values a real adversarial notebook would vary, giving the fuzzer a much
better chance of reaching validation/rules.py's actual branches.
"""

from __future__ import annotations

import sys

import atheris

with atheris.instrument_imports():
    from libipynb import NotebookError, validate

_CELL_TYPES = ("code", "markdown", "raw", "unknown_future_type")
_OUTPUT_TYPES = ("stream", "execute_result", "display_data", "error", "future_type")
_MIME_TYPES = (
    "text/plain",
    "text/html",
    "image/png",
    "image/svg+xml",
    "application/json",
    "",
    "not-a-mime-type",
)


def _fuzz_string(fdp: atheris.FuzzedDataProvider, max_len: int = 64) -> str:
    return fdp.ConsumeUnicodeNoSurrogates(fdp.ConsumeIntInRange(0, max_len))


def _fuzz_cell(fdp: atheris.FuzzedDataProvider) -> dict:
    cell_type = _CELL_TYPES[fdp.ConsumeIntInRange(0, len(_CELL_TYPES) - 1)]
    cell: dict = {
        "cell_type": cell_type,
        "id": _fuzz_string(fdp, 20),
        "metadata": {_fuzz_string(fdp, 10): _fuzz_string(fdp, 20)},
        "source": _fuzz_string(fdp, 200),
    }
    if cell_type == "code":
        cell["execution_count"] = fdp.ConsumeIntInRange(-5, 1000)
        cell["outputs"] = [_fuzz_output(fdp) for _ in range(fdp.ConsumeIntInRange(0, 3))]
    return cell


def _fuzz_output(fdp: atheris.FuzzedDataProvider) -> dict:
    output_type = _OUTPUT_TYPES[fdp.ConsumeIntInRange(0, len(_OUTPUT_TYPES) - 1)]
    output: dict = {"output_type": output_type}
    if output_type == "stream":
        output["name"] = _fuzz_string(fdp, 10)
        output["text"] = _fuzz_string(fdp, 100)
    elif output_type in ("execute_result", "display_data"):
        mime = _MIME_TYPES[fdp.ConsumeIntInRange(0, len(_MIME_TYPES) - 1)]
        output["data"] = {mime: _fuzz_string(fdp, 100)}
        output["metadata"] = {}
        if output_type == "execute_result":
            output["execution_count"] = fdp.ConsumeIntInRange(-5, 1000)
    elif output_type == "error":
        output["ename"] = _fuzz_string(fdp, 20)
        output["evalue"] = _fuzz_string(fdp, 50)
        output["traceback"] = [_fuzz_string(fdp, 50) for _ in range(fdp.ConsumeIntInRange(0, 3))]
    return output


def TestOneInput(data: bytes) -> None:
    fdp = atheris.FuzzedDataProvider(data)
    notebook = {
        "nbformat": fdp.ConsumeIntInRange(1, 6),
        "nbformat_minor": fdp.ConsumeIntInRange(0, 8),
        "metadata": {_fuzz_string(fdp, 10): _fuzz_string(fdp, 20)},
        "cells": [_fuzz_cell(fdp) for _ in range(fdp.ConsumeIntInRange(0, 5))],
    }
    try:
        validate(notebook)
    except NotebookError:
        pass  # A validator reporting "invalid" via its own error type is correct.
    except (TypeError, ValueError):
        pass  # Malformed-shape input reaching a defensive type/value check.


def main() -> None:
    atheris.Setup(sys.argv, TestOneInput)
    atheris.Fuzz()


if __name__ == "__main__":
    main()
