"""LIBIPYNB-Q35 Gate G8: real oracle comparison against installed `papermill`.

Calls papermill's own real, installed `parameterize_notebook()` (via its
own `load_notebook_node()` loader, which is what actually initializes the
`metadata.papermill`/per-cell `metadata.tags` scaffolding
`parameterize_notebook()` assumes already exists -- confirmed directly by
reading `papermill/iorw.py`; calling `parameterize_notebook()` on a raw,
never-papermill-touched notebook raises `AttributeError`, which is not a
libipynb bug, it's real papermill's own documented internal precondition)
and compares its generated injected-cell source, byte for byte, against
`libipynb.model.parameters.inject_parameters()`'s output for the same
parameters.

Environmental precondition (Gate-G2 review finding): real papermill's own
`PythonTranslator.codify()` pipes its output through `black` if that
package happens to be importable in the environment running it. `black`
is not installed here and is not a papermill dependency, so this
comparison is valid in this environment -- but the "byte-for-byte" parity
these tests assert is contingent on that, not an unconditional guarantee.
If `black` is ever added to this project's dev/test dependencies, these
tests would start failing for a reason unrelated to any libipynb
regression, not because parity was actually lost.
"""

from __future__ import annotations

import json
import os
import tempfile
from typing import Any

from libipynb import loads
from libipynb.model.parameters import PARAMETERS_TAG, inject_parameters


def _notebook_dict(*, cell_id: str = "params") -> dict[str, Any]:
    return {
        "nbformat": 4,
        "nbformat_minor": 5,
        "metadata": {
            "kernelspec": {"name": "python3", "display_name": "Python 3", "language": "python"}
        },
        "cells": [
            {
                "cell_type": "code",
                "id": cell_id,
                "metadata": {"tags": [PARAMETERS_TAG]},
                "execution_count": None,
                "outputs": [],
                "source": "pass",
            },
            {
                "cell_type": "code",
                "id": "body",
                "metadata": {"tags": []},
                "execution_count": None,
                "outputs": [],
                "source": "pass",
            },
        ],
    }


def _real_papermill_injected_source(
    parameters: dict[str, Any], *, comment: str = "Parameters"
) -> str:
    from papermill.iorw import load_notebook_node
    from papermill.parameterize import parameterize_notebook

    fd, path = tempfile.mkstemp(suffix=".ipynb")
    try:
        os.write(fd, json.dumps(_notebook_dict()).encode("utf-8"))
        os.close(fd)
        nb = load_notebook_node(path)
    finally:
        os.unlink(path)

    result = parameterize_notebook(nb, parameters, comment=comment)
    injected = next(
        cell
        for cell in result.cells
        if "injected-parameters" in cell.get("metadata", {}).get("tags", [])
    )
    source: str = injected["source"]
    return source


def _libipynb_injected_source(parameters: dict[str, Any], *, comment: str = "Parameters") -> str:
    document = loads(json.dumps(_notebook_dict()), mode="preservation")
    report = inject_parameters(document, parameters, comment=comment)
    return report.source


