"""Command-line interface for installed IPYNB packages."""

from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Any

from ..analytics import (
    average_source_length,
    cell_type_histogram,
    has_execution_errors,
    output_type_histogram,
)
from ..codec import dump, load, probe
from ..errors import NotebookError, NotebookExecutionError
from ..model import CellField, NotebookDocument, diff_notebooks, merge_notebooks, upgrade
from ..model.cleanup import CleanupPolicy, cleanup
from ..model.lifecycle import downgrade, plan_downgrade
from ..security import STRONG_HMAC_ALGORITHMS, HmacNotebookNotary, SqliteSignatureStore, sanitize
from ..validation import validate

# LIBIPYNB-P2 (nbstripout parity): the CLI's own opinionated default strip
# set, matching nbstripout's documented defaults exactly -- notebook-level
# `signature`/`widgets`, cell-level `ExecuteTime`/`collapsed`/`execution`/
# `heading_collapsed`/`hidden`/`scrolled`. This is deliberately a CLI-layer
# constant, not model.cleanup.CleanupPolicy's own default (which stays
# "strip nothing named unless asked" -- a library should be neutral; a
# version-control-hygiene CLI tool should be opinionated, matching
# nbstripout's own split between a neutral core and an opinionated CLI).
_NBSTRIPOUT_DEFAULT_NOTEBOOK_METADATA_KEYS = frozenset({"signature", "widgets"})
_NBSTRIPOUT_DEFAULT_CELL_METADATA_KEYS = frozenset(
    {"ExecuteTime", "collapsed", "execution", "heading_collapsed", "hidden", "scrolled"}
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="libipynb",
        description="Production Jupyter Notebook toolkit.",
    )
    # metavar="COMMAND" replaces the auto-generated {choice1,choice2,...}
    # list in the usage line -- argparse's `help=argparse.SUPPRESS` on a
    # subparser only hides its entry from the "positional arguments"
    # description below the usage line, not from that choices list itself
    # (Gate G2 finding: the two internal `_git-*-driver` commands, meant
    # for git's own invocation only, were leaking into `libipynb --help`'s
    # usage line despite SUPPRESS).
    commands = parser.add_subparsers(dest="command", required=True, metavar="COMMAND")

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

    # -- normalize -----------------------------------------------------------
    normalize_cmd = commands.add_parser(
        "normalize",
        help="Clean up a notebook: strip outputs, execution counts, and selected metadata "
        "(nbstripout-compatible defaults); or manage its git clean-filter integration.",
    )
    normalize_cmd.add_argument(
        "source",
        nargs="?",
        default=None,
        help="Path to the .ipynb file, or '-' to read from stdin (used by the installed git "
        "filter). Omit entirely with --install/--uninstall/--status.",
    )
    normalize_cmd.add_argument(
        "-o",
        "--output",
        metavar="PATH",
        default=None,
        help="Write the cleaned notebook to PATH instead of stdout.",
    )
    normalize_cmd.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would change without modifying anything.",
    )
    normalize_cmd.add_argument(
        "--keep-output", action="store_true", help="Do not strip cell outputs."
    )
    normalize_cmd.add_argument(
        "--keep-count", action="store_true", help="Do not reset execution_count."
    )
    normalize_cmd.add_argument(
        "--extra-keys",
        nargs="+",
        default=[],
        metavar="PATH",
        help="Additional metadata paths to strip, e.g. 'metadata.foo' (notebook-level) or "
        "'cell.metadata.bar' (cell-level).",
    )
    normalize_cmd.add_argument(
        "--keep-metadata-keys",
        nargs="+",
        default=[],
        metavar="PATH",
        help="Metadata paths (same 'metadata.'/'cell.metadata.' syntax) to exempt from the "
        "default nbstripout-compatible strip set.",
    )
    normalize_cmd.add_argument(
        "--install",
        action="store_true",
        help="Register libipynb as a git clean filter for *.ipynb and exit.",
    )
    normalize_cmd.add_argument(
        "--uninstall",
        action="store_true",
        help="Remove libipynb's git clean filter registration and exit.",
    )
    normalize_cmd.add_argument(
        "--status",
        action="store_true",
        help="Report whether libipynb's git clean filter is currently installed and exit.",
    )
    normalize_cmd.add_argument(
        "--global",
        dest="global_scope",
        action="store_true",
        help="With --install/--uninstall/--status: act on the user's global git config "
        "instead of the current repository.",
    )
    normalize_cmd.add_argument(
        "--attributes",
        metavar="PATH",
        default=None,
        help="With --install: write the filter attribute to this versioned file (e.g. "
        ".gitattributes) instead of the repo-local, unversioned .git/info/attributes.",
    )

    # -- convert -------------------------------------------------------------
    convert_cmd = commands.add_parser(
        "convert",
        help="Convert a notebook between nbformat versions (4.0 through 4.5).",
    )
    convert_cmd.add_argument("source", help="Path to the .ipynb file.")
    convert_cmd.add_argument(
        "--target",
        required=True,
        help="Target version (e.g. '4.5', '4.0').",
    )
    convert_cmd.add_argument(
        "-o",
        "--output",
        metavar="PATH",
        default=None,
        help="Write the converted notebook to PATH instead of stdout.",
    )
    convert_cmd.add_argument(
        "--accept-loss",
        action="store_true",
        help="Accept data loss during downgrade (e.g. cell id removal).",
    )

    # -- diff ----------------------------------------------------------------
    diff_cmd = commands.add_parser(
        "diff",
        help="Diff two notebooks by cell identity and report structural changes.",
    )
    diff_cmd.add_argument("before", nargs="?", default=None, help="Path to the base .ipynb file.")
    diff_cmd.add_argument(
        "after", nargs="?", default=None, help="Path to the modified .ipynb file."
    )
    diff_cmd.add_argument(
        "--install-git",
        action="store_true",
        help="Register libipynb as git's diff AND merge driver for *.ipynb and exit "
        "(nbdime 'config-git' equivalent).",
    )
    diff_cmd.add_argument(
        "--uninstall-git",
        action="store_true",
        help="Remove libipynb's git diff/merge driver registration and exit.",
    )
    diff_cmd.add_argument(
        "--git-status",
        action="store_true",
        help="Report whether libipynb's git diff/merge drivers are currently installed and exit.",
    )
    diff_cmd.add_argument(
        "--global",
        dest="global_scope",
        action="store_true",
        help="With --install-git/--uninstall-git/--git-status: act on the user's global git "
        "config instead of the current repository.",
    )

    # -- internal: invoked by git itself once drivers are installed, not by users directly --
    git_diff_driver_cmd = commands.add_parser("_git-diff-driver", help=argparse.SUPPRESS)
    for name in ("path", "old_file", "old_hex", "old_mode", "new_file", "new_hex", "new_mode"):
        git_diff_driver_cmd.add_argument(name)

    git_merge_driver_cmd = commands.add_parser("_git-merge-driver", help=argparse.SUPPRESS)
    git_merge_driver_cmd.add_argument("ancestor")
    git_merge_driver_cmd.add_argument("ours")
    git_merge_driver_cmd.add_argument("theirs")
    git_merge_driver_cmd.add_argument("path")

    # `help=argparse.SUPPRESS` alone leaves a literal "==SUPPRESS==" row in
    # `--help`'s positional-arguments listing once `metavar=` is set on
    # add_subparsers() above (an argparse formatting quirk, confirmed
    # directly against this Python version, not assumed -- Gate G2
    # finding). argparse has no public API for a fully hidden subcommand;
    # dropping the pretty-printed choice-action entries is the standard,
    # widely-used workaround. This does not affect dispatch -- `_git-diff-
    # driver`/`_git-merge-driver` remain fully callable, only invisible in
    # --help, matching their intended "invoked by git, not by users" role.
    commands._choices_actions[:] = [
        action
        for action in commands._choices_actions
        if action.dest not in ("_git-diff-driver", "_git-merge-driver")
    ]

    # -- merge -----------------------------------------------------------------
    merge_cmd = commands.add_parser(
        "merge",
        help="Three-way merge two notebooks against a common ancestor by cell identity.",
    )
    merge_cmd.add_argument("base", help="Path to the common-ancestor .ipynb file.")
    merge_cmd.add_argument("ours", help="Path to 'our' modified .ipynb file.")
    merge_cmd.add_argument("theirs", help="Path to 'their' modified .ipynb file.")
    merge_cmd.add_argument(
        "-o",
        "--output",
        metavar="PATH",
        default=None,
        help="Write the merged notebook to PATH instead of stdout.",
    )

    # -- execute -----------------------------------------------------------------
    execute_cmd = commands.add_parser(
        "execute",
        help="Execute a notebook's code cells through a real local Jupyter kernel "
        "(requires the 'exec' extra: pip install \"libipynb[exec]\"). Runs arbitrary "
        "code from the notebook with this process's own permissions -- only for "
        "notebooks you already trust; see --help below and libipynb.execution's "
        "module docs for the full security posture.",
    )
    execute_cmd.add_argument("source", help="Path to the .ipynb file.")
    execute_cmd.add_argument(
        "-o",
        "--output",
        metavar="PATH",
        default=None,
        help="Write the executed notebook to PATH instead of stdout.",
    )
    execute_cmd.add_argument(
        "--acknowledge-unsandboxed",
        action="store_true",
        help="Required. Confirms you understand this runs arbitrary notebook code with no "
        "sandbox -- the kernel has this process's own filesystem/network/process access.",
    )
    execute_cmd.add_argument(
        "--force",
        action="store_true",
        help="Allow --output to overwrite the input notebook (SOURCE and PATH resolving to "
        "the same file). Refused by default to prevent accidentally destroying the "
        "un-executed original.",
    )
    execute_cmd.add_argument(
        "--kernel",
        metavar="NAME",
        default=None,
        help="Kernel name to launch. Default: the notebook's own declared kernelspec, or "
        "jupyter_client's installed default if the notebook declares none.",
    )
    execute_cmd.add_argument(
        "--cell-timeout",
        type=float,
        default=60.0,
        metavar="SECONDS",
        help="Per-cell wall-clock budget (default: 60). Pass a negative number to disable.",
    )
    execute_cmd.add_argument(
        "--kernel-startup-timeout",
        type=float,
        default=60.0,
        metavar="SECONDS",
        help="How long to wait for the kernel to report ready (default: 60).",
    )
    execute_cmd.add_argument(
        "--on-error",
        choices=("stop", "continue"),
        default="stop",
        help="'stop' (default) halts remaining cells after the first cell error; "
        "'continue' runs every cell regardless.",
    )
    execute_cmd.add_argument(
        "--no-interrupt-on-timeout",
        action="store_true",
        help="A per-cell timeout aborts the whole run immediately instead of interrupting "
        "the kernel and reporting the timeout as that cell's own error.",
    )
    execute_cmd.add_argument(
        "--working-directory",
        metavar="PATH",
        default=None,
        help="Directory the kernel process starts in. Default: the current directory.",
    )
    execute_cmd.add_argument(
        "--record-timing",
        action="store_true",
        help="Record per-cell start/idle timestamps into each executed cell's metadata.",
    )

    # -- analytics -------------------------------------------------------------
    analytics_cmd = commands.add_parser(
        "analytics",
        help="Report structural analytics for a notebook (cell/output type histograms, "
        "execution errors, average source length).",
    )
    analytics_cmd.add_argument("source", help="Path to the .ipynb file.")

    # -- trust -------------------------------------------------------------------
    trust_cmd = commands.add_parser(
        "trust",
        help="Sign, verify, or revoke content-addressed notebook trust using a persistent "
        "HMAC store.",
    )
    trust_cmd.add_argument("source", help="Path to the .ipynb file.")
    trust_action = trust_cmd.add_mutually_exclusive_group(required=True)
    trust_action.add_argument(
        "--sign", action="store_true", help="Sign the notebook's current content."
    )
    trust_action.add_argument(
        "--verify",
        action="store_true",
        help="Check whether the notebook's current content is trusted.",
    )
    trust_action.add_argument(
        "--revoke", action="store_true", help="Remove trust for the notebook's current content."
    )
    trust_cmd.add_argument(
        "--store",
        required=True,
        metavar="PATH",
        help="Path to a persistent (SQLite) signature store. Created if it doesn't exist.",
    )
    trust_cmd.add_argument(
        "--secret-env",
        required=True,
        metavar="VAR",
        help="Name of the environment variable holding the HMAC secret (at least 32 bytes). "
        "There is deliberately no way to pass the secret directly as a CLI argument, since "
        "that would leak it into shell history and process listings.",
    )
    trust_cmd.add_argument(
        "--algorithm",
        default="sha256",
        choices=sorted(STRONG_HMAC_ALGORITHMS),
        help="HMAC algorithm (default: sha256).",
    )

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
    if args.command == "normalize":
        return _cmd_normalize(args)
    if args.command == "convert":
        return _cmd_convert(args)
    if args.command == "diff":
        return _cmd_diff(args)
    if args.command == "merge":
        return _cmd_merge(args)
    if args.command == "execute":
        return _cmd_execute(args)
    if args.command == "analytics":
        return _cmd_analytics(args)
    if args.command == "trust":
        return _cmd_trust(args)
    if args.command == "_git-diff-driver":
        return _cmd_git_diff_driver(args)
    if args.command == "_git-merge-driver":
        return _cmd_git_merge_driver(args)
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


