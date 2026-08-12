"""Tests for ipynb analytics functions.

Each function is exercised against real sample files (path-based) plus
inline byte sources, covering both the positive/behavior path and
malformed/boundary inputs.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from libipynb import NotebookParseError
from libipynb.analytics import (
    average_source_length,
    cell_type_histogram,
    has_execution_errors,
    output_type_histogram,
)

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
VALID_DIR = FIXTURES / "valid"
INVALID_DIR = FIXTURES / "invalid"


def _nb(cells: list[dict]) -> bytes:
    return json.dumps({"nbformat": 4, "nbformat_minor": 5, "metadata": {}, "cells": cells}).encode(
        "utf-8"
    )


class TestCellTypeHistogram:
    def test_returns_dict(self):
        result = cell_type_histogram(VALID_DIR / "minimal.ipynb")
        assert isinstance(result, dict)

    def test_code_and_markdown_counts(self):
        result = cell_type_histogram(VALID_DIR / "code-and-markdown.ipynb")
        assert result.get("markdown") == 5
        assert result.get("code") == 4

    def test_accepts_bytes(self):
        data = _nb([{"cell_type": "code", "source": "x", "metadata": {}}])
        assert cell_type_histogram(data) == {"code": 1}

    def test_multiple_cells_same_type(self):
        data = _nb(
            [
                {"cell_type": "markdown", "source": "a", "metadata": {}},
                {"cell_type": "markdown", "source": "b", "metadata": {}},
                {"cell_type": "code", "source": "c", "metadata": {}},
            ]
        )
        assert cell_type_histogram(data) == {"markdown": 2, "code": 1}

    def test_raw_cell_type_counted(self):
        data = _nb([{"cell_type": "raw", "source": "x", "metadata": {}}])
        assert cell_type_histogram(data) == {"raw": 1}

    def test_missing_cell_type_defaults_to_raw(self):
        data = _nb([{"source": "x", "metadata": {}}])
        assert cell_type_histogram(data) == {"raw": 1}

    def test_invalid_source_raises(self):
        with pytest.raises(NotebookParseError):
            cell_type_histogram(INVALID_DIR / "missing-nbformat.ipynb")


class TestOutputTypeHistogram:
    def test_returns_dict(self):
        result = output_type_histogram(VALID_DIR / "with-outputs.ipynb")
        assert isinstance(result, dict)

    def test_with_outputs_counts_execute_result(self):
        result = output_type_histogram(VALID_DIR / "with-outputs.ipynb")
        assert result.get("execute_result") == 1

    def test_markdown_only_cells_ignored(self):
        result = output_type_histogram(
            _nb([{"cell_type": "markdown", "source": "# no outputs", "metadata": {}}])
        )
        assert result == {}

    def test_accepts_bytes(self):
        data = _nb(
            [
                {
                    "cell_type": "code",
                    "source": "x",
                    "metadata": {},
                    "outputs": [{"output_type": "stream", "name": "stdout", "text": "hi"}],
                }
            ]
        )
        assert output_type_histogram(data) == {"stream": 1}

    def test_multiple_output_types(self):
        data = _nb(
            [
                {
                    "cell_type": "code",
                    "source": "x",
                    "metadata": {},
                    "outputs": [
                        {"output_type": "stream", "name": "stdout", "text": "hi"},
                        {"output_type": "error", "ename": "E", "evalue": "e", "traceback": []},
                    ],
                }
            ]
        )
        assert output_type_histogram(data) == {"stream": 1, "error": 1}

    def test_empty_cells_list_returns_empty_dict(self):
        assert output_type_histogram(_nb([])) == {}

    def test_invalid_source_raises(self):
        with pytest.raises(NotebookParseError):
            output_type_histogram(INVALID_DIR / "missing-nbformat.ipynb")


class TestAverageSourceLength:
    def test_returns_float(self):
        result = average_source_length(VALID_DIR / "code-and-markdown.ipynb")
        assert isinstance(result, float)

    def test_single_string_source(self):
        data = _nb([{"cell_type": "code", "source": "abcde", "metadata": {}}])
        assert average_source_length(data) == 5.0

    def test_list_of_lines_source(self):
        data = _nb([{"cell_type": "markdown", "source": ["abc", "de"], "metadata": {}}])
        assert average_source_length(data) == 5.0

    def test_average_across_multiple_cells(self):
        data = _nb(
            [
                {"cell_type": "code", "source": "ab", "metadata": {}},
                {"cell_type": "markdown", "source": "abcdefgh", "metadata": {}},
            ]
        )
        assert average_source_length(data) == 5.0

    def test_real_sample_nonzero(self):
        result = average_source_length(VALID_DIR / "with-outputs.ipynb")
        assert result > 0.0

    def test_missing_source_counts_as_zero(self):
        data = _nb([{"cell_type": "code", "metadata": {}}])
        assert average_source_length(data) == 0.0

    def test_invalid_source_raises(self):
        with pytest.raises(NotebookParseError):
            average_source_length(INVALID_DIR / "missing-nbformat.ipynb")


class TestHasExecutionErrors:
    def test_returns_bool(self):
        result = has_execution_errors(VALID_DIR / "minimal.ipynb")
        assert isinstance(result, bool)

    def test_error_output_detected(self):
        data = _nb(
            [
                {
                    "cell_type": "code",
                    "source": "1/0",
                    "metadata": {},
                    "outputs": [
                        {
                            "output_type": "error",
                            "ename": "ZeroDivisionError",
                            "evalue": "division by zero",
                            "traceback": [],
                        }
                    ],
                }
            ]
        )
        assert has_execution_errors(data) is True

    def test_stream_output_only_returns_false(self):
        data = _nb(
            [
                {
                    "cell_type": "code",
                    "source": "print(1)",
                    "metadata": {},
                    "outputs": [{"output_type": "stream", "name": "stdout", "text": "1\n"}],
                }
            ]
        )
        assert has_execution_errors(data) is False

    def test_error_in_second_cell_detected(self):
        data = _nb(
            [
                {"cell_type": "code", "source": "x = 1", "metadata": {}, "outputs": []},
                {
                    "cell_type": "code",
                    "source": "raise ValueError()",
                    "metadata": {},
                    "outputs": [
                        {
                            "output_type": "error",
                            "ename": "ValueError",
                            "evalue": "",
                            "traceback": [],
                        }
                    ],
                },
            ]
        )
        assert has_execution_errors(data) is True

    def test_markdown_cells_ignored(self):
        data = _nb([{"cell_type": "markdown", "source": "# hi", "metadata": {}}])
        assert has_execution_errors(data) is False

    def test_empty_notebook_returns_false(self):
        assert has_execution_errors(_nb([])) is False

    def test_invalid_source_raises(self):
        with pytest.raises(NotebookParseError):
            has_execution_errors(INVALID_DIR / "missing-nbformat.ipynb")
