"""LIBIPYNB-P6: README.md's CLI section must not drift from cli/main.py.

Gate G2 finding: P6's own taskcard named this check as an "implicit
prerequisite" ("if that check does not exist yet by the time this card is
picked up, building it is an implicit prerequisite of this card") and its
closeout rule required "a passing doc-drift check" -- but no such check was
actually built in the same pass, and README.md's CLI section drifted from
the real `--help` output within the same round (9 commands claimed, 11
showing in `--help` before a separate fix; see full-parity-execution-
evidence.md's independent-review addendum). This is the automated guardrail
that should have existed from the start, added during repair.
"""

from __future__ import annotations

import ast
from pathlib import Path

_SRC_ROOT = Path(__file__).resolve().parents[2] / "src" / "libipynb"
_README = Path(__file__).resolve().parents[2] / "README.md"

#: Commands meant only for git's own invocation (never a user typing at a
#: shell), registered with help=argparse.SUPPRESS and hidden from --help's
#: listing -- these are correctly absent from README's command reference,
#: not a drift.
_INTERNAL_ONLY_COMMANDS = frozenset({"_git-diff-driver", "_git-merge-driver"})


def _public_cli_command_names() -> set[str]:
    """Every subcommand name registered via `commands.add_parser("name", ...)`
    in cli/main.py, excluding the internal git-driver-only ones."""
    path = _SRC_ROOT / "cli" / "main.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "add_parser"
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
        ):
            names.add(node.args[0].value)
    return names - _INTERNAL_ONLY_COMMANDS


def test_every_public_cli_command_is_mentioned_in_the_readme() -> None:
    readme_text = _README.read_text(encoding="utf-8")
    missing = sorted(
        name for name in _public_cli_command_names() if f"libipynb {name}" not in readme_text
    )
    assert missing == [], f"README.md's CLI section is missing: {missing}"


def test_readme_never_documents_the_internal_git_driver_commands() -> None:
    """The reverse direction: these are invoked by git itself, never typed
    by a user -- documenting them as a user-facing command would be its own
    kind of inaccuracy."""
    readme_text = _README.read_text(encoding="utf-8")
    leaked = [name for name in _INTERNAL_ONLY_COMMANDS if name in readme_text]
    assert leaked == [], f"README.md should not document internal-only commands: {leaked}"


def test_readme_command_count_matches_actual_public_command_count() -> None:
    """A narrower regression guard for the exact drift Gate G2 found: the
    README's own stated count ("N subcommands") must match reality, not
    just individual command names being present somewhere in the text."""
    count = len(_public_cli_command_names())
    readme_text = _README.read_text(encoding="utf-8")
    assert f"{count} subcommands" in readme_text, (
        f"README.md should say '{count} subcommands' to match the actual public CLI surface "
        f"({sorted(_public_cli_command_names())})"
    )
