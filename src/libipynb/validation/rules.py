"""Pure profile selection and semantic validation rules for nbformat 4.x."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Mapping
from urllib.parse import unquote

from ..diagnostics import Diagnostic, DiagnosticSeverity as Severity, SourceLocation

from ..codec.reader import CELL_ID_PATTERN

KNOWN_TOP_LEVEL = frozenset({"nbformat", "nbformat_minor", "metadata", "cells"})
KNOWN_CELL_TYPES = frozenset({"code", "markdown", "raw"})
KNOWN_OUTPUT_TYPES = frozenset(
    {"stream", "display_data", "execute_result", "error"}
)
ATTACHMENT_REFERENCE = re.compile(r"attachment:([^\s)\]}>\"']+)")


@dataclass(frozen=True, slots=True)
class SelectedProfile:
    name: str
    expected_major: int
    expected_minor: int
    declared_major: int | None
    declared_minor: int | None
    allow_forward: bool

    @property
    def require_cell_ids(self) -> bool:
        declared = self.declared_minor
        return self.expected_minor >= 5 or declared is not None and declared >= 5

    @property
    def require_unique_cell_names(self) -> bool:
        """Whether notebook-wide cell-name uniqueness applies (nbformat 4.2+).

        The authority states from 4.4 that JSON Schema cannot express this, so
        it can only be enforced semantically. Scoped to 4.2 and later: 4.0 and
        4.1 permit duplicate names and tightening them would be its own defect.
        """
        declared = self.declared_minor
        return self.expected_minor >= 2 or declared is not None and declared >= 2


def diagnostic(
    code: str,
    message: str,
    path: tuple[str | int, ...],
    *,
    severity: Severity = Severity.ERROR,
) -> Diagnostic:
    return Diagnostic(
        code=code,
        message=message,
        severity=severity,
        location=SourceLocation(path=path),
    )


def _integer(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def select_profile(
    model: Mapping[str, Any],
    requested: str | None,
) -> tuple[SelectedProfile, list[Diagnostic]]:
    diagnostics: list[Diagnostic] = []
    major = _integer(model.get("nbformat"))
    minor = _integer(model.get("nbformat_minor"))
    if major != 4:
        diagnostics.append(
            diagnostic("IPYNB_VERSION", "nbformat must equal 4", ("nbformat",))
        )
    if minor is None or minor < 0:
        diagnostics.append(
            diagnostic(
                "IPYNB_MINOR_VERSION",
                "nbformat_minor must be a non-negative integer",
                ("nbformat_minor",),
            )
        )

    selected = (requested or "declared").removeprefix("nbformat-")
    allow_forward = False
    if selected == "declared":
        effective_minor = min(minor, 5) if minor is not None and minor >= 0 else 5
        allow_forward = major == 4 and minor is not None and minor > 5
        profile = SelectedProfile(
            "declared",
            4,
            effective_minor,
            major,
            minor,
            allow_forward,
        )
        if allow_forward:
            diagnostics.append(
                diagnostic(
                    "IPYNB_FORWARD_VERSION",
                    f"declared nbformat 4.{minor} is preservation-only; "
                    "validation uses the current 4.5 structural baseline",
                    ("nbformat_minor",),
                    severity=Severity.WARNING,
                )
            )
        return profile, diagnostics

    if selected == "current":
        expected = (4, 5)
    elif selected in {f"4.{value}" for value in range(6)}:
        expected = (4, int(selected.split(".", 1)[1]))
    else:
        raise ValueError(
            "profile must be 'declared', 'current', or one of "
            "nbformat 4.0 through 4.5"
        )
    profile = SelectedProfile(
        selected,
        expected[0],
        expected[1],
        major,
        minor,
        False,
    )
    if (major, minor) != expected:
        diagnostics.append(
            diagnostic(
                "IPYNB_PROFILE",
                f"document declares {major}.{minor}, expected "
                f"{expected[0]}.{expected[1]} for profile {selected}",
                ("nbformat", "nbformat_minor"),
            )
        )
    return profile, diagnostics


def _validate_source(
    value: object,
    path: tuple[str | int, ...],
    diagnostics: list[Diagnostic],
) -> str | None:
    if isinstance(value, str):
        return value
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return "".join(value)
    diagnostics.append(
        diagnostic(
            "IPYNB_CELL_SOURCE",
            "cell source must be a string or an array of strings",
            path,
        )
    )
    return None


def _validate_tags(
    metadata: Mapping[str, Any],
    path: tuple[str | int, ...],
    diagnostics: list[Diagnostic],
) -> None:
    if "tags" not in metadata:
        return
    tags = metadata["tags"]
    if not isinstance(tags, list) or any(not isinstance(tag, str) for tag in tags):
        diagnostics.append(
            diagnostic(
                "IPYNB_TAGS",
                "cell metadata tags must be an array of strings",
                (*path, "tags"),
            )
        )
        return
    seen: set[str] = set()
    for index, tag in enumerate(tags):
        if tag in seen:
            diagnostics.append(
                diagnostic(
                    "IPYNB_TAG_DUPLICATE",
                    f"duplicate cell tag {tag!r}",
                    (*path, "tags", index),
                )
            )
        seen.add(tag)
        if "," in tag:
            diagnostics.append(
                diagnostic(
                    "IPYNB_TAG_COMMA",
                    "cell tags must not contain commas",
                    (*path, "tags", index),
                )
            )


def _is_json_value(value: object) -> bool:
    if value is None or isinstance(value, (str, int, float, bool)):
        return True
    if isinstance(value, list):
        return all(_is_json_value(item) for item in value)
    if isinstance(value, Mapping):
        return all(
            isinstance(key, str) and _is_json_value(item)
            for key, item in value.items()
        )
    return False


def _validate_mime_bundle(
    value: object,
    path: tuple[str | int, ...],
    diagnostics: list[Diagnostic],
    *,
    container_code: str = "IPYNB_MIME_BUNDLE",
) -> None:
    if not isinstance(value, Mapping):
        diagnostics.append(
            diagnostic(container_code, "MIME bundle must be an object", path)
        )
        return
    for mime_type, payload in value.items():
        item_path = (*path, str(mime_type))
        if (
            not isinstance(mime_type, str)
            or not mime_type
            or "/" not in mime_type
        ):
            diagnostics.append(
                diagnostic(
                    "IPYNB_MIME_TYPE",
                    f"invalid MIME type key {mime_type!r}",
                    item_path,
                )
            )
        if not _is_json_value(payload):
            diagnostics.append(
                diagnostic(
                    "IPYNB_MIME_VALUE",
                    "MIME payload must be JSON-compatible data",
                    item_path,
                )
            )
        if isinstance(mime_type, str) and mime_type.startswith("image/"):
            if not (
                isinstance(payload, str)
                or isinstance(payload, list)
                and all(isinstance(item, str) for item in payload)
            ):
                diagnostics.append(
                    diagnostic(
                        "IPYNB_BINARY_MIME_VALUE",
                        "image MIME payload must be a string or string array",
                        item_path,
                    )
                )


def _validate_attachments(
    cell: Mapping[str, Any],
    cell_type: object,
    source_text: str | None,
    path: tuple[str | int, ...],
    diagnostics: list[Diagnostic],
) -> None:
    if "attachments" not in cell:
        if source_text is not None:
            for reference in ATTACHMENT_REFERENCE.findall(source_text):
                diagnostics.append(
                    diagnostic(
                        "IPYNB_ATTACHMENT_MISSING",
                        f"attachment target {unquote(reference)!r} is missing",
                        (*path, "source"),
                    )
                )
        return
    attachments = cell["attachments"]
    if cell_type not in {"markdown", "raw"}:
        diagnostics.append(
            diagnostic(
                "IPYNB_ATTACHMENTS_CELL_TYPE",
                "attachments are permitted only on markdown and raw cells",
                (*path, "attachments"),
            )
        )
    if not isinstance(attachments, Mapping):
        diagnostics.append(
            diagnostic(
                "IPYNB_ATTACHMENTS",
                "attachments must be an object",
                (*path, "attachments"),
            )
        )
        return
    names: set[str] = set()
    for name, bundle in attachments.items():
        if not isinstance(name, str) or not name:
            diagnostics.append(
                diagnostic(
                    "IPYNB_ATTACHMENT_NAME",
                    "attachment names must be non-empty strings",
                    (*path, "attachments", str(name)),
                )
            )
            continue
        names.add(name)
        _validate_mime_bundle(
            bundle,
            (*path, "attachments", name),
            diagnostics,
            container_code="IPYNB_ATTACHMENT_BUNDLE",
        )
    references = {
        unquote(value)
        for value in ATTACHMENT_REFERENCE.findall(source_text or "")
    }
    for missing in sorted(references.difference(names)):
        diagnostics.append(
            diagnostic(
                "IPYNB_ATTACHMENT_MISSING",
                f"attachment target {missing!r} is missing",
                (*path, "source"),
            )
        )
    for orphan in sorted(names.difference(references)):
        diagnostics.append(
            diagnostic(
                "IPYNB_ATTACHMENT_ORPHAN",
                f"attachment {orphan!r} has no attachment URI reference",
                (*path, "attachments", orphan),
                severity=Severity.WARNING,
            )
        )


def _validate_output(
    output: object,
    path: tuple[str | int, ...],
    profile: SelectedProfile,
    diagnostics: list[Diagnostic],
) -> None:
    if not isinstance(output, Mapping):
        diagnostics.append(
            diagnostic("IPYNB_OUTPUT", "output must be an object", path)
        )
        return
    output_type = output.get("output_type")
    if output_type not in KNOWN_OUTPUT_TYPES:
        code = (
            "IPYNB_FORWARD_OUTPUT_TYPE"
            if profile.allow_forward
            else "IPYNB_OUTPUT_TYPE"
        )
        diagnostics.append(
            diagnostic(
                code,
                f"unrecognized output_type {output_type!r}",
                (*path, "output_type"),
                severity=Severity.WARNING if profile.allow_forward else Severity.ERROR,
            )
        )
        return
    if output_type == "stream":
        if output.get("name") not in {"stdout", "stderr"}:
            diagnostics.append(
                diagnostic(
                    "IPYNB_STREAM_NAME",
                    "stream name must be 'stdout' or 'stderr'",
                    (*path, "name"),
                )
            )
        text = output.get("text")
        if not (
            isinstance(text, str)
            or isinstance(text, list)
            and all(isinstance(item, str) for item in text)
        ):
            diagnostics.append(
                diagnostic(
                    "IPYNB_STREAM_TEXT",
                    "stream text must be a string or string array",
                    (*path, "text"),
                )
            )
        return
    if output_type in {"display_data", "execute_result"}:
        _validate_mime_bundle(
            output.get("data"),
            (*path, "data"),
            diagnostics,
        )
        if not isinstance(output.get("metadata"), Mapping):
            diagnostics.append(
                diagnostic(
                    "IPYNB_OUTPUT_METADATA",
                    "rich output metadata must be an object",
                    (*path, "metadata"),
                )
            )
        if output_type == "execute_result":
            count = output.get("execution_count")
            if isinstance(count, bool) or (
                count is not None and not isinstance(count, int)
            ):
                diagnostics.append(
                    diagnostic(
                        "IPYNB_EXECUTION_COUNT",
                        "execute_result execution_count must be an integer or null",
                        (*path, "execution_count"),
                    )
                )
        return
    for field in ("ename", "evalue"):
        if not isinstance(output.get(field), str):
            diagnostics.append(
                diagnostic(
                    "IPYNB_ERROR_FIELD",
                    f"error output {field} must be a string",
                    (*path, field),
                )
            )
    traceback = output.get("traceback")
    if not isinstance(traceback, list) or any(
        not isinstance(item, str) for item in traceback
    ):
        diagnostics.append(
            diagnostic(
                "IPYNB_ERROR_TRACEBACK",
                "error traceback must be an array of strings",
                (*path, "traceback"),
            )
        )


def validate_model(
    model: Mapping[str, Any],
    profile: SelectedProfile,
) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    if profile.allow_forward:
        for key in model:
            if key not in KNOWN_TOP_LEVEL:
                diagnostics.append(
                    diagnostic(
                        "IPYNB_FORWARD_FIELD",
                        f"unrecognized future top-level field {key!r} is preserved",
                        (key,),
                        severity=Severity.WARNING,
                    )
                )

    if not isinstance(model.get("metadata"), Mapping):
        diagnostics.append(
            diagnostic(
                "IPYNB_METADATA",
                "metadata must be an object",
                ("metadata",),
            )
        )
    cells = model.get("cells")
    if not isinstance(cells, list):
        diagnostics.append(
            diagnostic("IPYNB_CELLS", "cells must be an array", ("cells",))
        )
        return diagnostics

    seen_ids: set[str] = set()
    seen_names: set[str] = set()
    for index, cell in enumerate(cells):
        path = ("cells", index)
        if not isinstance(cell, Mapping):
            diagnostics.append(
                diagnostic("IPYNB_CELL", "cell must be an object", path)
            )
            continue
        cell_type = cell.get("cell_type")
        known_cell = cell_type in KNOWN_CELL_TYPES
        if not known_cell:
            code = (
                "IPYNB_FORWARD_CELL_TYPE"
                if profile.allow_forward
                else "IPYNB_CELL_TYPE"
            )
            diagnostics.append(
                diagnostic(
                    code,
                    f"unrecognized cell_type {cell_type!r}",
                    (*path, "cell_type"),
                    severity=Severity.WARNING
                    if profile.allow_forward
                    else Severity.ERROR,
                )
            )

        cell_id = cell.get("id")
        if profile.require_cell_ids or cell_id is not None:
            if not isinstance(cell_id, str) or CELL_ID_PATTERN.fullmatch(cell_id) is None:
                diagnostics.append(
                    diagnostic(
                        "IPYNB_CELL_ID",
                        f"invalid or missing cell id {cell_id!r}",
                        (*path, "id"),
                    )
                )
            elif cell_id in seen_ids:
                diagnostics.append(
                    diagnostic(
                        "IPYNB_CELL_ID_DUPLICATE",
                        f"duplicate cell id {cell_id!r}",
                        (*path, "id"),
                    )
                )
            else:
                seen_ids.add(cell_id)

        metadata = cell.get("metadata")
        if not isinstance(metadata, Mapping):
            diagnostics.append(
                diagnostic(
                    "IPYNB_CELL_METADATA",
                    "cell metadata must be an object",
                    (*path, "metadata"),
                )
            )
        else:
            _validate_tags(metadata, (*path, "metadata"), diagnostics)
            # Notebook-wide cell-name uniqueness (nbformat 4.2+). The schema
            # cannot express this, so it is checked here or nowhere. Only a
            # PRESENT, well-formed name participates: absence is not a
            # collision, and an empty name is already reported by the schema.
            cell_name = metadata.get("name")
            if profile.require_unique_cell_names and isinstance(cell_name, str) and cell_name:
                if cell_name in seen_names:
                    diagnostics.append(
                        diagnostic(
                            "IPYNB_CELL_NAME_DUPLICATE",
                            f"duplicate cell name {cell_name!r}",
                            (*path, "metadata", "name"),
                        )
                    )
                else:
                    seen_names.add(cell_name)
        source_text = _validate_source(
            cell.get("source"),
            (*path, "source"),
            diagnostics,
        )
        _validate_attachments(
            cell,
            cell_type,
            source_text,
            path,
            diagnostics,
        )
        if not known_cell or cell_type != "code":
            continue
        count = cell.get("execution_count")
        if isinstance(count, bool) or (
            count is not None and not isinstance(count, int)
        ):
            diagnostics.append(
                diagnostic(
                    "IPYNB_EXECUTION_COUNT",
                    "code-cell execution_count must be an integer or null",
                    (*path, "execution_count"),
                )
            )
        outputs = cell.get("outputs")
        if not isinstance(outputs, list):
            diagnostics.append(
                diagnostic(
                    "IPYNB_OUTPUTS",
                    "code-cell outputs must be an array",
                    (*path, "outputs"),
                )
            )
            continue
        for output_index, output in enumerate(outputs):
            _validate_output(
                output,
                (*path, "outputs", output_index),
                profile,
                diagnostics,
            )
    return diagnostics
