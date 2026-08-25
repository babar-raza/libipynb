"""Fuzz the P0-A/B truncation functions directly (LIBIPYNB-Q40, Phase 4).

Complements tests/property/test_property_output_truncation.py's Hypothesis
coverage of the same two functions: Hypothesis does example-based search
against explicit invariants; this does coverage-guided mutation against the
one structural invariant that matters most for a crash-oriented fuzz
harness -- neither truncation function may ever change how many items it's
handed (LIBIPYNB-Q16/P0-A historically dropped whole cell results by
byte-slicing the raw combined stream before parsing; LIBIPYNB-Q17/P0-B's
`any()` short-circuit historically left later oversized outputs completely
unvisited, though still present in the list). A genuinely different search
strategy over the same boundary is worth having, not a substitute for the
property tests.
"""

from __future__ import annotations

import sys

import atheris

with atheris.instrument_imports():
    from libipynb.adapters.execute import CellExecutionResult, _apply_output_budget
    from libipynb.adapters.jupyter_execute import _truncate_outputs_if_needed

_OUTPUT_SHAPES = ("stream", "image/png", "image/svg+xml")


def _fuzz_output(fdp: atheris.FuzzedDataProvider) -> dict:
    shape = _OUTPUT_SHAPES[fdp.ConsumeIntInRange(0, len(_OUTPUT_SHAPES) - 1)]
    text = fdp.ConsumeUnicodeNoSurrogates(fdp.ConsumeIntInRange(0, 300))
    if shape == "stream":
        return {"output_type": "stream", "name": "stdout", "text": text}
    return {"output_type": "display_data", "data": {shape: text}}


def _fuzz_result(fdp: atheris.FuzzedDataProvider, index: int) -> CellExecutionResult:
    stdout = fdp.ConsumeUnicodeNoSurrogates(fdp.ConsumeIntInRange(0, 300))
    return CellExecutionResult(index=index, stdout=stdout)


def TestOneInput(data: bytes) -> None:
    fdp = atheris.FuzzedDataProvider(data)

    # LIBIPYNB-Q16 (P0-A): adapters.execute._apply_output_budget.
    result_count = fdp.ConsumeIntInRange(0, 15)
    results = tuple(_fuzz_result(fdp, i) for i in range(result_count))
    has_budget = fdp.ConsumeBool()
    max_bytes = fdp.ConsumeIntInRange(0, 500) if has_budget else None
    budgeted, _truncated_any = _apply_output_budget(results, max_bytes)
    assert len(budgeted) == len(results), (
        f"_apply_output_budget dropped results: {len(results)} in, {len(budgeted)} out"
    )

    # LIBIPYNB-Q17 (P0-B): adapters.jupyter_execute._truncate_outputs_if_needed.
    output_count = fdp.ConsumeIntInRange(0, 15)
    outputs = [_fuzz_output(fdp) for _ in range(output_count)]
    original_count = len(outputs)
    has_output_budget = fdp.ConsumeBool()
    output_max_bytes = fdp.ConsumeIntInRange(0, 500) if has_output_budget else None
    _truncate_outputs_if_needed(outputs, output_max_bytes)
    assert len(outputs) == original_count, (
        f"_truncate_outputs_if_needed changed the output count: "
        f"{original_count} in, {len(outputs)} out"
    )


def main() -> None:
    atheris.Setup(sys.argv, TestOneInput)
    atheris.Fuzz()


if __name__ == "__main__":
    main()
