"""Atomic file write tests for codec/writer.py.

Verifies that dump() uses write-to-temp-then-rename so partial writes
never corrupt the target file on disk.
"""

from __future__ import annotations

import io
import os
import stat
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from libipynb import dump, load, loads
from libipynb.errors import NotebookWriteError

POSIX_ONLY = pytest.mark.skipif(
    sys.platform == "win32",
    reason="POSIX permission bits are not meaningful on Windows",
)


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
        nonexistent = tmp_path / "no_such_dir" / "output.ipynb"
        with pytest.raises(NotebookWriteError):
            dump({"not": "a valid notebook"}, nonexistent, profile="declared")
        assert target.read_text(encoding="utf-8") == original

    @POSIX_ONLY
    def test_write_failure_in_a_permission_denied_directory_is_a_clean_notebookwriteerror(
        self, minimal_doc: object, tmp_path: Path
    ) -> None:
        """Second-review Gate G2 finding: the prior version of this file
        created a read_only_dir fixture but never actually used it or
        made it read-only -- the permission-denied-directory case (as
        opposed to the already-covered missing-parent-directory case
        above) was never genuinely exercised. root is exempt from POSIX
        permission checks, so this test is meaningless (and would fail
        for the wrong reason) when run as root."""
        if os.geteuid() == 0:
            pytest.skip("root is exempt from POSIX permission checks")
        read_only_dir = tmp_path / "readonly"
        read_only_dir.mkdir()
        os.chmod(read_only_dir, 0o555)
        try:
            with pytest.raises(NotebookWriteError):
                dump(minimal_doc, read_only_dir / "output.ipynb", profile="declared")
        finally:
            os.chmod(read_only_dir, 0o755)  # restore so tmp_path cleanup can remove it

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


class TestPermissionPreservation:
    """LIBIPYNB-Q19 (P0-D): tempfile.mkstemp() always creates its file at
    0600 -- without preserving the destination's own mode first,
    overwriting a 0644 file silently produced a 0600 one."""

    @POSIX_ONLY
    def test_overwriting_a_0644_file_preserves_its_mode(
        self, minimal_doc: object, tmp_path: Path
    ) -> None:
        target = tmp_path / "output.ipynb"
        target.write_text("old content", encoding="utf-8")
        os.chmod(target, 0o644)

        dump(minimal_doc, target, profile="declared")

        assert stat.S_IMODE(os.stat(target).st_mode) == 0o644

    @POSIX_ONLY
    def test_overwriting_a_0600_file_preserves_its_mode_too(
        self, minimal_doc: object, tmp_path: Path
    ) -> None:
        """Not just the common case -- an unusually restrictive existing
        mode must also survive, not be silently loosened."""
        target = tmp_path / "output.ipynb"
        target.write_text("old content", encoding="utf-8")
        os.chmod(target, 0o600)

        dump(minimal_doc, target, profile="declared")

        assert stat.S_IMODE(os.stat(target).st_mode) == 0o600

    @POSIX_ONLY
    def test_a_brand_new_file_gets_the_umask_aware_default_not_mkstemps_0600(
        self, minimal_doc: object, tmp_path: Path
    ) -> None:
        target = tmp_path / "new.ipynb"
        assert not target.exists()

        dump(minimal_doc, target, profile="declared")

        saved_umask = os.umask(0)
        os.umask(saved_umask)
        expected = 0o666 & ~saved_umask
        assert stat.S_IMODE(os.stat(target).st_mode) == expected


