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
from libipynb.security.limits import NotebookResourceLimits


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

    def test_multiple_non_finite_floats_at_distinct_paths_are_all_reported(self) -> None:
        """LIBIPYNB-Q18 Gate G2 finding: every prior test used exactly one
        non-finite value, unable to distinguish correct aggregation from a
        short-circuit bug (the exact class of bug LIBIPYNB-Q17 had). Three
        values at three distinct, non-overlapping paths must all surface,
        not just the first one found."""
        report = validate(
            {
                "nbformat": 4,
                "nbformat_minor": 5,
                "metadata": {"a": float("nan"), "b": float("inf")},
                "cells": [
                    {
                        "cell_type": "code",
                        "id": "x",
                        "metadata": {"c": float("-inf")},
                        "execution_count": None,
                        "outputs": [],
                        "source": "",
                    }
                ],
            }
        )
        assert report.is_valid is False
        non_finite_paths = {
            d.location.path for d in report.errors if d.code == "IPYNB_NON_FINITE_NUMBER"
        }
        assert non_finite_paths == {
            ("metadata", "a"),
            ("metadata", "b"),
            ("cells", 0, "metadata", "c"),
        }

    def test_a_non_finite_float_inside_a_tuple_is_found(self) -> None:
        """LIBIPYNB-Q18 Gate G2 CRITICAL finding: the original scanner
        recursed through Mapping/list only, silently missing a tuple
        anywhere in the structure -- a live, reproducible instance of
        exactly the "validate() says valid, dumps() fails" contract this
        whole taskcard exists to close, reproduced directly against the
        pre-repair code: validate() reported a NaN-inside-a-tuple document
        as fully valid, and dumps() then raised NotebookWriteError. A tuple
        is a realistic shape here specifically because validate() accepts
        an already-constructed Python mapping directly -- not only JSON
        text, which can never itself produce a tuple.

        Second-review Gate G2 finding: this test originally only asserted
        `any(...)` matched, which would still pass even if the reported
        path were subtly wrong (e.g. an off-by-one tuple index) -- now
        asserts the exact reported path too."""
        report = validate(
            {
                "nbformat": 4,
                "nbformat_minor": 5,
                "metadata": {"custom": (1, float("nan"), 3)},
                "cells": [],
            }
        )
        assert report.is_valid is False
        non_finite = [d for d in report.errors if d.code == "IPYNB_NON_FINITE_NUMBER"]
        assert len(non_finite) == 1
        assert non_finite[0].location.path == ("metadata", "custom", 1)

    def test_a_deeply_nested_structure_does_not_raise_recursion_error(self) -> None:
        """LIBIPYNB-Q18 Gate G2 finding: the original scanner used Python-
        call-stack recursion with no depth guard, raising an uncaught
        RecursionError on adversarially deep input (confirmed at ~1000
        levels) -- fixed via an explicit-stack iterative walk, matching
        security.limits.enforce_structure's own established pattern for
        untrusted-depth traversal. 5000 levels comfortably exceeds Python's
        default recursion limit (1000)."""
        nested: dict[str, object] = {"n": float("nan")}
        for _ in range(5000):
            nested = {"child": nested}
        report = validate({"nbformat": 4, "nbformat_minor": 5, "metadata": nested, "cells": []})
        # Not asserting is_valid here -- enforce_structure's own
        # max_nesting_depth limit (a separate, pre-existing resource guard)
        # legitimately rejects input this deep before the scanner even
        # runs. The only claim under test is that this does not crash with
        # an uncaught RecursionError.
        assert isinstance(report.is_valid, bool)

    def test_an_explicit_high_max_nesting_depth_does_not_leak_a_recursion_error(
        self,
    ) -> None:
        """LIBIPYNB-Q60: the test above relies on enforce_structure's own
        max_nesting_depth limit (default 64) tripping BEFORE
        find_non_finite_floats ever runs -- exactly the ordering
        find_non_finite_floats's own docstring documents as the reason it
        doesn't need a depth guard of its own beyond its 1000-level
        backstop. That assumption breaks the moment a caller explicitly
        configures max_nesting_depth above 1000: enforce_structure no
        longer trips first, and validate()'s own except clauses
        (ResourceLimitError, UnicodeEncodeError, NotebookError/OSError/
        TypeError/ValueError) do not catch RecursionError -- they only
        wrap the enforce_structure() call, not validate_model() below it,
        which is where find_non_finite_floats actually runs. Reproduced
        directly against the pre-fix code: this raised an uncaught
        RecursionError instead of returning a ValidationReport."""
        nested: object = "leaf"
        for _ in range(1500):
            nested = (nested,)
        model = {
            "nbformat": 4,
            "nbformat_minor": 5,
            "metadata": {"vendor": nested},
            "cells": [],
        }
        limits = NotebookResourceLimits(max_nesting_depth=5000)

        report = validate(model, limits=limits)

        assert any(d.code == "IPYNB_RESOURCE_LIMIT" for d in report.errors), report.errors

    def test_a_real_non_finite_float_is_still_found_under_a_high_max_nesting_depth(
        self,
    ) -> None:
        """Sanity check alongside the fix above: a document that stays
        within find_non_finite_floats's own 1000-level backstop, under
        the same explicit high max_nesting_depth, must still be correctly
        flagged as IPYNB_NON_FINITE_NUMBER -- not accidentally swallowed
        by whatever RecursionError handling the fix adds."""
        model = {
            "nbformat": 4,
            "nbformat_minor": 5,
            "metadata": {"vendor": float("nan")},
            "cells": [],
        }
        limits = NotebookResourceLimits(max_nesting_depth=5000)

        report = validate(model, limits=limits)

        assert any(d.code == "IPYNB_NON_FINITE_NUMBER" for d in report.errors), report.errors


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

    def test_an_explicit_high_max_nesting_depth_does_not_leak_a_recursion_error(
        self,
    ) -> None:
        """LIBIPYNB-Q60: probe() is the finiteness scanner's other named
        call site (_internal/finiteness.py's own docstring: "the two
        current call sites (validate(), probe())") and shares the
        identical gap -- its find_non_finite_floats(document.raw) call
        sits entirely outside the try/except that only wraps load().
        Reproduced directly against the pre-fix code: this raised an
        uncaught RecursionError instead of returning a ProbeResult."""
        # LIBIPYNB-Q65: build the JSON text directly via bracket
        # multiplication, not json.dumps() on a 1500-deep Python list.
        # Confirmed via a real CI failure that json.dumps() itself -- the
        # C-accelerated encoder's own recursion guard (Py_EnterRecursiveCall,
        # "while encoding a JSON object") -- can raise RecursionError at
        # this depth on ubuntu-latest/Python 3.11, even though
        # sys.getrecursionlimit() nominally allows it: the guard's
        # effective headroom depends on already-consumed C stack, which
        # varies by interpreter version/platform, and did not reproduce
        # locally on Windows/Python 3.13. That made this a flaky, version-
        # dependent bug in the TEST'S OWN fixture construction, not in the
        # library path under test -- probe() never even ran before the
        # crash. Matches the existing, recursion-free pattern in
        # tests/unit/test_obligation_security_limits.py::
        # test_json_recursion_failure_is_a_deterministic_parse_error.
        vendor_json = ("[" * 1500) + '"leaf"' + ("]" * 1500)
        text = (
            '{"nbformat": 4, "nbformat_minor": 5, '
            '"metadata": {"vendor": ' + vendor_json + "}, "
            '"cells": []}'
        )
        limits = NotebookResourceLimits(max_nesting_depth=5000)

        result = probe(text, limits=limits)

        assert result.matched is False
        # LIBIPYNB-Q65 real-CI finding: two DIFFERENT, equally legitimate
        # safety layers can be the one that actually catches this,
        # depending on how much C-stack headroom this exact platform/
        # interpreter has left at this depth -- probe()'s own load() call
        # decodes `text` first; if THAT hits reader.py's pre-existing
        # `except (RecursionError, MemoryError)` guard (confirmed live on
        # ubuntu-latest/Python 3.11 CI, never reproducible from this
        # session's own Windows/3.13 environment), probe() reports it via
        # its own `except Exception` wrapper around load() with reader.py's
        # message ("JSON complexity exceeds safe parser limits") -- decode
        # never even reaches find_non_finite_floats's own controlled
        # depth backstop (_internal/finiteness.py's MAX_DEPTH=1000,
        # "...exceeded 1000 levels of nesting..."), which is what
        # produces the "nesting"/"deep" wording this assertion originally
        # expected. Both are safe, deliberate, non-crashing outcomes for
        # the same underlying concern -- the test's actual invariant (no
        # uncaught RecursionError leaks past probe()) holds either way.
        assert (
            "nesting" in result.reason or "deep" in result.reason or "complexity" in result.reason
        )


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
