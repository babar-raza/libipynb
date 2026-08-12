"""Tests for adversarial input handling.

Verifies that the parser and loader handle malformed, malicious, and
pathological inputs gracefully -- raising clear errors rather than
crashing or producing silent corruption.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from libipynb import NotebookParseError, NotebookResourceLimitError, load, loads
from libipynb.security.limits import NotebookResourceLimits

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
ADVERSARIAL = FIXTURES / "adversarial"


def _minimal_notebook(
    *,
    cells: list[dict] | None = None,
    metadata: dict | None = None,
) -> dict:
    """Build a minimal valid nbformat 4.5 notebook dict."""
    return {
        "nbformat": 4,
        "nbformat_minor": 5,
        "metadata": metadata
        or {
            "kernelspec": {
                "display_name": "Python 3",
                "language": "python",
                "name": "python3",
            },
        },
        "cells": cells or [],
    }


def _code_cell(
    source: str = "",
    *,
    cell_id: str = "cell-0",
    outputs: list[dict] | None = None,
) -> dict:
    return {
        "cell_type": "code",
        "id": cell_id,
        "metadata": {},
        "source": source,
        "execution_count": None,
        "outputs": outputs or [],
    }


# ---------------------------------------------------------------------------
# Truncated JSON
# ---------------------------------------------------------------------------


def test_truncated_json_raises_parse_error() -> None:
    """Loading a truncated JSON file must raise NotebookParseError."""
    fixture = ADVERSARIAL / "truncated-json.ipynb"
    assert fixture.exists(), f"Missing adversarial fixture: {fixture}"

    with pytest.raises(NotebookParseError):
        load(fixture)


def test_truncated_json_string_raises_parse_error() -> None:
    """An inline truncated JSON string must also raise NotebookParseError."""
    truncated = '{"nbformat": 4, "nbformat_minor": 5, "metadata": {}, "cells": [{"cell_type":'

    with pytest.raises(NotebookParseError):
        loads(truncated)


# ---------------------------------------------------------------------------
# Huge base64 output (within default limits)
# ---------------------------------------------------------------------------


def test_huge_base64_output_loads_within_limits() -> None:
    """The huge-base64-output fixture (~1 MiB) must load under default limits."""
    fixture = ADVERSARIAL / "huge-base64-output.ipynb"
    if not fixture.exists():
        pytest.skip("huge-base64-output.ipynb fixture not available")

    doc = load(fixture, mode="recovery")
    assert doc.cell_count >= 1

    # Verify there is at least one output with image data.
    for cell in doc.raw.get("cells", []):
        for output in cell.get("outputs", []):
            data = output.get("data", {})
            if "image/png" in data:
                assert len(data["image/png"]) > 1000, (
                    "Expected substantial base64 payload in image/png output"
                )
                return

    # If we get here, the fixture did not contain the expected output shape.
    pytest.fail("Fixture should contain at least one output with image/png data")


# ---------------------------------------------------------------------------
# Malformed base64 in output
# ---------------------------------------------------------------------------


def test_malformed_base64_in_output_handled() -> None:
    """A notebook with invalid base64 in an output must not crash the loader.

    The loader/parser operates on JSON structure, not base64 content, so
    invalid base64 should pass through parsing. The important thing is no
    unhandled exception or crash.
    """
    nb = _minimal_notebook(
        cells=[
            _code_cell(
                source="display(image)",
                cell_id="bad-b64",
                outputs=[
                    {
                        "output_type": "display_data",
                        "metadata": {},
                        "data": {
                            "image/png": "THIS-IS-NOT!!!VALID===BASE64@@@",
                        },
                    },
                ],
            ),
        ]
    )
    payload = json.dumps(nb)

    # Should load without crashing -- base64 validity is not a parse concern.
    doc = loads(payload, mode="recovery")
    assert doc.cell_count == 1


# ---------------------------------------------------------------------------
# Pathological Unicode
# ---------------------------------------------------------------------------


def test_null_bytes_in_source_handled() -> None:
    """Null bytes in cell source must not crash the parser."""
    nb = _minimal_notebook(
        cells=[
            _code_cell(source="print('hello\x00world')", cell_id="null-cell"),
        ]
    )
    payload = json.dumps(nb)

    # Should either load successfully or raise a clean error -- never crash.
    try:
        doc = loads(payload, mode="recovery")
        assert doc.cell_count == 1
    except (NotebookParseError, NotebookResourceLimitError):
        pass  # A clean error is acceptable.


def test_overlong_unicode_sequences_handled() -> None:
    """Source with unusual but valid Unicode must not crash the parser."""
    # Mix of high-plane characters that stress Unicode handling.
    exotic_source = (
        "x = '\U0001f4a9'  # pile of poo\n"
        "y = '\U0001f600'  # grinning face\n"
        "z = '\u200b\u200b\u200b'  # zero-width spaces\n"
        "w = '￿'  # max BMP\n"
    )
    nb = _minimal_notebook(
        cells=[
            _code_cell(source=exotic_source, cell_id="unicode-cell"),
        ]
    )
    payload = json.dumps(nb)

    doc = loads(payload, mode="recovery")
    assert doc.cell_count == 1


def test_pathological_unicode_in_metadata_handled() -> None:
    """Metadata with unusual Unicode must not crash the parser."""
    nb = _minimal_notebook(
        metadata={
            "kernelspec": {
                "display_name": "Python 3 \U0001f40d",
                "language": "python",
                "name": "python3",
            },
            "language_info": {
                "name": "python",
                "version": "3.12\x00.0",
            },
        },
        cells=[_code_cell(cell_id="meta-cell")],
    )
    payload = json.dumps(nb)

    try:
        doc = loads(payload, mode="recovery")
        assert doc.cell_count == 1
    except (NotebookParseError, NotebookResourceLimitError):
        pass  # A clean error is acceptable.


# ---------------------------------------------------------------------------
# Malicious metadata keys
# ---------------------------------------------------------------------------


def test_very_long_metadata_keys_handled() -> None:
    """Metadata with extremely long keys must not crash or hang the parser."""
    long_key = "a" * 100_000
    nb = _minimal_notebook(
        metadata={
            "kernelspec": {
                "display_name": "Python 3",
                "language": "python",
                "name": "python3",
            },
            long_key: "value",
        },
        cells=[_code_cell(cell_id="longkey-cell")],
    )
    payload = json.dumps(nb)

    # Should load or raise cleanly -- never hang or crash.
    try:
        doc = loads(payload, mode="recovery")
        assert doc.cell_count == 1
    except (NotebookParseError, NotebookResourceLimitError):
        pass


def test_deeply_nested_metadata_handled() -> None:
    """Deeply nested metadata must be caught by nesting-depth limits."""
    # Build 100 levels of nesting.
    inner: dict = {"leaf": True}
    for i in range(100):
        inner = {f"level_{i}": inner}

    nb = _minimal_notebook(
        metadata={
            "kernelspec": {
                "display_name": "Python 3",
                "language": "python",
                "name": "python3",
            },
            "deep": inner,
        },
        cells=[_code_cell(cell_id="deep-cell")],
    )
    payload = json.dumps(nb)

    # With default max_nesting_depth=64, 100 levels should be caught.
    with pytest.raises(NotebookResourceLimitError, match="max_nesting_depth"):
        loads(payload)


def test_many_metadata_keys_counted_as_entries() -> None:
    """Notebooks with thousands of metadata keys must hit the max_entries limit."""
    bloated_metadata = {f"key_{i}": f"val_{i}" for i in range(500)}
    bloated_metadata["kernelspec"] = {
        "display_name": "Python 3",
        "language": "python",
        "name": "python3",
    }
    nb = _minimal_notebook(
        metadata=bloated_metadata,
        cells=[_code_cell(cell_id="bloat-cell")],
    )
    payload = json.dumps(nb)

    tight_limits = NotebookResourceLimits(max_entries=50)

    with pytest.raises(NotebookResourceLimitError, match="max_entries"):
        loads(payload, limits=tight_limits)


# ---------------------------------------------------------------------------
# Completely invalid inputs
# ---------------------------------------------------------------------------


def test_empty_string_raises_parse_error() -> None:
    """An empty string must raise NotebookParseError, not a generic exception."""
    with pytest.raises(NotebookParseError):
        loads("")


def test_non_json_input_raises_parse_error() -> None:
    """Arbitrary non-JSON text must raise NotebookParseError."""
    with pytest.raises(NotebookParseError):
        loads("this is not json at all")


def test_json_array_raises_parse_error() -> None:
    """A valid JSON array (not an object) must raise NotebookParseError."""
    with pytest.raises(NotebookParseError):
        loads("[1, 2, 3]")