class TestGeneratedSourceMatchesRealPapermill:
    """Every case here is a real value libipynb's own supported-type set
    (str/bool/int/float/None/list/dict) accepts -- the divergent,
    deliberately-unsupported cases are covered separately, not here, since
    real papermill itself has no equivalent rejection to compare against
    for them (see the module docstring of libipynb.model.parameters)."""

    def test_scalars(self, papermill_available: None) -> None:
        params = {"alpha": 0.5, "count": 42, "name": "run-1", "enabled": True, "disabled": False}
        assert _libipynb_injected_source(params) == _real_papermill_injected_source(params)

    def test_none_value(self, papermill_available: None) -> None:
        params = {"maybe": None}
        assert _libipynb_injected_source(params) == _real_papermill_injected_source(params)

    def test_negative_and_zero_numbers(self, papermill_available: None) -> None:
        params = {"a": -42, "b": 0, "c": -3.14, "d": -0.0}
        assert _libipynb_injected_source(params) == _real_papermill_injected_source(params)

    def test_non_finite_floats(self, papermill_available: None) -> None:
        params = {"nan": float("nan"), "pos_inf": float("inf"), "neg_inf": float("-inf")}
        assert _libipynb_injected_source(params) == _real_papermill_injected_source(params)

    def test_strings_needing_escaping(self, papermill_available: None) -> None:
        params = {
            "quoted": 'has "double quotes"',
            "apostrophe": "it's got one",
            "both": '"both" kinds\' here',
            "backslash": "a\\b",
            "newline_and_tab": "line1\nline2\ttabbed",
        }
        assert _libipynb_injected_source(params) == _real_papermill_injected_source(params)

    def test_unicode_string(self, papermill_available: None) -> None:
        params = {"text": "café 日本語 \U0001f600"}
        assert _libipynb_injected_source(params) == _real_papermill_injected_source(params)

    def test_empty_string(self, papermill_available: None) -> None:
        params = {"empty": ""}
        assert _libipynb_injected_source(params) == _real_papermill_injected_source(params)

    def test_lists(self, papermill_available: None) -> None:
        params = {"nums": [1, 2, 3], "mixed": ["a", 1, True, None, 2.5], "nested": [[1, 2], [3, 4]]}
        assert _libipynb_injected_source(params) == _real_papermill_injected_source(params)

    def test_dicts(self, papermill_available: None) -> None:
        params = {
            "flat": {"k": "v", "n": 1},
            "nested": {"outer": {"inner": [1, 2, {"deep": True}]}},
        }
        assert _libipynb_injected_source(params) == _real_papermill_injected_source(params)

    def test_empty_containers(self, papermill_available: None) -> None:
        params = {"empty_list": [], "empty_dict": {}}
        assert _libipynb_injected_source(params) == _real_papermill_injected_source(params)

    def test_empty_parameters(self, papermill_available: None) -> None:
        assert _libipynb_injected_source({}) == _real_papermill_injected_source({})

    def test_empty_comment(self, papermill_available: None) -> None:
        """Gate-G2 review finding: an earlier version omitted the comment
        line entirely for comment="", diverging from real papermill's own
        `f'# {cmt_str}'.strip()`, which still emits a bare "#" line."""
        params = {"alpha": 1}
        assert _libipynb_injected_source(params, comment="") == _real_papermill_injected_source(
            params, comment=""
        )

    def test_custom_comment(self, papermill_available: None) -> None:
        params = {"alpha": 1}
        assert _libipynb_injected_source(
            params, comment="Custom label"
        ) == _real_papermill_injected_source(params, comment="Custom label")


class TestTagConventionMatchesRealPapermill:
    def test_papermill_recognizes_a_libipynb_injected_cell_as_its_own(
        self, papermill_available: None
    ) -> None:
        """A notebook libipynb already injected into must look like a
        normal, re-injectable input to real papermill -- not a foreign
        artifact papermill fails to recognize."""
        from papermill.parameterize import parameterize_notebook
        from papermill.utils import find_first_tagged_cell_index

        document = loads(json.dumps(_notebook_dict()), mode="preservation")
        inject_parameters(document, {"alpha": 0.5})

        fd, path = tempfile.mkstemp(suffix=".ipynb")
        try:
            os.write(fd, json.dumps(document.raw).encode("utf-8"))
            os.close(fd)
            from papermill.iorw import load_notebook_node

            nb = load_notebook_node(path)
        finally:
            os.unlink(path)

        assert find_first_tagged_cell_index(nb, "injected-parameters") == 1

        # Real papermill re-parameterizing a libipynb-injected notebook
        # must replace that cell, not add a second one.
        reparameterized = parameterize_notebook(nb, {"alpha": 0.9})
        injected_cells = [
            c
            for c in reparameterized.cells
            if "injected-parameters" in c.get("metadata", {}).get("tags", [])
        ]
        assert len(injected_cells) == 1
        assert "0.9" in injected_cells[0]["source"]