def _load_normalize_config() -> dict[str, Any]:
    """Read `[tool.libipynb.normalize]` from `./pyproject.toml`, if present.

    Deliberately scoped to the current working directory only -- no
    upward directory search -- so behavior is always exactly what a plain
    `cat pyproject.toml` in the invocation directory would show; walking up
    toward a repo root is a real feature some tools offer but is out of
    scope here (LIBIPYNB-P2 non-goal).
    """
    path = Path("pyproject.toml")
    if not path.is_file():
        return {}
    try:
        with path.open("rb") as handle:
            data = tomllib.load(handle)
    except tomllib.TOMLDecodeError:
        return {}
    tool = data.get("tool")
    if not isinstance(tool, dict):
        return {}
    libipynb_section = tool.get("libipynb")
    if not isinstance(libipynb_section, dict):
        return {}
    normalize_section = libipynb_section.get("normalize")
    return normalize_section if isinstance(normalize_section, dict) else {}


class NormalizeConfigError(ValueError):
    """Malformed `--extra-keys`/`--keep-metadata-keys` value or
    `[tool.libipynb.normalize]` config -- always caught by `_cmd_normalize`
    and reported as clean, structured JSON, never left to crash out as a
    raw traceback (Gate G2 finding: it previously did exactly that)."""


