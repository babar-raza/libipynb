"""Lifecycle reports and explicit notebook version conversion."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from ..errors import NotebookValidationError

if TYPE_CHECKING:
    from ..security.limits import NotebookResourceLimits
    from .document import NotebookDocument


@dataclass(frozen=True, slots=True)
class NotebookVersion:
    """A declared or structurally detected nbformat version."""

    major: int | None
    minor: int | None

    def __post_init__(self) -> None:
        for name, value in (("major", self.major), ("minor", self.minor)):
            if value is not None and (
                isinstance(value, bool) or not isinstance(value, int) or value < 0
            ):
                raise ValueError(f"{name} must be a non-negative integer or None")

    def as_tuple(self) -> tuple[int | None, int | None]:
        return self.major, self.minor


@dataclass(frozen=True, slots=True)
class RecoveryAction:
    """One deterministic repair made by ``mode='recovery'``."""

    code: str
    path: tuple[str | int, ...]
    message: str


@dataclass(frozen=True, slots=True)
class ConversionAction:
    """One explicit, auditable notebook conversion operation."""

    code: str
    path: tuple[str | int, ...]
    message: str


class ConversionDisposition(StrEnum):
    """How a reported construct is handled by a downgrade."""

    REMOVE = "remove"
    PRESERVE_AS_EXTENSION = "preserve_as_extension"
    BLOCK = "block"


@dataclass(frozen=True, slots=True)
class ConversionIssue:
    """One loss, preserved extension, or blocker found before conversion."""

    code: str
    path: tuple[str | int, ...]
    message: str
    disposition: ConversionDisposition


@dataclass(frozen=True, slots=True)
class CellIdRewrite:
    """Cell ID rewrite emitted by an explicit upgrade."""

    cell_index: int
    old_id: str | None
    new_id: str


@dataclass(frozen=True, slots=True)
class ConversionResult:
    """Converted document and the complete conversion ledger."""

    document: NotebookDocument
    actions: tuple[ConversionAction, ...]
    id_rewrites: tuple[CellIdRewrite, ...]
    issues: tuple[ConversionIssue, ...] = ()

    @property
    def losses(self) -> tuple[ConversionIssue, ...]:
        return tuple(
            issue for issue in self.issues if issue.disposition is ConversionDisposition.REMOVE
        )


@dataclass(frozen=True, slots=True)
class DowngradePlan:
    """Immutable report bound to the exact source content and target."""

    source_version: NotebookVersion
    target_version: NotebookVersion
    source_digest: str
    issues: tuple[ConversionIssue, ...]

    @property
    def losses(self) -> tuple[ConversionIssue, ...]:
        return tuple(
            issue for issue in self.issues if issue.disposition is ConversionDisposition.REMOVE
        )

    @property
    def preserved_extensions(self) -> tuple[ConversionIssue, ...]:
        return tuple(
            issue
            for issue in self.issues
            if issue.disposition is ConversionDisposition.PRESERVE_AS_EXTENSION
        )

    @property
    def blockers(self) -> tuple[ConversionIssue, ...]:
        return tuple(
            issue for issue in self.issues if issue.disposition is ConversionDisposition.BLOCK
        )

    @property
    def requires_loss_acceptance(self) -> bool:
        return bool(self.losses)


def _target_version(target: str) -> tuple[int, int]:
    selected = target.removeprefix("nbformat-")
    if selected not in {f"4.{minor}" for minor in range(6)}:
        raise ValueError("target must be one of nbformat 4.0 through 4.5")
    major, minor = selected.split(".", 1)
    return int(major), int(minor)


def _copy_source(
    value: NotebookDocument | Mapping[str, Any],
    *,
    limits: NotebookResourceLimits | None = None,
) -> dict[str, Any]:
    """LIBIPYNB-Q5: ``enforce_structure`` (the library's own bounded,
    iterative traversal -- already used correctly by ``validate()``/
    ``load()``) runs BEFORE the recursive ``deepcopy()`` below, not after.
    Previously this called ``deepcopy()`` unconditionally first, so a
    caller-supplied dict/NotebookDocument with ~495+ levels of nested
    metadata raised an uncaught ``RecursionError`` instead of the graceful
    ``NotebookResourceLimitError`` ``validate()`` already produces for
    identical adversarial input -- a trivially-triggered DoS against a
    documented safety guarantee that ``upgrade()``/``plan_downgrade()``/
    ``downgrade()`` had zero protection against below that crash threshold."""
    from .document import NotebookDocument

    if isinstance(value, NotebookDocument):
        raw = value.raw
    elif isinstance(value, Mapping):
        raw = dict(value)
    else:
        raise TypeError("value must be an NotebookDocument or mapping")

    from ..security.limits import effective_limits, enforce_structure

    enforce_structure(raw, effective_limits(limits))
    return deepcopy(raw)


def _declared_version(data: Mapping[str, Any]) -> tuple[int, int]:
    major = data.get("nbformat")
    minor = data.get("nbformat_minor")
    if (
        isinstance(major, bool)
        or not isinstance(major, int)
        or isinstance(minor, bool)
        or not isinstance(minor, int)
        or minor < 0
    ):
        raise NotebookValidationError(
            "conversion requires integer nbformat and non-negative nbformat_minor fields",
            code="IPYNB_CONVERSION_VERSION",
            context={"path": ("nbformat",)},
        )
    if major != 4:
        raise NotebookValidationError(
            "production conversion supports nbformat major version 4 only",
            code="IPYNB_CONVERSION_MAJOR",
            context={"source_version": (major, minor)},
        )
    return major, minor


def _source_digest(data: Mapping[str, Any]) -> str:
    try:
        encoded = json.dumps(
            data,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise NotebookValidationError(
            f"conversion source is not canonical JSON data: {exc}",
            code="IPYNB_CONVERSION_JSON",
        ) from exc
    return hashlib.sha256(encoded).hexdigest()


def _extension_issue(
    code: str,
    path: tuple[str | int, ...],
    target_minor: int,
) -> ConversionIssue:
    return ConversionIssue(
        code=code,
        path=path,
        message=(
            f"{'.'.join(str(part) for part in path)} is newer than "
            f"nbformat 4.{target_minor}; it will be preserved as an "
            "extension but is not claimed as target-version semantics"
        ),
        disposition=ConversionDisposition.PRESERVE_AS_EXTENSION,
    )


def plan_downgrade(
    value: NotebookDocument | Mapping[str, Any],
    *,
    target: str,
    limits: NotebookResourceLimits | None = None,
) -> DowngradePlan:
    """Report every known downgrade effect without modifying the notebook."""

    data = _copy_source(value, limits=limits)
    source_major, source_minor = _declared_version(data)
    target_major, target_minor = _target_version(target)
    if (target_major, target_minor) >= (source_major, source_minor):
        raise ValueError("downgrade target must be older than the declared notebook version")

    source_version = NotebookVersion(source_major, source_minor)
    target_version = NotebookVersion(target_major, target_minor)
    digest = _source_digest(data)
    if source_minor > 5:
        return DowngradePlan(
            source_version=source_version,
            target_version=target_version,
            source_digest=digest,
            issues=(
                ConversionIssue(
                    code="IPYNB_DOWNGRADE_FUTURE_MINOR_UNSUPPORTED",
                    path=("nbformat_minor",),
                    message=(
                        f"nbformat 4.{source_minor} has unknown future "
                        "semantics and is preservation-only"
                    ),
                    disposition=ConversionDisposition.BLOCK,
                ),
            ),
        )

    from ..validation import validate

    report = validate(data, profile="declared")
    if not report.is_valid:
        first = report.errors[0]
        raise NotebookValidationError(
            f"cannot plan downgrade for invalid source: {first.message}",
            code="IPYNB_DOWNGRADE_SOURCE_INVALID",
            context={
                "diagnostic_code": first.code,
                "path": first.location.path if first.location is not None else (),
                "error_count": len(report.errors),
            },
        )

    issues: list[ConversionIssue] = []
    metadata = data.get("metadata")
    if target_minor < 2 and isinstance(metadata, Mapping):
        for key in ("title", "authors"):
            if key in metadata:
                issues.append(
                    _extension_issue(
                        "IPYNB_DOWNGRADE_NOTEBOOK_METADATA_EXTENSION",
                        ("metadata", key),
                        target_minor,
                    )
                )

    cells = data.get("cells")
    if not isinstance(cells, list):
        raise AssertionError("validated notebook cells must be an array")  # noqa: TRY004
    for index, cell in enumerate(cells):
        if not isinstance(cell, Mapping):
            raise AssertionError("validated notebook cells must be objects")  # noqa: TRY004
        cell_metadata = cell.get("metadata")
        if isinstance(cell_metadata, Mapping):
            if target_minor < 3 and "jupyter" in cell_metadata:
                issues.append(
                    _extension_issue(
                        "IPYNB_DOWNGRADE_JUPYTER_METADATA_EXTENSION",
                        ("cells", index, "metadata", "jupyter"),
                        target_minor,
                    )
                )
            if target_minor < 4 and "execution" in cell_metadata:
                issues.append(
                    _extension_issue(
                        "IPYNB_DOWNGRADE_EXECUTION_METADATA_EXTENSION",
                        ("cells", index, "metadata", "execution"),
                        target_minor,
                    )
                )
        if target_minor < 5 and "id" in cell:
            issues.append(
                ConversionIssue(
                    code="IPYNB_DOWNGRADE_CELL_ID_REMOVED",
                    path=("cells", index, "id"),
                    message=(
                        f"cell ID is not allowed by nbformat 4.{target_minor} and will be removed"
                    ),
                    disposition=ConversionDisposition.REMOVE,
                )
            )

    return DowngradePlan(
        source_version=source_version,
        target_version=target_version,
        source_digest=digest,
        issues=tuple(issues),
    )


def downgrade(
    value: NotebookDocument | Mapping[str, Any],
    *,
    plan: DowngradePlan,
    accept_loss: bool = False,
    limits: NotebookResourceLimits | None = None,
) -> ConversionResult:
    """Apply an exact downgrade plan, requiring explicit loss acceptance."""

    if not isinstance(plan, DowngradePlan):
        raise TypeError("plan must be a DowngradePlan")
    data = _copy_source(value, limits=limits)
    source_major, source_minor = _declared_version(data)
    if plan.source_version.as_tuple() != (
        source_major,
        source_minor,
    ) or plan.source_digest != _source_digest(data):
        raise NotebookValidationError(
            "downgrade plan does not match the current source content",
            code="IPYNB_DOWNGRADE_STALE_PLAN",
        )
    target_major, target_minor = plan.target_version.as_tuple()
    if (
        target_major != 4
        or target_minor is None
        or target_minor < 0
        or target_minor > 5
        or (target_major, target_minor) >= (source_major, source_minor)
    ):
        raise NotebookValidationError(
            "downgrade plan has an unsupported or non-older target",
            code="IPYNB_DOWNGRADE_PLAN_INVALID",
        )
    expected_plan = plan_downgrade(
        data,
        target=f"{target_major}.{target_minor}",
        limits=limits,
    )
    if plan != expected_plan:
        raise NotebookValidationError(
            "downgrade plan omits or changes required conversion issues",
            code="IPYNB_DOWNGRADE_PLAN_MISMATCH",
        )
    if plan.blockers:
        raise NotebookValidationError(
            "downgrade plan contains blocking unknown-version semantics",
            code="IPYNB_DOWNGRADE_BLOCKED",
            context={
                "blocker_codes": tuple(issue.code for issue in plan.blockers),
            },
        )
    if plan.losses and not accept_loss:
        raise NotebookValidationError(
            "downgrade would remove data; pass accept_loss=True only after "
            "reviewing the bound plan",
            code="IPYNB_DOWNGRADE_LOSS_NOT_ACCEPTED",
            context={
                "loss_count": len(plan.losses),
                "loss_paths": tuple(issue.path for issue in plan.losses),
            },
        )

    data["nbformat"] = target_major
    data["nbformat_minor"] = target_minor
    actions: list[ConversionAction] = [
        ConversionAction(
            "IPYNB_DOWNGRADE_VERSION",
            ("nbformat", "nbformat_minor"),
            f"changed declared version from {source_major}.{source_minor} "
            f"to {target_major}.{target_minor}",
        )
    ]
    cells = data.get("cells")
    if not isinstance(cells, list):
        raise AssertionError("validated notebook cells must be an array")  # noqa: TRY004
    if target_minor < 5:
        for index, cell in enumerate(cells):
            if not isinstance(cell, dict):
                raise AssertionError("validated notebook cells must be objects")  # noqa: TRY004
            if "id" in cell:
                del cell["id"]
                actions.append(
                    ConversionAction(
                        "IPYNB_DOWNGRADE_CELL_ID",
                        ("cells", index, "id"),
                        "removed a cell ID unsupported by the target schema",
                    )
                )

    from ..validation import validate
    from .document import NotebookDocument

    report = validate(data, profile=f"nbformat-{target_major}.{target_minor}")
    if not report.is_valid:
        first = report.errors[0]
        raise NotebookValidationError(
            f"downgrade result is invalid: {first.message}",
            code="IPYNB_DOWNGRADE_RESULT_INVALID",
            context={
                "diagnostic_code": first.code,
                "path": first.location.path if first.location is not None else (),
                "error_count": len(report.errors),
            },
        )
    version = NotebookVersion(target_major, target_minor)
    return ConversionResult(
        document=NotebookDocument(
            data,
            declared_version=version,
            detected_version=version,
        ),
        actions=tuple(actions),
        id_rewrites=(),
        issues=plan.issues,
    )


def upgrade(
    value: NotebookDocument | Mapping[str, Any],
    *,
    target: str = "4.5",
    limits: NotebookResourceLimits | None = None,
) -> ConversionResult:
    """Explicitly upgrade a notebook and return a conversion ledger.

    This is the only production API that synthesizes cell IDs. Downgrades are
    deliberately refused until their loss-report policy is selected explicitly.
    """

    from ..codec.reader import CELL_ID_PATTERN, ensure_cell_id
    from .document import NotebookDocument

    data = _copy_source(value, limits=limits)
    target_major, target_minor = _target_version(target)
    source_major = data.get("nbformat")
    source_minor = data.get("nbformat_minor")
    if (
        isinstance(source_major, bool)
        or not isinstance(source_major, int)
        or isinstance(source_minor, bool)
        or not isinstance(source_minor, int)
    ):
        raise NotebookValidationError(
            "explicit upgrade requires integer nbformat and nbformat_minor fields",
            code="IPYNB_UPGRADE_VERSION",
            context={"path": ("nbformat",)},
        )
    if source_major != 4 or (source_major, source_minor) > (
        target_major,
        target_minor,
    ):
        raise NotebookValidationError(
            "upgrade target must not be older than the declared notebook version",
            code="IPYNB_UPGRADE_DOWNGRADE_REQUIRES_LOSS_REPORT",
            context={
                "source_version": (source_major, source_minor),
                "target_version": (target_major, target_minor),
            },
        )

    cells = data.get("cells")
    if not isinstance(cells, list) or any(not isinstance(cell, dict) for cell in cells):
        raise NotebookValidationError(
            "explicit upgrade requires a cells array of objects",
            code="IPYNB_UPGRADE_CELLS",
            context={"path": ("cells",)},
        )

    actions: list[ConversionAction] = []
    rewrites: list[CellIdRewrite] = []
    if (source_major, source_minor) != (target_major, target_minor):
        data["nbformat"] = target_major
        data["nbformat_minor"] = target_minor
        # LIBIPYNB-Q14: matches nbformat.v4.convert.upgrade()'s own
        # unconditional `nb.metadata.orig_nbformat_minor = from_minor` --
        # the provenance field the reference implementation always records
        # on a real version bump, so consumers can tell a notebook was
        # converted (and from what) without diffing nbformat_minor history.
        metadata = data.get("metadata")
        if not isinstance(metadata, dict):
            metadata = {}
            data["metadata"] = metadata
        metadata["orig_nbformat_minor"] = source_minor
        actions.append(
            ConversionAction(
                "IPYNB_UPGRADE_VERSION",
                ("nbformat", "nbformat_minor"),
                f"changed declared version from {source_major}.{source_minor} "
                f"to {target_major}.{target_minor}",
            )
        )

    if target_minor >= 5:
        used_ids: set[str] = set()
        for index, cell in enumerate(cells):
            old_value = cell.get("id")
            old_id = old_value if isinstance(old_value, str) else None
            is_valid = (
                old_id is not None
                and CELL_ID_PATTERN.fullmatch(old_id) is not None
                and old_id not in used_ids
            )
            ensure_cell_id(cell, used_ids)
            new_id = str(cell["id"])
            if not is_valid:
                rewrites.append(CellIdRewrite(index, old_id, new_id))
                actions.append(
                    ConversionAction(
                        "IPYNB_UPGRADE_CELL_ID",
                        ("cells", index, "id"),
                        "generated a deterministic valid unique cell ID",
                    )
                )

    version = NotebookVersion(target_major, target_minor)
    return ConversionResult(
        document=NotebookDocument(
            data,
            declared_version=version,
            detected_version=version,
        ),
        actions=tuple(actions),
        id_rewrites=tuple(rewrites),
    )
