"""Vendor a real-world notebook fixture into tests/fixtures/, per the
process documented in tests/fixtures/PROVENANCE.md ("Repeatable sourcing
process" section).

This tool is stdlib-only (deliberately -- never triggers Gate G7's
`add_core_dependency` review), never wired into CI, and never runs
unattended: it exists to make an already-authorized (see below) fetch
cheap and consistent to repeat, not to make the authorization decision
itself.

Two structural checks gate `--commit` (not just human diligence):

1. The exact `--url` must match a row in PROVENANCE.md's "Candidate
   shortlist pending maintainer decision" table whose Decision column says
   `Approve` (or `Approve-with-substitution: <this url>`). No matching
   approved row -> refused.
2. The content re-fetched at `--commit` time must hash-match a prior
   `--dry-run`'s staged copy for the same URL (a time-of-check/time-of-use
   guard against the pinned URL's content having changed between review
   and commit). No prior matching dry-run -> refused.

`--dry-run` (the default) fetches, stages, and prints exactly what
`--commit` would do, without writing anything to tests/fixtures/ or
PROVENANCE.md. This is a deliberate human checkpoint: run --dry-run first,
review its output, then re-invoke with --commit once satisfied.

What this tool intentionally does NOT do, and cannot be made to do: decide
which candidate to fetch, or verify that a declared license genuinely
covers the exact file being vendored. `--license`/`--license-evidence-url`
are always human-supplied, declared values -- never derived or verified
by this tool. See PROVENANCE.md's own 5 qualifying criteria for what a
human must have already checked before ever running this tool.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import tempfile
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from urllib.error import URLError

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures"
PROVENANCE_PATH = FIXTURES_DIR / "PROVENANCE.md"
STAGING_DIR = Path(tempfile.gettempdir()) / "libipynb-fetch-fixture-staging"

VALID_CATEGORIES = ("valid", "invalid", "adversarial", "corpus")
DEFAULT_MAX_BYTES = 300_000

SHORTLIST_HEADING = "### Candidate shortlist pending maintainer decision"
VENDORED_HEADING = "### Vendored real-world fixtures"


class FetchFixtureError(Exception):
    """Any refusal this tool makes -- always a clear, user-facing message,
    never a bare traceback (this is an interactive maintainer tool, not a
    library)."""


@dataclass(frozen=True)
class StagedFetch:
    content: bytes
    sha256: str
    size: int


def _staging_paths(url: str) -> tuple[Path, Path]:
    """Deterministic per-URL staging file/lockfile pair, so a --dry-run and
    a later --commit for the SAME url reuse (and can cross-check against)
    the same staged copy, while two different URLs never collide."""
    key = hashlib.sha256(url.encode("utf-8")).hexdigest()[:32]
    STAGING_DIR.mkdir(parents=True, exist_ok=True)
    return STAGING_DIR / f"{key}.ipynb", STAGING_DIR / f"{key}.lock.json"


def _fetch(url: str) -> bytes:
    if not url.startswith("https://"):
        raise FetchFixtureError(f"--url must be https://, not vendoring from {url!r}")
    try:
        with urllib.request.urlopen(url, timeout=30) as response:
            data: bytes = response.read()
            return data
    except URLError as exc:
        raise FetchFixtureError(f"failed to fetch {url!r}: {exc}") from exc


def _stage(url: str, *, refetch: bool) -> StagedFetch:
    """Fetches (unless a staged copy from a PRIOR call for this exact url
    already exists and refetch=False) and (re-)writes the staging
    file/lockfile pair, returning the freshly-computed digest either way --
    --commit always calls this with refetch=True so its own hash check is
    against genuinely current content, never a stale cached one."""
    staged_path, lock_path = _staging_paths(url)
    if not refetch and staged_path.exists() and lock_path.exists():
        content = staged_path.read_bytes()
    else:
        content = _fetch(url)
        staged_path.write_bytes(content)
    digest = hashlib.sha256(content).hexdigest()
    lock_path.write_text(
        json.dumps({"url": url, "sha256": digest, "size": len(content)}, indent=2),
        encoding="utf-8",
    )
    return StagedFetch(content=content, sha256=digest, size=len(content))


def _load_prior_dry_run(url: str) -> StagedFetch | None:
    staged_path, lock_path = _staging_paths(url)
    if not staged_path.exists() or not lock_path.exists():
        return None
    try:
        lock = json.loads(lock_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    if lock.get("url") != url:
        return None
    content = staged_path.read_bytes()
    return StagedFetch(
        content=content, sha256=hashlib.sha256(content).hexdigest(), size=len(content)
    )


def _split_table_rows(markdown: str, heading: str) -> list[list[str]]:
    """Strict, narrow markdown-table parser scoped to exactly one `###`
    section of PROVENANCE.md -- fails closed (returns no rows) on anything
    ambiguous rather than guessing, since this feeds an authorization
    check. Only handles the specific `| a | b | ... |` pipe-table shape
    this project's own PROVENANCE.md tables use; not a general markdown
    parser."""
    lines = markdown.splitlines()
    try:
        start = next(i for i, line in enumerate(lines) if line.strip() == heading)
    except StopIteration:
        raise FetchFixtureError(
            f"PROVENANCE.md has no {heading!r} section -- has the file's structure changed?"
        ) from None

    rows: list[list[str]] = []
    in_table = False
    seen_separator = False
    for line in lines[start + 1 :]:
        stripped = line.strip()
        if stripped.startswith("### "):
            break  # next section -- table (if any) has ended
        if not stripped.startswith("|"):
            if in_table:
                break  # table ended, rest of the section is prose
            continue
        in_table = True
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if not seen_separator:
            # the `|---|---|...|` separator row -- never data
            if all(re.fullmatch(r":?-+:?", cell) for cell in cells):
                seen_separator = True
            continue
        if all(cell == "" for cell in cells):
            continue  # blank/placeholder row, e.g. an empty table's only row
        rows.append(cells)
    return rows


def _find_approved_row(markdown: str, url: str) -> list[str] | None:
    rows = _split_table_rows(markdown, SHORTLIST_HEADING)
    for row in rows:
        if len(row) < 3:
            continue
        row_url = row[2]  # "Source repo & pinned commit/tag URL" column
        decision = row[7] if len(row) > 7 else ""
        if row_url != url:
            continue
        decision_lower = decision.lower()
        if decision_lower.startswith("approve-with-substitution"):
            # only counts as approval for the SUBSTITUTE url it names, not
            # for this row's own original url
            continue
        if decision_lower.startswith("approve"):
            return row
    # also honor an Approve-with-substitution row that names this exact url
    # as its substitute, regardless of that row's own original url column
    for row in rows:
        decision = row[7] if len(row) > 7 else ""
        if decision.lower().startswith("approve-with-substitution") and url in decision:
            return row
    return None


def _append_vendored_row(markdown: str, row_cells: list[str]) -> str:
    lines = markdown.splitlines(keepends=True)
    try:
        heading_idx = next(i for i, line in enumerate(lines) if line.strip() == VENDORED_HEADING)
    except StopIteration:
        raise FetchFixtureError(
            f"PROVENANCE.md has no {VENDORED_HEADING!r} section -- has the file's structure changed?"
        ) from None

    # Find the separator row (the line right after the header row) --
    # insert the new data row immediately after it, before any existing
    # rows or the placeholder italic line.
    separator_idx = None
    for i in range(heading_idx + 1, len(lines)):
        stripped = lines[i].strip()
        if stripped.startswith("|") and all(
            re.fullmatch(r":?-+:?", c.strip()) for c in stripped.strip("|").split("|")
        ):
            separator_idx = i
            break
        if stripped.startswith("### "):
            break
    if separator_idx is None:
        raise FetchFixtureError(f"could not find the table under {VENDORED_HEADING!r}")

    new_row_line = "| " + " | ".join(row_cells) + " |\n"
    insert_at = separator_idx + 1
    # The empty table's italic placeholder line (`*(Empty until ...)*`)
    # immediately follows the separator when no rows exist yet -- drop it
    # once a real row is being added, rather than leaving a stale "empty"
    # claim directly under non-empty data.
    if insert_at < len(lines) and lines[insert_at].strip().startswith("*(Empty"):
        del lines[insert_at]
    updated = lines[:insert_at] + [new_row_line] + lines[insert_at:]
    return "".join(updated)


def _smoke_check_loadable(content: bytes) -> None:
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as exc:
        raise FetchFixtureError(f"fetched content is not valid JSON: {exc}") from exc
    if not isinstance(parsed, dict) or "cells" not in parsed:
        raise FetchFixtureError(
            "fetched content does not look like a .ipynb notebook (no 'cells' key)"
        )
    try:
        sys.path.insert(0, str(REPO_ROOT / "src"))
        from libipynb import load
    except ImportError:
        print(
            "warning: libipynb is not importable from this environment -- skipping the "
            "load(mode='recovery') smoke check (JSON-shape check above still applies)",
            file=sys.stderr,
        )
        return
    STAGING_DIR.mkdir(parents=True, exist_ok=True)
    tmp = STAGING_DIR / "smoke-check.ipynb"
    tmp.write_bytes(content)
    try:
        load(tmp, mode="recovery")
    except Exception as exc:
        raise FetchFixtureError(
            f"fetched content did not load even in recovery mode: {exc}"
        ) from exc
    finally:
        tmp.unlink(missing_ok=True)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--url", required=True, help="https://, commit/tag-pinned raw-content URL")
    parser.add_argument("--category", required=True, choices=VALID_CATEGORIES)
    parser.add_argument(
        "--dest-name", required=True, help="filename to vendor as, e.g. some-notebook.ipynb"
    )
    parser.add_argument(
        "--license",
        required=True,
        help="declared license, e.g. 'MIT' -- human-supplied, not verified by this tool",
    )
    parser.add_argument(
        "--license-evidence-url",
        required=True,
        help="https:// URL to the LICENSE file at the same pinned commit",
    )
    parser.add_argument(
        "--pattern",
        required=True,
        help="one-line note on the structural case this fixture exercises",
    )
    parser.add_argument("--max-bytes", type=int, default=DEFAULT_MAX_BYTES)
    parser.add_argument(
        "--allow-oversized-with-justification",
        default=None,
        help="required, non-empty, to vendor a file over --max-bytes",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--dry-run", action="store_true", help="default: fetch, stage, preview -- write nothing"
    )
    mode.add_argument(
        "--commit", action="store_true", help="actually vendor the file and update PROVENANCE.md"
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    commit = bool(args.commit)

    if args.max_bytes is not None and args.max_bytes <= 0:
        print("error: --max-bytes must be positive", file=sys.stderr)
        return 2
    if (
        args.allow_oversized_with_justification is not None
        and not args.allow_oversized_with_justification.strip()
    ):
        print(
            "error: --allow-oversized-with-justification, if given, must be non-empty",
            file=sys.stderr,
        )
        return 2
    if not args.license_evidence_url.startswith("https://"):
        print("error: --license-evidence-url must be https://", file=sys.stderr)
        return 2

    dest_dir = FIXTURES_DIR / args.category
    dest_path = dest_dir / args.dest_name
    if dest_path.exists():
        print(f"error: {dest_path} already exists -- refusing to overwrite", file=sys.stderr)
        return 2

    try:
        if commit:
            provenance_text = PROVENANCE_PATH.read_text(encoding="utf-8")
            approved_row = _find_approved_row(provenance_text, args.url)
            if approved_row is None:
                raise FetchFixtureError(
                    f"--url {args.url!r} has no Approve'd row in PROVENANCE.md's "
                    f"{SHORTLIST_HEADING!r} table -- refusing to commit. Add a shortlist "
                    "row and get the maintainer's dated decision recorded first."
                )
            prior = _load_prior_dry_run(args.url)
            if prior is None:
                raise FetchFixtureError(
                    "no prior --dry-run found for this exact --url -- run --dry-run first, "
                    "review its output, then re-run with --commit."
                )
            fresh = _stage(args.url, refetch=True)
            if fresh.sha256 != prior.sha256:
                raise FetchFixtureError(
                    "content at --url has changed since the reviewed --dry-run "
                    f"(dry-run sha256={prior.sha256}, now sha256={fresh.sha256}) -- refusing to "
                    "commit unreviewed content; re-run --dry-run to review the new content first."
                )
            staged = fresh
        else:
            staged = _stage(args.url, refetch=True)

        effective_max = args.max_bytes
        if staged.size > effective_max and not args.allow_oversized_with_justification:
            raise FetchFixtureError(
                f"fetched content is {staged.size} bytes, over --max-bytes={effective_max} -- "
                "pass --allow-oversized-with-justification '<reason>' to override"
            )

        _smoke_check_loadable(staged.content)

        import datetime as _dt

        retrieval_date = _dt.datetime.now(_dt.UTC).strftime("%Y-%m-%d")
        vendored_row = [
            args.dest_name,
            args.category,
            args.url,
            args.license,
            retrieval_date,
            staged.sha256,
            str(staged.size),
            args.pattern,
        ]

        print(f"{'COMMIT' if commit else 'DRY RUN'}: {args.url}")
        print(f"  -> would write: {dest_path.relative_to(REPO_ROOT)}")
        print(f"  sha256: {staged.sha256}")
        print(f"  size:   {staged.size} bytes")
        print(f"  PROVENANCE.md row: | {' | '.join(vendored_row)} |")

        if not commit:
            print("\n(dry run -- nothing written; re-run with --commit once reviewed)")
            return 0

        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_path.write_bytes(staged.content)
        updated_provenance = _append_vendored_row(provenance_text, vendored_row)
        PROVENANCE_PATH.write_text(updated_provenance, encoding="utf-8")
        print(f"\nvendored {dest_path.relative_to(REPO_ROOT)} and updated PROVENANCE.md")
        return 0
    except FetchFixtureError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