def _parse_metadata_path(value: str) -> tuple[str, str]:
    """nbstripout's own `metadata.KEY` / `cell.metadata.KEY` path syntax."""
    if value.startswith("cell.metadata."):
        return "cell", value[len("cell.metadata.") :]
    if value.startswith("metadata."):
        return "notebook", value[len("metadata.") :]
    raise NormalizeConfigError(
        f"metadata path {value!r} must start with 'metadata.' or 'cell.metadata.'"
    )


def _validated_str_list(value: Any, name: str) -> list[str]:
    """`[tool.libipynb.normalize].{name}` must be a list of strings if
    present -- a bare string (a common TOML authoring mistake, since a
    single value doesn't need brackets in some other TOML keys) would
    otherwise iterate character-by-character and crash deep inside path
    parsing with a confusing error (Gate G2 finding)."""
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise NormalizeConfigError(f"[tool.libipynb.normalize].{name} must be a list of strings")
    return value


def _validated_bool(value: Any, name: str) -> bool:
    if value is None:
        return False
    if not isinstance(value, bool):
        raise NormalizeConfigError(f"[tool.libipynb.normalize].{name} must be a boolean")
    return value


def _apply_metadata_paths(
    notebook_keys: set[str],
    cell_keys: set[str],
    extra_keys: list[str],
    keep_metadata_keys: list[str],
) -> None:
    for raw in extra_keys:
        scope, key = _parse_metadata_path(raw)
        (notebook_keys if scope == "notebook" else cell_keys).add(key)
    for raw in keep_metadata_keys:
        scope, key = _parse_metadata_path(raw)
        (notebook_keys if scope == "notebook" else cell_keys).discard(key)


