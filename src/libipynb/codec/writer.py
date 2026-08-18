"""Deterministic Jupyter Notebook JSON writer."""

from __future__ import annotations

import contextlib
import json
import os
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


def dump(
    document: NotebookDocument | Mapping[str, Any],
    destination: Destination,
    *,
    profile: str | None = None,
    indent: int | None = 1,
) -> None:
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
    try:
        fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
                f.write(text)
            os.replace(tmp, path)
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
