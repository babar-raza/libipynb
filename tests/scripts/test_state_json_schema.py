"""LIBIPYNB-Q25: mechanically enforce plans/state.json's own evidence rules.

Motivation (plans/publication-readiness-plan-2026-08-24.md section 10, self-audit
finding d): the rule "a task cannot be marked VERIFIED without real evidence
fields populated" was, on its own, a process convention -- nothing stopped a
future session from writing VERIFIED without populating them. This test
converts that convention into a mechanical, rerun-proof check, consistent with
this whole engagement's own diagnosis: prose discipline degrades across
reruns, mechanical checks don't.

Deliberately scoped to structural + evidence-presence checks only -- it
cannot verify that a cited commit hash actually contains the claimed fix, or
that a review_lenses_applied entry reflects a genuinely separate Agent
invocation and not a self-authored claim. Those remain judgment calls for
whoever reviews a VERIFIED row, not something ast/json-level validation can
settle. See adversarial-review.md's own AO-1 ("self-authored evidence") for
the class of gap this test does not close.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

STATUS_VOCABULARY = frozenset(
    {
        "NOT_STARTED",
        "IN_PROGRESS",
        "BLOCKED_EXTERNAL",
        "IMPLEMENTED_UNVERIFIED",
        "VERIFIED",
        "DEFERRED_WITH_AUTHORITY",
    }
)
LEGACY_STATUS_VOCABULARY = frozenset(
    {
        "not_attempted",
        "claimed_unproven",
        "partially_done",
        "completed_but_weakly_verified",
        "completed_verified",
        "blocker",
        "follow_up",
    }
)

#: Every taskcard whose diff touches one of the 4 hot modules
#: plans/state.json itself names as requiring a mutation baseline before
#: VERIFIED -- mirrored here (not imported from the JSON, and not derived
#: automatically from any diff) so a state.json edit that silently drops
#: this requirement is itself something this test would need updating to
#: match, not something that could disappear unnoticed by editing only
#: the data file.
#:
#: LIBIPYNB-Q66 Gate-G2 whole-session review finding: this allowlist was
#: never extended past its original 4 entries even as later taskcards
#: (Q63/Q64 touching adapters/execute.py, Q65 touching codec/writer.py,
#: Q66 touching codec/reader.py) landed and were marked VERIFIED -- so
#: this mechanical check silently stopped applying to new hot-module work
#: without failing loudly. A new taskcard touching a hot module MUST be
#: added here when it's added to plans/state.json, not only when it
#: reaches VERIFIED -- an easy step to forget, since nothing fails until
#: that later status change.
HOT_MODULE_TASK_IDS = frozenset(
    {
        "LIBIPYNB-Q16",
        "LIBIPYNB-Q17",
        "LIBIPYNB-Q18",
        "LIBIPYNB-Q19",
        "LIBIPYNB-Q63",
        "LIBIPYNB-Q64",
        "LIBIPYNB-Q65",
        "LIBIPYNB-Q66",
    }
)

REQUIRED_TASK_FIELDS = ("id", "phase", "title", "depends_on", "owner", "status")
REQUIRED_CARRIED_FORWARD_FIELDS = ("id", "title", "source_plan", "status")


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _load_state() -> dict[str, Any]:
    return json.loads((_repo_root() / "plans" / "state.json").read_text(encoding="utf-8"))


def _known_commit_hashes() -> set[str]:
    output = subprocess.run(
        ["git", "log", "--all", "--format=%H"],
        cwd=_repo_root(),
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return set(output.split())


def test_state_json_is_valid_json_and_loads() -> None:
    state = _load_state()
    assert isinstance(state["tasks"], list) and state["tasks"]


def test_every_task_has_the_required_structural_fields() -> None:
    state = _load_state()
    missing: dict[str, list[str]] = {}
    for task in state["tasks"]:
        absent = [f for f in REQUIRED_TASK_FIELDS if f not in task]
        if absent:
            missing[task.get("id", "<no id>")] = absent
    assert not missing, f"tasks missing required fields: {missing}"


def test_every_carried_forward_item_has_the_required_fields() -> None:
    state = _load_state()
    missing: dict[str, list[str]] = {}
    for item in state["carried_forward_from_prior_plans"]:
        absent = [f for f in REQUIRED_CARRIED_FORWARD_FIELDS if f not in item]
        if absent:
            missing[item.get("id", "<no id>")] = absent
    assert not missing, f"carried-forward items missing required fields: {missing}"


def test_no_duplicate_task_ids() -> None:
    state = _load_state()
    ids = [t["id"] for t in state["tasks"]] + [
        c["id"] for c in state["carried_forward_from_prior_plans"]
    ]
    duplicates = {i for i in ids if ids.count(i) > 1}
    assert not duplicates, f"duplicate task ids: {duplicates}"


def test_every_status_value_is_in_the_controlled_vocabulary() -> None:
    state = _load_state()
    bad = {t["id"]: t["status"] for t in state["tasks"] if t["status"] not in STATUS_VOCABULARY}
    assert not bad, f"tasks with a status outside the controlled vocabulary: {bad}"


def test_every_legacy_status_equivalent_is_in_the_legacy_vocabulary() -> None:
    state = _load_state()
    bad = {
        t["id"]: t["legacy_status_equivalent"]
        for t in state["tasks"]
        if "legacy_status_equivalent" in t
        and t["legacy_status_equivalent"] not in LEGACY_STATUS_VOCABULARY
    }
    assert not bad, f"tasks with a legacy_status_equivalent outside the legacy vocabulary: {bad}"


def test_every_dependency_reference_resolves_to_a_real_task_id() -> None:
    state = _load_state()
    known_ids = {t["id"] for t in state["tasks"]}
    dangling: dict[str, list[str]] = {}
    for task in state["tasks"]:
        unresolved = [dep for dep in task.get("depends_on", []) if dep not in known_ids]
        if unresolved:
            dangling[task["id"]] = unresolved
    assert not dangling, f"tasks depending on a task id that doesn't exist: {dangling}"


def test_verified_tasks_cite_a_real_commit_that_exists_in_this_repo() -> None:
    """A VERIFIED row (where the field is present at all -- Phase 2-5 rows are
    still title/status stubs pending detailed expansion when their phase
    starts, per plans/publication-readiness-plan-2026-08-24.md's own
    just-in-time taskcard-detail note) must cite a commit hash that actually
    exists, not merely a non-null string."""
    state = _load_state()
    commits = _known_commit_hashes()
    bad: dict[str, Any] = {}
    for task in state["tasks"]:
        if task["status"] != "VERIFIED" or "repair_commit" not in task:
            continue
        commit = task["repair_commit"]
        if not commit or commit not in commits:
            bad[task["id"]] = commit
    assert not bad, f"VERIFIED tasks with a missing or unresolvable repair_commit: {bad}"


def test_verified_reviewed_tasks_have_a_non_empty_review_lenses_applied() -> None:
    """Only tasks owned by 'implementer+separate_reviewer' (the functional
    P0 fixes and later reviewed work) require this -- pure infrastructure
    tasks (owner == 'implementer') are explicitly exempt by design, see each
    such taskcard's own 'no separate review needed -- infrastructure, not a
    functional fix' note in plans/publication-readiness-plan-2026-08-24.md."""
    state = _load_state()
    bad: dict[str, Any] = {}
    for task in state["tasks"]:
        if task["status"] != "VERIFIED" or task.get("owner") != "implementer+separate_reviewer":
            continue
        lenses = task.get("review_lenses_applied")
        if not lenses:
            bad[task["id"]] = lenses
    assert not bad, (
        f"VERIFIED reviewed tasks with no recorded review_lenses_applied evidence: {bad}"
    )


def test_verified_hot_module_tasks_have_a_mutation_baseline_or_a_documented_exception() -> None:
    """The 4 hot-module tasks may reach VERIFIED before LIBIPYNB-Q31's
    mutation-testing pilot lands -- but only with an explicit
    partial_evidence_note explaining the temporary acceptance, per this
    engagement's own plan text; a silently-null mutation_baseline_checked
    with no note is the exact silent gap this check exists to prevent."""
    state = _load_state()
    bad: dict[str, Any] = {}
    for task in state["tasks"]:
        if task["id"] not in HOT_MODULE_TASK_IDS or task["status"] != "VERIFIED":
            continue
        has_baseline = task.get("mutation_baseline_checked") is not None
        has_documented_exception = bool(task.get("partial_evidence_note"))
        if not (has_baseline or has_documented_exception):
            bad[task["id"]] = "no mutation_baseline_checked and no partial_evidence_note"
    assert not bad, f"VERIFIED hot-module tasks with an undocumented mutation-evidence gap: {bad}"
