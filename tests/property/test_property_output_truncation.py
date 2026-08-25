"""Property-based tests targeting the P0-A/B bug *class*, not just the two
known instances (LIBIPYNB-Q39, Phase 4).

Both LIBIPYNB-Q16 (P0-A, `adapters.execute._apply_output_budget`) and
LIBIPYNB-Q17 (P0-B, `adapters.jupyter_execute._truncate_outputs_if_needed`)
were real bugs that only manifested with >=2 oversized items in one run --
the regression tests each fix originally shipped with (still present,
unchanged, elsewhere) each cover a small, fixed number of instances (0, 1,
2, or 3). These tests instead generate variable-length (0..N) lists of
cells/outputs with variable oversized-ness via Hypothesis, to prove the
*class* of bug (results silently dropped past a truncation boundary,
outputs left unvisited past the first hit) can't recur for any N, not
just the specific N the original regression tests happened to pick.
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from libipynb.adapters.execute import CellExecutionResult, _apply_output_budget
from libipynb.adapters.jupyter_execute import _is_binary_mime_type, _truncate_outputs_if_needed

# --- Strategies -------------------------------------------------------------

_stdout_text = st.text(
    alphabet=st.characters(blacklist_categories=("Cs",)), min_size=0, max_size=200
)

_results = st.lists(
    st.builds(
        CellExecutionResult,
        index=st.integers(min_value=0, max_value=1000),
        stdout=_stdout_text,
        error=st.none(),
    ),
    min_size=0,
    max_size=15,
)

_text_output = st.builds(
    lambda text: {"output_type": "stream", "name": "stdout", "text": text},
    text=_stdout_text,
)

_image_output = st.builds(
    lambda payload: {"output_type": "display_data", "data": {"image/png": payload}},
    # Not real base64, but this code path only checks byte length, not
    # base64 validity -- keeping the strategy simple and fast.
    payload=st.text(
        alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=",
        min_size=0,
        max_size=300,
    ),
)

_svg_output = st.builds(
    lambda payload: {"output_type": "display_data", "data": {"image/svg+xml": payload}},
    payload=st.text(min_size=0, max_size=300),
)

_mixed_output = st.one_of(_text_output, _image_output, _svg_output)
_outputs = st.lists(_mixed_output, min_size=0, max_size=15)


# --- adapters.execute._apply_output_budget (LIBIPYNB-Q16, P0-A) ------------


class TestOutputBudgetNeverDropsResults:
    """The literal P0-A invariant: byte-slicing the combined stream before
    parsing silently dropped every result past the cut. Post-fix,
    `_apply_output_budget` operates on already-parsed results and must
    never drop any of them, for any count or any distribution of
    oversized stdout among them."""

    @given(
        results=_results, max_bytes=st.one_of(st.none(), st.integers(min_value=0, max_value=500))
    )
    @settings(max_examples=200)
    def test_result_count_is_always_preserved(
        self, results: list[CellExecutionResult], max_bytes: int | None
    ) -> None:
        budgeted, _truncated_any = _apply_output_budget(tuple(results), max_bytes)
        assert len(budgeted) == len(results)

    @given(results=_results, max_bytes=st.integers(min_value=0, max_value=500))
    @settings(max_examples=200)
    def test_index_and_error_are_never_altered(
        self, results: list[CellExecutionResult], max_bytes: int
    ) -> None:
        budgeted, _ = _apply_output_budget(tuple(results), max_bytes)
        for original, after in zip(results, budgeted, strict=True):
            assert after.index == original.index
            assert after.error == original.error

    @given(results=_results)
    @settings(max_examples=100)
    def test_none_budget_is_a_pure_no_op(self, results: list[CellExecutionResult]) -> None:
        budgeted, truncated_any = _apply_output_budget(tuple(results), None)
        assert budgeted == tuple(results)
        assert truncated_any is False

    @given(results=_results, max_bytes=st.integers(min_value=0, max_value=500))
    @settings(max_examples=200)
    def test_truncation_never_grows_a_cells_stdout(
        self, results: list[CellExecutionResult], max_bytes: int
    ) -> None:
        budgeted, _ = _apply_output_budget(tuple(results), max_bytes)
        for original, after in zip(results, budgeted, strict=True):
            assert len(after.stdout.encode("utf-8")) <= len(original.stdout.encode("utf-8"))

    @given(results=_results, max_bytes=st.integers(min_value=0, max_value=500))
    @settings(max_examples=200)
    def test_once_budget_is_exhausted_every_later_cell_is_empty(
        self, results: list[CellExecutionResult], max_bytes: int
    ) -> None:
        """Once the running cumulative budget hits zero, every subsequent
        cell's stdout must be empty -- the exact class of interaction the
        original bug's own regression test only proved for one specific
        cell ordering (oversized-first/middle/last), not for the general
        "N cells after exhaustion" case."""
        budgeted, _ = _apply_output_budget(tuple(results), max_bytes)
        exhausted = False
        for after in budgeted:
            if exhausted:
                assert after.stdout == ""
            if after.stdout_truncated and after.stdout == "":
                exhausted = True

    @given(results=_results, max_bytes=st.integers(min_value=0, max_value=500))
    @settings(max_examples=200)
    def test_truncated_stdout_is_always_valid_utf8_and_within_budget_context(
        self, results: list[CellExecutionResult], max_bytes: int
    ) -> None:
        budgeted, _ = _apply_output_budget(tuple(results), max_bytes)
        for after in budgeted:
            # Must not raise -- truncate_utf8_text's own byte-boundary
            # safety guarantee, re-checked here across arbitrary inputs
            # rather than the handful of fixed strings its own unit tests use.
            after.stdout.encode("utf-8").decode("utf-8")


# --- adapters.jupyter_execute._truncate_outputs_if_needed (LIBIPYNB-Q17, P0-B) --


def _is_within_budget(output: dict[str, object], max_bytes: int) -> bool:
    text = output.get("text")
    if isinstance(text, str) and len(text.encode("utf-8")) > max_bytes:
        return False
    data = output.get("data")
    if isinstance(data, dict):
        for mime_type, payload in data.items():
            # A binary-shaped oversized payload is expected to be *removed*
            # entirely, not shrunk -- its absence (checked separately) is
            # what "within budget" means for it.
            if (
                isinstance(payload, str)
                and len(payload.encode("utf-8")) > max_bytes
                and not (isinstance(mime_type, str) and _is_binary_mime_type(mime_type))
            ):
                return False
    return True


class TestTruncateOutputsNeverSkipsAnOutput:
    """The literal P0-B invariant: `any(_truncate_one_output(...) for o in
    outputs)` short-circuits on the first True, leaving every output after
    the first oversized one completely unvisited. Post-fix, every output
    in the list must end up within budget (or have its binary payload
    removed), regardless of how many oversized outputs exist or where
    they sit in the list."""

    @given(outputs=_outputs, max_bytes=st.integers(min_value=0, max_value=300))
    @settings(max_examples=200)
    def test_every_output_ends_up_within_budget(
        self, outputs: list[dict[str, object]], max_bytes: int
    ) -> None:
        _truncate_outputs_if_needed(outputs, max_bytes)  # mutates in place
        for output in outputs:
            assert _is_within_budget(output, max_bytes), output

    @given(outputs=_outputs)
    @settings(max_examples=100)
    def test_none_budget_is_a_pure_no_op(self, outputs: list[dict[str, object]]) -> None:
        import copy

        before = copy.deepcopy(outputs)
        changed, omitted = _truncate_outputs_if_needed(outputs, None)
        assert outputs == before
        assert changed is False
        assert omitted == ()

    @given(outputs=_outputs, max_bytes=st.integers(min_value=0, max_value=300))
    @settings(max_examples=200)
    def test_oversized_binary_payloads_are_removed_not_corrupted(
        self, outputs: list[dict[str, object]], max_bytes: int
    ) -> None:
        """LIBIPYNB-Q17's second finding: appending a text truncation
        marker to base64 content corrupts it into invalid base64 without
        raising. A binary-MIME payload still present after this call must
        be byte-for-byte unchanged (it was never oversized to begin with
        -- an oversized one is removed, never shrunk/spliced)."""
        before_payload_lengths = {
            id(output): {
                mime: len(payload)
                for mime, payload in output.get("data", {}).items()
                if isinstance(payload, str)
            }
            for output in outputs
            if isinstance(output.get("data"), dict)
        }
        _truncate_outputs_if_needed(outputs, max_bytes)
        for output in outputs:
            data = output.get("data")
            if not isinstance(data, dict):
                continue
            original_lengths = before_payload_lengths.get(id(output), {})
            for mime_type, payload in data.items():
                if mime_type in original_lengths and _is_binary_mime_type(mime_type):
                    assert len(payload) == original_lengths[mime_type]

    @given(outputs=_outputs, max_bytes=st.integers(min_value=0, max_value=300))
    @settings(max_examples=200)
    def test_oversized_binary_payloads_are_actually_absent_afterward(
        self, outputs: list[dict[str, object]], max_bytes: int
    ) -> None:
        """LIBIPYNB-Q40 Gate-G2 round-2 review finding: the sibling test
        above only checks that a binary-MIME payload STILL PRESENT after
        truncation is byte-for-byte unchanged -- it never checks that an
        ORIGINALLY-OVERSIZED one is actually gone. Both "correctly
        removed" and "left in place by a reintroduced any()-short-circuit
        bug" are indistinguishable to that test if the surviving payload
        (if any) happens to be unchanged either way. This test closes
        that gap directly: every binary-MIME key that was oversized
        before the call must not still be a key in `data` afterward."""
        originally_oversized_binary_keys = {
            id(output): {
                mime
                for mime, payload in output.get("data", {}).items()
                if isinstance(payload, str)
                and isinstance(mime, str)
                and _is_binary_mime_type(mime)
                and len(payload.encode("utf-8")) > max_bytes
            }
            for output in outputs
            if isinstance(output.get("data"), dict)
        }
        _truncate_outputs_if_needed(outputs, max_bytes)
        for output in outputs:
            data = output.get("data")
            remaining_keys = set(data) if isinstance(data, dict) else set()
            oversized_keys = originally_oversized_binary_keys.get(id(output), set())
            assert not (oversized_keys & remaining_keys), (
                f"an originally-oversized binary payload was left in place "
                f"instead of removed: {oversized_keys & remaining_keys!r}"
            )

    @given(outputs=_outputs, max_bytes=st.integers(min_value=0, max_value=300))
    @settings(max_examples=200)
    def test_outputs_never_oversized_originally_are_left_byte_for_byte_untouched(
        self, outputs: list[dict[str, object]], max_bytes: int
    ) -> None:
        """An output with no payload exceeding max_bytes at all (text OR
        binary OR non-binary data) must come out identical -- distinct
        from `_is_within_budget` above, which only describes an output's
        *final* state (also satisfied by a binary payload that was
        removed, i.e. genuinely modified) rather than whether it was ever
        touched in the first place."""

        def _has_any_oversized_payload(output: dict[str, object]) -> bool:
            text = output.get("text")
            if isinstance(text, str) and len(text.encode("utf-8")) > max_bytes:
                return True
            data = output.get("data")
            if isinstance(data, dict):
                for payload in data.values():
                    if isinstance(payload, str) and len(payload.encode("utf-8")) > max_bytes:
                        return True
            return False

        import copy

        before = copy.deepcopy(outputs)
        _truncate_outputs_if_needed(outputs, max_bytes)
        for original, after in zip(before, outputs, strict=True):
            if not _has_any_oversized_payload(original):
                assert after == original
