"""LIBIPYNB-Q18 (P0-C): non-standard JSON constants (NaN/Infinity/-Infinity).

Python's json.loads, by default, silently accepts these non-standard
constants (via parse_constant) and produces float('nan')/float('inf')/
float('-inf') -- legal Python values, but not legal JSON, and rejected by
this project's own writer (json.dumps(..., allow_nan=False)). Before this
fix, a notebook containing one of these constants could load in strict
mode, report as valid via validate(), and report as a matched IPYNB via
probe() -- then fail unrecoverably at dumps(), an asymmetric contract.

Strict mode now rejects the constant at JSON-text parse time
(IPYNB_NON_FINITE_NUMBER, codec.reader._reject_non_finite_constant).
Preservation/recovery modes intentionally keep the existing tolerant parse
(their own lossless/tolerant contract) -- validate()'s recursive scan
(_internal.finiteness.find_non_finite_floats, wired into
validation.rules.validate_model) still catches it downstream regardless of
load mode, and covers an already-constructed mapping handed to validate()
directly, which never goes through the JSON-text reader at all. probe()
(which loads in preservation mode) is checked explicitly too.
"""

from __future__ import annotations

import json
import math

import pytest

from libipynb import loads, validate
from libipynb.codec.reader import probe
from libipynb.errors import NotebookParseError


def _nb_with_constant_at(path_json_fragment: str, constant: str = "NaN") -> str:
    """Build minimal, strictly-valid-except-for-the-constant notebook JSON
    with *constant* (NaN/Infinity/-Infinity) spliced in at a caller-chosen
    location via a raw JSON fragment string (not json.dumps, since Python's
    json.dumps also happily emits these non-standard tokens by default --
    using raw text here keeps this test file's own fixture construction
    independent of that same leniency)."""
    return path_json_fragment.replace("__CONSTANT__", constant)


class TestStrictModeRejectsNonFiniteConstants:
    @pytest.mark.parametrize("constant", ["NaN", "Infinity", "-Infinity"])
    def test_in_notebook_metadata(self, constant: str) -> None:
        text = _nb_with_constant_at(
            '{"nbformat": 4, "nbformat_minor": 5, '
            '"metadata": {"custom": __CONSTANT__}, "cells": []}',
            constant,
        )
        with pytest.raises(NotebookParseError) as exc_info:
            loads(text, mode="strict")
        assert exc_info.value.code == "IPYNB_NON_FINITE_NUMBER"

    @pytest.mark.parametrize("constant", ["NaN", "Infinity", "-Infinity"])
    def test_in_cell_metadata(self, constant: str) -> None:
        text = _nb_with_constant_at(
            '{"nbformat": 4, "nbformat_minor": 5, "metadata": {}, '
            '"cells": [{"cell_type": "code", "id": "a", "metadata": {"custom": __CONSTANT__}, '
            '"execution_count": null, "outputs": [], "source": ""}]}',
            constant,
        )
        with pytest.raises(NotebookParseError) as exc_info:
            loads(text, mode="strict")
        assert exc_info.value.code == "IPYNB_NON_FINITE_NUMBER"

    @pytest.mark.parametrize("constant", ["NaN", "Infinity", "-Infinity"])
    def test_in_output_metadata(self, constant: str) -> None:
        text = _nb_with_constant_at(
            '{"nbformat": 4, "nbformat_minor": 5, "metadata": {}, '
            '"cells": [{"cell_type": "code", "id": "a", "metadata": {}, '
            '"execution_count": null, "source": "", "outputs": ['
            '{"output_type": "display_data", "data": {"text/plain": "x"}, '
            '"metadata": {"custom": __CONSTANT__}}]}]}',
            constant,
        )
        with pytest.raises(NotebookParseError) as exc_info:
            loads(text, mode="strict")
        assert exc_info.value.code == "IPYNB_NON_FINITE_NUMBER"

    @pytest.mark.parametrize("constant", ["NaN", "Infinity", "-Infinity"])
    def test_in_mime_data(self, constant: str) -> None:
        text = _nb_with_constant_at(
            '{"nbformat": 4, "nbformat_minor": 5, "metadata": {}, '
            '"cells": [{"cell_type": "code", "id": "a", "metadata": {}, '
            '"execution_count": null, "source": "", "outputs": ['
            '{"output_type": "execute_result", "execution_count": 1, '
            '"data": {"application/json": {"value": __CONSTANT__}}, "metadata": {}}]}]}',
            constant,
        )
        with pytest.raises(NotebookParseError) as exc_info:
            loads(text, mode="strict")
        assert exc_info.value.code == "IPYNB_NON_FINITE_NUMBER"

    def test_deeply_nested_inside_lists_and_dicts(self) -> None:
        text = _nb_with_constant_at(
            '{"nbformat": 4, "nbformat_minor": 5, '
            '"metadata": {"a": {"b": [1, 2, {"c": [__CONSTANT__]}]}}, "cells": []}'
        )
        with pytest.raises(NotebookParseError) as exc_info:
            loads(text, mode="strict")
        assert exc_info.value.code == "IPYNB_NON_FINITE_NUMBER"

    def test_a_finite_notebook_still_parses_normally(self) -> None:
        text = '{"nbformat": 4, "nbformat_minor": 5, "metadata": {"n": 1.5}, "cells": []}'
        doc = loads(text, mode="strict")
        assert doc.nbformat == 4


