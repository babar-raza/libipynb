"""Deterministic Jupyter Notebook JSON writer."""

from __future__ import annotations

import contextlib
import json
import os
import stat
import tempfile
from collections.abc import Mapping
from copy import deepcopy
from os import PathLike
from pathlib import Path
from typing import Any, TextIO

from ..errors import NotebookWriteError
from ..model import NotebookDocument
from ..security import IPYNB_DEFAULT_LIMITS
from .reader import Source, load

Destination = str | PathLike[str] | TextIO


def _as_mapping(value: NotebookDocument | Mapping[str, Any]) -> Mapping[str, Any]:
    if isinstance(value, NotebookDocument):
        return value.raw
    if isinstance(value, Mapping):
        return value
    raise TypeError("document must be an NotebookDocument or mapping")


def _profile_version(profile: str | None, source: Mapping[str, Any]) -> tuple[int, int]:
    selected = profile or "4.5"
    if selected.startswith("nbformat-"):
        selected = selected.removeprefix("nbformat-")
    if selected == "declared":
        major = source.get("nbformat")
        minor = source.get("nbformat_minor")
        if (
            isinstance(major, bool)
            or not isinstance(major, int)
            or major != 4
            or isinstance(minor, bool)
            or not isinstance(minor, int)
            or minor < 0
        ):
            raise NotebookWriteError(
                "declared profile requires a non-negative nbformat 4.x version"
            )
        return major, minor
    if selected not in {"4.0", "4.1", "4.2", "4.3", "4.4", "4.5"}:
        raise ValueError("profile must be 'declared' or one of nbformat 4.0 through 4.5")
    major, minor = selected.split(".", 1)
    return int(major), int(minor)


def _normalized(
    value: NotebookDocument | Mapping[str, Any], *, profile: str | None
) -> dict[str, Any]:
    source = deepcopy(dict(_as_mapping(value)))
    major, minor = _profile_version(profile, source)
    if profile == "declared" or (
        isinstance(profile, str) and profile.removeprefix("nbformat-") == "declared"
    ):
        return source

    declared_major = source.get("nbformat")
    declared_minor = source.get("nbformat_minor")
    if (declared_major, declared_minor) != (major, minor):
        raise NotebookWriteError(
            f"writing nbformat {major}.{minor} from declared version "
            f"{declared_major}.{declared_minor} requires explicit upgrade()",
            code="IPYNB_EXPLICIT_UPGRADE_REQUIRED",
            context={
                "declared_version": (declared_major, declared_minor),
                "target_version": (major, minor),
            },
        )

    from ..validation import validate

    report = validate(source, profile=f"nbformat-{major}.{minor}")
    if not report.is_valid:
        first = report.errors[0]
        raise NotebookWriteError(
            f"notebook is not valid for nbformat {major}.{minor}: {first.message}",
            code=first.code,
            context={
                "path": first.location.path if first.location is not None else (),
                "error_count": len(report.errors),
            },
        )
    return source