def _resolve_normalize_policy(args: argparse.Namespace) -> CleanupPolicy:
    """Compose the CLI's nbstripout-compatible opinionated default with
    config-file and CLI-flag overrides.

    For the metadata-key lists (`--extra-keys`/`--keep-metadata-keys`), CLI
    flags take precedence over config, which takes precedence over the
    built-in default -- applied as two ordered passes (config, then CLI),
    each pass's own add-then-keep operations kept together, so a CLI
    `--extra-keys` can always re-strip a key a config `keep_metadata_keys`
    tried to preserve, and vice versa (Gate G2 found the previous
    single-merged-pass implementation always let *keeps* win over *adds*
    regardless of which source asked for which -- config could silently
    override a CLI strip request).

    For the boolean `--keep-output`/`--keep-count` flags, either source
    asking to keep is sufficient (an OR, not a full override) -- there is
    no CLI flag to force stripping back on over a config that opts to keep,
    since `argparse.store_true` has no natural "explicitly False" state
    without a separate countermanding flag. This is a real, narrower
    guarantee than the metadata-key lists get, and is documented here
    rather than silently assumed to be the same.
    """
    config = _load_normalize_config()
    notebook_keys = set(_NBSTRIPOUT_DEFAULT_NOTEBOOK_METADATA_KEYS)
    cell_keys = set(_NBSTRIPOUT_DEFAULT_CELL_METADATA_KEYS)

    _apply_metadata_paths(
        notebook_keys,
        cell_keys,
        _validated_str_list(config.get("extra_keys"), "extra_keys"),
        _validated_str_list(config.get("keep_metadata_keys"), "keep_metadata_keys"),
    )
    _apply_metadata_paths(notebook_keys, cell_keys, args.extra_keys, args.keep_metadata_keys)

    keep_output = args.keep_output or _validated_bool(config.get("keep_output"), "keep_output")
    keep_count = args.keep_count or _validated_bool(config.get("keep_count"), "keep_count")

    return CleanupPolicy(
        output_types=frozenset() if keep_output else None,
        notebook_metadata_keys=frozenset(notebook_keys),
        cell_metadata_keys=frozenset(cell_keys),
        reset_execution_counts=not keep_count,
    )


# ── Git clean-filter integration (LIBIPYNB-P2) ──────────────────────────────

_FILTER_NAME = "libipynb"
_FILTER_ATTRIBUTE_LINE = "*.ipynb filter=libipynb"
#: Invoked via the *same* Python interpreter that ran `--install`, not the
#: bare `libipynb` command -- git spawns filter commands through its own
#: shell, which does not reliably inherit an activated venv's PATH (a real
#: gap found and fixed during this card's own end-to-end test: the plain
#: "libipynb normalize -" command resolved fine when this process ran it
#: directly, but failed with "command not found" once git's own shell
#: invoked it). `sys.executable -c ...` needs nothing on PATH except the
#: interpreter path itself, which is always correct because it's the exact
#: interpreter `libipynb` was installed into.
_FILTER_PYTHON_SNIPPET = (
    "import sys; from libipynb.cli import main; sys.exit(main(['normalize', '-']))"
)


def _git_config_scope_args(global_scope: bool) -> list[str]:
    return ["--global"] if global_scope else []


def _run_git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], capture_output=True, text=True, check=False)


def _default_attributes_path(global_scope: bool) -> Path | None:
    """The attributes file libipynb writes to when `--attributes` is not
    given: `.git/info/attributes` for repo-local (nbstripout's own default),
    or the configured/created global attributes file for `--global`."""
    if not global_scope:
        completed = _run_git("rev-parse", "--git-dir")
        if completed.returncode != 0:
            return None
        return Path(completed.stdout.strip()) / "info" / "attributes"
    completed = _run_git("config", "--global", "core.attributesfile")
    if completed.returncode == 0 and completed.stdout.strip():
        return Path(completed.stdout.strip()).expanduser()
    # nbstripout's own documented global default when none is configured yet.
    return Path.home() / ".config" / "git" / "attributes"


