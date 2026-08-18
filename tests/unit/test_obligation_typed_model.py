"""Failure-first proof for the typed notebook object model."""

from __future__ import annotations

import json
from copy import deepcopy

from hypothesis import given, settings
from hypothesis import strategies as st

from libipynb import (
    dumps,
    loads,
)
from libipynb.model import (
    CodeCell,
    DisplayDataOutput,
    ErrorOutput,
    ExecuteResultOutput,
    MarkdownCell,
    MimeBundle,
    RawCell,
    StreamOutput,
    UnknownCell,
    UnknownOutput,
)


def _model_vector() -> dict[str, object]:
    return {
        "nbformat": 4,
        "nbformat_minor": 6,
        "metadata": {},
        "cells": [
            {
                "cell_type": "markdown",
                "id": "markdown",
                "metadata": {"tags": ["docs"]},
                "source": ["logical ", "text"],
            },
            {
                "cell_type": "raw",
                "id": "raw",
                "metadata": {},
                "source": "raw text",
            },
            {
                "cell_type": "code",
                "id": "code",
                "metadata": {"tags": ["run"]},
                "source": ["print(", "'ok')"],
                "execution_count": 3,
                "outputs": [
                    {"output_type": "stream", "name": "stdout", "text": "ok\n"},
                    {
                        "output_type": "display_data",
                        "data": {"text/plain": "display"},
                        "metadata": {},
                    },
                    {
                        "output_type": "execute_result",
                        "execution_count": 3,
                        "data": {"application/vnd.example+json": {"value": 3}},
                        "metadata": {},
                    },
                    {
                        "output_type": "error",
                        "ename": "ValueError",
                        "evalue": "bad",
                        "traceback": ["ValueError: bad"],
                    },
                    {"output_type": "future_output", "vendor": {"keep": True}},
                ],
            },
            {
                "cell_type": "future_cell",
                "id": "future",
                "metadata": {"tags": ["future"]},
                "source": ["future ", "text"],
                "vendor": {"keep": True},
            },
        ],
    }


def test_typed_cells_outputs_and_logical_sources_preserve_raw_form() -> None:
    source = _model_vector()
    document = loads(json.dumps(source), mode="preservation")

    markdown, raw, code, unknown = document.cell_objects
    assert isinstance(markdown, MarkdownCell)
    assert isinstance(raw, RawCell)
    assert isinstance(code, CodeCell)
    assert isinstance(unknown, UnknownCell)
    assert markdown.source == "logical text"
    assert markdown.raw_source == ["logical ", "text"]
    assert code.source == "print('ok')"
    assert unknown.source == "future text"
    assert unknown.preservation_only

    stream, display, execute, error, unknown_output = code.output_objects
    assert isinstance(stream, StreamOutput)
    assert isinstance(display, DisplayDataOutput)
    assert isinstance(execute, ExecuteResultOutput)
    assert isinstance(error, ErrorOutput)
    assert isinstance(unknown_output, UnknownOutput)
    assert unknown_output.preservation_only
    assert isinstance(display.mime_bundle, MimeBundle)
    assert display.mime_bundle["text/plain"] == "display"
    assert execute.mime_bundle.mime_types == ("application/vnd.example+json",)

    assert document.raw == source
    assert json.loads(dumps(document, profile="declared")) == source


def test_mutating_to_dict_and_metadata_accessors_does_not_leak_into_raw() -> None:
    """LIBIPYNB-Q9 regression: NotebookDocument.to_dict()/.metadata,
    Cell.metadata, and Cell.outputs previously returned shallow copies --
    mutating a NESTED value obtained from any of them silently corrupted
    the live document.raw. Contrast-verified against Cell.attachments,
    which was already correctly deep-copied one level down, proving the
    object model itself is capable of true isolation."""
    document = loads(json.dumps(_model_vector()), mode="preservation")
    original_raw = deepcopy(document.raw)

    snapshot = document.to_dict()
    snapshot["cells"][0]["metadata"]["tags"].append("MUTATED")
    assert document.raw == original_raw

    metadata = document.metadata
    metadata["injected"] = "MUTATED"
    assert document.raw == original_raw

    (code_cell,) = [
        cell_obj for cell_obj in document.cell_objects if isinstance(cell_obj, CodeCell)
    ]
    cell_metadata = code_cell.metadata
    cell_metadata["tags"].append("MUTATED")
    assert document.raw == original_raw

    cell_outputs = code_cell.outputs
    cell_outputs[0]["text"] = "MUTATED"
    assert document.raw == original_raw


_json_scalar = st.one_of(
    st.none(), st.booleans(), st.integers(min_value=-1000, max_value=1000), st.text(max_size=20)
)
_json_value = st.recursive(
    _json_scalar,
    lambda children: st.one_of(
        st.lists(children, max_size=3),
        st.dictionaries(st.text(min_size=1, max_size=10), children, max_size=3),
    ),
    max_leaves=10,
)


@given(
    metadata_extra=st.dictionaries(st.text(min_size=1, max_size=10), _json_value, max_size=3),
    cell_metadata_extra=st.dictionaries(st.text(min_size=1, max_size=10), _json_value, max_size=3),
    output_text=st.text(max_size=50),
)
@settings(max_examples=100, deadline=None)
def test_mutating_accessors_never_leaks_into_raw_property(
    metadata_extra: dict[str, object],
    cell_metadata_extra: dict[str, object],
    output_text: str,
) -> None:
    """LIBIPYNB-Q9's own required verification calls for a Hypothesis
    property test alongside the concrete example above -- this exercises
    the same four accessors (`to_dict()`, `.metadata`, `Cell.metadata`,
    `Cell.outputs`) across a wide range of generated notebook-level and
    cell-level metadata shapes and output text content, rather than one
    hand-picked example."""
    vector = _model_vector()
    # Nested under an "extra" key (rather than merged directly) so a
    # generated key can never collide with a reserved field like "tags".
    vector["metadata"]["extra"] = metadata_extra
    code_cell_raw = next(cell for cell in vector["cells"] if cell["cell_type"] == "code")
    code_cell_raw["metadata"]["extra"] = cell_metadata_extra
    code_cell_raw["outputs"] = [{"output_type": "stream", "name": "stdout", "text": output_text}]

    document = loads(json.dumps(vector), mode="preservation")
    original_raw = deepcopy(document.raw)

    snapshot = document.to_dict()
    snapshot["metadata"]["MUTATED"] = True
    assert document.raw == original_raw

    live_metadata = document.metadata
    live_metadata["MUTATED"] = True
    assert document.raw == original_raw

    (code_cell,) = [
        cell_obj for cell_obj in document.cell_objects if isinstance(cell_obj, CodeCell)
    ]
    cell_metadata = code_cell.metadata
    cell_metadata["MUTATED"] = True
    assert document.raw == original_raw

    cell_outputs = code_cell.outputs
    cell_outputs[0]["text"] = "MUTATED"
    assert document.raw == original_raw


def test_typed_search_avoids_raw_dictionary_access() -> None:
    document = loads(json.dumps(_model_vector()), mode="preservation")

    assert [cell.id for cell in document.find_cells(cell_id="code")] == ["code"]
    assert [cell.id for cell in document.find_cells(cell_type="markdown")] == ["markdown"]
    assert [cell.id for cell in document.find_cells(tag="run")] == ["code"]
    assert [cell.id for cell in document.find_cells(source_text="text")] == [
        "markdown",
        "raw",
        "future",
    ]
