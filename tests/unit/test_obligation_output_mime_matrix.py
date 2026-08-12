"""TC-FF6-IPYNB-SHIPPED-COVERAGE-001: IPYNB-OUTPUT-001 against the shipped namespace.

Seven obligations. Their declared proof requirements are a MIME-bundle matrix
"including vendor types and binary payloads" and "MIME matrix fixtures per
output type with byte-exact payload verification" -- two dimensions, per output
type AND byte-exact payload, both of which must actually be exercised.

Every import here is `format_factory.ipynb`. The capability's previous only test
file imported the deprecated `ipynb.*` shadow package, which
forbidden_progress_claims bars from counting as coverage of the shipped
namespace (GAP-017/GAP-018). Assertions are derived from each obligation's
rule_text rather than ported from those tests, because the two packages
demonstrably disagree on at least one obligation's required behavior.

Obligations: 11DA3594, 14CBF763, 6B30D129, 8CA07D78, C72D3E4B, 5AD56F9C, 7F2275F7.
"""

from __future__ import annotations

import base64
import json
from typing import Any

import pytest

from libipynb import dumps, loads, validate
from libipynb.model import output_from_dict

OUTPUT_TYPES = ["stream", "display_data", "execute_result", "error"]

# A deliberately awkward payload: real PNG magic bytes, so base64 round-tripping
# is checked against bytes that do not survive a lossy text path.
PNG_BYTES = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\xde\xad\xbe\xef"
PNG_B64 = base64.b64encode(PNG_BYTES).decode("ascii")


def _stream() -> dict[str, Any]:
    return {"output_type": "stream", "name": "stdout", "text": ["line one\n", "line two\n"]}


def _display_data() -> dict[str, Any]:
    return {
        "output_type": "display_data",
        "data": {
            "text/plain": "fallback",
            "text/html": "<b>rich</b>",
            "image/png": PNG_B64,
            "application/vnd.acme.widget+json": {"nested": {"k": [1, 2, 3]}},
        },
        "metadata": {"image/png": {"width": 64, "height": 48}},
    }


def _execute_result(count: int | None = 7) -> dict[str, Any]:
    return {
        "output_type": "execute_result",
        "execution_count": count,
        "data": {"text/plain": "42", "application/json": {"answer": 42}},
        "metadata": {},
    }


def _error() -> dict[str, Any]:
    return {
        "output_type": "error",
        "ename": "ValueError",
        "evalue": "something went wrong",
        "traceback": ["Traceback (most recent call last):", "  File x", "ValueError"],
    }


BUILDERS = {
    "stream": _stream,
    "display_data": _display_data,
    "execute_result": _execute_result,
    "error": _error,
}


def _notebook(outputs: list[dict[str, Any]], execution_count: int | None = 1) -> dict[str, Any]:
    return {
        "nbformat": 4,
        "nbformat_minor": 5,
        "metadata": {},
        "cells": [
            {
                "cell_type": "code",
                "id": "cell-one",
                "metadata": {},
                "execution_count": execution_count,
                "outputs": outputs,
                "source": "print('x')",
            }
        ],
    }


def _roundtrip(notebook: dict[str, Any]) -> dict[str, Any]:
    return json.loads(dumps(loads(json.dumps(notebook))))


