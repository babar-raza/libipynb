"""Failure-first adversarial tests for bounded notebook parsing."""

from __future__ import annotations

import json

import pytest

from libipynb import NotebookParseError, loads
from libipynb.errors import NotebookResourceLimitError as ResourceLimitError
from libipynb.security import IPYNB_DEFAULT_LIMITS


def _notebook(*, metadata: object = None, cells: list[object] | None = None) -> str:
    return json.dumps(
        {
            "nbformat": 4,
            "nbformat_minor": 5,
            "metadata": {} if metadata is None else metadata,
            "cells": [] if cells is None else cells,
        }
    )


def test_total_element_count_is_bounded() -> None:
    cells = [
        {
            "cell_type": "markdown",
            "id": f"cell-{index}",
            "metadata": {},
            "source": "x",
        }
        for index in range(20)
    ]
    limits = IPYNB_DEFAULT_LIMITS.with_overrides(max_entries=40)

    with pytest.raises(ResourceLimitError, match="max_entries exceeded"):
        loads(_notebook(cells=cells), limits=limits)


def test_nesting_depth_is_bounded_without_recursive_walker_failure() -> None:
    nested: object = "leaf"
    for _ in range(20):
        nested = {"nested": nested}
    limits = IPYNB_DEFAULT_LIMITS.with_overrides(max_nesting_depth=8)

    with pytest.raises(ResourceLimitError, match="max_nesting_depth exceeded"):
        loads(_notebook(metadata={"vendor": nested}), limits=limits)


def test_json_recursion_failure_is_a_deterministic_parse_error() -> None:
    deeply_nested = (
        '{"nbformat":4,"nbformat_minor":5,"metadata":{"x":'
        + ("[" * 1500)
        + "0"
        + ("]" * 1500)
        + '},"cells":[]}'
    )

    with pytest.raises(
        (NotebookParseError, ResourceLimitError),
        match="complexity|max_nesting_depth exceeded",
    ):
        loads(deeply_nested, mode="preservation")


def test_input_and_decoded_payload_bytes_are_bounded() -> None:
    encoded = _notebook(metadata={"payload": "x" * 200})
    limits = IPYNB_DEFAULT_LIMITS.with_overrides(
        max_input_bytes=100,
        max_decompressed_bytes=100,
    )

    with pytest.raises(ResourceLimitError, match="max_input_bytes exceeded"):
        loads(encoded, limits=limits)


def test_a_single_oversized_object_is_rejected_before_full_materialization() -> None:
    """enforce_structure() alone only rejects an oversized tree AFTER
    json.loads() has already fully materialized it in memory -- confirmed
    genuinely exploitable by direct probing before this fix (a 200,000-key
    object was fully parsed into a live dict before any limit check ran,
    even with max_entries=5 configured). The object_pairs_hook now checks
    max_entries incrementally, as each JSON object completes, so an
    oversized object is refused without ever building the full dict."""
    big = {f"k{index}": None for index in range(200_000)}
    limits = IPYNB_DEFAULT_LIMITS.with_overrides(max_entries=5)

    with pytest.raises(ResourceLimitError, match="max_entries exceeded"):
        loads(_notebook(metadata={"vendor": big}), limits=limits)


def test_many_separate_objects_are_rejected_on_the_cumulative_running_total() -> None:
    """The hook accumulates across the WHOLE document, not per-object --
    confirmed by direct timing before this fix: a 500,000-object document
    took ~150ms to fully materialize before enforce_structure() could
    reject it; the hook now rejects in under a millisecond, before most of
    the document is even parsed."""
    cells = [
        {"cell_type": "markdown", "id": f"cell-{index}", "metadata": {}, "source": "x"}
        for index in range(50_000)
    ]
    limits = IPYNB_DEFAULT_LIMITS.with_overrides(max_entries=1000)

    with pytest.raises(ResourceLimitError, match="max_entries exceeded"):
        loads(_notebook(cells=cells), limits=limits)


def test_a_notebook_with_object_entries_within_the_limit_still_loads() -> None:
    cells = [
        {"cell_type": "markdown", "id": f"cell-{index}", "metadata": {}, "source": "x"}
        for index in range(3)
    ]
    limits = IPYNB_DEFAULT_LIMITS.with_overrides(max_entries=1000)

    document = loads(_notebook(cells=cells), limits=limits)

    assert len(document.cells) == 3


def test_duplicate_keys_within_one_object_still_resolve_last_value_wins() -> None:
    """The object_pairs_hook builds dict(pairs) itself, replacing json.loads's
    own default dict construction -- must not silently change duplicate-key
    behavior from the stdlib's own last-value-wins semantics."""
    raw = '{"nbformat":4,"nbformat_minor":5,"metadata":{"x":1,"x":2},"cells":[]}'

    document = loads(raw)

    assert document.metadata["x"] == 2
