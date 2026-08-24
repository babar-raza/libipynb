# libipynb publication-readiness plan — 2026-08-24

**This is the canonical plan for the 2026-08-24 publication-readiness engagement.** Live
per-task status lives in [`plans/state.json`](state.json), not duplicated here — read that file
for current status, dependencies, and gate citations. This document records the *why* (diagnosis,
machinery reconciliation) and the *what* (phase structure) once; it is not re-edited per taskcard.

## Relationship to `plans/*.md` and `.supervisor/`

This plan does not replace `plans/remediation-plan.md`, `plans/full-parity-plan.md`, or
`plans/production-hardening-plan.md` — those remain the narrative/evidence record for the work
they already govern (Tier B/M/V, Tier P, and `LIBIPYNB-Q1`–`Q15b` respectively). This plan governs
new work opened 2026-08-24 onward (`LIBIPYNB-Q1`, `Q16`–`Q54`), and `plans/state.json` is a new,
complementary machine-readable layer for it. 14 other dated documents under `plans/` are historical
and untouched.

Reading `.supervisor/`'s actual machinery (not assuming it matched this mission) surfaced real
conflicts, reconciled here rather than silently overridden:

| ID | Finding | Resolution |
|---|---|---|
| M1 | `.supervisor/project-adapter.yaml`'s `authoritative_plans` listed only `remediation-plan.md`/`full-parity-plan.md`, omitting the actually-current `production-hardening-plan.md`. | Healed directly in `project-adapter.yaml` — both that file and this one added. |
| M2 | `.supervisor/prompts/prompt-registry.yaml` and `prompt4-close-task.md` forbade a separate state file ("this repo's plan files are the single record"), conflicting with this mission's explicit requirement for one. | Mission wins (current, explicit, maintainer-authored). Both files healed to acknowledge `plans/state.json` as a complementary machine-readable layer, not a replacement. |
| M3 | Status vocabulary mismatch: this mission's 6 states vs. the repo's existing, more precise 7 (which names "tests pass but nobody independently checked" explicitly — `claimed_unproven`/`completed_but_weakly_verified`). | `plans/state.json` uses the mission's 6-state vocabulary (the explicit schema requirement) plus a `legacy_status_equivalent` field per row for cross-reference. |
| M4 | Three unrelated Gate-lettering schemes share bare "G#" names: this mission's G0–G9, the repo's taskcard Gate Contract G1–G9, and `plans/gate-status-g1-g7.md`'s separately-disambiguated capability-contract G1–G7. | Always prefixed going forward: `Mission-G#`, `Taskcard-G#`, `Capability-G#`. |
| M5 | `prompt4-close-task.md` instructed appending everything to the still-open `[0.1.0]` CHANGELOG entry, with no `[Unreleased]` section — conflicting with this mission's explicit instruction against backdating ongoing work under a historical release date. | Mission wins; `prompt4-close-task.md` healed to instruct opening `[Unreleased]` (`LIBIPYNB-Q33`). |
| M6 | Verification commands must be quoted verbatim from `.supervisor/project-adapter.yaml`'s `commands:` block / `.gitlab-ci.yml`, not paraphrased (`prompt3-controlled-execution.md`'s own explicit rule). | Applied throughout this engagement's taskcards. |
| M7 | Repair-loop cap mismatch: the repo's own convention defaults to 3 cycles; this mission's operating rules specify 2. | This mission's stricter cap (2) governs new work opened under this plan. |
| M8 | `.supervisor/prompts/adversarial-review.md` is an existing, battle-tested 15-question Anti-Overclaim checklist — evidence-integrity focused. It is **extended**, not replaced, with 4 new bug-finding-strategy questions (`LIBIPYNB-Q2`: combinatorial/cardinality, spec-conformance line-by-line, resource/durability/failure-path, test-infrastructure-honesty). | Append-only edit; questions 1–15 unchanged. |
| M9 | `Taskcard-G2` ("independent review... a separate invocation") must be operationalized, not just cited — this engagement's implementer is the same session for every fix in Phase 1. | Every functional taskcard's completion step spawns a genuinely separate Agent for review, fed only the diff and the (now 19-question) checklist. |
| M10 | A session must not end with "let me know if you'd like me to continue" when nothing external actually blocks further work. | This plan specifies all 5 phases as concrete taskcards up front; execution proceeds through them without soliciting interim permission, stopping only at named gates (`LIBIPYNB-Q54`'s `Mission-G9` publication authorization, and any `BLOCKED_EXTERNAL`/`DEFERRED_WITH_AUTHORITY` item). |

## Diagnosis — why this engagement is a forensic pass, not point-fixes

This repo's own process previously produced **"ACCEPTED_VERIFIED, CLEAN, zero confirmed
defects"** (`plans/final-report-2026-08-18.md`, commit `62bef51`) one day before two of this
round's confirmed defects were written into freshly-hardened code (`1c419e7`, `de9e191`,
2026-08-19). Direct evidence: `test_output_beyond_max_output_bytes_is_truncated_and_reported`
(execute.py) asserted `report.results == ()` as *correct* — codifying `LIBIPYNB-Q16`'s bug.
`test_max_output_bytes_truncates_only_the_oversized_output_not_downstream_cells`
(jupyter_execute.py) named the exact cross-engine regression class it was guarding against, and
still used only one oversized output — missing `LIBIPYNB-Q17`'s `any()` short-circuit on a second
one. Two independently-written adapters, two purpose-built regression tests, both shaped to miss
a ≥2-item interaction: a systematic test-authoring habit (build the simplest input that triggers
truncation, never the smallest input that could break aggregation across items), not two
coincidences — and one branch coverage (enforced at 85%) cannot see, since `any(gen)` and a full
loop are branch-identical when the generator only yields once.

