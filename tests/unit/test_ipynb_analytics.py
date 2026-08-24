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
    attachment_size_summary,
    average_source_length,
    cell_type_histogram,
    execution_errors,
    has_execution_errors,
    largest_cells,
    metadata_size_breakdown,
    notebook_byte_size,
    output_size_histogram,
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


class TestLargestCells:
    def test_returns_list(self):
        result = largest_cells(VALID_DIR / "code-and-markdown.ipynb")
        assert isinstance(result, list)

    def test_sorted_largest_first(self):
        data = _nb(
            [
                {"cell_type": "code", "source": "ab", "metadata": {}},
                {"cell_type": "markdown", "source": "abcdefgh", "metadata": {}},
                {"cell_type": "code", "source": "abcd", "metadata": {}},
            ]
        )
        result = largest_cells(data)
        assert [entry["index"] for entry in result] == [1, 2, 0]
        assert [entry["source_length"] for entry in result] == [8, 4, 2]

    def test_ties_keep_original_order(self):
        data = _nb(
            [
                {"cell_type": "code", "source": "ab", "metadata": {}},
                {"cell_type": "code", "source": "cd", "metadata": {}},
            ]
        )
        result = largest_cells(data)
        assert [entry["index"] for entry in result] == [0, 1]

    def test_top_n_truncates(self):
        data = _nb([{"cell_type": "code", "source": str(i), "metadata": {}} for i in range(10)])
        assert len(largest_cells(data, top_n=3)) == 3

    def test_fewer_cells_than_top_n_returns_all(self):
        data = _nb([{"cell_type": "code", "source": "x", "metadata": {}}])
        assert len(largest_cells(data, top_n=5)) == 1

    def test_empty_notebook_returns_empty_list(self):
        assert largest_cells(_nb([])) == []

    def test_non_positive_top_n_rejected(self):
        with pytest.raises(ValueError, match="top_n"):
            largest_cells(_nb([]), top_n=0)

    def test_invalid_source_raises(self):
        with pytest.raises(NotebookParseError):
            largest_cells(INVALID_DIR / "missing-nbformat.ipynb")


class TestNotebookByteSize:
    def test_returns_positive_int_for_a_real_notebook(self):
        result = notebook_byte_size(VALID_DIR / "minimal.ipynb")
        assert isinstance(result, int)
        assert result > 0

    def test_matches_actual_json_encoding(self):
        # A dict input bypasses the loader's own recovery-mode field
        # synthesis (e.g. filling in a missing code cell's `outputs`/
        # `execution_count`), so this can compare byte-for-byte directly
        # -- a bytes/path input would legitimately differ once the loader
        # normalizes it first, which is expected, not a bug.
        model = {
            "nbformat": 4,
            "nbformat_minor": 5,
            "metadata": {},
            "cells": [{"cell_type": "code", "source": "x = 1", "metadata": {}}],
        }
        assert notebook_byte_size(model) == len(json.dumps(model, sort_keys=True).encode("utf-8"))

    def test_larger_notebook_has_larger_size(self):
        small = _nb([{"cell_type": "code", "source": "x", "metadata": {}}])
        large = _nb([{"cell_type": "code", "source": "x" * 1000, "metadata": {}}])
        assert notebook_byte_size(large) > notebook_byte_size(small)

    def test_invalid_source_raises(self):
        with pytest.raises(NotebookParseError):
            notebook_byte_size(INVALID_DIR / "missing-nbformat.ipynb")


class TestMetadataSizeBreakdown:
    def test_returns_both_keys(self):
        result = metadata_size_breakdown(VALID_DIR / "minimal.ipynb")
        assert set(result) == {"notebook_metadata_bytes", "cell_metadata_bytes"}

    def test_notebook_metadata_measured(self):
        notebook = json.loads(_nb([{"cell_type": "code", "source": "x", "metadata": {}}]))
        notebook["metadata"] = {"kernelspec": {"name": "python3"}}
        data = json.dumps(notebook).encode("utf-8")
        result = metadata_size_breakdown(data)
        assert result["notebook_metadata_bytes"] > 0

    def test_cell_metadata_summed_across_cells(self):
        data = _nb(
            [
                {"cell_type": "code", "source": "x", "metadata": {"tags": ["a"]}},
                {"cell_type": "code", "source": "y", "metadata": {"tags": ["b"]}},
            ]
        )
        no_meta = _nb(
            [
                {"cell_type": "code", "source": "x", "metadata": {}},
                {"cell_type": "code", "source": "y", "metadata": {}},
            ]
        )
        assert (
            metadata_size_breakdown(data)["cell_metadata_bytes"]
            > metadata_size_breakdown(no_meta)["cell_metadata_bytes"]
        )

    def test_empty_notebook_returns_zeros(self):
        result = metadata_size_breakdown(_nb([]))
        assert result["cell_metadata_bytes"] == 0

    def test_invalid_source_raises(self):
        with pytest.raises(NotebookParseError):
            metadata_size_breakdown(INVALID_DIR / "missing-nbformat.ipynb")