def _cmd_normalize_install(args: argparse.Namespace) -> int:
    scope = _git_config_scope_args(args.global_scope)
    if not args.global_scope and _run_git("rev-parse", "--git-dir").returncode != 0:
        print(
            json.dumps({"installed": False, "error": "not inside a git repository"}),
            file=sys.stderr,
        )
        return 1
    clean_command = f"{shlex.quote(sys.executable)} -c {shlex.quote(_FILTER_PYTHON_SNIPPET)}"
    _run_git("config", *scope, f"filter.{_FILTER_NAME}.clean", clean_command)
    _run_git("config", *scope, f"filter.{_FILTER_NAME}.smudge", "cat")
    # Fail CLOSED, matching nbstripout's own install() exactly (verified
    # directly against nbstripout's source, not assumed -- Gate G2 finding):
    # if the filter command itself can't run (stale venv path, moved
    # interpreter, ImportError), `git add` must abort loudly, not silently
    # stage the raw, unstripped notebook. "required false" was the opposite
    # of this and defeated the feature's entire purpose on any filter
    # failure -- see full-parity-execution-evidence.md for the reproduction.
    _run_git("config", *scope, f"filter.{_FILTER_NAME}.required", "true")

    attributes_path = (
        Path(args.attributes) if args.attributes else _default_attributes_path(args.global_scope)
    )
    if attributes_path is None:
        print(json.dumps({"installed": False, "error": "could not resolve attributes file"}))
        return 1
    attributes_path.parent.mkdir(parents=True, exist_ok=True)
    existing = attributes_path.read_text(encoding="utf-8") if attributes_path.is_file() else ""
    if _FILTER_ATTRIBUTE_LINE not in existing.splitlines():
        with attributes_path.open("a", encoding="utf-8") as handle:
            if existing and not existing.endswith("\n"):
                handle.write("\n")
            handle.write(_FILTER_ATTRIBUTE_LINE + "\n")

    print(
        json.dumps(
            {
                "installed": True,
                "scope": "global" if args.global_scope else "local",
                "attributes_file": str(attributes_path),
            },
            sort_keys=True,
        )
    )
    return 0


def _normalize_attributes_candidates(args: argparse.Namespace) -> list[str]:
    """Every plausible location the attributes line could have been written
    to, regardless of the `--global` flag passed to *this* invocation --
    attribute files are inherently location-based, not scope-based, so
    `--uninstall` (no `--global`) must still clean up a line that
    `--install --global` wrote, and vice versa (Gate G2 finding: the first
    implementation only ever checked the scope-matching location, silently
    leaving an orphaned attributes line and reporting `{"uninstalled": true}`
    regardless)."""
    candidates: list[str] = [args.attributes] if args.attributes else []
    completed = _run_git("rev-parse", "--git-dir")
    if completed.returncode == 0:
        candidates.append(str(Path(completed.stdout.strip()) / "info" / "attributes"))
    candidates.append(".gitattributes")
    default_global = _default_attributes_path(True)
    if default_global is not None:
        candidates.append(str(default_global))
    return candidates


def _cmd_normalize_uninstall(args: argparse.Namespace) -> int:
    # Config unset respects --global exactly like --install/--status do --
    # unlike the attributes-file search below, unsetting the WRONG config
    # scope would be actively harmful (a plain local `--uninstall` must
    # never remove a `--global` filter config that other repositories still
    # rely on).
    scope = _git_config_scope_args(args.global_scope)
    for key in ("clean", "smudge", "required"):
        _run_git("config", *scope, "--unset", f"filter.{_FILTER_NAME}.{key}")

    removed_from: list[str] = []
    for candidate in _normalize_attributes_candidates(args):
        path = Path(candidate)
        if not path.is_file():
            continue
        lines = path.read_text(encoding="utf-8").splitlines()
        if _FILTER_ATTRIBUTE_LINE in lines:
            lines.remove(_FILTER_ATTRIBUTE_LINE)
            path.write_text(
                "\n".join(lines) + ("\n" if lines else ""),
                encoding="utf-8",
            )
            removed_from.append(str(path))

    print(
        json.dumps(
            {"uninstalled": True, "removed_from": removed_from},
            sort_keys=True,
        )
    )
    return 0


def _cmd_normalize_status(args: argparse.Namespace) -> int:
    scope = _git_config_scope_args(args.global_scope)
    clean = _run_git("config", *scope, "--get", f"filter.{_FILTER_NAME}.clean")
    installed = clean.returncode == 0 and clean.stdout.strip() != ""
    print(
        json.dumps(
            {
                "installed": installed,
                "scope": "global" if args.global_scope else "local",
                "clean_command": clean.stdout.strip() if installed else None,
            },
            sort_keys=True,
        )
    )
    return 0 if installed else 1


def _cmd_normalize(args: argparse.Namespace) -> int:
    # Gate G2 finding: these were previously silently resolved by if/elif
    # order (--install always won) rather than rejected -- a caller who
    # passed two by mistake got one silently ignored, not an error.
    action_flags = [name for name in ("install", "uninstall", "status") if getattr(args, name)]
    if len(action_flags) > 1:
        print(
            json.dumps({"error": f"--{'/--'.join(action_flags)} are mutually exclusive"}),
            file=sys.stderr,
        )
        return 2
    if args.global_scope and args.attributes and action_flags == ["install"]:
        print(
            json.dumps(
                {
                    "error": "--global and --attributes are mutually exclusive: --attributes "
                    "names a versioned, repo-local file, which cannot also be a global "
                    "config's attributes target"
                }
            ),
            file=sys.stderr,
        )
        return 2

    if args.install:
        return _cmd_normalize_install(args)
    if args.uninstall:
        return _cmd_normalize_uninstall(args)
    if args.status:
        return _cmd_normalize_status(args)
    if args.source is None:
        print(
            json.dumps({"error": "source is required unless --install/--uninstall/--status"}),
            file=sys.stderr,
        )
        return 2

    try:
        policy = _resolve_normalize_policy(args)
    except NormalizeConfigError as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 2

    source = sys.stdin if args.source == "-" else args.source
    document = load(source, mode="preservation")
    report = cleanup(document, policy=policy, dry_run=args.dry_run)
    output = {
        "change_count": report.count,
        "changes": [
            {
                "operation": c.operation,
                "path": list(c.path),
            }
            for c in report.changes
        ],
    }
    if not args.dry_run and args.output:
        dump(document, args.output, profile="declared")
        output["output"] = args.output
    elif not args.dry_run and not args.output:
        print(json.dumps(output, sort_keys=True), file=sys.stderr)
        dump(document, sys.stdout, profile="declared")
        return 0
    print(json.dumps(output, sort_keys=True))
    return 0


