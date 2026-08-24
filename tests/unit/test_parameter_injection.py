"""LIBIPYNB-Q35: Papermill-style parameter injection (`libipynb.model.parameters`).

Cross-tool byte-for-byte comparison against real Papermill lives in
`tests/oracle/test_papermill_parity.py`, not here -- these are the
dependency-free unit tests: cell-placement logic, the two deliberate
explicit-rejection divergences (unsupported type, unsupported language),
dry_run, and provenance recording.
"""

from __future__ import annotations

import json
import math

import pytest

from libipynb import NotebookDocument, loads
from libipynb.model.parameters import (
    INJECTED_PARAMETERS_TAG,
    PARAMETERS_TAG,
    UnsupportedLanguageError,
    UnsupportedParameterTypeError,
    find_injected_parameters_cell_index,
    find_parameters_cell_index,
    inject_parameters,
)


def _document(
    *, cells: list[dict[str, object]], language: str | None = "python"
) -> NotebookDocument:
    metadata: dict[str, object] = {}
    if language is not None:
        metadata["kernelspec"] = {
            "name": "python3",
            "display_name": "Python 3",
            "language": language,
        }
    return loads(
        json.dumps({"nbformat": 4, "nbformat_minor": 5, "metadata": metadata, "cells": cells}),
        mode="preservation",
    )


def _code_cell(
    source: str, *, tags: list[str] | None = None, cell_id: str = "c"
) -> dict[str, object]:
    cell: dict[str, object] = {
        "cell_type": "code",
        "id": cell_id,
        "metadata": {"tags": tags} if tags else {},
        "source": source,
        "execution_count": None,
        "outputs": [],
    }
    return cell


class TestCellPlacement:
    def test_inserts_after_the_parameters_cell_when_one_exists(self) -> None:
        doc = _document(
            cells=[
                _code_cell("alpha = 0.1", tags=[PARAMETERS_TAG], cell_id="p"),
                _code_cell("print(alpha)", cell_id="body"),
            ]
        )

        report = inject_parameters(doc, {"alpha": 0.5})

        assert report.injected_cell_index == 1
        assert report.parameters_cell_found is True
        assert report.replaced_existing_injection is False
        assert [c["id"] for c in doc.cells] == ["p", doc.cells[1]["id"], "body"]
        assert doc.cells[1]["metadata"]["tags"] == [INJECTED_PARAMETERS_TAG]

    def test_inserts_at_the_top_when_no_parameters_cell_exists(self) -> None:
        doc = _document(cells=[_code_cell("print('hi')", cell_id="body")])

        report = inject_parameters(doc, {"alpha": 0.5})

        assert report.injected_cell_index == 0
        assert report.parameters_cell_found is False
        assert [c["id"] for c in doc.cells][1] == "body"

    def test_replaces_an_existing_injected_parameters_cell_in_place(self) -> None:
        doc = _document(
            cells=[
                _code_cell("alpha = 0.1", tags=[PARAMETERS_TAG], cell_id="p"),
                _code_cell("alpha = 0.3", tags=[INJECTED_PARAMETERS_TAG], cell_id="old-injection"),
                _code_cell("print(alpha)", cell_id="body"),
            ]
        )

        report = inject_parameters(doc, {"alpha": 0.9})

        assert report.replaced_existing_injection is True
        assert report.injected_cell_index == 1
        assert len(doc.cells) == 3  # not duplicated
        assert doc.cells[1]["id"] != "old-injection"  # a fresh cell, not a mutated old one
        assert "0.9" in doc.cells[1]["source"]

    def test_find_helpers_return_minus_one_when_absent(self) -> None:
        doc = _document(cells=[_code_cell("x = 1", cell_id="c1")])

        assert find_parameters_cell_index(doc) == -1
        assert find_injected_parameters_cell_index(doc) == -1

    def test_find_helpers_ignore_cells_with_no_tags_key_at_all(self) -> None:
        """A cell entirely lacking a `tags` key (valid nbformat -- tags is
        optional) must not crash the lookup, unlike real Papermill's own
        `find_first_tagged_cell_index`, which raises AttributeError on
        exactly this input (confirmed directly against its source) --
        deliberately more robust here, not a compatibility target."""
        cell = _code_cell("x = 1", cell_id="c1")
        assert "tags" not in cell["metadata"]  # _code_cell with tags=None omits the key entirely
        doc = _document(cells=[cell])

        assert find_parameters_cell_index(doc) == -1


