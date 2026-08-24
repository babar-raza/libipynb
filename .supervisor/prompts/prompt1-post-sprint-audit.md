# POST-SESSION STRICT EVIDENCE AUDIT
# Three-Level Issue Discovery, Root-Cause Review, and Next-Stage Recommendation
# Governing vocabulary: plans/remediation-plan.md §7 (Gate Contract), §8 (Evidence Contract)

---

## Mode

Audit mode.
- Do not execute new implementation work.
- Do not modify source files unless recording evidence for this audit requires it.
- Do not exaggerate progress.
- Do not describe intent as achievement.
- Do not treat claims as facts.
- Do not accept summaries without evidence.
- Do not skip integration and system-connect-point review.

## Mission

Provide an evidence-based summary of what was actually achieved recently, then perform a strict manual and evidence-backed review of:
- what was completed
- what was partial
- what was unresolved
- what was not verified
- what was not proven
- what was integrated
- what was supposed to be integrated but was not
- what system weaknesses allowed gaps to happen

## Required Input Discovery

There is no separate evidence-bundle machinery in this repo. Discover the actual state directly:
- `git status --short` (lists both tracked changes and untracked files) and `git diff`
  (shows tracked-file changes only — it is silent on untracked files' content, so read
  any untracked file directly instead of assuming `git diff` covers it)
- the governing plan file for the taskcard(s) in scope: `plans/remediation-plan.md` (Tier B/M/V work) or `plans/full-parity-plan.md` (Tier P work)
- any existing `plans/*-execution-evidence.md` bundle relevant to this work
- this session's own prior command output (test/lint/type-check runs it actually performed)
- the affected source/test files directly, not a description of them

If a taskcard's own claimed evidence (a prior session's chat summary, a stale plan entry) cannot be independently reproduced from the above:
- classify the dependent claim as `claimed_unproven` (remediation-plan.md §8) or `not_attempted` — never as `completed_verified` on that basis alone
- recommend PSL-PROMPT-2 if the taskcard's own scope/dependencies/gates need to change
- recommend PSL-PROMPT-3 only if the remaining gap is closable by re-running verification, not by new design work

---

## Section A: What We Achieved

List concrete outputs, changes, validations, and decisions completed recently.

For each achievement, state:
- what changed
- where it changed
- whether fully done or partially done
- what evidence supports it
- whether behavior was verified
- whether it is integrated
- whether it is production-ready
- whether any caveats remain

Do not mix: code existence, behavior proof, integration proof, production readiness.

## Section B: What This Proves

Classify the level of proof for each conclusion:
- `implementation_only`
- `partial_validation`
- `focused_validation`
- `integration_validation`
- `end_to_end_proof`
- `no_proof_yet`

Identify: evidence-supported conclusions, unproven conclusions, carried assumptions, narrow proof, synthetic-only proof, missing raw logs, missing consumer/integration validation.

## Section C: Effect on Final Outcome

State whether the work:
- reduced risk
- improved confidence
- uncovered deeper issues
- changed the execution path
- moved materially closer to the taskcard's acceptance criteria
- exposed blockers
- revealed weak system machinery
- requires plan hardening (PSL-PROMPT-2)
- requires re-execution (PSL-PROMPT-3)

State: what still blocks closure, what remains unproven, what must happen next.

---

## Structured Issue Level L1: Execution Issues

Issues in the work's own execution:
- missed task, partially completed task, incorrectly completed task
- unverified work, unproven claim, missing raw log
- missing test output, weak test, synthetic-only test
- stale artifact, misleading final summary, taskcard not closed
- taskcard closed without evidence, changed file not listed
- generated output not inspected, commit/staging state unclear
- end-to-end claim without evidence

## Structured Issue Level L2: Integration and Connect-Point Issues

Where the work was supposed to connect into the rest of the repo:
- implementation not consumed (e.g. a new function with no CLI path — the exact gap `LIBIPYNB-V6`/`P3b`/`P4c` closed for `merge`/`execute`)
- README/CHANGELOG not synchronized with the actual CLI or API (the exact gap `LIBIPYNB-B2`/`P1`/`P6` closed)
- `plans/*.md` not updated to reflect a taskcard's real status (the exact drift Gate G9 in `plans/full-parity-plan.md` §4.1 exists to catch)
- a new dependency added outside its extras group, or without an import-boundary check (Gate G7)
- a new capability with no test at the layer it should be tested at (unit / integration / property / security / interoperability / oracle — see `.supervisor/README.md` §4)

## Structured Issue Level L3: System Weakness Issues

Deeper weaknesses that allowed the gap to happen:
- self-authored evidence was treated as proof (Anti-Overclaim Rule AO-1)
- "tests pass" was treated as "independently verified" (AO-2)
- a new validation rule was checked only against its own new tests, not the full fixture corpus (AO-3, Gate G5)
- historical/donor evidence was cited as current (AO-4, Gate G4)
- a check that doesn't raise was treated as a check that validates (AO-5)
- a push/tag/publish claim was asserted without git evidence (AO-6)
- coverage percentage alone was cited as test strength (AO-7)
- a parity claim was made without an executed oracle-comparison test (AO-8, Gate G8, `plans/full-parity-plan.md` §4.3 — only relevant to Tier P work)

---

## Issue Record Format

State each issue as:
- `issue_id`, `issue_level` (L1_EXECUTION, L2_INTEGRATION, L3_SYSTEM_WEAKNESS)
- `title`, `description`
- `evidence`, `missing_evidence`
- `root_cause`, `why_not_only_symptom`
- `affected_files`, `affected_components`
- `severity` (CRITICAL, HIGH, MEDIUM, LOW)
- `blocker` (boolean — if true, name the specific Gate)
- `recommended_next_stage` (PSL-PROMPT-2 / PSL-PROMPT-3 / PSL-PROMPT-4 / stop-and-record-in-plan)

---

## Status Assignment

For every claim or taskcard touched, assign exactly one of `plans/remediation-plan.md` §8's controlled status values — no other status string is valid in this repo's plans:

`not_attempted` · `claimed_unproven` · `partially_done` · `completed_but_weakly_verified` · `completed_verified` · `blocker` · `follow_up`

Cite the specific Gate(s) (§7 of `remediation-plan.md`, or §4.1 of `full-parity-plan.md` for Tier P work) that are satisfied or missing for that status. `completed_verified` requires both a Gate G1 (regression) citation and a Gate G2 (independent review, a separate invocation) citation — never assign it on the strength of this session's own say-so alone.

---

## Required Outputs

- In-place edits to the governing `plans/*.md` file's Taskcard Register / Unresolved Work Register / Verification Matrix, reflecting the status assignments above.
- For a large or multi-defect session, a new dated `plans/<topic>-execution-evidence.md` bundle, following the existing pattern of `plans/phase2-execution-evidence.md` / `plans/phase2b-execution-evidence.md` / `plans/full-parity-execution-evidence.md`.
- This session's own chat response, structured per Sections A/B/C above plus the Issue Record list — not prose-only.