def _cmd_convert(args: argparse.Namespace) -> int:
    document = load(args.source, mode="preservation")
    source_major = document.nbformat
    source_minor = document.nbformat_minor
    target_parts = args.target.removeprefix("nbformat-").split(".", 1)
    target_major = int(target_parts[0])
    target_minor = int(target_parts[1]) if len(target_parts) > 1 else 5

    if (target_major, target_minor) > (source_major, source_minor or 0):
        result = upgrade(document, target=args.target)
        ledger = {
            "direction": "upgrade",
            "source_version": f"{source_major}.{source_minor}",
            "target_version": f"{target_major}.{target_minor}",
            "actions": [
                {"code": a.code, "path": list(a.path), "message": a.message} for a in result.actions
            ],
            "id_rewrites": [
                {"cell_index": r.cell_index, "old_id": r.old_id, "new_id": r.new_id}
                for r in result.id_rewrites
            ],
        }
        converted = result.document
    elif (target_major, target_minor) < (source_major, source_minor or 0):
        plan = plan_downgrade(document, target=args.target)
        result_down = downgrade(document, plan=plan, accept_loss=args.accept_loss)
        ledger = {
            "direction": "downgrade",
            "source_version": f"{source_major}.{source_minor}",
            "target_version": f"{target_major}.{target_minor}",
            "actions": [
                {"code": a.code, "path": list(a.path), "message": a.message}
                for a in result_down.actions
            ],
            "id_rewrites": [
                {"cell_index": r.cell_index, "old_id": r.old_id, "new_id": r.new_id}
                for r in result_down.id_rewrites
            ],
        }
        converted = result_down.document
    else:
        print(
            json.dumps(
                {
                    "direction": "none",
                    "source_version": f"{source_major}.{source_minor}",
                    "target_version": f"{target_major}.{target_minor}",
                    "message": "source and target versions are identical",
                },
                sort_keys=True,
            )
        )
        return 0

    if args.output:
        dump(converted, args.output, profile="declared")
        ledger["output"] = args.output
        print(json.dumps(ledger, sort_keys=True))
    else:
        print(json.dumps(ledger, sort_keys=True), file=sys.stderr)
        dump(converted, sys.stdout, profile="declared")
    return 0


def _cmd_diff(args: argparse.Namespace) -> int:
    if args.install_git:
        return _cmd_git_drivers_install(args)
    if args.uninstall_git:
        return _cmd_git_drivers_uninstall(args)
    if args.git_status:
        return _cmd_git_drivers_status(args)
    if args.before is None or args.after is None:
        print(
            json.dumps(
                {
                    "error": "before/after are required unless --install-git/--uninstall-git/--git-status"
                }
            ),
            file=sys.stderr,
        )
        return 2

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
                                **(
                                    {
                                        "source_hunks": [
                                            {
                                                "op": hunk.op,
                                                "before_lines": list(hunk.before_lines),
                                                "after_lines": list(hunk.after_lines),
                                            }
                                            for hunk in fc.source_hunks
                                            if hunk.op != "equal"
                                        ]
                                    }
                                    if fc.source_hunks is not None
                                    else {}
                                ),
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


def _cmd_merge(args: argparse.Namespace) -> int:
    base = load(args.base, mode="preservation")
    ours = load(args.ours, mode="preservation")
    theirs = load(args.theirs, mode="preservation")
    result = merge_notebooks(base, ours, theirs)
    ledger = {
        "has_conflicts": result.report.has_conflicts,
        "conflict_count": len(result.report.conflicts),
        "conflicts": [
            {
                "cell_id": conflict.cell_id,
                "kind": conflict.kind.value,
                "field_name": conflict.field_name,
                "description": conflict.description,
            }
            for conflict in result.report.conflicts
        ],
    }
    if args.output:
        dump(result.merged, args.output, profile="declared")
        ledger["output"] = args.output
        print(json.dumps(ledger, sort_keys=True))
    else:
        print(json.dumps(ledger, sort_keys=True), file=sys.stderr)
        dump(result.merged, sys.stdout, profile="declared")
    return 0 if not result.report.has_conflicts else 1


