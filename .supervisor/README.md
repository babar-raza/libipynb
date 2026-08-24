# `.supervisor/` — Operating Manual for This Repo

## 1. Mission

libipynb is a single-maintainer (Babar Raza) Python 3.11+ library for reading, writing,
validating, diffing/merging, sanitizing, and converting Jupyter `.ipynb` notebooks. This
directory is the operating manual for a Claude Code session working in this repo — **it is
not a second governance system.** All taskcards, gates, evidence rules, and status
vocabulary already live in `plans/*.md`; `.supervisor/` only describes how a session should
move through that existing system safely.

## 2. Reading order

1. `plans/remediation-plan.md` — the governing plan for 0.1.0 publication-readiness. Read
   §5 (Taskcard Register) to see what's open.
2. `plans/full-parity-plan.md` — only if the work in scope is Tier P (nbformat/nbstripout/
   nbdime/nbconvert/papermill parity). Otherwise skip it.
3. `.supervisor/project-adapter.yaml` — the exact commands and gated actions for this repo.
4. Whichever of `.supervisor/prompts/prompt{1,2,3,4}-*.md` matches the mode you're in
   (audit / plan-harden / execute / close).

## 3. Authoritative sources of truth (pointed at, not restated here)

- `plans/remediation-plan.md`: §6 Lane Ownership, §7 Gate Contract (G1–G5), §8 Evidence
  Contract (the controlled status vocabulary), §10 Repair Loop, §11 Anti-Overclaim Rules
  (AO-1..AO-7), §13 Remaining True Blockers (Gate G3).
- `plans/full-parity-plan.md`: §4 Governance, extending the above with Gates G6–G9 and
  Anti-Overclaim Rules AO-8..AO-10 — relevant only to Tier P (execution-engine/parity) work.
- `CONTRIBUTING.md` and `.gitlab-ci.yml` — exact dev/CI commands. **If they ever disagree,
  `.gitlab-ci.yml` wins** — it's what actually gates a merge. (They currently disagree on one
  point: `CONTRIBUTING.md`'s `mypy src/libipynb` omits `--strict`, which `.gitlab-ci.yml`
  requires. This is a real `CONTRIBUTING.md` documentation gap, not something to silently
  paper over here — flag it to the maintainer if you notice it matters.)
- `SECURITY.md` — the security design principles already in force (resource limits,
  sanitizer modes, execution-adapter isolation posture, path safety).

## 4. Repo layout

```
src/libipynb/           codec, model, validation, security, adapters, analytics, cli
tests/unit/              tests/integration/       tests/security/
tests/property/          tests/interoperability/  tests/oracle/   (importorskip-gated)
plans/*.md               the governing taskcard/gate/evidence system
fuzz/                     atheris targets — Linux-only, manual, not yet wired into CI
```

No `.github/workflows/` exists — CI is `.gitlab-ci.yml` only.

## 5. Roles

- **Implementer** (`prompt3-controlled-execution.md`): implements a taskcard, runs the
  Repair Loop, stays within the taskcard's `Allowed actions`.
- **Independent reviewer** (`adversarial-review.md`, used for Gate G2): **must be a separate
  invocation** from the implementer — this repo's own history has real, evidenced cases of
  independent review catching defects the implementer's own regression loop missed (a
  fail-open git clean filter on `LIBIPYNB-P2`, a secret-redaction leak on `LIBIPYNB-V1`, a
  misleading CLI example on `LIBIPYNB-B2`). Do not skip this by having one session play both
  roles.
- **Coordinator** (whichever session is driving): owns `plans/*.md` edits, `pyproject.toml`,
  `.gitlab-ci.yml`, and final validation — these are shared, cross-cutting files and should
  not be edited piecemeal by multiple concurrent efforts without re-reading first (§7 below).

## 6. Human-approval boundaries

- **Never** `git tag`, push a tag, or publish to PyPI/any registry without a dated
  authorization already recorded in `plans/remediation-plan.md` §13 (Gate G3).
- **Never** start implementation on `LIBIPYNB-P4a-1`/`P4a-2`/`P4b`/`P4c`/`P5a`/`P5b`/`P5c`
  (real kernel-protocol execution, parameter injection) without a dated sign-off recorded in
  `plans/full-parity-plan.md` §7 (Gate G6) — design/planning work is fine, implementation is not.
- Both gates require a **maintainer** (Babar Raza) decision, not a session's own judgment
  that the risk is acceptable.

## 7. Safe concurrency

`plans/remediation-plan.md` and `plans/full-parity-plan.md` are shared files. **Re-read the
target plan file immediately before writing to it, not from an earlier read in the same
session** — a real concurrent-edit collision on section numbering already happened once and
was only caught this way (see `plans/full-parity-plan.md` §14/§15).

## 8. Definition of Done for a session

- All applicable gates (§7/§8 of `remediation-plan.md`, §4.1 of `full-parity-plan.md` for
  Tier P) satisfied for every taskcard touched.
- The governing `plans/*.md` file's own Taskcard Register/Verification Matrix rows amended
  in place to match.
- Changes committed (Conventional Commits format, per `CONTRIBUTING.md`), with the final
  response stating: files changed, commit hash(es), plan file+row updated, closure status.
- No stray uncommitted relevant changes left behind.

## 9. Session Handoff Log

Append-only. One line per session: date, one-sentence summary, plan file(s) touched.

- 2026-08-13: Customized `.supervisor/` from unrelated "Format Factory" boilerplate to
  libipynb's actual governance model (deferring to `plans/*.md`); deleted 6 dead-weight
  files, rewrote 10, added this README and `project-adapter.yaml` — no plan file touched.
- 2026-08-18: A forensic capability/publication-readiness audit
  (`plans/forensic-capability-audit-2026-08-18.md`) was run against
  `plans/libipynb-feature-analysis-and-execution.md`'s 15-capability mission spec, finding ~25
  gaps/defects. `plans/production-hardening-plan.md` (21 taskcards, `LIBIPYNB-Q1`-`Q15b`) closed
  all of them the same day; a second, later close-out session the same day (execution plan:
  `C:\Users\prora\.claude\plans\libipynb-required-capabilities-joyful-wind.md`) finished the five
  cards the first pass correctly left open pending independent review/maintainer decision
  (Q3, Q7, Q8, Q12c, Q12a — all now `completed_verified`), found and fixed two further real gaps
  during its own independent Gate G6 security review (sanitizer token-budget bypass on
  closing-tags/comments; MIME-parameter bypass on markdown/html scanning), and produced the
  mission's previously-missing standing deliverables: `plans/specification-traceability-matrix.md`,
  `plans/gate-status-g1-g7.md`, `ARCHITECTURE.md`, `plans/benchmarks-2026-08-18.md`,
  `plans/independence-audit-2026-08-18.md`, `plans/evidence-bundle-2026-08-18.md`. A future session
  bootstrapping from this file should read `plans/production-hardening-plan.md` first (current
  governing status) and `plans/evidence-bundle-2026-08-18.md` for the full artifact index. Three
  items remain deliberately open, none blocked on missing agent capability: Q2's execution-engine
  watchdog redesign (scope deferral), Q13b's CI schedule (needs GitLab project access), and
  real-world notebook corpus sourcing (needs a maintainer provenance/licensing decision, same class
  as Q12a's URL decision).