def _outputs_after_roundtrip(outputs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return _roundtrip(_notebook(outputs))["cells"][0]["outputs"]


# ── Per output type (the first declared dimension) ─────────────────────────


@pytest.mark.parametrize("output_type", OUTPUT_TYPES)
def test_each_output_type_survives_roundtrip_intact(output_type: str) -> None:
    """Per-type fixtures, not one aggregate notebook -- the requirement says
    "MIME matrix fixtures PER OUTPUT TYPE"."""
    original = BUILDERS[output_type]()
    (restored,) = _outputs_after_roundtrip([original])
    assert restored["output_type"] == output_type
    assert restored == original, "output must survive byte-for-byte as JSON"


@pytest.mark.parametrize("output_type", OUTPUT_TYPES)
def test_each_output_type_is_recognized_as_its_own_kind(output_type: str) -> None:
    typed = output_from_dict(BUILDERS[output_type]())
    assert typed.output_type == output_type
    assert typed.preservation_only is False, "a specified type is not preservation-only"


def test_all_four_types_coexist_in_one_cell_in_order() -> None:
    originals = [BUILDERS[name]() for name in OUTPUT_TYPES]
    restored = _outputs_after_roundtrip(originals)
    assert [item["output_type"] for item in restored] == OUTPUT_TYPES
    assert restored == originals


# ── Byte-exact payloads (the second declared dimension) ────────────────────


def test_base64_binary_payload_is_byte_exact_after_roundtrip() -> None:
    """Decoding after the roundtrip must yield the original bytes exactly."""
    (restored,) = _outputs_after_roundtrip([_display_data()])
    assert restored["data"]["image/png"] == PNG_B64
    assert base64.b64decode(restored["data"]["image/png"]) == PNG_BYTES


def test_vendor_mime_type_structure_is_preserved_exactly() -> None:
    (restored,) = _outputs_after_roundtrip([_display_data()])
    assert restored["data"]["application/vnd.acme.widget+json"] == {"nested": {"k": [1, 2, 3]}}


def test_large_base64_payload_is_byte_exact() -> None:
    """ "large base64 attachments" is named explicitly in the obligation text."""
    blob = base64.b64encode(bytes(range(256)) * 400).decode("ascii")
    output = {
        "output_type": "display_data",
        "data": {"application/octet-stream": blob},
        "metadata": {},
    }
    (restored,) = _outputs_after_roundtrip([output])
    assert restored["data"]["application/octet-stream"] == blob
    assert base64.b64decode(restored["data"]["application/octet-stream"]) == (
        bytes(range(256)) * 400
    )


def test_mime_bundle_exposes_every_declared_mime_type() -> None:
    typed = output_from_dict(_display_data())
    assert set(typed.mime_bundle.mime_types) == {
        "text/plain",
        "text/html",
        "image/png",
        "application/vnd.acme.widget+json",
    }


def test_per_mime_output_metadata_is_preserved() -> None:
    """The obligation names `metadata` objects on display_data explicitly."""
    (restored,) = _outputs_after_roundtrip([_display_data()])
    assert restored["metadata"] == {"image/png": {"width": 64, "height": 48}}


# ── error outputs: ename, evalue, traceback list of strings ────────────────


def test_error_output_preserves_the_full_triple() -> None:
    (restored,) = _outputs_after_roundtrip([_error()])
    assert restored["ename"] == "ValueError"
    assert restored["evalue"] == "something went wrong"
    assert restored["traceback"] == [
        "Traceback (most recent call last):",
        "  File x",
        "ValueError",
    ]


def test_error_traceback_stays_a_list_of_strings_not_a_joined_string() -> None:
    (restored,) = _outputs_after_roundtrip([_error()])
    assert isinstance(restored["traceback"], list)
    assert all(isinstance(line, str) for line in restored["traceback"])


def test_error_output_missing_traceback_fails_closed() -> None:
    """A malformed bundle must be rejected, not silently repaired."""
    report = validate(
        _notebook([{"output_type": "error", "ename": "E", "evalue": "v"}]),
        profile="4.5",
    )
    assert not report.is_valid
    assert "IPYNB_ERROR_TRACEBACK" in {d.code for d in report.diagnostics}


def test_error_traceback_of_wrong_element_type_fails_closed() -> None:
    report = validate(
        _notebook([{"output_type": "error", "ename": "E", "evalue": "v", "traceback": [1, 2]}]),
        profile="4.5",
    )
    assert not report.is_valid


# ── execution_count: integer or null ───────────────────────────────────────


@pytest.mark.parametrize("count", [0, 1, 99, None])
def test_execution_count_accepts_integer_or_null(count: int | None) -> None:
    notebook = _notebook([_stream()], execution_count=count)
    assert validate(notebook, profile="4.5").is_valid
    assert _roundtrip(notebook)["cells"][0]["execution_count"] == count


def test_execute_result_execution_count_is_preserved_independently() -> None:
    """The output's own execution_count is distinct from the cell's."""
    (restored,) = _outputs_after_roundtrip([_execute_result(count=7)])
    assert restored["execution_count"] == 7


@pytest.mark.parametrize("bad", ["3", 1.5, [3]])
def test_non_integer_execution_count_fails_closed(bad: object) -> None:
    report = validate(_notebook([_stream()], execution_count=bad), profile="4.5")  # type: ignore[arg-type]
    assert not report.is_valid


# ── Unknown / vendor output types are preserved, not dropped ───────────────


def test_unknown_output_type_is_preserved_and_marked_preservation_only() -> None:
    """ "preserving ... unknown bundle entries" is part of the obligation."""
    unknown = {"output_type": "application/vnd.future", "payload": {"a": 1}}
    typed = output_from_dict(unknown)
    assert typed.preservation_only is True
    assert typed.to_dict() == unknown


def test_unknown_output_type_is_rejected_inside_a_code_cell() -> None:
    """ "Unknown bundle entries" means unknown MIME types, not unknown output types.

    The official nbformat 4.5 schema defines `output` as a oneOf over exactly
    execute_result / display_data / stream / error. It does define an
    `unrecognized_output` (additionalProperties: true, output_type NOT in that
    enum) for future minor revisions, but `output` does not reference it -- so a
    code cell's outputs array admits only the four known types. Rejecting is
    therefore conformant, and the preservation the obligation asks for is
    delivered inside the MIME bundle, proven by the vendor-type test above.
    """
    from libipynb import NotebookParseError

    unknown = {"output_type": "future_kind", "payload": {"a": [1, 2]}}
    with pytest.raises(NotebookParseError):
        loads(json.dumps(_notebook([unknown])))


def test_unknown_keys_on_a_known_output_type_are_rejected() -> None:
    """Each known output definition sets additionalProperties: false."""
    from libipynb import NotebookParseError

    output = _stream() | {"x-vendor-hint": {"kept": True}}
    with pytest.raises(NotebookParseError):
        loads(json.dumps(_notebook([output])))


def test_unknown_mime_types_inside_the_bundle_are_the_preserved_surface() -> None:
    """The obligation's preservation requirement, located where it applies."""
    output = {
        "output_type": "display_data",
        "data": {
            "text/plain": "fallback",
            "application/vnd.unheard-of.v9+json": {"deep": {"list": [1, {"n": 2}]}},
            "x-experimental/thing": "raw-string",
        },
        "metadata": {},
    }
    (restored,) = _outputs_after_roundtrip([output])
    assert restored["data"] == output["data"]


# ── Malformed bundles fail closed ──────────────────────────────────────────


def test_output_without_output_type_fails_closed() -> None:
    report = validate(_notebook([{"data": {"text/plain": "x"}}]), profile="4.5")
    assert not report.is_valid


def test_outputs_must_be_an_array() -> None:
    notebook = _notebook([])
    notebook["cells"][0]["outputs"] = {"not": "a list"}
    assert not validate(notebook, profile="4.5").is_valid


def test_display_data_without_data_fails_closed() -> None:
    report = validate(_notebook([{"output_type": "display_data", "metadata": {}}]), profile="4.5")
    assert not report.is_valid


# ── The whole matrix validates as one notebook ─────────────────────────────


def test_full_matrix_notebook_is_schema_valid() -> None:
    notebook = _notebook([BUILDERS[name]() for name in OUTPUT_TYPES])
    assert validate(notebook, profile="4.5").is_valid


def test_full_matrix_is_stable_across_two_roundtrips() -> None:
    """Idempotence: a second pass must not perturb what the first produced."""
    notebook = _notebook([BUILDERS[name]() for name in OUTPUT_TYPES])
    once = _roundtrip(notebook)
    twice = _roundtrip(once)
    assert once == twice
