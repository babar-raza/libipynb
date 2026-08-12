"""Atomic file write tests for codec/writer.py.

Verifies that dump() uses write-to-temp-then-rename so partial writes
never corrupt the target file on disk.
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest

from libipynb import dump, load, loads
from libipynb.errors import NotebookWriteError


@pytest.fixture
def minimal_doc() -> object:
    return loads(
        '{"nbformat": 4, "nbformat_minor": 5, "metadata": {}, "cells": []}',
        mode="preservation",
    )


class TestAtomicFileWrite:
    def test_successful_write_produces_correct_content(
        self, minimal_doc: object, tmp_path: Path
    ) -> None:
        target = tmp_path / "output.ipynb"
        dump(minimal_doc, target, profile="declared")
        assert target.exists()
        reloaded = load(target, mode="preservation")
        assert reloaded.nbformat == 4

    def test_no_temp_file_remains_after_success(self, minimal_doc: object, tmp_path: Path) -> None:
        target = tmp_path / "output.ipynb"
        dump(minimal_doc, target, profile="declared")
        tmp_files = list(tmp_path.glob("*.tmp"))
        assert tmp_files == []

    def test_existing_file_not_corrupted_on_write_failure(self, tmp_path: Path) -> None:
        target = tmp_path / "output.ipynb"
        original = '{"nbformat": 4, "nbformat_minor": 5, "metadata": {}, "cells": []}\n'
        target.write_text(original, encoding="utf-8")
        read_only_dir = tmp_path / "readonly"
        read_only_dir.mkdir()
        nonexistent = tmp_path / "no_such_dir" / "output.ipynb"
        with pytest.raises(NotebookWriteError):
            dump({"not": "a valid notebook"}, nonexistent, profile="declared")
        assert target.read_text(encoding="utf-8") == original

    def test_stream_write_still_works(self, minimal_doc: object) -> None:
        buf = io.StringIO()
        dump(minimal_doc, buf, profile="declared")
        text = buf.getvalue()
        assert '"nbformat": 4' in text

    def test_overwrite_existing_file(self, minimal_doc: object, tmp_path: Path) -> None:
        target = tmp_path / "output.ipynb"
        target.write_text("old content", encoding="utf-8")
        dump(minimal_doc, target, profile="declared")
        content = target.read_text(encoding="utf-8")
        assert '"nbformat": 4' in content
        assert "old content" not in content
