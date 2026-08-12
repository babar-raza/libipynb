"""Command-line interface for installed IPYNB packages."""

from __future__ import annotations

import argparse
import json
import sys

from ..codec import dump, load, probe
from ..model import diff_notebooks, upgrade
from ..security import sanitize
from ..validation import validate


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="libipynb",
        description="Production Jupyter Notebook toolkit.",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    # -- probe ---------------------------------------------------------------
    probe_cmd = commands.add_parser(
        "probe",
        help="Detect whether a file is a Jupyter Notebook and report its profile.",
    )
    probe_cmd.add_argument("source", help="Path to the .ipynb file.")

    # -- inspect -------------------------------------------------------------
    inspect_cmd = commands.add_parser(
        "inspect",
        help="Load a notebook and print basic structure information.",
    )
    inspect_cmd.add_argument("source", help="Path to the .ipynb file.")

    # -- validate ------------------------------------------------------------
    validate_cmd = commands.add_parser(
        "validate",
        help="Validate a notebook against the nbformat schema.",
    )
    validate_cmd.add_argument("source", help="Path to the .ipynb file.")

    # -- sanitize ------------------------------------------------------------
    sanitize_cmd = commands.add_parser(
        "sanitize",
        help="Scan a notebook for active content and security hazards.",
    )
    sanitize_cmd.add_argument("source", help="Path to the .ipynb file.")

    # -- upgrade -------------------------------------------------------------
    upgrade_cmd = commands.add_parser(
        "upgrade",
        help="Upgrade a notebook to nbformat 4.5 and print the conversion ledger.",
    )
    upgrade_cmd.add_argument("source", help="Path to the .ipynb file.")
    upgrade_cmd.add_argument(
        "-o",
        "--output",
        metavar="PATH",
        default=None,
        help="Write the upgraded notebook to PATH instead of stdout.",
    )

    # -- diff ----------------------------------------------------------------
    diff_cmd = commands.add_parser(
        "diff",
        help="Diff two notebooks by cell identity and report structural changes.",
    )
    diff_cmd.add_argument("before", help="Path to the base .ipynb file.")
    diff_cmd.add_argument("after", help="Path to the modified .ipynb file.")

    args = parser.parse_args(argv)

    if args.command == "probe":
        return _cmd_probe(args)
    if args.command == "validate":
        return _cmd_validate(args)
    if args.command == "inspect":
        return _cmd_inspect(args)
    if args.command == "sanitize":
        return _cmd_sanitize(args)
    if args.command == "upgrade":
        return _cmd_upgrade(args)
    if args.command == "diff":
        return _cmd_diff(args)
    return 1  # unreachable


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------


def _cmd_probe(args: argparse.Namespace) -> int:
    result = probe(args.source)
    print(json.dumps({"matched": result.matched, "profile": result.profile}))
    return 0 if result else 1


def _cmd_validate(args: argparse.Namespace) -> int:
    report = validate(args.source)
    print(
        json.dumps(
            {
                "valid": report.is_valid,
                "diagnostics": [{"code": item.code, "message": item.message} for item in report],
            },
            sort_keys=True,
        )
    )
    return 0 if report else 1


def _cmd_inspect(args: argparse.Namespace) -> int:
    document = load(args.source, mode="preservation")
    print(
        json.dumps(
            {
                "nbformat": document.nbformat,
                "nbformat_minor": document.nbformat_minor,
                "cell_count": document.cell_count,
            },
            sort_keys=True,
        )
    )
    return 0


def _cmd_sanitize(args: argparse.Namespace) -> int:
    document = load(args.source, mode="preservation")
    report = sanitize(document, dry_run=True)
    print(
        json.dumps(
            {
                "mode": report.mode.value,
                "finding_count": report.count,
                "would_change": report.would_change,
                "findings": [
                    {
                        "path": list(f.path),
                        "media_type": f.media_type,
                        "hazards": list(f.hazards),
                        "references": list(f.references),
                        "action": f.action,
                    }
                    for f in report.findings
                ],
            },
            sort_keys=True,
        )
    )
    return 0


def _cmd_upgrade(args: argparse.Namespace) -> int:
    document = load(args.source, mode="preservation")
    result = upgrade(document, target="4.5")
    ledger = {
        "source_version": f"{document.nbformat}.{document.nbformat_minor}",
        "target_version": "4.5",
        "actions": [
            {
                "code": a.code,
                "path": list(a.path),
                "message": a.message,
            }
            for a in result.actions
        ],
        "id_rewrites": [
            {
                "cell_index": r.cell_index,
                "old_id": r.old_id,
                "new_id": r.new_id,
            }
            for r in result.id_rewrites
        ],
    }
    if args.output:
        dump(result.document, args.output, profile="declared")
        ledger["output"] = args.output
        print(json.dumps(ledger, sort_keys=True))
    else:
        print(json.dumps(ledger, sort_keys=True), file=sys.stderr)
        dump(result.document, sys.stdout, profile="declared")
    return 0


def _cmd_diff(args: argparse.Namespace) -> int:
    before = load(args.before, mode="preservation")
    after = load(args.after, mode="preservation")
    result = diff_notebooks(before, after)
    print(
        json.dumps(
            {
                "has_changes": result.has_changes,
                "notebook_changes": [
                    {
                        "path": list(nc.path),
                        "before": nc.before,
                        "after": nc.after,
                    }
                    for nc in result.notebook_changes
                ],
                "cell_changes": [
                    {
                        "cell_id": cc.cell_id,
                        "added": cc.added,
                        "removed": cc.removed,
                        "moved": cc.moved,
                        "modified": cc.modified,
                        "before_index": cc.before_index,
                        "after_index": cc.after_index,
                        "field_changes": [
                            {
                                "field": fc.field.value,
                                "path": list(fc.path),
                            }
                            for fc in cc.field_changes
                        ],
                    }
                    for cc in result.cell_changes
                ],
            },
            sort_keys=True,
        )
    )
    return 0 if not result.has_changes else 1
