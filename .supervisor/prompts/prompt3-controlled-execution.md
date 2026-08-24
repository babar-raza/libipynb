# EXECUTION MODE: CONTROLLED TASKCARD EXECUTION
# Applies plans/remediation-plan.md §10's Repair Loop, gated by §7's Gate Contract

---

## Operating Principles

- Act on the maintainer's behalf where `plans/*.md`'s own governance allows it.
- Do not bypass tests, lint, type checks, or the Gate Contract.
- Do not use destructive git operations (reset --hard, clean -f, force-push, branch -D).
- Do not mutate files outside the taskcard's own `Allowed actions`.
- Do not trust prior summaries — verify source files and command output directly.
- Prefer durable fixes over one-off local patches; preserve what already works.
- Do not accept a prose-only final summary.

---

## Phase 0: Preflight Safety and State Capture

1. Record: repo path, branch, HEAD commit, `git status --short`, staged files, untracked files, the governing plan file (`plans/remediation-plan.md` for Tier B/M/V, `plans/full-parity-plan.md` for Tier P), the specific taskcard(s) in scope.
2. Classify every dirty/untracked file as: owned_by_this_session, unrelated_prior_work, stale_generated, unsafe_unknown.
3. If unrelated or unsafe changes exist, do not overwrite them — isolate this session's own edits from them.

## Phase 1: Readiness Gate

A taskcard is NOT ready for execution if any of these are true:
- its objective is vague or conflicts with `plans/*.md`'s own scope for it
- its `Dependencies` are not satisfied (check their status in the Taskcard Register)
- it is `blocker` on Gate G3 or G6 and no dated authorization is recorded (§13 of `remediation-plan.md`, §7 of `full-parity-plan.md`)
- its acceptance criteria or required evidence fields are missing or too vague to check

If not ready: run PSL-PROMPT-2 (plan hardening) first — do not execute. If it's blocked on G3/G6 specifically, stop entirely; hardening cannot unblock an authority gate.

If ready: proceed.

## Phase 2: Controlled Execution — the Repair Loop

Apply `plans/remediation-plan.md` §10's Repair Loop verbatim, per taskcard:

1. Implement the change, staying within the taskcard's `Allowed actions`.
2. Run the **full** validated command set below — not just new tests written for this change.
3. If anything fails: identify the first failing boundary and the **root cause**, not the symptom (the worked example is `LIBIPYNB-M1`'s two real defects, `phase2-execution-evidence.md` §4a/§4b — a scope error and a lenient-decode bug, neither of which would have been caught by patching the failing test).
4. Re-implement to fix the root cause. Add a regression test that encodes the specific failure mode.
5. Return to step 2. Repeat until the full validated command set is clean.
6. Only once step 5 is clean, run Gate G2 (independent verification) using `adversarial-review.md` — **a separate invocation** that did not implement the change, re-running the checks itself and specifically hunting for missed call sites, corpus-wide regressions, and doc/code inconsistencies.
7. If G2 finds anything (real precedent: it caught a fail-open git clean filter on `LIBIPYNB-P2`, a redaction leak on `LIBIPYNB-V1`, a misleading CLI example on `LIBIPYNB-B2` — see the relevant `plans/*-execution-evidence.md`), fix it and return to step 2.
8. Only after a clean step 5 **and** a clean step 6/7 may the taskcard be marked `completed_verified`.

**Do not skip step 6.** Some defects are only caught by the implementer's own loop (steps 2–5); others are only caught by an independent pass (step 6/7) — this repo's own history has real examples of both, and neither gate alone is sufficient.

### Validated command set

```
ruff format --check src/ tests/
ruff check src/ tests/
mypy --strict src/libipynb/
pytest tests/unit/ tests/integration/ tests/security/ -v --tb=short
pytest tests/property/ -v --tb=short
pytest tests/interoperability/ -v --tb=short   # needs: pip install -e ".[test,reference]"
pytest tests/oracle/ -v --tb=short              # importorskip-gated; needs .[oracle] extras, skips cleanly if absent
```

These are the exact commands `.gitlab-ci.yml` gates on — use them as written, not a paraphrase. (`CONTRIBUTING.md`'s dev-shorthand commands are looser — e.g. mypy without `--strict` — and should not be substituted; if the two ever disagree, `.gitlab-ci.yml` wins.)

## Phase 3: Which Gates Apply

G1 (regression) and G2 (independent review) apply to every code-changing taskcard, always. Beyond that, apply only what the change actually touches:

| If the taskcard touches... | Also satisfy |
|---|---|
| validation/parsing/serialization logic | Gate G5 — check the **full** fixture corpus under `tests/fixtures/**`, not just the fixtures the new tests happen to exercise |
| the execution adapter's trust surface (`adapters/execute.py`) | Gate G6 — requires a dated maintainer sign-off **before implementation starts**, not just before shipping (`plans/full-parity-plan.md` §4.1) |
| `pyproject.toml`'s core `dependencies`, or any new extras-group dependency | Gate G7 — extras-only, pinned version, license-compatible, import-boundary check (`tests/unit/test_import_boundary.py`) passing |
| a "matches/parity with `<reference tool>`" claim | Gate G8 — an **executed** oracle-comparison test against the real installed tool, not just a plausible-looking implementation |

## Phase 4: Commit Rules

Commit only if: all applicable gates pass, unrelated files are excluded, evidence exists (diff + command output + Gate G2 citation), the governing `plans/*.md` file is updated in the same session, and the final `git status` is understood before committing.

Commit messages must follow `CONTRIBUTING.md`'s Conventional Commits format.

**Anything in the Release & Publish lane — `git tag`, pushing a tag, publishing to PyPI or any registry — requires a dated authorization already recorded in `plans/remediation-plan.md` §13 (Gate G3). Never perform it otherwise, even if every other gate is clean.**

## Phase 5: Final Self-Review

Produce a structured self-review, not prose-only:
- What was achieved
- What this proves (proof level, per `prompt1-post-sprint-audit.md`'s Section B categories)
- Effect on the taskcard's own acceptance criteria
- Open issues found, with severity
- Proposed status per taskcard, from the real vocabulary, with Gate citations

---

## Session Outcomes

- **All touched taskcards reached `completed_verified`** — proceed to `prompt4-close-task.md`.
- **One or more remain `blocker` on Gate G3 or G6** — stop; record the exact resume condition in the governing plan file's blocker section (§13 of `remediation-plan.md`, §7 of `full-parity-plan.md`); do not attempt to satisfy the gate yourself.
- **The plan itself needs hardening** (scope/dependency/gate mismatch found mid-execution) — hand off to `prompt2-plan-hardening.md`.
- **A true external blocker exists** (missing credential, missing infrastructure) — record it precisely in the governing plan file and stop.

## Required Outputs

- In-place edits to the governing `plans/*.md` file's Taskcard Register and Verification Matrix.
- For a large or multi-defect session, a new dated `plans/<topic>-execution-evidence.md` bundle, following the pattern of the existing evidence bundles.
- This session's own chat response, per Phase 5 above.
