"""Fuzz the P0-A/B truncation functions directly (LIBIPYNB-Q40, Phase 4).

Complements tests/property/test_property_output_truncation.py's Hypothesis
coverage of the same two functions: Hypothesis does example-based search
against explicit invariants; this does coverage-guided mutation against the
same invariants (LIBIPYNB-Q16/P0-A historically dropped whole cell results
by byte-slicing the raw combined stream before parsing; LIBIPYNB-Q17/P0-B's
`any()` short-circuit historically left later oversized outputs completely
unvisited -- still present in the list, but never actually truncated). A
genuinely different search strategy over the same boundary is worth having,
not a substitute for the property tests.

LIBIPYNB-Q40 Gate-G2 review finding (round 1): an earlier version of this
file only asserted `len(outputs) == original_count` after
`_truncate_outputs_if_needed` -- a real check (LIBIPYNB-Q16/P0-A's own bug
class), but one the historical P0-B `any()` short-circuit bug does NOT
violate: that bug never changed the list's length, only left later
oversized outputs un-truncated while still present. `_is_within_budget`
below (mirroring tests/property/test_property_output_truncation.py's own
helper of the same name) closes that gap by checking the actual
content-correctness invariant a short-circuit would violate.

LIBIPYNB-Q40 Gate-G2 review finding (round 2): `_is_within_budget` itself
only checks text-shaped payload size -- for a binary-MIME payload (the
`not _is_binary_mime_type(mime_type)` clause), the whole size condition is
forced False unconditionally, so it never actually verifies the
"oversized binary payloads are removed, not merely still present and
oversized" half of the invariant its own comment claims. A reintroduction
of the historical short-circuit bug would go completely undetected
whenever the skipped output happens to be binary-shaped rather than
text-shaped -- independently reproduced live by the round-2 reviewer.
`_originally_oversized_binary_mime_types` plus the explicit post-call
absence check in `TestOneInput` below close this for real: captured
*before* truncation runs (the only point at which "was this actually
oversized" is still knowable), checked *after* (that every such key is
now genuinely absent from `output["data"]`, not merely unchecked).
"""

from __future__ import annotations

import sys
from typing import Any

import atheris

with atheris.instrument_imports():
    from libipynb.adapters.execute import CellExecutionResult, _apply_output_budget
    from libipynb.adapters.jupyter_execute import _is_binary_mime_type, _truncate_outputs_if_needed

_OUTPUT_SHAPES = ("stream", "image/png", "image/svg+xml")


def _is_within_budget(output: dict[str, Any], max_bytes: int) -> bool:
    text = output.get("text")
    if isinstance(text, str) and len(text.encode("utf-8")) > max_bytes:
        return False
    data = output.get("data")
    if isinstance(data, dict):
        for mime_type, payload in data.items():
            # A binary-shaped oversized payload is expected to be *removed*
            # entirely, not shrunk -- its absence is what "within budget"
            # means for it, not a size check on a value that's gone.
            if (
                isinstance(payload, str)
                and len(payload.encode("utf-8")) > max_bytes
                and not (isinstance(mime_type, str) and _is_binary_mime_type(mime_type))
            ):
                return False
    return True


def _originally_oversized_binary_mime_types(output: dict[str, Any], max_bytes: int) -> set[str]:
    """The set of MIME keys in *output*'s ``data`` that are both
    binary-shaped and already over *max_bytes* -- computed BEFORE
    truncation runs, since that's the only point at which "was this
    actually oversized" is still knowable (truncation is expected to
    remove them entirely, not shrink them, so their size afterward tells
    you nothing)."""
    data = output.get("data")
    if not isinstance(data, dict):
        return set()
    return {
        mime_type
        for mime_type, payload in data.items()
        if isinstance(mime_type, str)
        and isinstance(payload, str)
        and _is_binary_mime_type(mime_type)
        and len(payload.encode("utf-8")) > max_bytes
    }


def _fuzz_output(fdp: atheris.FuzzedDataProvider) -> dict[str, Any]:
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
    originally_oversized_binary = (
        [_originally_oversized_binary_mime_types(o, output_max_bytes) for o in outputs]
        if output_max_bytes is not None
        else None
    )
    _truncate_outputs_if_needed(outputs, output_max_bytes)
    assert len(outputs) == original_count, (
        f"_truncate_outputs_if_needed changed the output count: "
        f"{original_count} in, {len(outputs)} out"
    )
    if output_max_bytes is not None:
        assert originally_oversized_binary is not None  # narrows for the loop below
        for output, oversized_binary_keys in zip(outputs, originally_oversized_binary, strict=True):
            assert _is_within_budget(output, output_max_bytes), (
                f"_truncate_outputs_if_needed left an output over budget "
                f"(max_bytes={output_max_bytes}): {output!r}"
            )
            # LIBIPYNB-Q40 Gate-G2 round-2 finding: _is_within_budget alone
            # cannot tell "binary payload still present and oversized"
            # (the historical short-circuit bug) apart from "binary
            # payload correctly removed" -- both look identical to it
            # (its own size check is unconditionally skipped for binary
            # MIME types). This explicit absence check closes that gap.
            remaining_data = output.get("data")
            still_present = (
                oversized_binary_keys & set(remaining_data)
                if isinstance(remaining_data, dict)
                else oversized_binary_keys
            )
            assert not still_present, (
                f"_truncate_outputs_if_needed left an originally-oversized binary "
                f"payload in place instead of removing it (max_bytes={output_max_bytes}): "
                f"{still_present!r} still present in {output!r}"
            )


def main() -> None:
    atheris.Setup(sys.argv, TestOneInput)
    atheris.Fuzz()


if __name__ == "__main__":
    main()
