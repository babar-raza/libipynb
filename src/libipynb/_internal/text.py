"""LIBIPYNB-Q16/Q17: shared, dependency-free UTF-8-boundary-safe text
truncation used by both execution adapters (:mod:`libipynb.adapters.execute`
and :mod:`libipynb.adapters.jupyter_execute`) -- lives in ``_internal`` for
the same reason as :mod:`libipynb._internal.paths`: one implementation, not
two independently-maintained copies of the same byte-boundary-safety logic.
"""

from __future__ import annotations


def truncate_utf8_text(text: str, max_bytes: int) -> str:
    """Truncate *text* to at most *max_bytes* UTF-8 bytes, appending a
    marker that states the limit -- never returns more than *max_bytes*
    bytes total (marker included), and never raises on a cut that lands
    mid-codepoint at the byte boundary (the partial trailing codepoint is
    dropped rather than corrupting the string or raising)."""
    encoded = text.encode("utf-8")
    if len(encoded) <= max_bytes:
        return text
    marker = f"\n... [output truncated: exceeded {max_bytes} bytes]"
    keep = max(0, max_bytes - len(marker.encode("utf-8")))
    return encoded[:keep].decode("utf-8", errors="ignore") + marker


__all__ = ["truncate_utf8_text"]