class TestSymlinkPolicy:
    """LIBIPYNB-Q19 (P0-D): dump() writes THROUGH an existing symlink --
    the symlink itself survives and keeps pointing at the (now updated)
    real file, rather than being replaced by a plain file."""

    def test_writing_to_a_symlink_updates_the_real_target_and_keeps_the_symlink(
        self, minimal_doc: object, tmp_path: Path
    ) -> None:
        real_target = tmp_path / "real.ipynb"
        real_target.write_text("old content", encoding="utf-8")
        link = tmp_path / "link.ipynb"
        os.symlink(real_target, link)

        dump(minimal_doc, link, profile="declared")

        assert link.is_symlink(), "dump() must not replace the symlink with a plain file"
        # os.path.samefile() compares file identity (device+inode on
        # POSIX), not path strings -- os.readlink() on Windows can return
        # an extended-length (\\?\-prefixed) path that a literal/resolved
        # string comparison would spuriously fail on even though both
        # sides name the same file.
        assert os.path.samefile(link, real_target)
        content = real_target.read_text(encoding="utf-8")
        assert '"nbformat": 4' in content
        assert "old content" not in content

    @POSIX_ONLY
    def test_writing_through_a_symlink_preserves_the_targets_own_permissions(
        self, minimal_doc: object, tmp_path: Path
    ) -> None:
        real_target = tmp_path / "real.ipynb"
        real_target.write_text("old content", encoding="utf-8")
        os.chmod(real_target, 0o644)
        link = tmp_path / "link.ipynb"
        os.symlink(real_target, link)

        dump(minimal_doc, link, profile="declared")

        assert stat.S_IMODE(os.stat(real_target).st_mode) == 0o644

    def test_writing_to_a_new_destination_through_a_symlinked_parent_directory(
        self, minimal_doc: object, tmp_path: Path
    ) -> None:
        """A symlinked PARENT directory, not the destination file itself,
        is a different and equally realistic shape -- the temp file must
        still land on the real directory (for atomic same-filesystem
        rename) and the write must succeed."""
        real_dir = tmp_path / "real_dir"
        real_dir.mkdir()
        link_dir = tmp_path / "link_dir"
        os.symlink(real_dir, link_dir, target_is_directory=True)

        dump(minimal_doc, link_dir / "output.ipynb", profile="declared")

        assert (real_dir / "output.ipynb").exists()
        content = (real_dir / "output.ipynb").read_text(encoding="utf-8")
        assert '"nbformat": 4' in content

    def test_a_broken_symlink_destination_is_healed_not_rejected(
        self, minimal_doc: object, tmp_path: Path
    ) -> None:
        """A symlink whose target does not (yet) exist -- dump() must
        create the target with a sensible new-file default, following the
        same "write through the symlink" policy as any other symlink
        destination, rather than treating a dangling symlink as an
        error."""
        nonexistent_target = tmp_path / "not_yet_created.ipynb"
        link = tmp_path / "broken_link.ipynb"
        os.symlink(nonexistent_target, link)
        assert not nonexistent_target.exists()

        dump(minimal_doc, link, profile="declared")

        assert nonexistent_target.exists()
        assert link.is_symlink()
        content = nonexistent_target.read_text(encoding="utf-8")
        assert '"nbformat": 4' in content

    def test_a_symlink_loop_destination_fails_as_notebookwriteerror_not_a_raw_runtimeerror(
        self, minimal_doc: object, tmp_path: Path
    ) -> None:
        """Second-review Gate G2 CRITICAL-adjacent finding: on CPython
        3.11/3.12 specifically, Path.resolve() (strict=False) deliberately
        raises RuntimeError -- not OSError -- for a symlink loop. Left
        uncaught, that RuntimeError leaked straight past dump()'s
        NotebookWriteError contract, on the project's own stated minimum
        supported Python version, on POSIX -- undetectable from this
        Windows development environment alone, where the same input
        doesn't trip pathlib's loop guard the same way (the failure
        instead surfaces later, correctly, at os.replace()). Whichever
        internal mechanism actually fires on a given platform, dump()
        itself must always raise NotebookWriteError here, never anything
        else."""
        a = tmp_path / "a.ipynb"
        b = tmp_path / "b.ipynb"
        os.symlink(b, a)
        os.symlink(a, b)

        with pytest.raises(NotebookWriteError):
            dump(minimal_doc, a, profile="declared")


class TestDurability:
    """LIBIPYNB-Q19 (P0-D): the temp file's content is fsync-ed before the
    rename, and the containing directory is best-effort fsync-ed after --
    a test can't directly observe crash-durability, but can confirm the
    fsync calls actually happen on the path this function's own docstring
    now promises."""

    def test_the_temp_files_content_is_fsynced_before_the_rename(
        self, minimal_doc: object, tmp_path: Path
    ) -> None:
        target = tmp_path / "output.ipynb"
        with patch("os.fsync", wraps=os.fsync) as spy:
            dump(minimal_doc, target, profile="declared")
        assert spy.call_count >= 1

    @POSIX_ONLY
    def test_the_parent_directory_is_fsynced_after_the_rename_on_posix(
        self, minimal_doc: object, tmp_path: Path
    ) -> None:
        target = tmp_path / "output.ipynb"
        with patch("os.fsync", wraps=os.fsync) as spy:
            dump(minimal_doc, target, profile="declared")
        # One fsync for the temp file's content, one for the parent
        # directory (POSIX only) -- both must have actually happened, not
        # just the file-content one.
        assert spy.call_count >= 2

    @POSIX_ONLY
    def test_a_failure_during_directory_fsync_does_not_fail_the_write(
        self, minimal_doc: object, tmp_path: Path
    ) -> None:
        """Best-effort: the atomic rename has already succeeded by the
        time the directory fsync runs -- a platform/filesystem that
        doesn't support it must not turn a successful write into a
        reported failure. Only the SECOND os.fsync call (the directory,
        after the content one already legitimately succeeded) is made to
        fail here -- a failure on the first (content) call is a different,
        legitimately-fatal case, covered separately below."""
        target = tmp_path / "output.ipynb"
        real_fsync = os.fsync
        call_count = 0

        def flaky_fsync(fd: int) -> None:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                real_fsync(fd)
                return
            raise OSError("simulated: directory fsync not supported here")

        with patch("os.fsync", side_effect=flaky_fsync):
            dump(minimal_doc, target, profile="declared")  # must not raise
        assert call_count >= 2
        assert target.exists()
        reloaded = load(target, mode="preservation")
        assert reloaded.nbformat == 4


class TestCleanupOnFailure:
    """LIBIPYNB-Q19 (P0-D): the temp file must be removed on every failure
    path, including a failure inside the new chmod/fsync steps -- not just
    the pre-existing write/rename failure paths."""

    def test_temp_file_is_removed_if_chmod_fails(self, minimal_doc: object, tmp_path: Path) -> None:
        target = tmp_path / "output.ipynb"
        with (
            patch("os.chmod", side_effect=OSError("simulated chmod failure")),
            pytest.raises(NotebookWriteError),
        ):
            dump(minimal_doc, target, profile="declared")
        assert list(tmp_path.glob("*.tmp")) == []
        assert not target.exists()

    def test_temp_file_is_removed_if_fsync_fails_on_the_content_write(
        self, minimal_doc: object, tmp_path: Path
    ) -> None:
        target = tmp_path / "output.ipynb"
        with (
            patch("os.fsync", side_effect=OSError("simulated fsync failure")),
            pytest.raises(NotebookWriteError),
        ):
            dump(minimal_doc, target, profile="declared")
        assert list(tmp_path.glob("*.tmp")) == []
        assert not target.exists()