def dumps(
    document: NotebookDocument | Mapping[str, Any],
    *,
    profile: str | None = None,
    indent: int | None = 1,
) -> str:
    """Serialize *document* to a JSON string.

    LIBIPYNB-Q4: the default ``profile=None`` resolves to the schema-
    validating ``"4.5"`` profile (via ``_profile_version``), which
    re-validates the ENTIRE document against the nbformat 4.5 schema on
    every call and requires the document already be declared 4.5 -- not a
    cheap no-op. Pass ``profile="declared"`` for a passthrough that
    preserves the document's own declared version and skips
    re-validation. This is deliberate, not an oversight: it is the
    mechanism that enforces IPYNB-ID-001 ("cell IDs are synthesized only
    via an explicit ``upgrade()`` call, never silently by a write-time
    version bump") -- changing the default would silently defeat that
    guarantee, so it is not configurable here; choose ``profile``
    explicitly at each call site instead.
    """
    try:
        result = json.dumps(
            _normalized(document, profile=profile),
            ensure_ascii=False,
            indent=indent,
            sort_keys=True,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        if isinstance(exc, ValueError) and str(exc).startswith("profile must"):
            raise
        raise NotebookWriteError(f"cannot serialize notebook: {exc}") from exc
    try:
        encoded_length = len(result.encode("utf-8"))
    except UnicodeEncodeError as exc:
        # LIBIPYNB-Q6: a lone/unpaired UTF-16 surrogate in the notebook's
        # content is legal Python str content (json.dumps above happily
        # produced it) but cannot be UTF-8 encoded -- crashes here
        # unconditionally, and profile="declared" (the profile every
        # shipped CLI write path uses) skips _normalized()'s validate()
        # call above, so this was previously the ONE genuinely unguarded
        # path to this exact crash (non-declared profiles incidentally
        # survive via validate()'s own broad exception handling).
        raise NotebookWriteError(
            f"notebook contains invalid unicode (unpaired UTF-16 surrogate): {exc}",
            code="IPYNB_INVALID_SURROGATE",
        ) from exc
    IPYNB_DEFAULT_LIMITS.enforce("max_output_bytes", encoded_length)
    return result


def _target_mode(real_path: Path) -> int:
    """LIBIPYNB-Q19 (P0-D): the mode a new temp file should end up with,
    before it gets renamed onto *real_path*. If *real_path* already
    exists, preserve its exact mode -- ``tempfile.mkstemp()`` always
    creates its file at ``0600``, so without this an overwrite of an
    existing ``0644`` file silently produced a ``0600`` one. If it does
    not exist yet, use the umask-aware default a plain ``open(path,
    "w")`` would have produced (``0666 & ~umask``), not ``mkstemp``'s
    restrictive ``0600`` -- a newly-created notebook file should not be
    surprisingly more locked-down than any other file this process
    creates."""
    try:
        return stat.S_IMODE(os.stat(real_path).st_mode)
    except FileNotFoundError:
        saved_umask = os.umask(0)
        os.umask(saved_umask)  # umask has no read-only getter; restore immediately
        return 0o666 & ~saved_umask


def _fsync_directory_best_effort(directory: Path) -> None:
    """LIBIPYNB-Q19 (P0-D): fsync-ing the parent directory after
    ``os.replace()`` is what makes the rename itself durable across a
    crash/power loss on POSIX -- the temp file's own fsync only
    guarantees its *content* is durable, not that the directory entry now
    pointing at it is. Best-effort only, and POSIX-only: not every
    filesystem supports/needs a directory fsync, Windows has no
    equivalent, and a failure here must never fail the write -- the
    atomic rename itself has already succeeded by the time this runs."""
    if os.name != "posix":
        return
    with contextlib.suppress(OSError):
        dir_fd = os.open(str(directory), os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)


def _resolve_destination(path: Path) -> Path:
    """Resolve *path* through any symlinks (``strict=False``, so this also
    works for a destination that does not exist yet), converting the
    loop-detection ``RuntimeError`` CPython's own ``pathlib`` deliberately
    raises for a symlink loop (confirmed present on 3.11 and 3.12; not
    raised the same way on every platform/version -- see the call site's
    own comment) into this module's ``NotebookWriteError`` contract, which
    every other failure path in ``dump()`` reports through. A bare
    ``RuntimeError`` would otherwise leak past that contract."""
    try:
        return path.resolve()
    except RuntimeError as exc:
        raise NotebookWriteError(f"cannot write notebook to {path}: {exc}") from exc


def dump(
    document: NotebookDocument | Mapping[str, Any],
    destination: Destination,
    *,
    profile: str | None = None,
    indent: int | None = 1,
) -> None:
    """Serialize *document* and write it to *destination*.

    LIBIPYNB-Q19 (P0-D): for a path destination, this is a write-to-temp-
    then-``os.replace()`` -- the destination either ends up with the
    complete new content or is left completely untouched; it is never
    observable half-written. Beyond that atomicity guarantee, this
    function also provides:

    - **Permission preservation**: overwriting an existing file keeps its
      exact mode; a new file gets the umask-aware default a plain
      ``open(path, "w")`` would produce. Never ``tempfile.mkstemp()``'s
      restrictive ``0600`` for either case.
    - **Durability** (POSIX only): the temp file's content is ``fsync``ed
      before the rename, and the containing directory is best-effort
      ``fsync``ed after -- both are what actually survive a crash/power
      loss immediately after this call returns, not merely "the OS write
      buffer accepted it." Windows has no equivalent directory-fsync
      primitive; ``os.replace()``'s own atomicity still holds there, but
      this function makes no durability-across-power-loss claim on
      Windows beyond what the OS/filesystem itself provides.
    - **Symlink policy**: if *destination* is (or is inside) a symlink,
      this writes *through* it -- the symlink itself survives and keeps
      pointing at the (now updated) real file, matching the common "safe
      overwrite" convention for a config-file-like target. It does not
      replace the symlink with a plain file.
    - **Cleanup**: the temp file is removed on every failure path, before
      the failure is reported.

    The stream-write path (writing to a file-like object instead of a
    path) has none of the above -- streams cannot support atomic/durable
    replace semantics, permission inheritance, or symlink resolution, so
    this function does not attempt to simulate any of them there.
    """
    text = dumps(document, profile=profile, indent=indent) + "\n"
    if hasattr(destination, "write"):
        try:
            written = destination.write(text)
        except (OSError, UnicodeError) as exc:
            raise NotebookWriteError(f"cannot write notebook: {exc}") from exc
        if written is not None and written != len(text):
            raise NotebookWriteError("notebook destination accepted a partial write")
        return
    path = Path(destination)
    # Resolve symlinks BEFORE deciding the temp-file directory and the
    # os.replace() target, so this writes THROUGH an existing symlink
    # rather than replacing the symlink itself -- and so the temp file
    # lands on the same filesystem as the real destination, keeping
    # os.replace() atomic. strict=False (the default) also works
    # correctly for a destination that does not exist yet. Routed through
    # _resolve_destination() rather than called bare: on CPython 3.11 and
    # 3.12 specifically (confirmed against the actual interpreter
    # source), Path.resolve() deliberately raises RuntimeError -- not
    # OSError -- for a symlink loop, even with strict=False; on Windows
    # it doesn't raise at all for the same input (the failure instead
    # surfaces later, correctly, at os.replace()). Left uncaught here,
    # that RuntimeError would leak past every other failure path in this
    # function, which all report through NotebookWriteError.
    real_path = _resolve_destination(path)
    try:
        target_mode = _target_mode(real_path)
        fd, tmp = tempfile.mkstemp(dir=real_path.parent, suffix=".tmp")
        try:
            # os.fdopen(fd, ...) must come first, before anything else
            # that could raise: it hands the raw fd from mkstemp() to a
            # proper file object, so the `with` block's __exit__ closes
            # it on any failure path, not just success. A prior version
            # called os.chmod(tmp, ...) BEFORE this -- if chmod raised,
            # fd was never closed, and on Windows an open handle to a
            # file blocks deleting it, so the cleanup os.unlink(tmp)
            # below silently failed too (suppressed, since it's expected
            # to be a no-op on the success path where the file is
            # already gone).
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
                os.chmod(tmp, target_mode)
                f.write(text)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, real_path)
            _fsync_directory_best_effort(real_path.parent)
        except BaseException:
            with contextlib.suppress(OSError):
                os.unlink(tmp)
            raise
    except (OSError, UnicodeError) as exc:
        raise NotebookWriteError(f"cannot write notebook to {path}: {exc}") from exc


def roundtrip(source: Source, dest: Destination) -> dict[str, Any]:
    document = load(source, mode="preservation")
    dump(document, dest, profile="declared")
    return load(dest, mode="preservation").raw
