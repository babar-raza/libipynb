"""LIBIPYNB-Q3: flag any()/all() used over a generator or comprehension whose
element expression is itself a call to a side-effecting function/method.

Motivation (plans/publication-readiness-plan-2026-08-24.md section M8/Q3, LIBIPYNB-Q17):
`any(_truncate_one_output(output, max_bytes) for output in outputs)` in
adapters/jupyter_execute.py stopped iterating the moment the first oversized
output was found, silently leaving every later oversized output in the same
call untouched -- `any()`'s short-circuit is correct when the generator's
element expression is a pure predicate, and a real bug when the element call
has side effects the caller actually depends on (as here, where the call
both mutates its argument in place AND returns whether it did).

This is a static check, same idiom as test_import_boundary.py: it parses
every module under src/libipynb with `ast` and flags the *pattern*, so it
holds even for a module the runtime suite never exercises with >=2 relevant
items. It cannot prove a flagged call is actually buggy (a genuinely pure
predicate that happens to be a function call, e.g. a local helper wrapping
`isinstance`, would still be flagged) -- it is a prompt for a human/reviewer
to confirm intent, not a proof of defect. The curated PURE_PREDICATE_NAMES
allowlist below exists to keep known-safe, common cases quiet; it was
calibrated by running this check against the real src/libipynb tree and
extending the allowlist only for genuine false positives found there (see
test_the_real_sweep_finds_no_unreviewed_violations for the live record).
"""

from __future__ import annotations

import ast
import textwrap
from pathlib import Path

#: Bare-name callables assumed pure (a predicate check, not a side-effecting
#: operation) even when their result feeds any()/all() directly. Deliberately
#: small -- keep it that way; adding a real production helper here should be
#: rare and each addition should cite why it is genuinely side-effect-free.
#: The three module-local additions below were added after running this
#: check against the real src/libipynb tree (LIBIPYNB-Q3's own calibration
#: pass) and individually confirming, by reading each body, that none
#: assigns into an argument's attribute/subscript -- each only reads and
#: recurses/computes a bool:
#:   - model/attachments.py::_json_value, validation/rules.py::_is_json_value
#:     -- recursive structural "is this a valid JSON value" check
#:   - validation/schema.py::_is_discriminator_mismatch -- reads
#:     error.validator/error.absolute_path only, returns a bool expression
PURE_PREDICATE_NAMES = frozenset(
    {
        "isinstance",
        "issubclass",
        "hasattr",
        "callable",
        "len",
        "bool",
        "_json_value",
        "_is_json_value",
        "_is_discriminator_mismatch",
    }
)

#: Attribute-call method names assumed pure regardless of receiver -- narrow
#: on purpose: these are well-known stdlib query methods (re.Pattern's
#: search/match/fullmatch return a Match or None, never mutate the pattern
#: or the searched string). Covers validation/schema.py's
#: `pattern.search(str(key))` (LIBIPYNB-Q3 calibration pass).
PURE_PREDICATE_METHOD_NAMES = frozenset({"search", "match", "fullmatch"})


def _call_in_short_circuit_position(node: ast.expr) -> ast.Call | None:
    """If *node* is a Call, or `not <Call>`, return the Call -- else None.

    Matches the exact shape of the real bug: the generator/comprehension's
    yielded expression IS the call (not a call buried inside a comparison,
    e.g. `len(x) > 0`, where the comparison's truthiness -- not the call's
    own side effects -- is what any()/all() actually short-circuits on).
    """
    if isinstance(node, ast.Call):
        return node
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        return _call_in_short_circuit_position(node.operand)
    return None


def _is_pure_predicate_call(call: ast.Call) -> bool:
    func = call.func
    if isinstance(func, ast.Name):
        return func.id in PURE_PREDICATE_NAMES
    if isinstance(func, ast.Attribute):
        return func.attr in PURE_PREDICATE_METHOD_NAMES
    return False


def _short_circuit_findings(source: str) -> list[tuple[str, int]]:
    """Return (function_name, lineno) for every any()/all() call whose
    generator/comprehension element is a non-allowlisted side-effecting call."""
    tree = ast.parse(source)
    findings: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in ("any", "all")
            and len(node.args) == 1
        ):
            continue
        arg = node.args[0]
        if not isinstance(arg, (ast.GeneratorExp, ast.ListComp, ast.SetComp)):
            continue
        call = _call_in_short_circuit_position(arg.elt)
        if call is None or _is_pure_predicate_call(call):
            continue
        findings.append((node.func.id, node.lineno))
    return findings


