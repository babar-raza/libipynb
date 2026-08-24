"""LIBIPYNB-Q16/Q17: locks the shared UTF-8-boundary-safe truncation
helper's location and behavior in place -- both `adapters.execute` and
`adapters.jupyter_execute` depend on
`libipynb._internal.text.truncate_utf8_text` existing at this exact import
path, so a refactor that moves or renames it should fail a test here first.

LIBIPYNB-Q17 Gate G2 finding: an independent review found the function's own
docstring claimed "never returns more than max_bytes bytes total" while the
pre-repair implementation actually exceeded max_bytes by ~12 bytes for any
max_bytes below ~40-50 (the explanatory marker itself didn't fit in the
budget, and the code never shortened it). Fixed to genuinely honor the
claim, verified here down to max_bytes == 0."""

from __future__ import annotations

from libipynb._internal.text import truncate_utf8_text


def test_text_within_the_limit_is_returned_unchanged() -> None:
    assert truncate_utf8_text("short", 100) == "short"


def test_oversized_text_is_truncated_with_a_marker() -> None:
    result = truncate_utf8_text("x" * 500, 100)
    assert len(result.encode("utf-8")) <= 100
    assert result.endswith("bytes]")
    assert result != "x" * 500


def test_unicode_text_is_truncated_at_a_byte_boundary_without_raising() -> None:
    # 'é' is 2 UTF-8 bytes -- a naive byte-slice at an odd offset lands
    # mid-codepoint.
    result = truncate_utf8_text("é" * 500, 101)
    result.encode("utf-8")  # must not raise
    assert len(result.encode("utf-8")) <= 101


def test_the_max_bytes_guarantee_holds_for_extreme_small_limits() -> None:
    """The exact regression this test locks down: for every max_bytes from
    0 up through comfortably past the marker's own length, the result must
    never exceed max_bytes UTF-8 bytes -- not just "close to" it."""
    text = "x" * 10_000
    for max_bytes in range(80):
        result = truncate_utf8_text(text, max_bytes)
        encoded_len = len(result.encode("utf-8"))
        assert encoded_len <= max_bytes, (
            f"max_bytes={max_bytes} produced {encoded_len} bytes: {result!r}"
        )


def test_zero_max_bytes_returns_an_empty_string() -> None:
    assert truncate_utf8_text("anything", 0) == ""


def test_a_negative_max_bytes_is_clamped_to_zero_not_fabricated_content() -> None:
    """LIBIPYNB-Q16 Gate G2 finding: before this clamp, a negative max_bytes
    reached `_FALLBACK_MARKER[:max_bytes]` -- Python's negative-index slice
    semantics ("all but the last N bytes") produced fabricated marker
    content (`'...'`) instead of an empty result, even for text that fit
    comfortably or was itself empty. Callers (adapters/execute.py) also
    reject a negative max_output_bytes up front; this is the independent
    backstop at the shared-utility level."""
    assert truncate_utf8_text("anything", -5) == ""
    assert truncate_utf8_text("", -5) == ""


def test_a_comfortably_large_max_bytes_still_uses_the_full_explanatory_marker() -> None:
    """Only pathologically small limits should fall back to the minimal
    ASCII marker -- a realistic limit (the library's own 10 MiB default is
    the common case, but even a modest 200 bytes here) must still get the
    full, human-readable explanation."""
    result = truncate_utf8_text("x" * 10_000, 200)
    assert "output truncated: exceeded 200 bytes" in result
