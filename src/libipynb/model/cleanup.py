"""Deterministic notebook cleanup with previewable change reports."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .._internal.immutable import deep_freeze
from .document import NotebookDocument


def _cell_requests_keep_output(cell_metadata: dict[str, Any]) -> bool:
    if cell_metadata.get("keep_output") is True:
        return True
    tags = cell_metadata.get("tags")
    return isinstance(tags, list) and "keep_output" in tags


@dataclass(frozen=True, slots=True)
class CleanupPolicy:
    """Selection and mutation policy for version-control cleanup."""

    cell_ids: frozenset[str] | None = None
    output_types: frozenset[str] | None = None
    notebook_metadata_keys: frozenset[str] = frozenset()
    cell_metadata_keys: frozenset[str] = frozenset()
    reset_execution_counts: bool = True
    #: LIBIPYNB-P2 (nbstripout parity): when True (the default), a cell
    #: whose metadata sets `"keep_output": true` or whose `tags` include
    #: `"keep_output"` is exempted from output stripping and execution-count
    #: reset -- matching nbstripout's own per-cell escape hatch. This is a
    #: default-on library behavior (not CLI-only) because it is an explicit,
    #: per-cell author decision baked into the notebook itself, not a global
    #: policy choice the way the CLI's opinionated metadata-key defaults are.
    respect_keep_output_marker: bool = True

    def __post_init__(self) -> None:
        for name in (
            "cell_ids",
            "output_types",
            "notebook_metadata_keys",
            "cell_metadata_keys",
        ):
            value = getattr(self, name)
            if value is not None and any(not isinstance(item, str) or not item for item in value):
                raise ValueError(f"{name} must contain only non-empty strings")


@dataclass(frozen=True, slots=True)
class Change:
    """One deterministic notebook mutation."""

    operation: str
    path: tuple[str | int, ...]
    before: Any
    after: Any

    def __post_init__(self) -> None:
        # LIBIPYNB-Q43 Gate-G2 round-2 review finding: `deepcopy` only
        # broke aliasing to the constructor's input, not later mutation of
        # the field itself -- see model.diff.FieldChange's identical fix.
        object.__setattr__(self, "before", deep_freeze(self.before))
        object.__setattr__(self, "after", deep_freeze(self.after))


@dataclass(frozen=True, slots=True)
class ChangeReport:
    """Immutable ordered cleanup result."""

    changes: tuple[Change, ...] = ()

    @property
    def changed(self) -> bool:
        return bool(self.changes)

    @property
    def count(self) -> int:
        return len(self.changes)


def cleanup(
    document: NotebookDocument,
    *,
    policy: CleanupPolicy | None = None,
    dry_run: bool = False,
) -> ChangeReport:
    """Clear selected outputs/state and strip explicitly selected metadata.

    The same ordered report is returned by preview and mutation runs. Unknown
    metadata is never removed unless its exact key is in the policy.
    """

    if not isinstance(document, NotebookDocument):
        raise TypeError("document must be an NotebookDocument")
    selected = policy or CleanupPolicy()
    changes: list[Change] = []
    root = document.raw

    metadata = root.get("metadata")
    if not isinstance(metadata, dict):
        raise TypeError("notebook metadata must be an object before cleanup")
    for key in sorted(selected.notebook_metadata_keys):
        if key in metadata:
            changes.append(
                Change(
                    "remove_notebook_metadata",
                    ("metadata", key),
                    metadata[key],
                    None,
                )
            )
            if not dry_run:
                del metadata[key]

    cells = root.get("cells")
    if not isinstance(cells, list):
        raise TypeError("notebook cells must be an array before cleanup")
    for index, cell in enumerate(cells):
        if not isinstance(cell, dict):
            raise TypeError(f"cell {index} must be an object before cleanup")
        cell_id = cell.get("id")
        if selected.cell_ids is not None and cell_id not in selected.cell_ids:
            continue
        cell_metadata = cell.get("metadata")
        if not isinstance(cell_metadata, dict):
            raise TypeError(f"cell {index} metadata must be an object before cleanup")
        for key in sorted(selected.cell_metadata_keys):
            if key in cell_metadata:
                changes.append(
                    Change(
                        "remove_cell_metadata",
                        ("cells", index, "metadata", key),
                        cell_metadata[key],
                        None,
                    )
                )
                if not dry_run:
                    del cell_metadata[key]
        if cell.get("cell_type") != "code":
            continue
        if selected.respect_keep_output_marker and _cell_requests_keep_output(cell_metadata):
            continue
        outputs = cell.get("outputs")
        if not isinstance(outputs, list):
            raise TypeError(f"cell {index} outputs must be an array before cleanup")
        retained = (
            []
            if selected.output_types is None
            else [
                output
                for output in outputs
                if not isinstance(output, dict)
                or output.get("output_type") not in selected.output_types
            ]
        )
        if retained != outputs:
            changes.append(
                Change(
                    "replace_outputs",
                    ("cells", index, "outputs"),
                    outputs,
                    retained,
                )
            )
            if not dry_run:
                cell["outputs"] = retained
        if selected.reset_execution_counts and cell.get("execution_count") is not None:
            changes.append(
                Change(
                    "reset_execution_count",
                    ("cells", index, "execution_count"),
                    cell.get("execution_count"),
                    None,
                )
            )
            if not dry_run:
                cell["execution_count"] = None
        # LIBIPYNB-P2 Gate G8 finding: real nbstripout resets an
        # execute_result output's own embedded `execution_count` field in
        # lockstep with the cell-level one (confirmed by running real
        # nbstripout: `--keep-output` alone still nulls the nested field;
        # `--keep-output --keep-count` together preserves both). A kept
        # output's execution_count is exactly as much version-control noise
        # as the cell-level one -- resetting one but not the other partially
        # defeats the point of resetting at all.
        if selected.reset_execution_counts:
            for output_index, output in enumerate(retained):
                if isinstance(output, dict) and output.get("execution_count") is not None:
                    changes.append(
                        Change(
                            "reset_output_execution_count",
                            ("cells", index, "outputs", output_index, "execution_count"),
                            output.get("execution_count"),
                            None,
                        )
                    )
                    if not dry_run:
                        output["execution_count"] = None
    return ChangeReport(tuple(changes))
