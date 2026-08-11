"""Bounded, non-rendering classification and sanitization of active content.

The sanitizer deliberately removes or quarantines an entire renderable payload
when it is unsafe. It does not claim to rewrite arbitrary HTML, SVG, Markdown,
or JavaScript into a safe subset.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
from html.parser import HTMLParser
import json
import re
from typing import Any

from .limits import NotebookResourceLimits as ResourceLimits

from ..model import IpynbDocument
from .limits import effective_limits

DEFAULT_ACTIVE_MIME_TYPES = frozenset(
    {
        "application/ecmascript",
        "application/javascript",
        "application/x-javascript",
        "image/svg+xml",
        "text/ecmascript",
        "text/html",
        "text/javascript",
        "text/x-javascript",
    }
)
_ACTIVE_ELEMENTS = frozenset(
    {
        "applet",
        "audio",
        "embed",
        "form",
        "frame",
        "frameset",
        "iframe",
        "link",
        "meta",
        "object",
        "script",
        "source",
        "style",
        "video",
    }
)
_URI_ATTRIBUTES = frozenset(
    {
        "action",
        "background",
        "cite",
        "data",
        "formaction",
        "href",
        "longdesc",
        "manifest",
        "poster",
        "src",
        "srcset",
        "xlink:href",
    }
)
_MARKDOWN_TARGET = re.compile(
    r"!?\[[^\]]*]\(\s*(?:<([^>]+)>|([^\s)]+))"
)
_MARKDOWN_AUTOLINK = re.compile(
    r"<((?:https?|ftp|file|mailto|javascript|data):[^>\s]+)>",
    re.IGNORECASE,
)
_CSS_URL = re.compile(
    r"url\(\s*(?:\"([^\"]+)\"|'([^']+)'|([^)'\"\s]+))\s*\)",
    re.IGNORECASE,
)


class SanitizationMode(str, Enum):
    """Explicit handling policy for classified active content."""

    LOSSLESS = "lossless"
    REMOVE = "remove"
    QUARANTINE = "quarantine"
    MARK_UNTRUSTED = "mark_untrusted"


@dataclass(frozen=True, slots=True)
class SanitizationPolicy:
    """Configurable catalog and handling mode.

    External references include absolute, scheme-relative, and relative
    resource targets. Fragment-only and ``attachment:`` references remain
    local and are not classified as external.
    """

    mode: SanitizationMode = SanitizationMode.LOSSLESS
    active_mime_types: frozenset[str] = DEFAULT_ACTIVE_MIME_TYPES
    inspect_markdown: bool = True
    inspect_external_references: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.mode, SanitizationMode):
            raise TypeError("mode must be a SanitizationMode")
        if any(
            not isinstance(media_type, str) or "/" not in media_type
            for media_type in self.active_mime_types
        ):
            raise ValueError(
                "active_mime_types must contain syntactically valid MIME types"
            )


@dataclass(frozen=True, slots=True)
class SanitizationFinding:
    """One classified renderable payload, without copying its content."""

    path: tuple[str | int, ...]
    media_type: str
    hazards: tuple[str, ...]
    references: tuple[str, ...]
    payload_sha256: str
    action: str


@dataclass(frozen=True, slots=True)
class SanitizationReport:
    """Deterministic findings and mutation outcome."""

    mode: SanitizationMode
    findings: tuple[SanitizationFinding, ...]
    would_change: bool
    applied: bool

    @property
    def count(self) -> int:
        return len(self.findings)


@dataclass(slots=True)
class _Candidate:
    path: tuple[str | int, ...]
    media_type: str
    hazards: tuple[str, ...]
    references: tuple[str, ...]
    payload: Any
    payload_sha256: str
    container: dict[str, Any]
    key: str
    delete_key: bool


class _MarkupScanner(HTMLParser):
    """Classify active markup without rendering or resolving resources."""

    def __init__(
        self,
        *,
        inspect_external_references: bool,
        limits: ResourceLimits,
    ) -> None:
        super().__init__(convert_charrefs=True)
        self.inspect_external_references = inspect_external_references
        self.limits = limits
        self.observations = 0
        self.hazards: set[str] = set()
        self.references: set[str] = set()

    def _observe(self) -> None:
        self.observations += 1
        self.limits.enforce("max_entries", self.observations)

    def _handle_element(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        normalized_tag = tag.casefold()
        if normalized_tag in _ACTIVE_ELEMENTS:
            self._observe()
            self.hazards.add(f"active_element:{normalized_tag}")
        for raw_name, value in attrs:
            name = raw_name.casefold()
            if name.startswith("on"):
                self._observe()
                self.hazards.add(f"event_handler:{name}")
            if value is None:
                continue
            if name == "style":
                for match in _CSS_URL.finditer(value):
                    reference = next(
                        item for item in match.groups() if item is not None
                    )
                    self._add_reference(reference)
            if name in _URI_ATTRIBUTES:
                references = (
                    value.split(",") if name == "srcset" else [value]
                )
                for reference in references:
                    target = (
                        reference.strip().split(maxsplit=1)[0]
                        if name == "srcset"
                        else reference
                    )
                    self._add_reference(target)

    def _add_reference(self, value: str) -> None:
        reference = value.strip()
        if (
            self.inspect_external_references
            and _is_external_reference(reference)
        ):
            self._observe()
            self.references.add(reference)

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        self._handle_element(tag, attrs)

    def handle_startendtag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        self._handle_element(tag, attrs)


@dataclass(slots=True)
class _ScanBudget:
    limits: ResourceLimits
    decoded_bytes: int = 0
    entries: int = 0

    def consume(self, payload: Any) -> None:
        serialized = _canonical_payload(payload)
        self.decoded_bytes += len(serialized)
        self.entries += 1
        self.limits.enforce("max_decompressed_bytes", self.decoded_bytes)
        self.limits.enforce("max_entries", self.entries)


def _canonical_payload(payload: Any) -> bytes:
    try:
        return json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise TypeError("sanitizer payloads must be JSON-compatible") from exc


def _payload_text(payload: Any) -> str:
    if isinstance(payload, str):
        return payload
    if isinstance(payload, list) and all(
        isinstance(item, str) for item in payload
    ):
        return "".join(payload)
    return ""


def _is_external_reference(value: str) -> bool:
    normalized = value.strip()
    if not normalized or normalized.startswith("#"):
        return False
    return not normalized.casefold().startswith("attachment:")


def _scan_markup(
    text: str,
    *,
    inspect_external_references: bool,
    limits: ResourceLimits,
) -> tuple[set[str], set[str]]:
    scanner = _MarkupScanner(
        inspect_external_references=inspect_external_references,
        limits=limits,
    )
    try:
        scanner.feed(text)
        scanner.close()
    except (AssertionError, ValueError):
        scanner.hazards.add("malformed_markup")
    return scanner.hazards, scanner.references


def _scan_markdown(
    text: str,
    *,
    inspect_external_references: bool,
    limits: ResourceLimits,
) -> tuple[set[str], set[str]]:
    hazards, references = _scan_markup(
        text,
        inspect_external_references=inspect_external_references,
        limits=limits,
    )
    if inspect_external_references:
        observations = len(hazards) + len(references)
        for match in _MARKDOWN_TARGET.finditer(text):
            target = match.group(1) or match.group(2) or ""
            if _is_external_reference(target):
                observations += 1
                limits.enforce("max_entries", observations)
                references.add(target)
        for match in _MARKDOWN_AUTOLINK.finditer(text):
            target = match.group(1)
            if _is_external_reference(target):
                observations += 1
                limits.enforce("max_entries", observations)
                references.add(target)
    return hazards, references


def _action(mode: SanitizationMode) -> str:
    return {
        SanitizationMode.LOSSLESS: "reported",
        SanitizationMode.REMOVE: "removed",
        SanitizationMode.QUARANTINE: "quarantined",
        SanitizationMode.MARK_UNTRUSTED: "marked_untrusted",
    }[mode]


def _add_candidate(
    candidates: list[_Candidate],
    budget: _ScanBudget,
    *,
    path: tuple[str | int, ...],
    media_type: str,
    payload: Any,
    container: dict[str, Any],
    key: str,
    delete_key: bool,
    policy: SanitizationPolicy,
    markdown: bool = False,
) -> None:
    active_mime = media_type.casefold() in {
        item.casefold() for item in policy.active_mime_types
    }
    text = _payload_text(payload)
    hazards: set[str] = set()
    references: set[str] = set()
    if active_mime:
        hazards.add(f"active_mime:{media_type.casefold()}")
    if text and (active_mime or markdown):
        budget.consume(payload)
        if markdown:
            markup_hazards, markup_references = _scan_markdown(
                text,
                inspect_external_references=policy.inspect_external_references,
                limits=budget.limits,
            )
        else:
            markup_hazards, markup_references = _scan_markup(
                text,
                inspect_external_references=policy.inspect_external_references,
                limits=budget.limits,
            )
        hazards.update(markup_hazards)
        references.update(markup_references)
    if not hazards and not references:
        return
    if not text:
        budget.consume(payload)
    serialized = _canonical_payload(payload)
    candidates.append(
        _Candidate(
            path=path,
            media_type=media_type,
            hazards=tuple(sorted(hazards)),
            references=tuple(sorted(references)),
            payload=deepcopy(payload),
            payload_sha256=sha256(serialized).hexdigest(),
            container=container,
            key=key,
            delete_key=delete_key,
        )
    )


def _collect_candidates(
    root: dict[str, Any],
    policy: SanitizationPolicy,
    limits: ResourceLimits,
) -> list[_Candidate]:
    cells = root.get("cells")
    if not isinstance(cells, list):
        raise TypeError("notebook cells must be an array before sanitization")
    budget = _ScanBudget(limits)
    candidates: list[_Candidate] = []
    for cell_index, cell in enumerate(cells):
        if not isinstance(cell, dict):
            raise TypeError(
                f"cell {cell_index} must be an object before sanitization"
            )
        cell_path: tuple[str | int, ...] = ("cells", cell_index)
        if policy.inspect_markdown and cell.get("cell_type") == "markdown":
            _add_candidate(
                candidates,
                budget,
                path=(*cell_path, "source"),
                media_type="text/markdown",
                payload=cell.get("source", ""),
                container=cell,
                key="source",
                delete_key=False,
                policy=policy,
                markdown=True,
            )

        attachments = cell.get("attachments")
        if attachments is not None:
            if not isinstance(attachments, dict):
                raise TypeError(
                    f"cell {cell_index} attachments must be an object"
                )
            for name in sorted(attachments):
                bundle = attachments[name]
                if not isinstance(bundle, dict):
                    raise TypeError(
                        f"attachment {name!r} MIME bundle must be an object"
                    )
                for media_type in sorted(bundle):
                    _add_candidate(
                        candidates,
                        budget,
                        path=(
                            *cell_path,
                            "attachments",
                            name,
                            media_type,
                        ),
                        media_type=media_type,
                        payload=bundle[media_type],
                        container=bundle,
                        key=media_type,
                        delete_key=True,
                        policy=policy,
                    )

        outputs = cell.get("outputs")
        if outputs is None:
            continue
        if not isinstance(outputs, list):
            raise TypeError(
                f"cell {cell_index} outputs must be an array before sanitization"
            )
        for output_index, output in enumerate(outputs):
            if not isinstance(output, dict):
                raise TypeError(
                    f"output {cell_index}:{output_index} must be an object"
                )
            data = output.get("data")
            if data is None:
                continue
            if not isinstance(data, dict):
                raise TypeError(
                    f"output {cell_index}:{output_index} data must be an object"
                )
            for media_type in sorted(data):
                _add_candidate(
                    candidates,
                    budget,
                    path=(
                        *cell_path,
                        "outputs",
                        output_index,
                        "data",
                        media_type,
                    ),
                    media_type=media_type,
                    payload=data[media_type],
                    container=data,
                    key=media_type,
                    delete_key=True,
                    policy=policy,
                )
    return candidates


def _entry(candidate: _Candidate, action: str, *, payload: bool) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "action": action,
        "hazards": list(candidate.hazards),
        "media_type": candidate.media_type,
        "path": list(candidate.path),
        "payload_sha256": candidate.payload_sha256,
        "references": list(candidate.references),
        "schema_version": 1,
    }
    if payload:
        entry["payload"] = deepcopy(candidate.payload)
    return entry


def _security_metadata(root: dict[str, Any]) -> dict[str, Any]:
    metadata = root.get("metadata")
    if not isinstance(metadata, dict):
        raise TypeError("notebook metadata must be an object before sanitization")
    security = metadata.get("notebook_security")
    if security is None:
        security = {}
        metadata["notebook_security"] = security
    if not isinstance(security, dict):
        raise TypeError("metadata.notebook_security must be an object")
    return security


def _apply_candidates(
    root: dict[str, Any],
    candidates: list[_Candidate],
    mode: SanitizationMode,
) -> None:
    if mode is SanitizationMode.LOSSLESS:
        return
    if mode is SanitizationMode.MARK_UNTRUSTED:
        security = _security_metadata(root)
        marks = [
            _entry(candidate, "marked_untrusted", payload=False)
            for candidate in candidates
        ]
        if security.get("untrusted") != marks:
            security["untrusted"] = marks
        return

    for candidate in candidates:
        if candidate.delete_key:
            del candidate.container[candidate.key]
        else:
            candidate.container[candidate.key] = (
                [] if isinstance(candidate.payload, list) else ""
            )
    if mode is SanitizationMode.QUARANTINE and candidates:
        security = _security_metadata(root)
        existing = security.get("quarantine", [])
        if not isinstance(existing, list) or any(
            not isinstance(item, dict) for item in existing
        ):
            raise TypeError(
                "metadata.notebook_security.quarantine must be an array "
                "of objects"
            )
        additions = [
            _entry(candidate, "quarantined", payload=True)
            for candidate in candidates
        ]
        security["quarantine"] = [*existing, *additions]


def sanitize(
    document: IpynbDocument,
    *,
    policy: SanitizationPolicy | None = None,
    limits: ResourceLimits | None = None,
    dry_run: bool = False,
) -> SanitizationReport:
    """Classify and explicitly handle active notebook payloads.

    ``LOSSLESS`` is the default and only reports findings. ``REMOVE`` and
    ``QUARANTINE`` remove the entire unsafe renderable payload rather than
    attempting incomplete markup surgery. ``MARK_UNTRUSTED`` preserves the
    payload and writes digest-only security metadata. No mode renders,
    executes, imports, opens, or resolves payload content or references.
    """

    if not isinstance(document, IpynbDocument):
        raise TypeError("document must be an IpynbDocument")
    selected = policy or SanitizationPolicy()
    selected_limits = effective_limits(limits)
    before = deepcopy(document.raw)
    target = deepcopy(document.raw)
    candidates = _collect_candidates(target, selected, selected_limits)
    _apply_candidates(target, candidates, selected.mode)
    would_change = target != before
    if would_change:
        selected_limits.enforce(
            "max_output_bytes",
            len(_canonical_payload(target)),
        )
    applied = would_change and not dry_run
    if applied:
        document.raw.clear()
        document.raw.update(target)
    action = _action(selected.mode)
    findings = tuple(
        SanitizationFinding(
            path=candidate.path,
            media_type=candidate.media_type,
            hazards=candidate.hazards,
            references=candidate.references,
            payload_sha256=candidate.payload_sha256,
            action=action,
        )
        for candidate in candidates
    )
    return SanitizationReport(
        mode=selected.mode,
        findings=findings,
        would_change=would_change,
        applied=applied,
    )


__all__ = [
    "DEFAULT_ACTIVE_MIME_TYPES",
    "SanitizationFinding",
    "SanitizationMode",
    "SanitizationPolicy",
    "SanitizationReport",
    "sanitize",
]
