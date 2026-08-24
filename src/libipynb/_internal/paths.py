"""LIBIPYNB-Q9: shared, dependency-free filename-safety check used by both
the model layer (:mod:`libipynb.model.attachments`) and the adapters layer
(:mod:`libipynb.adapters.export`'s resource writer) -- lives in ``_internal``
specifically so neither layer has to import from the other. ``adapters``
already imports from ``model`` (e.g. ``export.py`` imports
``NotebookDocument``); ``model`` must not import from ``adapters`` in the
reverse direction, mirroring this codebase's other established layering
(``codec``/``validation``/``security`` never import ``model``'s siblings
out of order either).
"""

from __future__ import annotations

from pathlib import PurePosixPath

#: LIBIPYNB-Q41: MS-DOS/Win32 reserved device names (case-insensitive) --
#: CON, PRN, AUX, NUL, COM1-COM9, LPT1-LPT9, plus the Unicode superscript-
#: digit variants COM¹/²/³ and LPT¹/²/³, all
#: confirmed against Microsoft's live "Naming Files, Paths, and Namespaces"
#: documentation (Gate-G2 review finding: an earlier version of this set
#: both included COM0/LPT0 -- not actually documented by Microsoft, though
#: harmlessly conservative to reject anyway -- and omitted the superscript
#: variants, which genuinely are documented as reserved and were a real
#: gap). Historically these could not be created as regular files on
#: Windows at all (device-name aliasing at the Win32-namespace level);
#: Windows 11 has since relaxed this for some build/API combinations
#: (confirmed empirically on this session's own machine, build 10.0.26200:
#: ``Path("CON").write_bytes(...)`` now succeeds and produces a genuine,
#: readable regular file, not a device alias). That relaxation is not
#: universal across the still-deployed Windows install base (older Windows
#: 11 builds, Windows 10), where writing one of these names still raises
#: ``OSError`` -- rejecting them unconditionally keeps this check's result
#: independent of which exact Windows build/version a caller happens to be
#: running on, matching its own stated purpose (safe to join onto a
#: directory and write, anywhere). COM0/LPT0 are kept in the set too --
#: not documented, but their real-world status is disputed even among
#: other language ecosystems (e.g. golang/go#67245 found COM0 empirically
#: writable on some tested Windows versions and not others), so rejecting
#: them is the conservative, never-wrong-to-reject choice for a safety gate.
_WINDOWS_RESERVED_STEMS = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{digit}" for digit in range(10)}
    | {f"LPT{digit}" for digit in range(10)}
    | {f"COM{digit}" for digit in "¹²³"}
    | {f"LPT{digit}" for digit in "¹²³"}
)


def _is_windows_reserved_name(name: str) -> bool:
    # Windows reserves a name by its stem up to (not including) the first
    # "." -- "CON.txt" and "con.tar.gz" are both reserved (stem "CON");
    # "CONFIG" and "CONSOLE.txt" are not (stem "CONFIG"/"CONSOLE"). A
    # trailing space on the stem (no dot at all, e.g. "CON ") is also
    # reserved -- Win32's CreateFile strips trailing dots/spaces from the
    # final path component before resolving it, so "CON " and "CON" name
    # the same reserved device (Gate-G2 review finding: previously missed,
    # since only the dot-split was stripped, not trailing whitespace).
    stem = name.split(".", 1)[0].rstrip(" ")
    return stem.upper() in _WINDOWS_RESERVED_STEMS


def is_safe_resource_filename(name: str) -> bool:
    """An attachment/resource key is untrusted document content, not a
    path -- reject anything that is not a bare filename (no separators, no
    ``..`` segments, not absolute, not a Windows-reserved device name)
    before it becomes a resource filename a caller might join onto a
    directory when writing to disk."""
    if not name or name in {".", ".."} or "\\" in name:
        return False
    candidate = PurePosixPath(name)
    if candidate.name != name or ".." in candidate.parts:
        return False
    return not _is_windows_reserved_name(name)


__all__ = ["is_safe_resource_filename"]
