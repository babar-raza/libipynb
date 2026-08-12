"""Edge case coverage for codec/writer.py."""

from __future__ import annotations

import io
from pathlib import Path

import pytest

from libipynb import dump, dumps, loads
from libipynb.errors import NotebookWriteError


def _minimal_doc() -> object:
    return loads(
        '{"nbformat": 4, "nbformat_minor": 5, "metadata": {}, "cells": []}',
        mode="preservation",
    )


class TestProfileVersion:
    def test_declared_profile(self) -> None:
        doc = _minimal_doc()
        text = dumps(doc, profile="declared")
        assert '"nbformat": 4' in text

    def test_nbformat_prefix_stripped(self) -> None:
        doc = _minimal_doc()
        text = dumps(doc, profile="nbformat-4.5")
        assert '"nbformat": 4' in text

    def test_invalid_profile_raises(self) -> None:
        doc = _minimal_doc()
        with pytest.raises(ValueError, match="profile must be"):
            dumps(doc, profile="3.0")

    def test_declared_with_bad_version_raises(self) -> None:
        raw = {"nbformat": True, "nbformat_minor": 5, "metadata": {}, "cells": []}
        with pytest.raises(NotebookWriteError, match="declared profile"):
            dumps(raw, profile="declared")


class TestVersionMismatch:
    def test_explicit_upgrade_required(self) -> None:
        doc = _minimal_doc()
        with pytest.raises(NotebookWriteError, match="requires explicit upgrade"):
            dumps(doc, profile="4.4")


class TestDumpErrors:
    def test_non_serializable_content_raises(self) -> None:
        raw = {
            "nbformat": 4,
            "nbformat_minor": 5,
            "metadata": {"bad": object()},
            "cells": [],
        }
        with pytest.raises(NotebookWriteError, match="cannot serialize"):
            dumps(raw, profile="declared")

    def test_partial_stream_write(self) -> None:
        class LimitedWriter:
            def write(self, text: str) -> int:
                return 1

        doc = _minimal_doc()
        with pytest.raises(NotebookWriteError, match="partial write"):
            dump(doc, LimitedWriter(), profile="declared")  # type: ignore[arg-type]

    def test_stream_write_os_error(self) -> None:
        class FailWriter:
            def write(self, text: str) -> int:
                raise OSError("disk full")

        doc = _minimal_doc()
        with pytest.raises(NotebookWriteError, match="cannot write"):
            dump(doc, FailWriter(), profile="declared")  # type: ignore[arg-type]

    def test_file_write_to_nonexistent_dir(self, tmp_path: Path) -> None:
        doc = _minimal_doc()
        bad_path = tmp_path / "no_such_dir" / "out.ipynb"
        with pytest.raises(NotebookWriteError, match="cannot write"):
            dump(doc, bad_path, profile="declared")


class TestDumpSuccess:
    def test_stream_write(self) -> None:
        buf = io.StringIO()
        doc = _minimal_doc()
        dump(doc, buf, profile="declared")
        assert '"nbformat": 4' in buf.getvalue()

    def test_file_write(self, tmp_path: Path) -> None:
        doc = _minimal_doc()
        dest = tmp_path / "out.ipynb"
        dump(doc, dest, profile="declared")
        assert dest.exists()
        content = dest.read_text(encoding="utf-8")
        assert '"nbformat": 4' in content
