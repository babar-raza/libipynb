"""Bounded, non-exfiltrating pattern scanning for likely secrets and credentials.

Pattern-based only, and deliberately conservative about what counts as
proof. A clean :class:`SecretScanReport` is not evidence a notebook is free
of secrets -- it only means none of the configured patterns matched.
Anything novel, obfuscated, base64-wrapped, or simply outside the built-in
ruleset will not be found. Findings never carry the full matched text, only
a short redacted preview, so a shared or logged report cannot itself become
a new leak vector. Nothing here is ever auto-removed: this module reports,
callers decide what to do (e.g. via ``model.cleanup.cleanup()``).
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from enum import Enum
from typing import Any

from ..model import NotebookDocument
from .limits import NotebookResourceLimits as ResourceLimits
from .limits import effective_limits


def _compile(pattern: str) -> re.Pattern[str]:
    return re.compile(pattern)


@dataclass(frozen=True, slots=True)
class SecretRule:
    """One pattern in the ruleset."""

    rule_id: str
    pattern: re.Pattern[str]
    description: str


#: A small, illustrative ruleset covering common credential shapes -- not
#: an exhaustive secret-detection product. Callers may extend or replace
#: this via ``scan_for_secrets(..., extra_rules=...)``.
DEFAULT_SECRET_RULES: tuple[SecretRule, ...] = (
    SecretRule("aws_access_key_id", _compile(r"\bAKIA[0-9A-Z]{16}\b"), "AWS access key ID"),
    SecretRule(
        "aws_secret_access_key_assignment",
        _compile(r"(?i)aws_secret_access_key\s*[:=]\s*['\"]?[A-Za-z0-9/+=]{40}['\"]?"),
        "AWS secret access key assignment",
    ),
    SecretRule("github_token", _compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b"), "GitHub token"),
    SecretRule("slack_token", _compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,48}\b"), "Slack token"),
    SecretRule("google_api_key", _compile(r"\bAIza[0-9A-Za-z\-_]{35}\b"), "Google API key"),
    SecretRule(
        "private_key_block",
        _compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY-----"),
        "PEM private key block",
    ),
    SecretRule(
        "jwt_shaped_token",
        _compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"),
        "JWT-shaped token",
    ),
    SecretRule(
        "bearer_token",
        _compile(r"(?i)bearer\s+[A-Za-z0-9._~+/-]{20,}"),
        "Bearer token",
    ),
    SecretRule(
        "generic_credential_assignment",
        _compile(
            r"(?i)\b(api[_-]?key|secret|token|password|passwd|pwd)\b\s*[:=]\s*"
            r"['\"][^'\"\s]{8,}['\"]"
        ),
        "Generic credential-shaped assignment",
    ),
    SecretRule(
        "url_embedded_credentials",
        _compile(r"\b\w+://[^\s/:@'\"]+:[^\s/:@'\"]+@"),
        "URL with embedded username:password",
    ),
)


class SecretScope(str, Enum):
    """Where in the notebook a finding was located."""

    SOURCE = "source"
    OUTPUT_TEXT = "output_text"
    TRACEBACK = "traceback"
    METADATA = "metadata"


@dataclass(frozen=True, slots=True)
class SecretFinding:
    """One pattern match. Never carries the full matched secret text."""

    path: tuple[str | int, ...]
    rule_id: str
    description: str
    scope: SecretScope
    preview: str


@dataclass(frozen=True, slots=True)
class SecretScanReport:
    """Deterministic scan findings."""

    findings: tuple[SecretFinding, ...]

    @property
    def count(self) -> int:
        return len(self.findings)

    @property
    def is_clean(self) -> bool:
        """True iff no configured pattern matched.

        This is NOT proof the notebook contains no secrets -- see the
        module docstring. Prefer ``count`` in reports over ``is_clean`` in
        user-facing language, to avoid implying a completeness guarantee.
        """
        return not self.findings


def _redact(text: str, start: int, end: int) -> str:
    """A finding preview that reveals none of the matched text's content
    or exact length -- only a coarse length bucket, so a reviewer
    triaging findings has *some* signal without the preview itself being
    reconstructable into the secret.

    A first version of this function showed a fixed number of leading
    and trailing characters (e.g. "first 4 ... last 4"), which independent
    review proved leaks most or all of any match shorter than ~17
    characters -- a 9-character ``url_embedded_credentials`` match like
    ``"ab://c:d@"`` showed 8 of its 9 real characters, and combined with
    the fixed literal characters the matching rule's own pattern
    guarantees, the omitted 9th was trivially inferable too. Exact length
    is also withheld (not just content), since a precise character count
    narrows a brute-force search for a short secret.
    """
    length = end - start
    if length <= 12:
        bucket = "short"
    elif length <= 40:
        bucket = "medium"
    else:
        bucket = "long"
    return f"<redacted:{bucket}>"


def _payload_text(payload: Any) -> str:
    if isinstance(payload, str):
        return payload
    if isinstance(payload, list) and all(isinstance(item, str) for item in payload):
        return "".join(payload)
    return ""


def _scan_text(
    text: str,
    rules: Iterable[SecretRule],
    *,
    path: tuple[str | int, ...],
    scope: SecretScope,
) -> Iterator[SecretFinding]:
    for rule in rules:
        for match in rule.pattern.finditer(text):
            yield SecretFinding(
                path=path,
                rule_id=rule.rule_id,
                description=rule.description,
                scope=scope,
                preview=_redact(text, match.start(), match.end()),
            )


#: Metadata is structured key/value data, unlike source/output text -- a
#: value stored under one of these keys is a strong signal on its own,
#: independent of whether the value's *content* matches a regex shape.
_SENSITIVE_METADATA_KEYS = frozenset(
    {
        "password",
        "passwd",
        "pwd",
        "secret",
        "secret_key",
        "client_secret",
        "api_key",
        "apikey",
        "token",
        "access_token",
        "auth_token",
        "private_key",
        "credential",
        "credentials",
    }
)


def _is_sensitive_metadata_key(path: tuple[str | int, ...]) -> bool:
    if not path or not isinstance(path[-1], str):
        return False
    normalized = path[-1].strip("_").lower().replace("-", "_")
    return normalized in _SENSITIVE_METADATA_KEYS


def _walk_metadata_strings(
    value: Any, path: tuple[str | int, ...]
) -> Iterator[tuple[tuple[str | int, ...], str]]:
    """Iteratively (not recursively) walk a metadata tree for string leaves."""
    stack: list[tuple[Any, tuple[str | int, ...]]] = [(value, path)]
    while stack:
        current, current_path = stack.pop()
        if isinstance(current, str):
            yield current_path, current
        elif isinstance(current, dict):
            for key, item in current.items():
                stack.append((item, (*current_path, str(key))))
        elif isinstance(current, list):
            for index, item in enumerate(current):
                stack.append((item, (*current_path, index)))


def scan_for_secrets(
    document: NotebookDocument,
    *,
    rules: Iterable[SecretRule] | None = None,
    extra_rules: Iterable[SecretRule] = (),
    scan_metadata: bool = True,
    limits: ResourceLimits | None = None,
) -> SecretScanReport:
    """Scan cell source, output text, tracebacks, and (optionally) metadata
    for pattern-shaped likely secrets.

    Report-only: never mutates the document and never auto-removes
    anything. Pair with ``model.cleanup.cleanup()`` to act on findings.
    A clean report means no configured pattern matched -- it is not a
    guarantee of secret-free content.
    """
    if not isinstance(document, NotebookDocument):
        raise TypeError("document must be a NotebookDocument")
    selected_rules = tuple(rules) if rules is not None else DEFAULT_SECRET_RULES
    selected_rules = (*selected_rules, *extra_rules)
    selected_limits = effective_limits(limits)

    findings: list[SecretFinding] = []
    scanned_bytes = 0
    scanned_entries = 0

    def _consume(text: str) -> None:
        nonlocal scanned_bytes, scanned_entries
        scanned_bytes += len(text.encode("utf-8"))
        scanned_entries += 1
        selected_limits.enforce("max_decompressed_bytes", scanned_bytes)
        selected_limits.enforce("max_entries", scanned_entries)

    cells = document.raw.get("cells", [])
    if not isinstance(cells, list):
        raise TypeError("notebook cells must be an array before scanning")

    for cell_index, cell in enumerate(cells):
        if not isinstance(cell, dict):
            continue
        cell_path: tuple[str | int, ...] = ("cells", cell_index)

        source_text = _payload_text(cell.get("source", ""))
        if source_text:
            _consume(source_text)
            findings.extend(
                _scan_text(
                    source_text,
                    selected_rules,
                    path=(*cell_path, "source"),
                    scope=SecretScope.SOURCE,
                )
            )

        for output_index, output in enumerate(cell.get("outputs", []) or []):
            if not isinstance(output, dict):
                continue
            output_path = (*cell_path, "outputs", output_index)

            stream_text = _payload_text(output.get("text", ""))
            if stream_text:
                _consume(stream_text)
                findings.extend(
                    _scan_text(
                        stream_text,
                        selected_rules,
                        path=(*output_path, "text"),
                        scope=SecretScope.OUTPUT_TEXT,
                    )
                )

            traceback_lines = output.get("traceback")
            if isinstance(traceback_lines, list):
                traceback_text = "\n".join(
                    line for line in traceback_lines if isinstance(line, str)
                )
                if traceback_text:
                    _consume(traceback_text)
                    findings.extend(
                        _scan_text(
                            traceback_text,
                            selected_rules,
                            path=(*output_path, "traceback"),
                            scope=SecretScope.TRACEBACK,
                        )
                    )

            data = output.get("data")
            if isinstance(data, dict):
                for mime_type, payload in data.items():
                    if not isinstance(mime_type, str) or not mime_type.startswith("text/"):
                        continue
                    text = _payload_text(payload)
                    if text:
                        _consume(text)
                        findings.extend(
                            _scan_text(
                                text,
                                selected_rules,
                                path=(*output_path, "data", mime_type),
                                scope=SecretScope.OUTPUT_TEXT,
                            )
                        )

    def _scan_metadata_tree(tree: Any, base_path: tuple[str | int, ...]) -> None:
        for path, text in _walk_metadata_strings(tree, base_path):
            if not text:
                continue
            _consume(text)
            findings.extend(_scan_text(text, selected_rules, path=path, scope=SecretScope.METADATA))
            if _is_sensitive_metadata_key(path) and len(text) >= 6:
                findings.append(
                    SecretFinding(
                        path=path,
                        rule_id="sensitive_metadata_key",
                        description="Value stored under a credential-shaped metadata key",
                        scope=SecretScope.METADATA,
                        preview=_redact(text, 0, len(text)),
                    )
                )

    if scan_metadata:
        _scan_metadata_tree(document.raw.get("metadata", {}), ("metadata",))
        for cell_index, cell in enumerate(cells):
            if not isinstance(cell, dict):
                continue
            _scan_metadata_tree(cell.get("metadata", {}), ("cells", cell_index, "metadata"))

    return SecretScanReport(findings=tuple(findings))


__all__ = [
    "DEFAULT_SECRET_RULES",
    "SecretFinding",
    "SecretRule",
    "SecretScanReport",
    "SecretScope",
    "scan_for_secrets",
]
