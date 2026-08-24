"""LIBIPYNB-Q16/Q17: shared, dependency-free UTF-8-boundary-safe text
truncation used by both execution adapters (:mod:`libipynb.adapters.execute`
and :mod:`libipynb.adapters.jupyter_execute`) -- lives in ``_internal`` for
the same reason as :mod:`libipynb._internal.paths`: one implementation, not
two independently-maintained copies of the same byte-boundary-safety logic.
"""

from __future__ import annotations

#: LIBIPYNB-Q17 Gate G2 finding: the full explanatory marker does not fit
#: inside a pathologically small max_bytes budget (e.g. 1-30 bytes); this
#: ASCII-only fallback always does, byte-for-byte, so it can be sliced to
#: any length without ever landing mid-codepoint (every ASCII byte is
#: already a complete character).
_FALLBACK_MARKER = b"...[cut]"


def truncate_utf8_text(text: str, max_bytes: int) -> str:
    """Truncate *text* to at most *max_bytes* UTF-8 bytes, appending a
    marker that states the limit -- never returns more than *max_bytes*
    bytes total (marker included, verified down to ``max_bytes == 0``), and
    never raises on a cut that lands mid-codepoint at the byte boundary (the
    partial trailing codepoint is dropped rather than corrupting the string
    or raising)."""
    encoded = text.encode("utf-8")
    if len(encoded) <= max_bytes:
        return text
    marker_bytes = f"\n... [output truncated: exceeded {max_bytes} bytes]".encode()
    if len(marker_bytes) > max_bytes:
        # The full marker alone would already exceed the budget -- fall
        # back to a minimal marker, itself byte-sliced to fit if needed,
        # so the max_bytes guarantee holds even here rather than being
        # quietly violated for small limits.
        return _FALLBACK_MARKER[:max_bytes].decode("ascii")
    keep = max_bytes - len(marker_bytes)
    return encoded[:keep].decode("utf-8", errors="ignore") + marker_bytes.decode("utf-8")


__all__ = ["truncate_utf8_text"]