class TestDryRun:
    def test_dry_run_reports_the_same_placement_without_mutating_anything(self) -> None:
        doc = _document(
            cells=[
                _code_cell("alpha = 0.1", tags=[PARAMETERS_TAG], cell_id="p"),
                _code_cell("print(alpha)", cell_id="body"),
            ]
        )

        report = inject_parameters(doc, {"alpha": 0.5}, dry_run=True)

        assert report.injected_cell_index == 1
        assert len(doc.cells) == 2  # unchanged
        assert [c["id"] for c in doc.cells] == ["p", "body"]
        assert "papermill" not in doc.raw.get("metadata", {})


class TestProvenance:
    def test_records_injected_parameters_in_metadata_papermill(self) -> None:
        doc = _document(cells=[_code_cell("x = 1", tags=[PARAMETERS_TAG], cell_id="p")])

        inject_parameters(doc, {"alpha": 0.5, "name": "run"})

        assert doc.raw["metadata"]["papermill"]["parameters"] == {"alpha": 0.5, "name": "run"}

    def test_re_injecting_overwrites_the_recorded_parameters_not_merges(self) -> None:
        doc = _document(cells=[_code_cell("x = 1", tags=[PARAMETERS_TAG], cell_id="p")])

        inject_parameters(doc, {"alpha": 0.5, "beta": 1})
        inject_parameters(doc, {"alpha": 0.9})

        assert doc.raw["metadata"]["papermill"]["parameters"] == {"alpha": 0.9}


class TestUnsupportedType:
    @pytest.mark.parametrize(
        "value",
        [
            object(),
            {1, 2, 3},  # a set -- JSON/papermill have no set type
            b"bytes",
            complex(1, 2),
            (1, 2, "three"),  # a tuple -- real papermill stringifies it; this rejects it
        ],
    )
    def test_rejects_a_top_level_unsupported_value(self, value: object) -> None:
        doc = _document(cells=[_code_cell("x = 1", tags=[PARAMETERS_TAG], cell_id="p")])

        with pytest.raises(UnsupportedParameterTypeError):
            inject_parameters(doc, {"bad": value})

    def test_rejects_an_unsupported_value_nested_inside_a_list(self) -> None:
        doc = _document(cells=[_code_cell("x = 1", tags=[PARAMETERS_TAG], cell_id="p")])

        with pytest.raises(UnsupportedParameterTypeError):
            inject_parameters(doc, {"items": [1, 2, object()]})

    def test_rejects_an_unsupported_value_nested_inside_a_dict(self) -> None:
        doc = _document(cells=[_code_cell("x = 1", tags=[PARAMETERS_TAG], cell_id="p")])

        with pytest.raises(UnsupportedParameterTypeError):
            inject_parameters(doc, {"config": {"a": 1, "b": object()}})

    def test_rejects_a_non_string_dict_key(self) -> None:
        doc = _document(cells=[_code_cell("x = 1", tags=[PARAMETERS_TAG], cell_id="p")])

        with pytest.raises(UnsupportedParameterTypeError):
            inject_parameters(doc, {"config": {1: "a"}})

    def test_rejection_happens_before_any_mutation_all_or_nothing(self) -> None:
        doc = _document(
            cells=[
                _code_cell("alpha = 0.1", tags=[PARAMETERS_TAG], cell_id="p"),
                _code_cell("print(alpha)", cell_id="body"),
            ]
        )

        with pytest.raises(UnsupportedParameterTypeError):
            inject_parameters(doc, {"alpha": 0.5, "bad": object()})

        assert len(doc.cells) == 2
        assert "papermill" not in doc.raw.get("metadata", {})


