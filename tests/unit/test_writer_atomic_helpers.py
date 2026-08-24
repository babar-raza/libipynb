"""LIBIPYNB-Q19 (P0-D) direct, platform-independent unit tests for
codec/writer.py's ``_target_mode``/``_fsync_directory_best_effort`` helpers.

The integration-style tests in tests/security/test_atomic_writes.py prove
real POSIX permission/fsync behavior, but most of that file's assertions
are ``@POSIX_ONLY`` and cannot run on this project's Windows development
environment -- disclosed honestly, not silently skipped over. These tests
verify the helpers' own LOGIC (mode arithmetic, platform branching) with
mocked os.stat/os.umask/os.name, which is meaningful cross-platform since
it is testing Python-level decisions, not real OS permission enforcement.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from libipynb.codec.writer import _fsync_directory_best_effort, _target_mode


class TestTargetMode:
    def test_returns_the_existing_files_exact_mode(self, tmp_path: Path) -> None:
        target = tmp_path / "existing.ipynb"
        target.write_text("x", encoding="utf-8")
        fake_stat = MagicMock(st_mode=stat.S_IFREG | 0o644)
        with patch("os.stat", return_value=fake_stat):
            assert _target_mode(target) == 0o644

    def test_preserves_an_unusually_restrictive_existing_mode(self, tmp_path: Path) -> None:
        target = tmp_path / "existing.ipynb"
        fake_stat = MagicMock(st_mode=stat.S_IFREG | 0o600)
        with patch("os.stat", return_value=fake_stat):
            assert _target_mode(target) == 0o600

    def test_a_nonexistent_file_gets_the_umask_aware_default(self, tmp_path: Path) -> None:
        target = tmp_path / "does_not_exist.ipynb"
        with (
            patch("os.stat", side_effect=FileNotFoundError()),
            patch("os.umask", side_effect=[0o022, 0o022]) as umask_mock,
        ):
            mode = _target_mode(target)
        assert mode == 0o666 & ~0o022
        assert mode == 0o644
        # Must restore the umask immediately after peeking at it, not
        # leave the process-wide umask at 0.
        assert umask_mock.call_count == 2
        assert umask_mock.call_args_list[0].args == (0,)
        assert umask_mock.call_args_list[1].args == (0o022,)

    def test_a_restrictive_umask_produces_a_restrictive_default(self) -> None:
        with (
            patch("os.stat", side_effect=FileNotFoundError()),
            patch("os.umask", side_effect=[0o077, 0o077]),
        ):
            mode = _target_mode(Path("/does/not/exist"))
        assert mode == 0o600

    def test_a_permission_error_on_an_existing_file_propagates_not_silently_treated_as_new(
        self,
    ) -> None:
        """Only FileNotFoundError means "treat as a new file" -- a
        different OSError (e.g. permission denied reading an EXISTING
        file's stat) must not be silently reinterpreted as "doesn't
        exist" and given a fresh-file default; it should propagate so the
        caller's own OSError handling reports it accurately."""
        with (
            patch("os.stat", side_effect=PermissionError("denied")),
            pytest.raises(PermissionError),
        ):
            _target_mode(Path("/no/access"))


class TestFsyncDirectoryBestEffort:
    def test_does_nothing_on_non_posix_platforms(self, tmp_path: Path) -> None:
        with patch("os.name", "nt"), patch("os.open") as open_mock:
            _fsync_directory_best_effort(tmp_path)
        open_mock.assert_not_called()

    def test_opens_and_fsyncs_and_closes_the_directory_on_posix(self, tmp_path: Path) -> None:
        with (
            patch("os.name", "posix"),
            patch("os.open", return_value=42) as open_mock,
            patch("os.fsync") as fsync_mock,
            patch("os.close") as close_mock,
        ):
            _fsync_directory_best_effort(tmp_path)
        open_mock.assert_called_once_with(str(tmp_path), os.O_RDONLY)
        fsync_mock.assert_called_once_with(42)
        close_mock.assert_called_once_with(42)

    def test_a_failure_to_open_the_directory_is_swallowed(self, tmp_path: Path) -> None:
        with (
            patch("os.name", "posix"),
            patch("os.open", side_effect=OSError("simulated")),
        ):
            _fsync_directory_best_effort(tmp_path)  # must not raise

    def test_a_failure_to_fsync_still_closes_the_directory_handle(self, tmp_path: Path) -> None:
        """A failed fsync must not leak the open directory file
        descriptor -- close() must still run."""
        with (
            patch("os.name", "posix"),
            patch("os.open", return_value=42),
            patch("os.fsync", side_effect=OSError("simulated")),
            patch("os.close") as close_mock,
        ):
            _fsync_directory_best_effort(tmp_path)  # must not raise
        close_mock.assert_called_once_with(42)