def _cmd_execute(args: argparse.Namespace) -> int:
    """LIBIPYNB-P4c: CLI exposure of the real Jupyter-kernel-protocol
    executor (:mod:`libipynb.execution`). Requires the `exec` extra --
    imported lazily here, never at module import time, so every other CLI
    command keeps working without it installed."""
    if (
        args.output
        and Path(args.source).resolve() == Path(args.output).resolve()
        and not args.force
    ):
        print(
            json.dumps(
                {
                    "error": "--output resolves to the same file as SOURCE; refusing to "
                    "overwrite the un-executed original. Pass --force to confirm."
                }
            ),
            file=sys.stderr,
        )
        return 2

    try:
        from ..execution import ExecutionOptions, LocalJupyterExecutor
        from ..execution.exceptions import MissingExecutionDependencyError
    except ImportError as exc:  # pragma: no cover -- libipynb.execution itself has no hard import
        print(json.dumps({"error": f"execute command is unavailable: {exc}"}), file=sys.stderr)
        return 2

    document = load(args.source, mode="preservation")
    options = ExecutionOptions(
        kernel_name=args.kernel,
        working_directory=args.working_directory,
        cell_timeout=args.cell_timeout if args.cell_timeout >= 0 else None,
        kernel_startup_timeout=args.kernel_startup_timeout,
        stop_on_error=args.on_error == "stop",
        interrupt_on_timeout=not args.no_interrupt_on_timeout,
        record_timing=args.record_timing,
        acknowledge_unsandboxed=args.acknowledge_unsandboxed,
    )

    try:
        executor = LocalJupyterExecutor()
        result = executor.execute(document, options=options)
    except MissingExecutionDependencyError as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 2
    except NotebookExecutionError as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 2
    except ValueError as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 2

    ledger = {
        "kernel": result.kernel_name,
        "cell_count": len(result.cell_records),
        "executed_count": sum(1 for r in result.cell_records if r.executed),
        "succeeded": result.succeeded,
        "completed": result.completed,
        "stopped_early": result.stopped_early,
        "timed_out": result.timed_out,
        "timed_out_cell_index": result.timed_out_cell_index,
        "kernel_launch_error": result.kernel_launch_error,
        "kernel_death_error": result.kernel_death_error,
        "first_error": (
            {"ename": result.first_error.ename, "evalue": result.first_error.evalue}
            if result.first_error is not None
            else None
        ),
    }
    if args.output:
        dump(result.notebook, args.output, profile="declared")
        ledger["output"] = args.output
        print(json.dumps(ledger, sort_keys=True))
    else:
        print(json.dumps(ledger, sort_keys=True), file=sys.stderr)
        dump(result.notebook, sys.stdout, profile="declared")
    return 0 if result.succeeded else 1


def _cmd_analytics(args: argparse.Namespace) -> int:
    document = load(args.source, mode="preservation")
    print(
        json.dumps(
            {
                "cell_type_histogram": cell_type_histogram(document.raw),
                "output_type_histogram": output_type_histogram(document.raw),
                "has_execution_errors": has_execution_errors(document.raw),
                "average_source_length": average_source_length(document.raw),
            },
            sort_keys=True,
        )
    )
    return 0


def _cmd_trust(args: argparse.Namespace) -> int:
    secret_value = os.environ.get(args.secret_env)
    if secret_value is None:
        print(
            json.dumps({"error": f"environment variable {args.secret_env!r} is not set"}),
            file=sys.stderr,
        )
        return 2

    document = load(args.source, mode="preservation")
    store = SqliteSignatureStore(args.store)
    try:
        try:
            notary = HmacNotebookNotary(
                secret=secret_value.encode("utf-8"), algorithm=args.algorithm, store=store
            )
        except ValueError as exc:
            print(json.dumps({"error": str(exc)}), file=sys.stderr)
            return 2
        if args.sign:
            record = notary.sign(document)
            result: dict[str, Any] = {
                "action": "sign",
                "digest": record.digest,
                "algorithm": record.algorithm,
                "trusted": True,
            }
        elif args.verify:
            verification = notary.verify(document)
            result = {
                "action": "verify",
                "digest": verification.record.digest,
                "algorithm": verification.record.algorithm,
                "trusted": verification.trusted,
                "reason": verification.reason,
            }
        else:
            digest = notary.compute_signature(document)
            revoked = notary.revoke(document)
            result = {
                "action": "revoke",
                "digest": digest,
                "algorithm": notary.algorithm,
                "revoked": revoked,
            }
    finally:
        store.close()

    print(json.dumps(result, sort_keys=True))
    if args.verify:
        return 0 if result["trusted"] else 1
    return 0


# ── Git diff/merge driver integration (LIBIPYNB-P3c) ────────────────────────
#
# Registers libipynb as git's diff AND merge driver for *.ipynb in one step,
# matching nbdime's own `nbdime config-git --enable` (which wires up both
# drivers together rather than requiring two separate registrations).
# `git diff`/`git merge` then transparently invoke libipynb for .ipynb
# files, exactly as documented for nbdime's own integration.
#
# The exact positional-argument contract below (7 args for a diff driver:
# path old-file old-hex old-mode new-file new-hex new-mode; the merge
# driver's %O/%A/%B/%P placeholders, with %A doubling as the file git
# expects overwritten with the merge result) is git's own external-driver
# contract (gitattributes(5)), not something libipynb invents.


def _empty_notebook_document() -> NotebookDocument:
    return NotebookDocument({"nbformat": 4, "nbformat_minor": 5, "metadata": {}, "cells": []})


def _load_for_git_driver(path_str: str) -> NotebookDocument | None:
    """Git passes `/dev/null` (or an empty temp file) for a side that
    doesn't exist yet (a newly added or fully deleted notebook) -- treated
    as an empty notebook so the diff/merge shows every cell as added/
    removed rather than crashing on a missing file."""
    path = Path(path_str)
    if not path.is_file() or path.stat().st_size == 0:
        return _empty_notebook_document()
    try:
        return load(path, mode="preservation")
    except (NotebookError, OSError):
        return None