class TestExplicitDivergencesFromRealPapermill:
    """LIBIPYNB-Q35's two deliberate divergences (see
    libipynb.model.parameters's module docstring) -- confirmed here that
    real papermill genuinely does NOT reject these inputs, so the
    divergence is real and evidenced, not assumed."""

    def test_papermill_silently_stringifies_an_unsupported_type_libipynb_rejects(
        self, papermill_available: None
    ) -> None:
        class Sentinel:
            def __str__(self) -> str:
                return "sentinel-value"

        real_source = _real_papermill_injected_source({"weird": Sentinel()})
        assert "sentinel-value" in real_source  # real papermill: silent str() fallback

        from libipynb.model.parameters import UnsupportedParameterTypeError

        document = loads(json.dumps(_notebook_dict()), mode="preservation")
        try:
            inject_parameters(document, {"weird": Sentinel()})
        except UnsupportedParameterTypeError:
            pass
        else:
            raise AssertionError("expected UnsupportedParameterTypeError")

    def test_papermill_stringifies_a_bare_tuple_via_its_str_fallback_libipynb_rejects(
        self, papermill_available: None
    ) -> None:
        """Gate-G2 review finding: an earlier version of this module
        special-cased `isinstance(value, (list, tuple))` identically,
        silently rendering a tuple as a Python list literal -- a different
        value AND a different type than what real papermill actually
        produces. Real papermill's `Translator.translate()` only
        special-cases `isinstance(val, list)`; a bare tuple falls through
        to the same str()-fallback path as any other unrecognized type."""
        real_source = _real_papermill_injected_source({"point": (1, 2, "three")})
        assert "(1, 2, 'three')" in real_source  # real papermill: str(tuple) fallback, quoted
        assert "[1, 2" not in real_source  # confirms it is NOT rendered as a list

        from libipynb.model.parameters import UnsupportedParameterTypeError

        document = loads(json.dumps(_notebook_dict()), mode="preservation")
        try:
            inject_parameters(document, {"point": (1, 2, "three")})
        except UnsupportedParameterTypeError:
            pass
        else:
            raise AssertionError("expected UnsupportedParameterTypeError")


class TestCellPlacementMatchesRealPapermill:
    """LIBIPYNB-Q35 Gate G2 review finding: cell-placement edge cases were
    implemented correctly (verified independently by the review) but had
    no checked-in test coverage, unit or oracle."""

    def test_only_the_first_of_multiple_parameters_tagged_cells_is_used(
        self, papermill_available: None
    ) -> None:
        notebook = _notebook_dict()
        notebook["cells"].insert(
            1,
            {
                "cell_type": "code",
                "id": "second_params",
                "metadata": {"tags": [PARAMETERS_TAG]},
                "execution_count": None,
                "outputs": [],
                "source": "pass",
            },
        )

        from papermill.iorw import load_notebook_node
        from papermill.parameterize import parameterize_notebook
        from papermill.utils import find_first_tagged_cell_index

        fd, path = tempfile.mkstemp(suffix=".ipynb")
        try:
            os.write(fd, json.dumps(notebook).encode("utf-8"))
            os.close(fd)
            nb = load_notebook_node(path)
        finally:
            os.unlink(path)
        assert find_first_tagged_cell_index(nb, PARAMETERS_TAG) == 0
        real_result = parameterize_notebook(nb, {"alpha": 1})
        real_injected_index = next(
            i
            for i, cell in enumerate(real_result.cells)
            if "injected-parameters" in cell.get("metadata", {}).get("tags", [])
        )
        assert real_injected_index == 1  # right after the FIRST parameters cell

        document = loads(json.dumps(notebook), mode="preservation")
        report = inject_parameters(document, {"alpha": 1})
        assert report.injected_cell_index == 1

    def test_re_injecting_without_a_parameters_cell_present_replaces_in_place(
        self, papermill_available: None
    ) -> None:
        """A notebook already carrying only an injected-parameters cell
        (the original parameters cell removed or never present) -- both
        real papermill and libipynb must replace that cell at its own
        index, not fall back to inserting at the top."""
        notebook = _notebook_dict()
        notebook["cells"][0]["metadata"]["tags"] = ["injected-parameters"]

        from papermill.iorw import load_notebook_node
        from papermill.parameterize import parameterize_notebook

        fd, path = tempfile.mkstemp(suffix=".ipynb")
        try:
            os.write(fd, json.dumps(notebook).encode("utf-8"))
            os.close(fd)
            nb = load_notebook_node(path)
        finally:
            os.unlink(path)
        real_result = parameterize_notebook(nb, {"alpha": 1})
        real_injected_indices = [
            i
            for i, cell in enumerate(real_result.cells)
            if "injected-parameters" in cell.get("metadata", {}).get("tags", [])
        ]
        assert real_injected_indices == [0]
        # Confirms an actual replace, not an insert-at-top masked by
        # "index 0" being ambiguous in a 1-cell notebook -- a cell count
        # that grew would mean a second cell was inserted instead.
        assert len(real_result.cells) == len(notebook["cells"])

        document = loads(json.dumps(notebook), mode="preservation")
        report = inject_parameters(document, {"alpha": 1})
        assert report.injected_cell_index == 0
        assert report.replaced_existing_injection is True
        assert len(document.cells) == len(notebook["cells"])
