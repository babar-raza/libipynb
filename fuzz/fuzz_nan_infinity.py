"""Fuzz libipynb.loads() specifically around the NaN/Infinity strict-mode
rejection path (LIBIPYNB-Q18/P0-C, LIBIPYNB-Q40, Phase 4).

fuzz_parser.py already fuzzes raw bytes through loads() in every mode, but
pure random byte mutation is extremely unlikely to stumble onto the exact
literal tokens "NaN"/"Infinity"/"-Infinity" sitting in a syntactically
valid JSON numeric position within a bounded time budget -- the same
reasoning fuzz_validator.py's own docstring gives for existing as a
structure-aware target separate from fuzz_parser.py. This target builds a
plausible notebook shape by hand (json.dumps can't emit these tokens
itself with allow_nan=False, so the JSON text is assembled directly) with
a fuzzer-chosen non-finite constant embedded at a fuzzer-chosen leaf
position, driving coverage reliably into codec/reader.py's
_reject_non_finite_constant instead of leaving it to chance.
"""

from __future__ import annotations

import json
import sys

import atheris

with atheris.instrument_imports():
    from libipynb import NotebookError, loads

_MODES = ("strict", "preservation", "recovery")
_CONSTANTS = ("NaN", "Infinity", "-Infinity", "42", "-1.5")
_LEAF_KEYS = ("nbformat_minor", "execution_count", "custom_numeric_field")


def _fuzz_string(fdp: atheris.FuzzedDataProvider, max_len: int = 20) -> str:
    return fdp.ConsumeUnicodeNoSurrogates(fdp.ConsumeIntInRange(0, max_len))


def _build_notebook_text(fdp: atheris.FuzzedDataProvider) -> tuple[str, bool]:
    constant = _CONSTANTS[fdp.ConsumeIntInRange(0, len(_CONSTANTS) - 1)]
    is_non_finite = constant in ("NaN", "Infinity", "-Infinity")
    leaf_key = _LEAF_KEYS[fdp.ConsumeIntInRange(0, len(_LEAF_KEYS) - 1)]
    cell_id = json.dumps(_fuzz_string(fdp, 10) or "a")
    source = json.dumps(_fuzz_string(fdp, 50))
    leaf_key_json = json.dumps(leaf_key)
    # Hand-assembled, not json.dumps for the whole structure -- the
    # non-finite tokens are not representable via the standard library's
    # own encoder under this project's allow_nan=False writer contract.
    # Every OTHER value is still individually json.dumps-escaped so the
    # surrounding document stays syntactically valid JSON.
    text = (
        "{"
        f'"nbformat": 4, "nbformat_minor": 5, "metadata": {{{leaf_key_json}: {constant}}}, '
        '"cells": [{'
        f'"cell_type": "code", "id": {cell_id}, "metadata": {{}}, '
        f'"source": {source}, "execution_count": null, "outputs": []'
        "}]"
        "}"
    )
    return text, is_non_finite


def TestOneInput(data: bytes) -> None:
    fdp = atheris.FuzzedDataProvider(data)
    mode = _MODES[fdp.ConsumeIntInRange(0, len(_MODES) - 1)]
    text, is_non_finite = _build_notebook_text(fdp)

    try:
        loads(text, mode=mode)
        rejected = False
    except NotebookError:
        rejected = True
    except UnicodeDecodeError:
        return  # Invalid UTF-8 in a fuzzed string, expected adversarial input.

    if is_non_finite and mode == "strict":
        # LIBIPYNB-Q18's own contract: strict mode must never silently
        # accept a non-finite JSON constant. A regression here (loads()
        # returning successfully instead of raising) is exactly the P0-C
        # bug this fuzz target exists to keep caught.
        assert rejected, (
            f"strict mode accepted a non-finite constant instead of rejecting it: {text!r}"
        )


def main() -> None:
    atheris.Setup(sys.argv, TestOneInput)
    atheris.Fuzz()


if __name__ == "__main__":
    main()