class TestPreservationModeStillTolerantAtParseTime:
    """Preservation/recovery mode keep the pre-existing tolerant parse --
    validate() (below) is what catches it for these modes, not the parser."""

    def test_preservation_mode_still_loads_a_nan_bearing_notebook(self) -> None:
        text = '{"nbformat": 4, "nbformat_minor": 5, "metadata": {"n": NaN}, "cells": []}'
        doc = loads(text, mode="preservation")
        assert math.isnan(doc.raw["metadata"]["n"])

    def test_recovery_mode_still_loads_a_nan_bearing_notebook(self) -> None:
        text = '{"nbformat": 4, "nbformat_minor": 5, "metadata": {"n": NaN}, "cells": []}'
        doc = loads(text, mode="recovery")
        assert math.isnan(doc.raw["metadata"]["n"])


class TestValidateRejectsNonFiniteConstants:
    """validate() must reject non-finite floats regardless of how the
    document arrived -- an already-constructed Python mapping (never
    touching the JSON-text reader at all) is exactly the case the reader's
    own parse_constant hook cannot cover."""

    def test_constructed_mapping_with_nan_in_notebook_metadata(self) -> None:
        report = validate(
            {
                "nbformat": 4,
                "nbformat_minor": 5,
                "metadata": {"custom": float("nan")},
                "cells": [],
            }
        )
        assert report.is_valid is False
        assert any(d.code == "IPYNB_NON_FINITE_NUMBER" for d in report.errors)

    def test_constructed_mapping_with_infinity_in_cell_metadata(self) -> None:
        report = validate(
            {
                "nbformat": 4,
                "nbformat_minor": 5,
                "metadata": {},
                "cells": [
                    {
                        "cell_type": "code",
                        "id": "a",
                        "metadata": {"custom": float("inf")},
                        "execution_count": None,
                        "outputs": [],
                        "source": "",
                    }
                ],
            }
        )
        assert report.is_valid is False
        assert any(d.code == "IPYNB_NON_FINITE_NUMBER" for d in report.errors)

    def test_constructed_mapping_with_negative_infinity_in_output_metadata(self) -> None:
        report = validate(
            {
                "nbformat": 4,
                "nbformat_minor": 5,
                "metadata": {},
                "cells": [
                    {
                        "cell_type": "code",
                        "id": "a",
                        "metadata": {},
                        "execution_count": None,
                        "source": "",
                        "outputs": [
                            {
                                "output_type": "display_data",
                                "data": {"text/plain": "x"},
                                "metadata": {"custom": float("-inf")},
                            }
                        ],
                    }
                ],
            }
        )
        assert report.is_valid is False
        assert any(d.code == "IPYNB_NON_FINITE_NUMBER" for d in report.errors)

    def test_constructed_mapping_with_nan_in_mime_data(self) -> None:
        report = validate(
            {
                "nbformat": 4,
                "nbformat_minor": 5,
                "metadata": {},
                "cells": [
                    {
                        "cell_type": "code",
                        "id": "a",
                        "metadata": {},
                        "execution_count": None,
                        "source": "",
                        "outputs": [
                            {
                                "output_type": "execute_result",
                                "execution_count": 1,
                                "data": {"application/json": {"value": float("nan")}},
                                "metadata": {},
                            }
                        ],
                    }
                ],
            }
        )
        assert report.is_valid is False
        assert any(d.code == "IPYNB_NON_FINITE_NUMBER" for d in report.errors)

    def test_constructed_mapping_with_nan_deeply_nested_in_lists_and_dicts(self) -> None:
        report = validate(
            {
                "nbformat": 4,
                "nbformat_minor": 5,
                "metadata": {"a": {"b": [1, 2, {"c": [float("nan")]}]}},
                "cells": [],
            }
        )
        assert report.is_valid is False
        assert any(d.code == "IPYNB_NON_FINITE_NUMBER" for d in report.errors)

    def test_a_preservation_loaded_nan_bearing_document_is_invalid(self) -> None:
        text = '{"nbformat": 4, "nbformat_minor": 5, "metadata": {"n": NaN}, "cells": []}'
        doc = loads(text, mode="preservation")
        report = validate(doc.raw)
        assert report.is_valid is False
        assert any(d.code == "IPYNB_NON_FINITE_NUMBER" for d in report.errors)

    def test_a_finite_document_is_unaffected(self) -> None:
        report = validate({"nbformat": 4, "nbformat_minor": 5, "metadata": {"n": 1.5}, "cells": []})
        assert not any(d.code == "IPYNB_NON_FINITE_NUMBER" for d in report.errors)


