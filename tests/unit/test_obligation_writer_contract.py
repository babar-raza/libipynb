"""TC-FF6-IPYNB-WRITER-CONTRACT-001: IPYNB-WRITE-001 against the shipped namespace.

`SAL-IPYNB-OBL-...FCCD0E0C` (MUST): write valid UTF-8 JSON with configurable
formatting and canonical key ordering that never reorders cells or outputs;
retain unknown fields and binary MIME payloads exactly. Its declared proof is
"Determinism byte-compare; binary-payload integrity fixtures" — both are taken
literally here.

Formatting is configurable; ordering is not. The obligation uses those two words
in one sentence about different things, so `indent` is exposed and `sort_keys`
deliberately is not: a caller able to disable canonical ordering could produce
output that violates the same obligation's determinism requirement.

This capability's only prior test file imported the deprecated `ipynb.*` shadow
package (GAP-017), so none of this was covered for the shipped namespace.
"""

from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any

import pytest

from libipynb import dump, dumps, loads, validate

INDENTS: list[int | None] = [None, 0, 1, 2, 4]

BINARY = bytes(range(256)) * 8
BINARY_B64 = base64.b64encode(BINARY).decode("ascii")
UNICODE_SOURCE = "héllo ☃ — naïve café 日本語"


def _notebook() -> dict[str, Any]:
    return {
        "nbformat": 4,
        "nbformat_minor": 5,
        "metadata": {
            "zeta": {"nested": 1},
            "alpha": 2,
            # kernelspec requires display_name as well as name; a partial one is
            # rejected, which is the schema doing its job.
            "kernelspec": {"name": "python3", "display_name": "Python 3"},
        },
        "cells": [
            {
                "cell_type": "code",
                "id": "zzz-last-alphabetically-but-first",
                "metadata": {},
                "execution_count": 2,
                "outputs": [
                    {
                        "output_type": "display_data",
                        "data": {
                            "image/png": BINARY_B64,
                            "application/vnd.acme+json": {"k": [3, 1, 2]},
                            "text/plain": UNICODE_SOURCE,
                        },
                        "metadata": {},
                    },
                    {"output_type": "stream", "name": "stdout", "text": ["second\n"]},
                ],
                "source": UNICODE_SOURCE,
            },
            {
                "cell_type": "markdown",
                "id": "aaa-first-alphabetically-but-second",
                "metadata": {},
                "source": "second cell",
            },
        ],
    }


def _write(indent: int | None | object = ..., document: dict[str, Any] | None = None) -> str:
    doc = loads(json.dumps(document or _notebook()))
    if indent is ...:
        return dumps(doc)
    return dumps(doc, indent=indent)  # type: ignore[arg-type]


# ── Configurable formatting (the clause that was missing) ──────────────────


def test_default_output_is_unchanged() -> None:
    """The default must stay byte-identical, or every existing digest breaks."""
    assert _write() == _write(indent=1)


@pytest.mark.parametrize("indent", [2, 4])
def test_indent_controls_the_indentation_width(indent: int) -> None:
    text = _write(indent=indent)
    assert f'\n{" " * indent}"cells"' in text


def test_indent_none_produces_compact_output() -> None:
    text = _write(indent=None)
    assert "\n" not in text
    assert len(text) < len(_write(indent=1))


def test_indent_zero_produces_newlines_without_leading_spaces() -> None:
    text = _write(indent=0)
    assert "\n" in text
    assert '\n"cells"' in text


# ── Canonical ordering survives every formatting choice ────────────────────


@pytest.mark.parametrize("indent", INDENTS)
def test_key_ordering_stays_canonical_at_every_indent(indent: int | None) -> None:
    parsed = json.loads(_write(indent=indent))
    assert list(parsed) == sorted(parsed)
    assert list(parsed["metadata"]) == sorted(parsed["metadata"])


@pytest.mark.parametrize("indent", INDENTS)
def test_cell_order_is_never_changed(indent: int | None) -> None:
    """Cell ids here are deliberately reverse-alphabetical: a writer that sorted
    them would pass a weaker fixture."""
    parsed = json.loads(_write(indent=indent))
    assert [cell["id"] for cell in parsed["cells"]] == [
        "zzz-last-alphabetically-but-first",
        "aaa-first-alphabetically-but-second",
    ]


@pytest.mark.parametrize("indent", INDENTS)
def test_output_order_is_never_changed(indent: int | None) -> None:
    parsed = json.loads(_write(indent=indent))
    outputs = parsed["cells"][0]["outputs"]
    assert [o["output_type"] for o in outputs] == ["display_data", "stream"]


def test_sort_keys_is_not_exposed() -> None:
    """Canonical ordering is non-negotiable: a caller must not be able to
    disable it and still call the result conformant."""
    import inspect

    assert "sort_keys" not in inspect.signature(dumps).parameters
    assert "sort_keys" not in inspect.signature(dump).parameters


# ── Determinism byte-compare (named in the required proof) ─────────────────


@pytest.mark.parametrize("indent", INDENTS)
def test_repeated_writes_are_byte_identical(indent: int | None) -> None:
    assert _write(indent=indent) == _write(indent=indent)


@pytest.mark.parametrize("indent", INDENTS)
def test_roundtrip_is_stable_across_two_passes(indent: int | None) -> None:
    once = _write(indent=indent)
    twice = dumps(loads(once), indent=indent)  # type: ignore[arg-type]
    assert once == twice


def test_formatting_changes_bytes_but_not_content() -> None:
    compact = _write(indent=None)
    wide = _write(indent=4)
    assert compact != wide
    assert json.loads(compact) == json.loads(wide)


# ── Binary payload integrity (named in the required proof) ─────────────────


@pytest.mark.parametrize("indent", INDENTS)
def test_binary_mime_payload_is_byte_exact_at_every_indent(
    indent: int | None,
) -> None:
    parsed = json.loads(_write(indent=indent))
    restored = parsed["cells"][0]["outputs"][0]["data"]["image/png"]
    assert restored == BINARY_B64
    assert base64.b64decode(restored) == BINARY


@pytest.mark.parametrize("indent", INDENTS)
def test_unknown_mime_entries_are_retained_at_every_indent(
    indent: int | None,
) -> None:
    parsed = json.loads(_write(indent=indent))
    assert parsed["cells"][0]["outputs"][0]["data"]["application/vnd.acme+json"] == {"k": [3, 1, 2]}


# ── Valid UTF-8 JSON ───────────────────────────────────────────────────────


@pytest.mark.parametrize("indent", INDENTS)
def test_non_ascii_is_written_as_utf8_not_escaped(indent: int | None) -> None:
    text = _write(indent=indent)
    assert UNICODE_SOURCE in text
    assert "\\u00e9" not in text


@pytest.mark.parametrize("indent", INDENTS)
def test_dump_writes_utf8_bytes_to_a_file(tmp_path: Path, indent: int | None) -> None:
    target = tmp_path / "notebook.ipynb"
    document = loads(json.dumps(_notebook()))
    dump(document, target, indent=indent)  # type: ignore[arg-type]
    raw = target.read_bytes()
    assert UNICODE_SOURCE.encode("utf-8") in raw
    # dump() deliberately terminates the file with a newline; dumps() does not.
    assert raw.decode("utf-8") == dumps(document, indent=indent) + "\n"  # type: ignore[arg-type]
    assert raw.endswith(b"\n")


@pytest.mark.parametrize("indent", INDENTS)
def test_written_notebook_still_validates(indent: int | None) -> None:
    assert validate(json.loads(_write(indent=indent)), profile="4.5").is_valid
