"""Command-line interface for installed IPYNB packages."""

from __future__ import annotations

import argparse
import json

from ..codec import load, probe
from ..validation import validate


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="libipynb")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("probe", "inspect", "validate"):
        command = commands.add_parser(name)
        command.add_argument("source")
    args = parser.parse_args(argv)

    if args.command == "probe":
        result = probe(args.source)
        print(json.dumps({"matched": result.matched, "profile": result.profile}))
        return 0 if result else 1
    if args.command == "validate":
        report = validate(args.source)
        print(
            json.dumps(
                {
                    "valid": report.is_valid,
                    "diagnostics": [
                        {"code": item.code, "message": item.message}
                        for item in report
                    ],
                },
                sort_keys=True,
            )
        )
        return 0 if report else 1
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