class TestUnsupportedLanguage:
    def test_rejects_a_notebook_with_a_non_python_declared_language(self) -> None:
        doc = _document(
            cells=[_code_cell("alpha <- 0.1", tags=[PARAMETERS_TAG], cell_id="p")], language="R"
        )

        with pytest.raises(UnsupportedLanguageError):
            inject_parameters(doc, {"alpha": 0.5})

    def test_a_notebook_with_no_declared_language_is_allowed(self) -> None:
        """No declared language is an under-specified notebook, not a
        positive claim it's some other language -- Python is attempted,
        matching how `execute`'s own kernel resolution treats an absent
        kernelspec (falls through to a default, doesn't refuse)."""
        doc = _document(
            cells=[_code_cell("alpha = 0.1", tags=[PARAMETERS_TAG], cell_id="p")], language=None
        )

        report = inject_parameters(doc, {"alpha": 0.5})

        assert report.injected_cell_index == 1


class TestPythonSourceGeneration:
    """Direct spot-checks; the exhaustive byte-for-byte oracle comparison
    against real Papermill lives in tests/oracle/test_papermill_parity.py."""

    def test_comment_line_is_first(self) -> None:
        doc = _document(cells=[_code_cell("x = 1", tags=[PARAMETERS_TAG], cell_id="p")])
        report = inject_parameters(doc, {"alpha": 1}, comment="My Comment")
        assert report.source.startswith("# My Comment\n")

    def test_empty_comment_still_emits_a_bare_comment_line_matching_real_papermill(self) -> None:
        """Real papermill's PythonTranslator.codify() always calls
        cls.comment(comment) unconditionally -- for an empty string,
        `f'# {cmt_str}'.strip()` reduces to a bare "#", not to no comment
        line at all. Verified directly against real papermill (Gate-G2
        review finding): real papermill's own output for comment="" is
        "#\\nalpha = 1\\n", not "alpha = 1\\n"."""
        doc = _document(cells=[_code_cell("x = 1", tags=[PARAMETERS_TAG], cell_id="p")])
        report = inject_parameters(doc, {"alpha": 1}, comment="")
        assert report.source == "#\nalpha = 1\n"

    def test_nan_and_infinity_are_valid_python_source_not_repr(self) -> None:
        doc = _document(cells=[_code_cell("x = 1", tags=[PARAMETERS_TAG], cell_id="p")])
        report = inject_parameters(
            doc, {"a": float("nan"), "b": float("inf"), "c": float("-inf")}, comment=""
        )
        assert "float('nan')" in report.source
        assert "float('inf')" in report.source
        assert "float('-inf')" in report.source
        # Sanity: these really do parse and evaluate as intended Python.
        namespace: dict[str, object] = {}
        exec(report.source, namespace)  # noqa: S102 -- generated from validated literals only
        assert math.isnan(namespace["a"])  # type: ignore[arg-type]
        assert namespace["b"] == math.inf
        assert namespace["c"] == -math.inf

    def test_an_empty_parameters_dict_produces_only_the_comment(self) -> None:
        doc = _document(cells=[_code_cell("x = 1", tags=[PARAMETERS_TAG], cell_id="p")])
        report = inject_parameters(doc, {})
        assert report.source == "# Parameters\n"


class TestInputValidation:
    def test_rejects_a_non_notebookdocument(self) -> None:
        with pytest.raises(TypeError):
            inject_parameters({"cells": []}, {"alpha": 1})  # type: ignore[arg-type]

    def test_rejects_a_non_dict_parameters_argument(self) -> None:
        doc = _document(cells=[_code_cell("x = 1", tags=[PARAMETERS_TAG], cell_id="p")])
        with pytest.raises(TypeError):
            inject_parameters(doc, [("alpha", 1)])  # type: ignore[arg-type]

    def test_rejects_a_non_string_parameter_name(self) -> None:
        doc = _document(cells=[_code_cell("x = 1", tags=[PARAMETERS_TAG], cell_id="p")])
        with pytest.raises(TypeError):
            inject_parameters(doc, {1: "a"})  # type: ignore[dict-item]


class TestDocumentConvenienceMethod:
    def test_document_inject_parameters_delegates_to_the_module_function(self) -> None:
        doc = _document(
            cells=[
                _code_cell("alpha = 0.1", tags=[PARAMETERS_TAG], cell_id="p"),
                _code_cell("print(alpha)", cell_id="body"),
            ]
        )

        report = doc.inject_parameters({"alpha": 0.7})

        assert report.injected_cell_index == 1
        assert doc.raw["metadata"]["papermill"]["parameters"] == {"alpha": 0.7}