class TestExecutionErrors:
    def test_returns_list(self):
        result = execution_errors(VALID_DIR / "minimal.ipynb")
        assert isinstance(result, list)

    def test_names_the_failing_cell_and_error(self):
        data = _nb(
            [
                {"cell_type": "code", "source": "x = 1", "metadata": {}, "outputs": []},
                {
                    "cell_type": "code",
                    "source": "raise ValueError('boom')",
                    "metadata": {},
                    "outputs": [
                        {
                            "output_type": "error",
                            "ename": "ValueError",
                            "evalue": "boom",
                            "traceback": [],
                        }
                    ],
                },
            ]
        )
        result = execution_errors(data)
        assert result == [{"cell_index": 1, "ename": "ValueError", "evalue": "boom"}]

    def test_multiple_errors_across_cells_all_listed(self):
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
                },
                {
                    "cell_type": "code",
                    "source": "raise KeyError()",
                    "metadata": {},
                    "outputs": [
                        {"output_type": "error", "ename": "KeyError", "evalue": "", "traceback": []}
                    ],
                },
            ]
        )
        result = execution_errors(data)
        assert [e["cell_index"] for e in result] == [0, 1]

    def test_no_errors_returns_empty_list(self):
        data = _nb([{"cell_type": "code", "source": "print(1)", "metadata": {}, "outputs": []}])
        assert execution_errors(data) == []

    def test_markdown_cells_ignored(self):
        data = _nb([{"cell_type": "markdown", "source": "# hi", "metadata": {}}])
        assert execution_errors(data) == []

    def test_invalid_source_raises(self):
        with pytest.raises(NotebookParseError):
            execution_errors(INVALID_DIR / "missing-nbformat.ipynb")


class TestOutputSizeHistogram:
    def test_returns_dict(self):
        result = output_size_histogram(VALID_DIR / "with-outputs.ipynb")
        assert isinstance(result, dict)

    def test_stream_text_measured_in_bytes(self):
        data = _nb(
            [
                {
                    "cell_type": "code",
                    "source": "x",
                    "metadata": {},
                    "outputs": [{"output_type": "stream", "name": "stdout", "text": "hello"}],
                }
            ]
        )
        assert output_size_histogram(data) == {"stream": 5}

    def test_list_of_lines_text_summed(self):
        data = _nb(
            [
                {
                    "cell_type": "code",
                    "source": "x",
                    "metadata": {},
                    "outputs": [
                        {"output_type": "stream", "name": "stdout", "text": ["ab\n", "cd\n"]}
                    ],
                }
            ]
        )
        assert output_size_histogram(data) == {"stream": 6}

    def test_non_ascii_text_measured_as_utf8_bytes_not_characters(self):
        data = _nb(
            [
                {
                    "cell_type": "code",
                    "source": "x",
                    "metadata": {},
                    "outputs": [{"output_type": "stream", "name": "stdout", "text": "café"}],
                }
            ]
        )
        # "café" is 4 characters but 5 UTF-8 bytes (é is 2 bytes).
        assert output_size_histogram(data) == {"stream": 5}

    def test_display_data_mime_payloads_summed(self):
        data = _nb(
            [
                {
                    "cell_type": "code",
                    "source": "x",
                    "metadata": {},
                    "outputs": [
                        {
                            "output_type": "display_data",
                            "data": {"text/plain": "abc", "image/png": "iVBORw0"},
                            "metadata": {},
                        }
                    ],
                }
            ]
        )
        assert output_size_histogram(data) == {"display_data": 10}

    def test_empty_notebook_returns_empty_dict(self):
        assert output_size_histogram(_nb([])) == {}

    def test_invalid_source_raises(self):
        with pytest.raises(NotebookParseError):
            output_size_histogram(INVALID_DIR / "missing-nbformat.ipynb")


class TestAttachmentSizeSummary:
    def test_returns_both_keys(self):
        result = attachment_size_summary(VALID_DIR / "minimal.ipynb")
        assert set(result) == {"count", "total_bytes"}

    def test_no_attachments_returns_zeros(self):
        data = _nb([{"cell_type": "markdown", "source": "# hi", "metadata": {}}])
        assert attachment_size_summary(data) == {"count": 0, "total_bytes": 0}

    def test_counts_and_sizes_attachments(self):
        data = _nb(
            [
                {
                    "cell_type": "markdown",
                    "source": "![img](attachment:x.png)",
                    "metadata": {},
                    "attachments": {"x.png": {"image/png": "abcd"}},
                }
            ]
        )
        assert attachment_size_summary(data) == {"count": 1, "total_bytes": 4}

    def test_multiple_mime_representations_each_counted(self):
        data = _nb(
            [
                {
                    "cell_type": "markdown",
                    "source": "x",
                    "metadata": {},
                    "attachments": {"x": {"image/png": "ab", "image/svg+xml": "cde"}},
                }
            ]
        )
        result = attachment_size_summary(data)
        assert result == {"count": 2, "total_bytes": 5}

    def test_invalid_source_raises(self):
        with pytest.raises(NotebookParseError):
            attachment_size_summary(INVALID_DIR / "missing-nbformat.ipynb")
