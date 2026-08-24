"""LIBIPYNB-Q9: locks the shared filename-safety helper's location and
behavior in place -- both `model.attachments` and `adapters.export` depend
on `libipynb._internal.paths.is_safe_resource_filename` existing at this
exact import path (deferred/module-level imports respectively), so a
refactor that moves or renames it should fail a test here first."""

from __future__ import annotations

from libipynb._internal.paths import is_safe_resource_filename


def test_bare_filenames_are_safe() -> None:
    assert is_safe_resource_filename("plot.png") is True
    assert is_safe_resource_filename("a-b_c.png") is True


def test_path_traversal_and_absolute_shapes_are_unsafe() -> None:
    for unsafe in ("../../etc/passwd", "/etc/passwd", "..", ".", "a/b.png", "a\\b.png"):
        assert is_safe_resource_filename(unsafe) is False


def test_empty_name_is_unsafe() -> None:
    assert is_safe_resource_filename("") is False


def test_windows_reserved_device_names_are_unsafe() -> None:
    """LIBIPYNB-Q41: CON/PRN/AUX/NUL/COM0-9/LPT0-9, case-insensitive, with
    or without an extension -- Microsoft's documented reserved-name list.
    Historically unwriteable as a regular file on Windows; empirically
    confirmed (this session, Windows 11 build 10.0.26200) that at least one
    current Windows build now allows creating a file with one of these
    exact names via `Path.write_bytes` -- this check still rejects them
    unconditionally so a caller gets identical, portable behavior
    regardless of which Windows build it runs on, rather than one that
    silently varies by OS version."""
    for reserved in (
        "CON",
        "con",
        "Con",
        "PRN",
        "AUX",
        "NUL",
        "COM0",
        "COM1",
        "COM9",
        "LPT0",
        "LPT1",
        "LPT9",
        "CON.png",
        "con.tar.gz",
        "NUL.txt",
    ):
        assert is_safe_resource_filename(reserved) is False, reserved


def test_names_merely_starting_with_a_reserved_stem_are_safe() -> None:
    """A reserved name is matched by its exact stem up to the first "." --
    not as a substring/prefix. "CONFIG" and "CONSOLE.txt" both write fine
    on every Windows version (verified empirically alongside the reserved
    cases above), and must not be over-rejected."""
    for safe in ("CONFIG", "CONSOLE.txt", "COMPANY.png", "LPT10", "COM10", "AUXILIARY"):
        assert is_safe_resource_filename(safe) is True, safe
