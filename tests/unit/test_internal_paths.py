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