**Preserve:** the layered test taxonomy and "obligation"-test discipline; the core/adapter
boundary enforced by `tests/unit/test_import_boundary.py` via static AST parsing (`LIBIPYNB-Q3`
replicates this pattern for a second known defect class); the gate/taskcard vocabulary (M3/M4
reconcile, not discard, it).

**Honest limits:** mutation testing (`LIBIPYNB-Q31`) is slow, Linux-only, scoped to 4 modules.
GitHub's `schedule:` trigger is more durable than GitLab's out-of-band setting but is known to be
silently disabled after ~60 days of repo inactivity — `LIBIPYNB-Q29`'s staleness check is
best-effort, not a guarantee. A separately-spawned review Agent still shares a model family with
the implementer — reduced variance, not absolute independence. None of this guarantees zero
future escapes, only that the specific classes already proven to exist here (collection/
short-circuit bugs, dormant CI tiers, unfalsifiable "clean" claims) can't recur silently.

## Phase structure

- **Phase 0** (`LIBIPYNB-Q1`, `Q2`, `Q3`, `Q25`) — this file, `plans/state.json`, machinery
  healing, the anti-pattern check, and its own schema-check test.
- **Phase 1** (`LIBIPYNB-Q16`–`Q23`) — the 8 confirmed P0 defects (mission labels P0-A..H), each
  with a failing-test-first repair and a genuinely separate Taskcard-Gate-G2 review.
- **Phase 2** (`LIBIPYNB-Q26`–`Q33`) — GitHub Actions CI/CD (`ci`/`oracle`/`fuzz`/`release`.yml),
  mutation-testing scaffold, packaging metadata, changelog.
- **Phase 3** (`LIBIPYNB-Q34`–`Q38`) — mandatory capability completion: v3 legacy import decision,
  Papermill-style parameters, analytics expansion, PDF/export decision, CLI parity sweep.
- **Phase 4** (`LIBIPYNB-Q39`–`Q45`) — adversarial hardening: property/fuzz expansion,
  cross-platform tests, supply-chain audit, mutation-after-access and leak re-verification.
- **Phase 5** (`LIBIPYNB-Q46`–`Q54`) — clean-room release-candidate verification, final evidence
  report, and the single mandatory human stop (`Mission-G9` publication authorization).

Full taskcard detail (objective, steps, validation commands, rollback, completion criteria) lives
in `plans/state.json` plus this engagement's commit history — not duplicated here.