def _cmd_git_diff_driver(args: argparse.Namespace) -> int:
    before = _load_for_git_driver(args.old_file)
    after = _load_for_git_driver(args.new_file)
    if before is None or after is None:
        print(f"libipynb: could not parse {args.path} as a notebook; showing no diff")
        return 0
    result = diff_notebooks(before, after)
    print(f"--- a/{args.path}")
    print(f"+++ b/{args.path}")
    if not result.has_changes:
        print("(no structural changes)")
        return 0
    for change in result.cell_changes:
        if change.added:
            print(f"@@ cell {change.cell_id} added @@")
            continue
        if change.removed:
            print(f"@@ cell {change.cell_id} removed @@")
            continue
        status = [s for s, flag in (("moved", change.moved), ("modified", change.modified)) if flag]
        print(f"@@ cell {change.cell_id} {', '.join(status) or 'changed'} @@")
        for field_change in change.field_changes:
            if field_change.field == CellField.SOURCE and field_change.source_hunks:
                for hunk in field_change.source_hunks:
                    if hunk.op == "equal":
                        continue
                    for line in hunk.before_lines:
                        print(f"-{line.rstrip(chr(10))}")
                    for line in hunk.after_lines:
                        print(f"+{line.rstrip(chr(10))}")
            else:
                print(f"  {field_change.field.value} changed")
    return 0


def _cmd_git_merge_driver(args: argparse.Namespace) -> int:
    ancestor = _load_for_git_driver(args.ancestor)
    ours = _load_for_git_driver(args.ours)
    theirs = _load_for_git_driver(args.theirs)
    if ancestor is None or ours is None or theirs is None:
        print(f"libipynb: could not parse {args.path} as a notebook for merge", file=sys.stderr)
        return 1
    result = merge_notebooks(ancestor, ours, theirs)
    dump(result.merged, args.ours, profile="declared")
    if result.report.has_conflicts:
        print(
            f"libipynb: {len(result.report.conflicts)} conflict(s) in {args.path} "
            "(unresolved fields kept the common ancestor's value -- resolve manually)",
            file=sys.stderr,
        )
        return 1
    return 0


def _driver_command(subcommand: str) -> str:
    snippet = f"import sys; from libipynb.cli import main; sys.exit(main(['{subcommand}'] + sys.argv[1:]))"
    return f"{shlex.quote(sys.executable)} -c {shlex.quote(snippet)}"


def _cmd_git_drivers_install(args: argparse.Namespace) -> int:
    scope = _git_config_scope_args(args.global_scope)
    if not args.global_scope and _run_git("rev-parse", "--git-dir").returncode != 0:
        print(json.dumps({"installed": False, "error": "not inside a git repository"}))
        return 1
    _run_git("config", *scope, "diff.libipynb.command", _driver_command("_git-diff-driver"))
    _run_git(
        "config",
        *scope,
        "merge.libipynb.driver",
        _driver_command("_git-merge-driver") + " %O %A %B %P",
    )
    _run_git("config", *scope, "merge.libipynb.name", "libipynb notebook merge driver")

    attributes_path = _default_attributes_path(args.global_scope)
    if attributes_path is not None:
        attributes_path.parent.mkdir(parents=True, exist_ok=True)
        existing = attributes_path.read_text(encoding="utf-8") if attributes_path.is_file() else ""
        line = "*.ipynb diff=libipynb merge=libipynb"
        if line not in existing.splitlines():
            with attributes_path.open("a", encoding="utf-8") as handle:
                if existing and not existing.endswith("\n"):
                    handle.write("\n")
                handle.write(line + "\n")

    print(
        json.dumps(
            {
                "installed": True,
                "scope": "global" if args.global_scope else "local",
                "attributes_file": str(attributes_path) if attributes_path else None,
            },
            sort_keys=True,
        )
    )
    return 0


def _cmd_git_drivers_uninstall(args: argparse.Namespace) -> int:
    scope = _git_config_scope_args(args.global_scope)
    _run_git("config", *scope, "--unset", "diff.libipynb.command")
    _run_git("config", *scope, "--unset", "merge.libipynb.driver")
    _run_git("config", *scope, "--unset", "merge.libipynb.name")

    removed_from: list[str] = []
    line = "*.ipynb diff=libipynb merge=libipynb"
    for candidate in _attributes_candidates(args.global_scope):
        path = Path(candidate)
        if not path.is_file():
            continue
        lines = path.read_text(encoding="utf-8").splitlines()
        if line in lines:
            lines.remove(line)
            path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
            removed_from.append(str(path))

    print(json.dumps({"uninstalled": True, "removed_from": removed_from}, sort_keys=True))
    return 0


def _attributes_candidates(global_scope: bool) -> list[str]:
    if global_scope:
        default = _default_attributes_path(True)
        return [str(default)] if default is not None else []
    candidates = []
    completed = _run_git("rev-parse", "--git-dir")
    if completed.returncode == 0:
        candidates.append(str(Path(completed.stdout.strip()) / "info" / "attributes"))
    candidates.append(".gitattributes")
    return candidates


def _cmd_git_drivers_status(args: argparse.Namespace) -> int:
    scope = _git_config_scope_args(args.global_scope)
    diff_cmd = _run_git("config", *scope, "--get", "diff.libipynb.command")
    merge_cmd = _run_git("config", *scope, "--get", "merge.libipynb.driver")
    installed = diff_cmd.returncode == 0 and merge_cmd.returncode == 0
    print(
        json.dumps(
            {
                "installed": installed,
                "scope": "global" if args.global_scope else "local",
                "diff_installed": diff_cmd.returncode == 0,
                "merge_installed": merge_cmd.returncode == 0,
            },
            sort_keys=True,
        )
    )
    return 0 if installed else 1
