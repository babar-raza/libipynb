"""Failure-first proof for the typed notebook object model."""

from __future__ import annotations

import json

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


def test_typed_search_avoids_raw_dictionary_access() -> None:
    document = loads(json.dumps(_model_vector()), mode="preservation")

    assert [cell.id for cell in document.find_cells(cell_id="code")] == ["code"]
    assert [cell.id for cell in document.find_cells(cell_type="markdown")] == [
        "markdown"
    ]
    assert [cell.id for cell in document.find_cells(tag="run")] == ["code"]
    assert [cell.id for cell in document.find_cells(source_text="text")] == [
        "markdown",
        "raw",
        "future",
    ]
