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


def is_safe_resource_filename(name: str) -> bool:
    """An attachment/resource key is untrusted document content, not a
    path -- reject anything that is not a bare filename (no separators, no
    ``..`` segments, not absolute) before it becomes a resource filename a
    caller might join onto a directory when writing to disk."""
    if not name or name in {".", ".."} or "\\" in name:
        return False
    candidate = PurePosixPath(name)
    return candidate.name == name and ".." not in candidate.parts


__all__ = ["is_safe_resource_filename"]
