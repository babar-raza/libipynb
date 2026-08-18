"""LIBIPYNB-Q6: a syntactically-valid JSON payload containing an unpaired
UTF-16 surrogate escape (e.g. ``\\ud800``) is legal per RFC 8259 -- Python's
``json.loads()`` decodes it fine into a ``str`` with a genuinely unpaired
surrogate character -- but crashes libipynb's own resource-limit UTF-8
byte-counting walk (``security/limits.py::_utf8_size``) with an uncaught
``UnicodeEncodeError``, in every parse mode including ``recovery`` (whose
entire documented purpose is graceful degradation on malformed input), and
crashes the writer specifically under ``profile='declared'`` -- the profile
every shipped CLI write path actually uses.
"""

from __future__ import annotations

import json

import pytest

from libipynb import (
    NotebookDocument,
    NotebookParseError,
    NotebookWriteError,
    dumps,
    loads,
    validate,
)
from libipynb.errors import NotebookResourceLimitError
from libipynb.security import IPYNB_DEFAULT_LIMITS

_LONE_SURROGATE_PAYLOAD = json.dumps(
    {
        "nbformat": 4,
        "nbformat_minor": 5,
        "metadata": {"bad": "\ud800broken"},
        "cells": [],
    },
    ensure_ascii=False,
)


@pytest.mark.parametrize("mode", ["strict", "preservation", "recovery"])
def test_lone_surrogate_raises_typed_parse_error_in_every_mode(mode: str) -> None:
    with pytest.raises(NotebookParseError) as excinfo:
        loads(_LONE_SURROGATE_PAYLOAD, mode=mode)
    assert excinfo.value.code == "IPYNB_INVALID_SURROGATE"


def test_lone_surrogate_in_a_cell_source_also_raises_a_typed_parse_error() -> None:
    payload = json.dumps(
        {
            "nbformat": 4,
            "nbformat_minor": 5,
            "metadata": {},
            "cells": [
                {
                    "cell_type": "code",
                    "id": "c",
                    "metadata": {},
                    "execution_count": None,
                    "outputs": [],
                    "source": "x = '\ud800'",
                }
            ],
        },
        ensure_ascii=False,
    )
    with pytest.raises(NotebookParseError) as excinfo:
        loads(payload, mode="preservation")
    assert excinfo.value.code == "IPYNB_INVALID_SURROGATE"


def test_lone_surrogate_raises_typed_write_error_under_declared_profile() -> None:
    """profile='declared' is exactly the profile every shipped CLI write
    path uses (dump()'s default targets 4.5 instead, which incidentally
    survives via validate()'s own broad exception handling -- see the
    'still produces a clean validation report' test below)."""
    doc = NotebookDocument(
        {"nbformat": 4, "nbformat_minor": 5, "metadata": {"bad": "\ud800"}, "cells": []}
    )

    with pytest.raises(NotebookWriteError) as excinfo:
        dumps(doc, profile="declared")
    assert excinfo.value.code == "IPYNB_INVALID_SURROGATE"


def test_lone_surrogate_still_produces_a_clean_validation_report_not_a_crash() -> None:
    report = validate(
        {"nbformat": 4, "nbformat_minor": 5, "metadata": {"bad": "\ud800"}, "cells": []}
    )

    assert not report.is_valid
    assert report.errors[0].code == "IPYNB_INVALID_SURROGATE"


def test_a_properly_paired_surrogate_round_trips_correctly() -> None:
    """Non-regression: only genuinely UNPAIRED surrogates are the problem --
    a real astral character (e.g. an emoji), which Python's json.loads()
    already recombines into one codepoint from a surrogate-pair escape
    before this code ever sees the string, must keep working."""
    payload = json.dumps(
        {"nbformat": 4, "nbformat_minor": 5, "metadata": {"emoji": "\U0001f600"}, "cells": []},
        ensure_ascii=False,
    )

    document = loads(payload, mode="strict")

    assert document.raw["metadata"]["emoji"] == "\U0001f600"
    assert dumps(document, profile="declared")  # must not raise


def test_well_formed_utf8_is_still_correctly_size_limited() -> None:
    """Non-regression: the fix must not weaken real max_decompressed_bytes
    enforcement for well-formed (non-surrogate) content."""
    tight_limits = IPYNB_DEFAULT_LIMITS.with_overrides(max_decompressed_bytes=1024)
    huge = "x" * 4096
    payload = json.dumps({"nbformat": 4, "nbformat_minor": 5, "metadata": {"k": huge}, "cells": []})

    with pytest.raises(NotebookResourceLimitError, match="max_decompressed_bytes"):
        loads(payload, mode="preservation", limits=tight_limits)