class TestProbeRejectsNonFiniteConstants:
    def test_probe_does_not_match_a_nan_bearing_notebook(self) -> None:
        text = '{"nbformat": 4, "nbformat_minor": 5, "metadata": {"n": NaN}, "cells": []}'
        result = probe(text)
        assert result.matched is False
        assert "non-finite" in result.reason

    def test_probe_still_matches_a_finite_notebook(self) -> None:
        text = '{"nbformat": 4, "nbformat_minor": 5, "metadata": {}, "cells": []}'
        result = probe(text)
        assert result.matched is True


class TestStrictReadValidateWriteAreConsistent:
    """The end-to-end contract this whole taskcard exists to fix: a
    NaN-carrying notebook must be rejected at the EARLIEST possible point
    (strict load), not permitted to appear valid and then crash at dumps()."""

    def test_strict_load_validate_and_dumps_all_agree_the_notebook_is_rejected(self) -> None:
        text = '{"nbformat": 4, "nbformat_minor": 5, "metadata": {"n": NaN}, "cells": []}'

        with pytest.raises(NotebookParseError):
            loads(text, mode="strict")

        doc = loads(text, mode="preservation")
        report = validate(doc.raw)
        assert report.is_valid is False

        from libipynb import dumps
        from libipynb.errors import NotebookWriteError

        with pytest.raises(NotebookWriteError):
            dumps(doc, profile="declared")

    def test_json_dumps_itself_would_have_written_the_non_standard_constant(self) -> None:
        """Sanity check that this test file's premise is real: Python's own
        json.dumps happily emits NaN by default, which is exactly why the
        reader-side check matters (a NaN-bearing notebook is a realistic
        artifact some other tool could produce, not a purely synthetic
        adversarial input)."""
        assert "NaN" in json.dumps({"n": float("nan")})