def _src_root() -> Path:
    return Path(__file__).resolve().parents[2] / "src" / "libipynb"


# ── The check itself must be able to fail, or it proves nothing ────────────


def test_the_checker_actually_detects_a_side_effecting_short_circuit() -> None:
    hostile_source = textwrap.dedent(
        """
        def scan(outputs, max_bytes):
            return any(_truncate_one_output(o, max_bytes) for o in outputs)
        """
    )
    assert _short_circuit_findings(hostile_source) == [("any", 3)]


def test_the_checker_flags_all_too() -> None:
    hostile_source = "all(mutate(x) for x in items)\n"
    assert _short_circuit_findings(hostile_source) == [("all", 1)]


def test_the_checker_flags_the_not_wrapped_form() -> None:
    hostile_source = "any(not mutate(x) for x in items)\n"
    assert _short_circuit_findings(hostile_source) == [("any", 1)]


def test_the_checker_flags_list_and_set_comprehensions_too() -> None:
    assert _short_circuit_findings("any([mutate(x) for x in items])\n") == [("any", 1)]
    assert _short_circuit_findings("all({mutate(x) for x in items})\n") == [("all", 1)]


# ── The check must not flag legitimate, side-effect-free usage ─────────────


def test_the_checker_does_not_flag_a_pure_attribute_or_comparison_predicate() -> None:
    benign_source = textwrap.dedent(
        """
        any(x.is_valid for x in items)
        any(x.value > 0 for x in items)
        all(len(x) > 0 for x in items)
        """
    )
    assert _short_circuit_findings(benign_source) == []


def test_the_checker_does_not_flag_the_curated_pure_predicate_allowlist() -> None:
    benign_source = "\n".join(f"any({name}(x) for x in items)" for name in PURE_PREDICATE_NAMES)
    assert _short_circuit_findings(benign_source) == []


def test_the_checker_does_not_flag_the_curated_pure_predicate_method_allowlist() -> None:
    benign_source = "\n".join(
        f"any(pattern.{name}(x) for x in items)" for name in PURE_PREDICATE_METHOD_NAMES
    )
    assert _short_circuit_findings(benign_source) == []


def test_the_checker_does_not_flag_any_all_used_with_a_plain_iterable_or_attribute() -> None:
    """`any(flags)` (no generator argument at all) and `x.ok` (an Attribute,
    not a Call) are both unambiguously safe usages this check has no opinion
    on."""
    assert _short_circuit_findings("any(flags)\n") == []
    assert _short_circuit_findings("all(x.ok for x in items if x)\n") == []


# ── The real sweep over src/libipynb ────────────────────────────────────────


def test_the_real_sweep_finds_no_unreviewed_violations() -> None:
    """Calibration record: as of LIBIPYNB-Q3's own introduction, the only
    real instance in src/libipynb was adapters/jupyter_execute.py's
    `_truncate_outputs_if_needed` (LIBIPYNB-Q17's own bug). Once Q17 lands
    (rewriting that function to an explicit loop, not any()/all()), this
    sweep must be clean with an EMPTY allowlist below -- a growing
    per-file-exception list here would silently re-open exactly the gap
    this check exists to close, so any future finding must be fixed at the
    source, not allowlisted here, unless it is a genuine, individually
    justified pure-predicate case (extend PURE_PREDICATE_NAMES instead, with
    a comment explaining why)."""
    root = _src_root()
    assert root.is_dir(), f"expected package root at {root}"
    offenders: dict[str, list[tuple[str, int]]] = {}
    for path in sorted(root.rglob("*.py")):
        findings = _short_circuit_findings(path.read_text(encoding="utf-8"))
        if findings:
            offenders[str(path.relative_to(root))] = findings
    assert not offenders, (
        f"any()/all() over a side-effecting call element found -- confirm each is a "
        f"genuine short-circuit-safe predicate (extend PURE_PREDICATE_NAMES with "
        f"justification) or fix the short-circuit bug at its source: {offenders}"
    )
