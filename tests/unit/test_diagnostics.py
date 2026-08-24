"""Failure-first tests for the public Diagnostic/ValidationResult types."""

from __future__ import annotations

import pytest

from libipynb import Diagnostic, DiagnosticSeverity


class TestQ43DiagnosticDetailsMutationAfterAccessDoesNotChangeLaterReads:
    """LIBIPYNB-Q43 Gate-G2 round-3 review finding: `Diagnostic.details`
    had the identical gap `NotebookDiff._target_snapshot` was fixed for
    (see test_obligation_structure_diff.py) -- `dict(self.details)` in
    `__post_init__` only broke aliasing to the constructor's input, not
    later mutation of the field itself, so `diagnostic.details["x"] =
    "evil"` silently corrupted every later read of `diagnostic.details`
    on the SAME instance. This exact field was explicitly reconsidered
    (not overlooked) by the taskcard's own round-3 repair and left
    unfixed on the reasoning that no in-repo caller constructs a
    `Diagnostic` with a non-empty `details=` -- true, but `Diagnostic` is
    a public, top-level-exported, documented dataclass any external
    caller can construct directly, so that reasoning did not actually
    cover the field's real reachability. Found live during a further
    independent review round, not by the round-3 repair itself."""

    def test_details_rejects_item_assignment(self) -> None:
        diagnostic = Diagnostic(
            code="X1",
            message="test message",
            details={"a": 1, "b": "safe"},
        )

        with pytest.raises(TypeError):
            diagnostic.details["a"] = "EVIL_MUTATED"  # type: ignore[index]
        with pytest.raises(TypeError):
            diagnostic.details["injected_new_key"] = "ALSO_EVIL"  # type: ignore[index]

    def test_mutating_details_does_not_change_a_later_read(self) -> None:
        diagnostic = Diagnostic(
            code="X1",
            message="test message",
            details={"a": 1, "b": "safe"},
        )

        first_read = diagnostic.details
        with pytest.raises(TypeError):
            first_read["a"] = "EVIL_MUTATED"  # type: ignore[index]

        second_read = diagnostic.details
        assert second_read == {"a": 1, "b": "safe"}
        assert second_read == first_read

    def test_details_is_not_aliased_to_the_callers_own_dict(self) -> None:
        source = {"a": 1}
        diagnostic = Diagnostic(code="X1", message="test message", details=source)

        source["a"] = "mutated-after-construction"

        assert diagnostic.details["a"] == 1

    def test_default_empty_details_is_also_frozen(self) -> None:
        diagnostic = Diagnostic(code="X1", message="test message")

        assert diagnostic.details == {}
        with pytest.raises(TypeError):
            diagnostic.details["new"] = "evil"  # type: ignore[index]

    def test_severity_default_and_construction_still_work(self) -> None:
        diagnostic = Diagnostic(code="X1", message="test message")
        assert diagnostic.severity is DiagnosticSeverity.ERROR
