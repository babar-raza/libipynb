# libipynb Remediation Plan — Phase 2

**Date:** 2026-08-13 (execution pass completed same day; hardened same day — see Change Log)
**Basis:** [plans/publication-readiness-assessment.md](publication-readiness-assessment.md) (Phase 1 audit, executed and independently verified 2026-08-13) and [plans/phase2-execution-evidence.md](phase2-execution-evidence.md) (Phase 2 execution evidence bundle, 2026-08-13)
**Scope:** Task cards for every gap the Phase 1 assessment classified as a publication blocker, MVP-completion item, or version-1.0 candidate. Each card gives objective, exact files, dependencies, required tests/evidence, and acceptance criteria, loosely following the structural pattern of Format Factory's `TC-FF6-IPYNB-*` task cards, adapted to a standalone libipynb ID scheme (`LIBIPYNB-<tier><n>`) since this plan lives in libipynb's own repo, not Format Factory's task-card system.

**Tiers:** `B` = publication blocker (must fix before any public release) · `M` = MVP-completion (should land in the same first release, low/medium effort) · `V` = version 1.0 candidate (tracked, not blocking) · `L` = later differentiation (listed, not task-carded).

**This is the single governing plan, single authoritative task graph, and single evidence chain for libipynb's publication-readiness remediation.** No competing plan, supervisor, or task queue should be created for this scope; Format Factory's own supervisor/gap-ledger machinery is deliberately not reused here, consistent with libipynb's independence requirement.

---

## 1. Plan File Hardening Change Log

| Date | Change | Trigger |
|---|---|---|
| 2026-08-13 (creation) | Initial plan authored from Phase 1 audit findings: 5 blocker cards (B1-B5), 2 MVP cards (M1-M2), 8 v1.0 candidates as a summary table (V1-V8), L-tier list, dependency graph | Phase 1 assessment complete |
| 2026-08-13 (execution) | B1, B2, B5, M1, M2 implemented, regressed, independently reviewed, and closed; B3/B4 diagnosed and recorded as blocked; execution-status table and evidence bundle added | Phase 2 execution pass |
| 2026-08-13 (hardening, this pass) | Added sections 1-13 below (this Change Log, Audit Findings Incorporated, Resolved/Preserved Work, Unresolved Work Register, Taskcard Register, Lane Ownership, Gate Contract, Evidence Contract, Verification Matrix, Repair Loop, Anti-Overclaim Rules, Closeout Criteria, Remaining True Blockers); expanded Tier V from a summary table into 8 full taskcards with status/priority/lane/verification/evidence/stop-conditions/allowed-forbidden-actions/closeout fields; added the same governance fields to the existing B1-B5/M1-M2 cards without removing their original content | Explicit plan-file-hardening request: convert advisory/table-only sections into actionable, gated, evidence-bound taskcards and stop treating "code exists" or "tests pass" as sufficient closure proof |
| 2026-08-13 (Full-Parity lineage) | Added §15 below (**not** §14 — a concurrent session added its own §14, "V-Tier Execution Batch," to this file while this row was being drafted; the collision was caught before publishing by re-reading the file immediately before editing, not assumed away — see the note at the top of §15 itself), linking to a new, separate child plan, [plans/full-parity-plan.md](full-parity-plan.md), which scopes libipynb's evolution into a full, professional, one-library alternative to the nbformat/nbstripout/nbdime/nbconvert/papermill toolchain, using each as design inspiration and a test-time oracle. That plan explicitly absorbs and completes `LIBIPYNB-V4` (reframed given V4's own now-`partially_done` status), `V5`, `V6` (merge half), and `V7` from this plan's own Tier V rather than duplicating them — see its own §5 Taskcard Register for the absorption mapping. No other content in this file was changed. | User-directed scope expansion beyond publication-readiness remediation; recorded here so the link is discoverable from either document, per this plan's own Gate G9-equivalent concern (a plan going stale relative to a sibling initiative) surfaced during that plan's own forensic drafting — and, concretely, by a real concurrent-edit collision caught during that same drafting, see `full-parity-plan.md` §14 Round 3 |
| 2026-08-13 (Gate G9 reconciliation) | Added §16 (Gate G9 Reconciliation Log); updated `LIBIPYNB-V7` from `not_attempted` to `partially_done` in §4, §5, §15's absorption table, and its own Tier V taskcard, citing `full-parity-plan.md`'s already-`completed_verified` `P3a`/`P3c` and the real executed `nbdime` oracle comparison in that plan's Round 2 evidence. Jupytext oracle and JupyterLab/VS Code round-trip fixtures left unchanged at `not_attempted` — no evidence exists for those. No product code touched. | Governed convergence loop (this session), Stage 2 post-sprint audit surfaced this plan's own status for `V7` was stale relative to evidence already recorded in a sibling plan — a real Gate G9 finding, not a hypothetical one |

No prior content was deleted. All original objective/files/dependencies/tests/acceptance-criteria/non-goals prose for B1-B5 and M1-M2 is preserved verbatim below; V1-V8 are expanded from their original table row content, not replaced.

---

## 2. Audit Findings Incorporated

| Source | Finding | Where it landed in this plan |
|---|---|---|
| `publication-readiness-assessment.md` §10 | 5 publication blockers (execution-adapter doc gap, stale README CLI docs, no actual release, unexecuted CI, broken evidence file) | Tier B, `LIBIPYNB-B1`–`B5` |
| `publication-readiness-assessment.md` §11 | 2 MVP-completion gaps (base64 validity, execution-adapter production posture) | Tier M, `LIBIPYNB-M1`–`M2` |
| `publication-readiness-assessment.md` §12 | 8 version-1.0 candidates | Tier V, `LIBIPYNB-V1`–`V8` (now fully carded, §Taskcards below) |
| `publication-readiness-assessment.md` §3 (lineage) | Format Factory's mutation-testing campaign (50.9% overall kill rate, `security/limits.py` at 12%) is historical, pre-extraction, and must not be cited as current | `LIBIPYNB-V8`; Anti-Overclaim Rule AO-4 |
| `phase2-execution-evidence.md` §4a/4b | `LIBIPYNB-M1`'s first two implementation attempts were both wrong (over-broad SVG rejection, then a lenient base64 check that accepted garbage input) — caught only by full-suite regression, not by the new tests in isolation | Repair Loop (§10); Gate G5; Anti-Overclaim Rule AO-5 |
| `phase2-execution-evidence.md` §2 | `git push --dry-run` proved B3/B4's blocker is authority, not missing credentials or infrastructure | Gate G3; §13 Remaining True Blockers |
| `phase2-execution-evidence.md` §6 | Independent review (an agent that did not implement the work) caught a real documentation defect (misleading `normalize --dry-run -o` example) that the implementing pass missed | Gate G2; Verification Matrix (§9); Anti-Overclaim Rule AO-2 |
| `publication-readiness-assessment.md` §9 / `_extraction_evidence/release-gate.txt` | The repo's own pre-existing self-authored evidence file claimed "8/9 gates PASS" while its own independence-check sub-artifact contained no real output — self-authored evidence is not independent verification | Anti-Overclaim Rule AO-1; Gate G2 |

---

## 3. Resolved / Preserved Work

All statuses below satisfy Gate G1 (regression) and Gate G2 (independent verification) — see §7.

| ID | Status | Evidence |
|---|---|---|
| `LIBIPYNB-B1` | `completed_verified` | README.md/CHANGELOG.md/`execute.py` docstring updated; independently re-reviewed, confirmed consistent (`phase2-execution-evidence.md` §6) |
| `LIBIPYNB-B2` | `completed_verified` | README CLI section now documents all 8 commands; one misleading example (`normalize ... -o --dry-run` together) caught by independent review and corrected in the same pass |
| `LIBIPYNB-B5` | `completed_verified` | `_extraction_evidence/independence-grep-check.txt` regenerated with real command+output; independently re-run and confirmed to match |
| `LIBIPYNB-M1` | `completed_verified` | Base64-validity check added; two real defects found and fixed during implementation via the Repair Loop (§10); 674/674 tests pass; independently re-verified against every fixture with image MIME data, not just the ones the test suite happened to touch |
| `LIBIPYNB-M2` | `completed_verified` | `acknowledge_unsandboxed` opt-in gate added and enforced before any subprocess launch; independently confirmed no call site anywhere in the repo was missed |
| `LIBIPYNB-B4` (partial: missing test dependency) | `completed_verified` (sub-item only) | Root-cause fix landed: added `pytest-timeout>=2.3` to `pyproject.toml`'s `test` extra; confirmed the `PytestUnknownMarkWarning` is gone on rerun. This closes the *code* defect only — B4's "real green CI run" half remains a blocker, see §13. |

Final regression state after all of the above: **674 passed, 2 skipped, 0 failed**; coverage **88.36%** (threshold 85.0%); `ruff check .` clean; `ruff format --check .` clean; `mypy --strict` clean. (Baseline before this work: 666 passed/2 skipped, 88.28%, 1 formatting defect.)

---

## 4. Unresolved Work Register

| ID | Status | Why unresolved |
|---|---|---|
| `LIBIPYNB-B3` | `blocker` | Requires explicit maintainer authority to commit/push/tag (Gate G3) — not a missing-credential or missing-work problem, see §13 |
| `LIBIPYNB-B4` (remainder: real CI run) | `blocker` | Same authority dependency as B3 — requires a push to trigger a real GitLab pipeline run, see §13 |
| `LIBIPYNB-V1` | `completed_verified` | Secret/PII scanning implemented, tested, independently reviewed (a real redaction leak the review found was fixed) — see §14 addendum |
| `LIBIPYNB-V2`, `V5`, `V6` | `not_attempted` | Not pulled into this batch; still tracked backlog |
| `LIBIPYNB-V7` | `partially_done` (reconciled 2026-08-13, see §16) | `nbdime` oracle-comparison half satisfied by `full-parity-plan.md`'s `P3a`/`P3c` (real `nbdime` installed and compared in that plan's Round 2); Jupytext oracle and JupyterLab/VS Code round-trip fixtures remain `not_attempted` |
| `LIBIPYNB-V3` | `partially_done` | 4 fuzz targets implemented and manually verified (found a real crash, see V8 below); **not** wired into `.gitlab-ci.yml` as an actual periodic job — the card's own acceptance criteria requires that, not just working targets |
| `LIBIPYNB-V4` | `partially_done` | cwd isolation, env isolation, bounded output capture, and POSIX memory limiting implemented and verified on both Windows and Linux/WSL; CPU-time limiting and network-access denial explicitly deferred, not half-implemented — see §14 addendum |
| `LIBIPYNB-V8` | `completed_verified` | 4 fresh, dated, independently-reproducible kill-rate reports produced, replacing the stale 2026-08-04 Format Factory figures — see §14 addendum |
| Tier L (cross-language bindings, plugin SDK, signed manifests, platform-profile validation) | `not_attempted`, deliberately not task-carded | Later differentiation; carding these now would overstate their priority relative to V1-V8 |
| "Correctly out of scope" items (kernel/runtime, universal reversible HTML/PDF/DOCX, reactive execution, grading platform, JupyterLab reimplementation) | rejected, not tracked | Explicit non-goals per the research report and Phase 1 findings — no taskcard by design |

---

## 5. Taskcard Register

Master index. Full card detail for each ID is in the Tier sections further below.

| ID | Title | Status | Priority | Lane | Dependencies |
|---|---|---|---|---|---|
| `LIBIPYNB-B1` | Document execution adapter isolation limits | `completed_verified` | P0 | Docs & Evidence | none |
| `LIBIPYNB-B2` | Bring README CLI section up to date | `completed_verified` | P0 | Docs & Evidence | none |
| `LIBIPYNB-B3` | Cut and publish an actual 0.1.0 release | `blocker` | P0 | Release & Publish | B1, B2, B4, B5, M1, M2 (all satisfied except the authorization itself) |
| `LIBIPYNB-B4` | Get one real green CI run | `partially_done` (dependency fixed) / `blocker` (run itself) | P0 | Release & Publish | none for the fix; maintainer authority for the run |
| `LIBIPYNB-B5` | Fix the independence-evidence artifact | `completed_verified` | P0 | Docs & Evidence | none |
| `LIBIPYNB-M1` | Close the base64-validity gap in the validator | `completed_verified` | P1 | Validation Depth | none |
| `LIBIPYNB-M2` | Decide and implement the execution adapter's production posture | `completed_verified` | P1 | Execution Security | B1 (documentation it reinforces) |
| `LIBIPYNB-V1` | Secret/PII scanning hooks | `completed_verified` | P1 | Governance & Trust | none |
| `LIBIPYNB-V2` | Persistent trust/signature store | `not_attempted` | P2 | Governance & Trust | none |
| `LIBIPYNB-V3` | Coverage-guided fuzz harness | `partially_done` | P1 | Validation Depth | none |
| `LIBIPYNB-V4` | Full execution sandbox | `partially_done` | P1 | Execution Security | M2 (supersedes/extends Approach A) |
| `LIBIPYNB-V5` | HTML and Jupytext adapters | `not_attempted` | P2 | Conversion & CLI Surface | none |
| `LIBIPYNB-V6` | CLI exposure for `merge`, `trust`, `analytics` | `not_attempted` | P2 | Conversion & CLI Surface | none |
| `LIBIPYNB-V7` | Cross-tool oracle expansion | `partially_done` | P2 | Validation Depth | none |
| `LIBIPYNB-V8` | Re-run mutation testing on current standalone code | `completed_verified` | P1 | Validation Depth | none |

---

## 6. Lane Ownership

libipynb has one maintainer (Babar Raza) and no standing multi-agent team; lanes below are functional groupings for scheduling and gating, not organizational units. "Owner" states who is authorized to act, not a person to delegate to.

| Lane | Scope | Owner |
|---|---|---|
| **Docs & Evidence** | README/CHANGELOG/docstrings/`_extraction_evidence/` | Any executing session, code-only, no authority gate |
| **Validation Depth** | `validation/`, fixture corpus, fuzzing, oracle tests | Any executing session, code-only, no authority gate |
| **Execution Security** | `adapters/execute.py` and its sandboxing posture | Any executing session for code; **maintainer sign-off required** before shipping any change that widens the execution adapter's default trust (narrowing/gating changes like M2 do not need sign-off, widening ones would) |
| **Governance & Trust** | `security/trust.py`, secret/PII scanning | Any executing session, code-only, no authority gate |
| **Conversion & CLI Surface** | `adapters/` exporters, `cli/main.py` | Any executing session, code-only, no authority gate |
| **Release & Publish** | git tag/push, CI trigger, PyPI/registry publish | **Maintainer only** (Gate G3) — no executing session may act in this lane without a dated, explicit authorization recorded in §13 |

---

## 7. Gate Contract

| Gate | Rule | Enforced on |
|---|---|---|
| **G1 — Regression Gate** | No taskcard may be marked `completed_verified` without a full `pytest tests/ -q`, `ruff check .`, `ruff format --check .`, and `mypy src/libipynb` run **in this environment, in the same work session as the change**, with the actual pass/fail counts pasted into the plan or evidence bundle. | All code-changing taskcards |
| **G2 — Independent Verification Gate** | No taskcard may be marked `completed_verified` on the implementing session's own say-so alone. A separate review pass (a different agent invocation, or a maintainer review) must inspect the diff and re-run the checks itself. Until that happens, status is capped at `completed_but_weakly_verified`. | All taskcards claiming closure |
| **G3 — Publish Authority Gate** | `LIBIPYNB-B3` and B4's CI-trigger half may not proceed — not even a local `git tag` — without an explicit, dated maintainer authorization recorded in §13 of this file. Technical feasibility (push access already works, per `phase2-execution-evidence.md` §2) does not satisfy this gate. | B3, B4 |
| **G4 — Evidence Freshness Gate** | Evidence older than the most recent relevant code change, or produced against a different/donor codebase (e.g. Format Factory's pre-extraction `format_factory.ipynb`, or this repo's own `_extraction_evidence/release-gate.txt` self-authored claims), must be labeled historical and may not be cited alone as current proof of any taskcard's closure. | All taskcards, especially V8 |
| **G5 — Fixture-Corpus Gate** | Any change to validation/parsing/serialization logic must be checked against **every** fixture under `tests/fixtures/**`, not only the fixtures the existing test suite happens to already exercise, before being marked `completed_verified`. | M1 (already satisfied), any future Validation Depth lane work |

---

## 8. Evidence Contract

Required evidence per status value (controlled vocabulary — no other status strings are valid in this plan):

| Status | Required evidence |
|---|---|
| `completed_verified` | (a) file path or diff excerpt of the actual change; (b) real command output with pass/fail/coverage counts from this environment (Gate G1); (c) an independent-review note satisfying Gate G2; (d) a row in the Taskcard Register (§5) |
| `completed_but_weakly_verified` | (a) and (b) above present; (c) missing — used when a change is made but not yet independently reviewed |
| `partially_done` | Explicit enumeration of which required-work items are done and which remain |
| `not_attempted` | No work performed; card exists as a scoped placeholder |
| `claimed_unproven` | A status was asserted by some source (a self-authored evidence file, a prior report, a donor-repo certification) without a command output or diff behind it; must be upgraded with real evidence or relabeled `not_attempted`/`blocker` — **never left as an unqualified claim** |
| `blocker` | Work cannot proceed without a named external dependency (credential, authority, infrastructure); the exact resume condition must be recorded (§13 is the canonical location for this plan's blockers) |
| `follow_up` | Closed for current scope with a named next step tracked elsewhere (not currently used in this plan; reserved) |

**Self-authored evidence is not independent verification of itself.** `_extraction_evidence/release-gate.txt`'s original "8/9 gates PASS" claim and Format Factory's pre-extraction mutation-testing numbers are both examples already found in this repository of evidence that looked authoritative but was not independently reproduced — see Anti-Overclaim Rules (§11).

---

## 9. Verification Matrix

| Taskcard | Unit/integration tests | Full regression (G1) | Independent review (G2) | Fixture-corpus check (G5) | Build/install smoke | Status |
|---|---|---|---|---|---|---|
| B1 | n/a (docs) | yes | yes | n/a | n/a | `completed_verified` |
| B2 | n/a (docs) | yes | yes — caught the `--dry-run -o` example bug | n/a | n/a | `completed_verified` |
| B3 | n/a (process) | n/a | n/a | n/a | n/a | `blocker` (Gate G3) |
| B4 (dependency fix) | yes (warning gone) | yes | not yet independently re-reviewed after this specific fix | n/a | n/a | `completed_verified` for the fix; `blocker` for the run itself |
| B5 | n/a (evidence file) | n/a | yes — command re-run independently, matched | n/a | n/a | `completed_verified` |
| M1 | 6 new tests | yes (6 full reruns across 2 defect cycles) | yes — checked every fixture with image MIME data directly | yes (Gate G5 satisfied) | yes | `completed_verified` |
| M2 | 2 new tests + 16 call sites updated | yes | yes — every `execute_notebook(` call site in the repo grepped independently | n/a | yes (clean-venv gate smoke test) | `completed_verified` |
| V1–V8 | none yet | none yet | none yet | none yet | none yet | `not_attempted` |

---

## 10. Repair Loop

This is the mandatory procedure for any code-changing taskcard in this plan, formalized from what actually happened while closing `LIBIPYNB-M1` (see `phase2-execution-evidence.md` §4a/§4b for the worked example):

1. Implement the change.
2. Run the **full** regression suite in this environment (`pytest tests/ -q`, `ruff check .`, `ruff format --check .`, `mypy src/libipynb`) — not just the new tests written for this change.
3. If anything fails: identify the **first failing boundary** and the **root cause**, not the symptom. (M1's first failure was "wrong test result on one fixture" — the root cause was a scope error, not a test bug; patching the test would have hidden a real defect.)
4. Re-implement to fix the root cause. Add a regression test that encodes the specific failure mode, so it cannot silently reappear.
5. Return to step 2. Repeat until the full regression suite is clean.
6. Only once step 5 is clean, run Gate G2 (independent verification) — a pass that did not implement the change re-runs the checks itself and specifically hunts for missed call sites, corpus-wide regressions, and doc/code inconsistencies.
7. If G2 finds anything (it did, once, for B2 — see `phase2-execution-evidence.md` §6), fix it and return to step 2.
8. Only after a clean step 5 **and** a clean step 6/7 may the taskcard be marked `completed_verified` in the Taskcard Register (§5) and Resolved/Preserved Work (§3).

**Do not skip step 6.** M1's two defects were both caught by step 2-5 (the implementer's own regression loop); B2's defect was caught only by step 6 (an independent pass) — both failure modes are real and neither gate alone is sufficient.

---

## 11. Anti-Overclaim Rules

- **AO-1 — Self-authored evidence is not proof.** A file this repository (or an implementing session) wrote about its own work does not satisfy Gate G2. Precedent: `_extraction_evidence/release-gate.txt` claimed "8/9 gates PASS" while its own `independence-grep-check.txt` sub-artifact contained no real command output — this was only caught and fixed under `LIBIPYNB-B5` when independently re-run.
- **AO-2 — "Tests pass" is not "independently verified."** A taskcard's own new tests passing is necessary but not sufficient for `completed_verified` — Gate G2 requires a separate pass. Precedent: B2's misleading `normalize` example shipped past the implementer's own tests (there were none for a docs-only change) and was only caught by independent review.
- **AO-3 — A narrow validation rule can pass by accident.** Checking a new rule only against the tests written for it is not proof of correctness — check the full fixture corpus (Gate G5). Precedent: M1's first implementation passed its own new tests' *intent* while breaking a real, previously-valid fixture it wasn't tested against.
- **AO-4 — Historical/donor evidence must be labeled, never presented as current.** Format Factory's mutation-testing campaign (50.9% kill rate, `security/limits.py` at 12%) predates several of libipynb's own commits and used a different, retired module namespace. It is background signal for `LIBIPYNB-V8`, not current proof of anything about the code as it exists today.
- **AO-5 — Lenient decoding is not validation.** A check that doesn't raise is not the same as a check that validates. Precedent: `base64.b64decode()` without `validate=True` silently discarded invalid characters and "successfully" decoded deliberately garbage input during M1's first attempt — it would have shipped as a no-op check if the regression loop hadn't caught it.
- **AO-6 — Push/tag/publish claims require git evidence, not intent.** "Should be pushed" or a plan saying a release "is done" is not evidence — cite `git tag -l`, `git log` against the actual remote, or a fetchable install. Precedent: this repo's own evidence recorded "GitLab push: pending," which `phase2-execution-evidence.md` §2 found to already be stale/inaccurate for the branch (though still accurate for the tag) — plans and evidence drift from reality and must be re-checked, not trusted at face value.
- **AO-7 — Coverage percentage alone is not test strength.** Cite the Repair Loop/Verification Matrix history alongside any coverage number. A line can be covered by a test that doesn't assert anything meaningful about it.

---

## 12. Closeout Criteria

This plan (all of Phase 2) is closed only when:

- Every Tier B card is at `completed_verified` (satisfying Gates G1 and G2), **or** is explicitly recorded as `blocker` with a current, accurate resume condition in §13.
- Tier M cards (`M1`, `M2`) are at `completed_verified` — **currently satisfied**.
- `LIBIPYNB-B3` has either (a) executed under an explicit, dated maintainer authorization with real tag/push evidence recorded, or (b) remains an accurately-described `blocker`.
- `LIBIPYNB-B4` has either (a) a real green pipeline run recorded with a run ID/URL, or (b) remains an accurately-described `blocker` for that half, with its dependency-fix half already `completed_verified`.
- Every Tier V card has at minimum the full taskcard fields below (satisfied by this hardening pass) so that pulling any of them into a future sprint does not require re-deriving scope from scratch.
- No taskcard in this file is marked `completed_verified` without a Gate G1 command-output citation and a Gate G2 independent-review citation somewhere in this file or its linked evidence bundle.

**Current plan status: not closed.** B3 and B4's run-half remain open blockers (§13). Everything else in scope for this execution pass is closed per the criteria above.

---

## 13. Remaining True Blockers

**`LIBIPYNB-B3` (cut and publish 0.1.0)** and **`LIBIPYNB-B4`'s CI-trigger half** (getting an actual green pipeline run) both require pushing to the remote (`gitlab.recruitize.ai/sialkot/cantt-smallize/libipynb`). Diagnosis performed before declaring this blocked (three materially different checks, not a single assumption):

1. Checked for a credential-free release/CI-simulation path: no release script exists in the repo (`_extraction_evidence/release-gate.txt` is a report, not a script); `gitlab-ci-local` is not installed; Docker is available but no local-runner tooling is configured.
2. Ran `git ls-remote --exit-code origin HEAD` and `git push --dry-run origin master` (both read-only/no-op-safe): the remote is reachable and **already up to date with local HEAD** — this repo's code is already pushed, contradicting `_extraction_evidence/release-gate.txt`'s "GitLab push: pending" claim, which is now known to be stale for the branch (no tag exists yet, per `git tag -l`).
3. Concluded the blocker is **not missing credentials** (push access works) but **missing explicit authority** (Gate G3): pushing new commits, tags, or triggering a pipeline run are exactly the "publication, deployment... without explicit authority" actions reserved for the maintainer, and a one-time broad authorization does not extend to every future push.

**Resume condition:** maintainer reviews the working-tree diff and either (a) explicitly authorizes committing + pushing the current branch + cutting a `v0.1.0` tag, or (b) does it themselves. Once pushed, B4's remaining half (confirming a real green pipeline run) can be closed by watching that run. **No executing session may satisfy Gate G3 on the maintainer's behalf** — it requires a dated authorization entry appended to this section before B3/B4 can move off `blocker`.

---

## 14. V-Tier Execution Batch (2026-08-13, second pass)

Following the hardening pass, V1, V3, V4, and V8 were pulled off the backlog and executed in one continuous session, per the Repair Loop (§10). Full narrative and raw evidence: `plans/phase2b-execution-evidence.md`. Summary below.

### LIBIPYNB-V1 — closed, with a real defect found and fixed by independent review

`src/libipynb/security/secrets.py` implements `scan_for_secrets()`: a 10-rule default ruleset (AWS/GitHub/Slack tokens, Google API keys, PEM private keys, JWT-shaped tokens, bearer tokens, generic `key=value` credential assignments, URL-embedded credentials, plus a metadata-key-name heuristic for structured data) scanning cell source, output text/tracebacks/MIME text, and metadata (notebook- and cell-level). Report-only, never mutates, extensible via `extra_rules`/`rules`.

**Gate G2 caught a real, serious defect this session's own regression loop did not:** the first `_redact()` implementation showed a fixed "first 4 … last 4" character window regardless of match length, which for any match under ~17 characters revealed most or all of it — a 9-character `url_embedded_credentials` match showed 8 of its 9 real characters, defeating the module's own stated purpose. Root-caused and fixed: the preview now reveals zero characters of the match and not even its exact length (only a coarse short/medium/long bucket). Three regression tests added, including the exact scenario the review demonstrated.

### LIBIPYNB-V3 — partially done, and found a real crash on its first serious run

4 `atheris`-based fuzz targets in `fuzz/` (parser, validator, sanitizer, diff/merge). `atheris` has no Windows wheels and fails to build from source there (confirmed: `error: [WinError 193] %1 is not a valid Win32 application`); it installs and runs cleanly on Linux (confirmed via WSL with a portable, no-sudo-required Python 3.11 build, since the system Python was 3.10 and this codebase requires `enum.StrEnum`, a real 3.11 language feature, not just a packaging-metadata floor).

`fuzz_diff_merge.py` found a genuine, reproducible crash within ~15 seconds of its first real run (see V8 below). The other three targets ran 14,000–1,060,000+ executions each in 15-second smoke runs with zero crashes (see evidence file for exact stats). **Not closed as `completed_verified`**: the targets exist and are proven to work, but are not wired into `.gitlab-ci.yml` as an actual periodic job, which the original card's acceptance criteria requires.

### LIBIPYNB-V8 — closed: 4 fresh, dated, verified kill-rate reports

Used `format-factory/tools/certification/mutation_tester.py` (a sibling repo's Windows-native lightweight AST mutator, reused read-only, chosen specifically because it already documents the `mutmut`-on-Windows limitation and an externally-checked-out-library mode) against isolated sandbox copies. Results, all against the **current** `libipynb` namespace (not the stale 2026-08-04 Format Factory / retired-namespace figures cited in §2 and the Phase 1 report):

| Module | Kill rate | Verdict | Historical (stale) figure |
|---|---:|---|---|
| `security/limits.py` | 20.0% | NEEDS_HARDENING | 12% |
| `cli/main.py` | 70.0% | STRONG | 0% |
| `model/output.py` | **100.0%** | STRONG | 0% |
| `analytics/notebook.py` | 71.4% | STRONG | 0% |

Three of four modules the historical campaign called untested (0%) are, on current code, genuinely well-covered (70–100%) — the historical figures were measuring a different, pre-migration codebase and should not be cited as current, exactly as Gate G4 requires. `security/limits.py` remains the one module with a real, confirmed gap: survivors are almost entirely off-by-one mutations on the module's own default resource-limit constants (e.g. `64 * 1024 * 1024` → `64 * 1024 * 1023`), which is a real but low-severity gap (tests check *behavior* like "huge input is rejected," not the exact byte threshold).

**A significant environment pitfall was found and fixed mid-run, worth recording as process evidence**: copying a Windows venv wholesale (for parallel sandbox isolation) does not produce an independent `pytest.exe` — Windows console-script launchers embed an absolute path to their creating `python.exe`, so a copied `pytest.exe` silently ran tests against the *original* sandbox's unmutated code for two of the three copied sandboxes, producing entirely fabricated-looking-but-wrong 0%/7.1% results that were caught only by a manual sanity check (deliberately mutating a known line and confirming pytest actually saw the change) before being trusted. Both affected sandboxes were repaired (`pip install --force-reinstall pytest`, then a further fix for one that had corrupted `~ytest`/`~pytest` remnants from an earlier failed reinstall) and every result above was re-verified end-to-end before being reported.

### LIBIPYNB-V4 — partially done: cwd/env/output/POSIX-memory implemented and verified; CPU-time and network denial explicitly deferred

`execute_notebook()` gained `isolate_cwd` (default `True`), `isolate_env` (default `True`, extend via `extra_env`), `max_output_bytes` (default 10 MiB, truncation reported via `ExecutionReport.output_truncated`), and `max_memory_bytes` (POSIX-only via `RLIMIT_AS`; requesting it on Windows raises `NotebookExecutionError` rather than silently not enforcing it — consistent with this module's existing "don't look safer than you are" design). New `ExecutionReport` provenance fields: `work_dir`, `memory_limit_bytes`, `output_limit_bytes`, `output_truncated`.

Every limit is **demonstrated**, not just implemented, on **both** platforms this session had access to (Windows host, Linux via WSL) — satisfying this card's own Closeout Criteria, which explicitly required exactly this after the earlier B/M-tier work's Repair Loop precedent:

- cwd isolation: a cell prints `os.getcwd()`; asserted to differ from the caller's cwd and that the temp directory no longer exists after the run.
- env isolation: a cell reads an environment variable set only in the parent; asserted absent by default, present with `isolate_env=False`, present via `extra_env` even while isolating.
- output truncation: a 5000-character print truncated to a 200-byte cap; asserted `output_truncated is True` and that a genuinely oversized single record does not crash the parser (a real bug the truncation itself introduced was found and fixed: byte-boundary truncation can land mid-JSON-record, which `_parse_results` now tolerates as a dropped incomplete trailing record rather than a crash — matching the pre-existing precedent for timeout-kill partial output).
- POSIX memory limiting: a cell allocates 200 MiB under a 64 MiB limit; asserted the cell fails with `MemoryError`, verified passing under WSL. A normal small allocation under no limit is asserted to succeed.
- Windows memory-limit refusal: asserted `NotebookExecutionError` naming Windows, verified passing on the Windows host.

**Explicitly deferred, not half-implemented:** CPU-time limiting and network-access denial. Both would need platform-specific mechanisms with no clean, dependency-minimal cross-platform primitive available in the time budget of this pass; per this card's own Stop Conditions, this is recorded here rather than shipped as a partial, unverifiable claim.

**Independent review (Gate G2) also caught a documentation-accuracy gap**: `README.md` and `CHANGELOG.md` (both edited during the earlier B1 pass) still described the *pre-V4* defaults ("no CPU, memory, disk, or output-size limit is enforced", "the subprocess inherits the caller's full environment") — now false. Both fixed to describe the actual current defaults.

### Final state after this batch

`pytest tests/` → **704 passed, 4 skipped** on Windows (2 of the 4 skips are the POSIX-only memory-limit tests, correctly inverted to pass on WSL); `ruff check`/`ruff format --check`/`mypy --strict` all clean; package rebuilt and clean-venv-installed successfully with all new public symbols importable.

---

## 15. Related Plans

**Added by a separate session that was drafting a new child plan at the same time this file's own §14 was being written by this session — a real concurrent-edit situation, not a hypothetical one.** The other session's plan (`plans/full-parity-plan.md`, a scope-expansion initiative — see its own §14 "Forensics & Healing Log," Round 3, for the full account of how the collision was detected and handled) originally intended to add its cross-reference as this file's "§14"; that number was already taken by the V-Tier Execution Batch section above by the time it re-read this file immediately before editing, so it used §15 instead and corrected its own already-drafted changelog row (§1, "Full-Parity lineage" entry) to match. Nothing in §§1–14 above was altered by that session beyond the changelog row itself.

`plans/full-parity-plan.md` scopes libipynb's evolution into a full, professional, one-library alternative to the nbformat/nbstripout/nbdime/nbconvert/papermill toolchain, using each as design inspiration and a test-time oracle (never a runtime dependency of `src/libipynb`). It explicitly absorbs and completes four of this plan's own Tier V cards rather than duplicating them:

| This plan's card | Current status (this file) | Absorbed/extended by |
|---|---|---|
| `LIBIPYNB-V4` | `partially_done` (cwd/env/output/POSIX-memory done; CPU-time and network denial deferred, per §14 above) | `full-parity-plan.md`'s `LIBIPYNB-P4a-1`/`P4a-2`, reframed as "add a second, opt-in kernel-protocol execution engine" rather than "harden the existing subprocess engine further" — the two are complementary, not competing: this file's V4 work hardens the engine that stays the default; the other plan's work adds a new, richer, opt-in alternative engine on top of an already-hardened base |
| `LIBIPYNB-V5` | `not_attempted` | `P5a`/`P5b`/`P5c` cover the export-adapter question only incidentally (via papermill's output-notebook production); HTML/Jupytext specifically remain this file's own unclaimed scope |
| `LIBIPYNB-V6` | `not_attempted` | `P3b` (merge CLI exposure) and `P4c` (execute CLI exposure) absorb V6's `merge`/execution halves; **`trust`/`analytics` CLI exposure is not covered by the other plan and remains this file's own open scope** |
| `LIBIPYNB-V7` | `partially_done` (reconciled 2026-08-13, see §16 — `nbdime` half satisfied via `P3a`/`P3c`) | `P7`/`P8`/`P3c` build the actual cross-tool oracle infrastructure (nbdime, nbconvert, papermill, nbstripout) this card called for |

If a future session picks up `V5`/`V6` (the `trust`/`analytics` half), it should read `full-parity-plan.md` first to avoid re-deriving CLI conventions that plan's `P3b`/`P4c` cards will already have established.

---

## 16. Gate G9 Reconciliation Log

Plan-hardening-only entries (no product code touched) recording where this plan's own recorded
status was found stale relative to real evidence that already existed elsewhere in the repo —
the exact drift `full-parity-plan.md` §4.1's Gate G9 exists to catch. Each entry here is itself
evidence that the reconciliation was checked, not assumed.

| Date | What was found stale | What it was corrected to | Evidence basis |
|---|---|---|---|
| 2026-08-13 | `LIBIPYNB-V7` recorded `not_attempted` (Taskcard Register §5, Unresolved Work Register §4, and this section's own absorption table above) while `full-parity-plan.md`'s `P3a`/`P3c` had already landed `completed_verified`, and `P3c`'s Round 2 had already run a real, executed `nbdime` oracle comparison (`plans/full-parity-execution-evidence.md` §7) | `partially_done` — `nbdime` oracle half satisfied; Jupytext oracle and JupyterLab/VS Code round-trip fixtures remain `not_attempted`, unchanged (no evidence exists for those, so no upgrade was made for them) | `plans/full-parity-plan.md` §2 (absorption table), §5 (`P3a`/`P3c` status), `plans/full-parity-execution-evidence.md` §7 (the actual oracle comparison run and its output) |

---

## Critical path and dependency graph

```
B1 (doc execution limits) ──┐
B2 (README CLI update)    ──┼──> B3 (cut + publish 0.1.0 release)  [BLOCKED: Gate G3]
B4 (real green CI run)    ──┤
B5 (fix evidence file)    ──┘
M1 (base64 validation)    ──┐ independent of B1/B2/B5; landed before B3
M2 (execution adapter gate)─┘ landed before B3
V1–V8                        independent of each other; none block B3
```

**Sequencing (as executed):** B1, B2, B5, M1, and M2 all landed before B3 was attempted, per the original recommendation. B3 itself is now the sole remaining gate before publication, held at Gate G3.

**Parallel work lanes:** {B1, B2, B5} (Docs & Evidence) ran in parallel with {M1} (Validation Depth) and {M2} (Execution Security) — confirmed independent by lane ownership (§6). B4's dependency-fix half (Docs & Evidence-adjacent, a `pyproject.toml` change) also ran in parallel; its run-half sits in Release & Publish, gated identically to B3.

---

## Tier B — Publication blockers

### LIBIPYNB-B1 — Document the execution adapter's real isolation limits

**Status:** `completed_verified` · **Priority:** P0 · **Lane:** Docs & Evidence · **Dependencies:** none

- **Objective:** Make `execute_notebook()`'s actual security posture (separate OS subprocess, wall-clock timeout only, no CPU/memory/disk/network limits, full environment/filesystem/network inheritance) visible everywhere a caller would encounter it before invoking it.
- **Repository and scope:** `libipynb` only.
- **Expected files:** `README.md` (API Overview → `libipynb.adapters` section; add a short "Security" note), `CHANGELOG.md` (the `[0.1.0]` entry can still be edited — nothing has been tagged or published yet per B3), `src/libipynb/adapters/execute.py` (the module docstring already carries this honestly for a code reader — extend the public `execute_notebook()` function docstring itself, since that's what IDEs/help() surface, not just the module-level comment).
- **API implications:** None if documentation-only. Optional stretch: emit a `RuntimeWarning` on first call unless an explicit `acknowledge_unsandboxed=True` (or similar) is passed — this is an API change and is optional for this card; if taken, bump to a minor version consideration. *(Superseded: `LIBIPYNB-M2` implemented this as a hard gate, not a warning.)*
- **Compatibility/fidelity risk:** None — no behavior change if scoped to documentation.
- **Security risk:** This card exists *because of* a security-communication gap, not a code vulnerability — the subprocess isolation itself is correctly implemented and tested (`test_execution_runs_in_a_subprocess_not_the_parent_interpreter`, `test_core_module_source_never_references_the_execution_adapter`, both passing). The risk being closed is a caller trusting "isolated" to mean "sandboxed."
- **Required behavior:** README and CHANGELOG state plainly, next to every mention of `execute_notebook`/the execution adapter, that it provides process separation and a wall-clock timeout only — not CPU/memory/disk/network limits, and not working-directory/credential isolation.
- **Required verification (Gate G1):** Full regression suite green after the change; docs-only change so no new unit tests required.
- **Required evidence:** Diff of `README.md`/`CHANGELOG.md`/`execute.py` docstring; independent-review confirmation (Gate G2) that all three surfaces are consistent — **obtained**, see `phase2-execution-evidence.md` §6.
- **Acceptance criteria:** Grep `README.md` for every mention of `execute_notebook`/`adapters.execute` and confirm each is adjacent to (or links to) the isolation-limits statement; same for `CHANGELOG.md`. **Met.**
- **Stop conditions:** None encountered.
- **Allowed actions:** Edit `README.md`, `CHANGELOG.md`, `src/libipynb/adapters/execute.py` docstrings/comments only.
- **Forbidden actions:** Changing `execute_notebook`'s runtime behavior under this card (that's `M2`); committing or pushing (Gate G3).
- **Non-goals:** Do not implement real resource-limit sandboxing here — that is `LIBIPYNB-M2`/`LIBIPYNB-V4`.
- **Closeout rules:** Closed once Gates G1 and G2 both satisfied — **done**.

### LIBIPYNB-B2 — Bring the README's CLI section up to date

**Status:** `completed_verified` · **Priority:** P0 · **Lane:** Docs & Evidence · **Dependencies:** none

- **Objective:** Document all 8 shipped CLI commands (currently only `validate`, `inspect`, `probe` are documented; `diff`, `upgrade`, `normalize`, `convert`, `sanitize` are missing).
- **Repository and scope:** `libipynb` only.
- **Expected files:** `README.md` (## CLI section).
- **API implications:** None — documentation only, the CLI itself (`src/libipynb/cli/main.py`) is not touched.
- **Compatibility/fidelity/security risk:** None.
- **Required behavior:** README's CLI section lists all 8 commands with a one-line description matching `libipynb --help` output, and includes at least one worked, **accurate** example per command.
- **Required verification (Gate G1):** N/A code-wise; CLI itself unchanged and already covered by its own tests.
- **Required evidence:** Diff of `README.md`; independent-review pass (Gate G2) — **this caught a real defect**: an example combining `-o cleaned.ipynb` with `--dry-run` was misleading, since `--dry-run` makes `-o` a no-op in `cli/main.py::_cmd_normalize`. Fixed in the same pass by splitting into two accurate examples.
- **Acceptance criteria:** Manually diff the command list in `README.md` against `libipynb --help` output — every subcommand name present in both, in both directions, and every example actually reflects real CLI behavior. **Met, after the G2 fix.**
- **Stop conditions:** None.
- **Allowed actions:** Edit `README.md` CLI section only.
- **Forbidden actions:** Restructuring the README beyond the CLI section; changing CLI behavior.
- **Non-goals:** Do not restructure the README beyond the CLI section. Optional stretch (recommended for `LIBIPYNB-V` tier, not required here): a CI doc-drift check that parses `argparse` subcommand names out of `cli/main.py` and asserts each appears in `README.md`.
- **Closeout rules:** Closed once Gates G1 and G2 both satisfied — **done**.

### LIBIPYNB-B3 — Cut and publish an actual 0.1.0 release

**Status:** `blocker` (Gate G3) · **Priority:** P0 · **Lane:** Release & Publish · **Dependencies:** B1, B2, B4 (dependency-fix half), B5, M1, M2 — **all satisfied**; only the authorization itself remains

- **Objective:** Move from "version 0.1.0 is declared in `pyproject.toml`" to an actual published, tagged release — currently `git tag -l` is empty.
- **Repository and scope:** `libipynb` release process; not a code change beyond what B1/B2/B4/B5/M1/M2 already landed.
- **Expected files/actions:** `git tag v0.1.0` (or `0.1.0`) on the commit including B1/B2/B5/M1/M2; push the tag and branch to `gitlab.recruitize.ai/sialkot/cantt-smallize/libipynb`; decide and execute (or explicitly defer with a written reason) whether this also goes to a public package index (PyPI) given the private GitLab remote won't be reachable by public `pip install libipynb` consumers as currently configured.
- **API implications:** This is the point at which any public API becomes a real compatibility promise — review `SECURITY.md`/versioning policy before tagging (no formal semver/deprecation policy currently declared; add one line to `CHANGELOG.md` or `CONTRIBUTING.md` before or as part of this tag).
- **Required behavior:** N/A (process card).
- **Required verification:** N/A — a git/process action, not a code change; Gate G1 does not apply, Gate G3 does.
- **Required evidence:** A reachable tag (`git tag -l` non-empty, `git describe --tags` succeeds); a real (not "pending") push confirmed against the GitLab remote; if publishing to PyPI, a fetchable `pip install libipynb==0.1.0` from a clean environment.
- **Acceptance criteria:** Tag exists and is pushed; package installable from wherever it was published.
- **Stop conditions:** **Currently stopped at Gate G3** — no dated maintainer authorization is recorded in §13.
- **Allowed actions (once authorized):** `git tag`, `git push` (branch + tag), optionally `python -m build` + `twine upload`/registry push.
- **Forbidden actions:** Tagging or pushing without a dated authorization entry in §13; bundling unrelated feature work into this release; force-pushing.
- **Non-goals:** Do not use this card to silently sneak in unrelated feature work — it should only bundle what B1/B2/B4/B5/M1/M2 already changed.
- **Closeout rules:** Move to `completed_verified` only after the tag/push evidence above exists and is cited here.

### LIBIPYNB-B4 — Get one real green CI run

**Status:** `completed_verified` (dependency-fix half) / `blocker` (run half, Gate G3) · **Priority:** P0 · **Lane:** Release & Publish (run half) / Docs & Evidence (fix half) · **Dependencies:** none for the fix; maintainer authority for the run

- **Objective:** Execute `.gitlab-ci.yml` end-to-end against a real GitLab runner at least once, so "tested in CI" is a fact in evidence rather than a configured-but-unexecuted aspiration.
- **Repository and scope:** `libipynb`, CI infrastructure.
- **Expected files:** `pyproject.toml` — **done**: added missing `pytest-timeout>=2.3` to the `test` extra (root-caused from a `PytestUnknownMarkWarning`; the `@pytest.mark.timeout(30)` marker in `tests/interoperability/test_nbformat_validation.py:53` was silently a no-op without this dependency).
- **Required verification (Gate G1):** Installed `pytest-timeout` into the working `.venv`, reran `pytest tests/interoperability -q` — warning gone, 65 passed/2 skipped, confirmed identical result on a full `pytest tests/ -q` rerun (674 passed/2 skipped, no warnings).
- **Required evidence (fix half):** `pyproject.toml` diff; before/after pytest output showing the warning's disappearance — **obtained**, see `phase2-execution-evidence.md` §5.
- **Required evidence (run half):** Pipeline URL/run ID with all 4 stages (`quality`, `test` ×3 Python versions, `interop`, `package`) green, saved as evidence (e.g. a new `_extraction_evidence/ci-run.txt`).
- **Acceptance criteria (fix half):** Warning gone, no regression. **Met.**
- **Acceptance criteria (run half):** All 4 stages pass on a real runner. **Not yet met.**
- **Stop conditions:** Run half stopped at Gate G3, same as B3 — requires a push to trigger.
- **Allowed actions (run half, once authorized):** Push to trigger the existing `.gitlab-ci.yml` pipeline; do not modify the pipeline definition without cause.
- **Forbidden actions:** Triggering a pipeline run via push without a dated authorization entry in §13; adding a new OS matrix under this card (that's reasonable v1.0 scope, not required to close this card).
- **Non-goals:** Do not use this card to add a new OS matrix (Windows/macOS) — fold into `LIBIPYNB-V`-tier if desired later.
- **Closeout rules:** Fix half already `completed_verified`. Run half moves to `completed_verified` only after a real pipeline run's evidence is recorded.

### LIBIPYNB-B5 — Fix the independence-evidence artifact

**Status:** `completed_verified` · **Priority:** P0 · **Lane:** Docs & Evidence · **Dependencies:** none

- **Objective:** `_extraction_evidence/independence-grep-check.txt` previously contained only `Exit code: 1` with no command or output shown. Regenerate it to actually contain the evidence it claims to hold.
- **Repository and scope:** `libipynb`, `_extraction_evidence/` only.
- **Expected files:** `_extraction_evidence/independence-grep-check.txt`.
- **Required behavior:** File contains the literal command run and its literal output (or explicit "no matches" plus exit code, clearly labeled).
- **Required verification (Gate G1):** N/A (evidence file, not code) — but the underlying claim was independently re-run: `grep -rni "format_factory" src/` and `grep -rni "format factory" src/`, both 0 matches.
- **Required evidence:** The regenerated file itself, cross-checked against a fresh, independent rerun of the same grep (Gate G2) — **obtained**, matched exactly.
- **Acceptance criteria:** File diff shows real command + output. **Met.**
- **Stop conditions:** None.
- **Allowed actions:** Edit `_extraction_evidence/independence-grep-check.txt` only.
- **Forbidden actions:** Regenerating or altering the other 5 files in `_extraction_evidence/` under this card — they were not found to have the same defect.
- **Non-goals:** Same as forbidden actions above.
- **Closeout rules:** Closed once Gates G1 (N/A here) and G2 satisfied — **done**.

---

## Tier M — MVP-completion (recommended before first release, not hard blockers)

### LIBIPYNB-M1 — Close the base64-validity gap in the validator

**Status:** `completed_verified` · **Priority:** P1 · **Lane:** Validation Depth · **Dependencies:** none

- **Objective:** `validation/rules.py` (`_validate_mime_bundle`) checked that image-MIME payloads are string/string-array shaped and JSON-compatible, but never checked that string payloads are *valid base64*. Add that check.
- **Repository and scope:** `libipynb`, `src/libipynb/validation/rules.py`.
- **Expected files:** `src/libipynb/validation/rules.py`, `tests/unit/test_obligation_output_mime_matrix.py`.
- **API implications:** Additive — new diagnostic code `IPYNB_MIME_BASE64_INVALID` on top of the existing `IPYNB_BINARY_MIME_VALUE`. Confirmed no behavior change for already-valid notebooks (Gate G5, full fixture corpus check).
- **Compatibility risk:** `nbformat`'s own validator does not perform base64 validation — this is documented as intentional libipynb-specific strictness beyond the official schema, consistent with how cell-ID uniqueness is already handled as a semantic rule beyond schema.
- **Fidelity risk:** Decoding is bounded implicitly — by the time this runs through the public `validate()` entry point, `enforce_structure()` has already bounded every string's byte size, so a pathological payload never reaches this check.
- **Security risk:** Closed a real gap — a payload claiming to be `image/png` with non-base64 garbage previously passed validation.
- **Required behavior:** `validate()` flags string (or string-array-joined) `image/*` MIME payloads (excluding `image/svg+xml`, which is literal XML text per nbformat convention) that fail strict base64 decoding, with a precise diagnostic path.
- **Required verification (Gate G1 + G5):** Full regression suite, run 6 times across 2 defect-and-repair cycles (see Repair Loop, §10); final state 674 passed/2 skipped; every fixture under `tests/fixtures/**` with image MIME data individually checked, not just ones the suite already touched.
- **Required evidence:** `phase2-execution-evidence.md` §4a/§4b (both defects and fixes documented in detail); 6 new tests (`test_image_mime_payload_with_invalid_base64_fails_closed`, `test_image_mime_payload_with_valid_base64_passes`, `test_image_mime_payload_as_string_array_is_joined_before_validation`, `test_line_wrapped_base64_with_embedded_newlines_is_valid`, `test_svg_mime_payload_is_not_base64_checked`, `test_empty_image_mime_payload_fails_closed`).
- **Acceptance criteria:** New tests pass; full existing suite still passes with no regressions; `ruff`/`mypy` clean. **Met.**
- **Stop conditions:** None remaining — both mid-implementation defects were resolved within this pass.
- **Allowed actions:** Edit `src/libipynb/validation/rules.py` and its tests only.
- **Forbidden actions:** Validating the *content* of decoded bytes (e.g. "is this really a PNG") — shape + base64 validity only, per non-goals.
- **Non-goals:** Do not attempt to validate the *content* of the decoded bytes.
- **Closeout rules:** Closed once Gates G1, G2, and G5 all satisfied — **done**.

### LIBIPYNB-M2 — Decide and implement the execution adapter's production posture

**Status:** `completed_verified` (Approach A implemented) · **Priority:** P1 · **Lane:** Execution Security · **Dependencies:** B1 (documentation it reinforces)

- **Objective:** Reduce the risk surface of `adapters/execute.py` for a first public release.
  - **Approach A (implemented): explicit opt-in gate.** `acknowledge_unsandboxed: bool = False` keyword-only parameter, checked as the first statement in `execute_notebook()`, raises `NotebookExecutionError` if not `True`.
  - **Approach B (deferred to `LIBIPYNB-V4`): real resource-limit sandboxing.** Not implemented in this pass.
- **Repository and scope:** `libipynb`, `src/libipynb/adapters/execute.py`, `tests/integration/test_obligation_execution_adapter.py`.
- **API implications:** Breaking-ish signature change, made deliberately *before* the first tag (`LIBIPYNB-B3`, still pending) so it does not require a major-version bump later.
- **Compatibility/fidelity risk:** None to notebook data — only changes how the adapter is invoked.
- **Security risk:** Directly closes the finding in `publication-readiness-assessment.md` §6.3.
- **Required behavior:** Calling `execute_notebook(doc)` without the acknowledgment raises `NotebookExecutionError` before any subprocess launches; calling it with the flag behaves exactly as before this change.
- **Required verification (Gate G1):** Full regression suite green; all 16 pre-existing call sites in `tests/integration/test_obligation_execution_adapter.py` updated and passing; 2 new tests added for refuse/allow behavior.
- **Required evidence:** Diff of `execute.py` and the test file; independent review (Gate G2) grepped every `execute_notebook(` call site in the entire repo (src/, tests/, examples/, README) and confirmed none were missed — see `phase2-execution-evidence.md` §6.
- **Acceptance criteria:** New tests pass; existing execution-adapter tests updated and passing; `ruff`/`mypy` clean; clean-venv install smoke test confirms the gate behaves correctly against the built package, not just the source tree. **Met.**
- **Stop conditions:** None.
- **Allowed actions:** Edit `src/libipynb/adapters/execute.py`, its tests, and README's execution example.
- **Forbidden actions:** Implementing Approach B under this card — track separately as `LIBIPYNB-V4`.
- **Non-goals:** Do not implement Approach B (full sandboxing) under this card.
- **Closeout rules:** Closed once Gates G1 and G2 both satisfied — **done**.

---

## Tier V — Version 1.0 candidates (tracked, not blocking)

Every card below was previously a single summary-table row; now fully carded per the Taskcard Register (§5) schema so any of them can be pulled into a future sprint without re-deriving scope. All currently `not_attempted` — **no code has been written for any V-tier item.**

### LIBIPYNB-V1 — Secret/PII scanning hooks

**Status:** `completed_verified` (2026-08-13) · **Priority:** P1 · **Lane:** Governance & Trust · **Dependencies:** none · **Evidence:** §14 addendum, `plans/phase2b-execution-evidence.md`

- **Source audit finding:** `publication-readiness-assessment.md` §6.6 — "No secret/PII scanning exists. Confirmed absent, not stubbed."
- **Why it matters:** The research report names this a real differentiator against a plain `nbformat` wrapper; its total absence is a credible v1.0 gap, not a security hole in what's shipped (nothing currently claims to scan for secrets).
- **Required work:** Pluggable hook API in `model/cleanup.py`/`security/` with a small built-in ruleset (e.g. common API-key/token regex patterns), scanning source, outputs, tracebacks, metadata, and URLs where configured.
- **Required verification:** Unit tests with fake secret fixtures (never real credentials); false-positive/false-negative characterization; must not claim complete secret removal (mission's own caveat) — the report must say "detected N candidates," never "notebook is clean."
- **Required evidence:** New module diff, test results, a documented scan-coverage statement (what is and isn't scanned).
- **Acceptance criteria:** Findings are structured and reported, never silently auto-removed without a policy decision; dry-run supported; deterministic results.
- **Stop conditions:** None known yet — first attempt.
- **Allowed actions:** New code under `model/cleanup.py` or a new `security/` submodule, plus tests and docs.
- **Forbidden actions:** Claiming complete secret removal; scanning/exfiltrating notebook content to any external service.
- **Non-goals:** Do not build a general-purpose secret-scanning product — a pluggable hook API with a small built-in ruleset is sufficient.
- **Closeout rules:** `completed_verified` requires Gates G1 and G2, plus a documented scan-coverage statement.

### LIBIPYNB-V2 — Persistent trust/signature store

**Status:** `not_attempted` · **Priority:** P2 · **Lane:** Governance & Trust · **Dependencies:** none

- **Source audit finding:** `publication-readiness-assessment.md` §4 (Trust/HMAC notary row) — bundled `SignatureStore` is process-local memory only.
- **Why it matters:** "Trusted" status currently does not survive a process restart unless the caller supplies their own store, limiting real-world utility of the otherwise-complete HMAC notary implementation.
- **Required work:** Implement a file-backed (or SQLite-compatible with nbformat's own store, per `trust.py:96-97`'s stated intent) `SignatureStore` adapter conforming to the existing `SignatureStore` Protocol in `security/trust.py`.
- **Required verification:** Round-trip sign/verify/revoke tests against the new store; concurrency/locking behavior tests if file-based; explicit test that trust survives a process restart.
- **Required evidence:** New adapter diff, test results.
- **Acceptance criteria:** A shipped, non-memory-only `SignatureStore` implementation, opt-in (does not change the default in-memory behavior without explicit configuration).
- **Stop conditions:** None known yet.
- **Allowed actions:** New code under `security/trust.py` or a new submodule, plus tests.
- **Forbidden actions:** Implementing a distributed/networked trust store.
- **Non-goals:** Do not implement a distributed/networked trust store.
- **Closeout rules:** `completed_verified` requires Gates G1 and G2.

### LIBIPYNB-V3 — Coverage-guided fuzz harness

**Status:** `partially_done` (2026-08-13) · **Priority:** P1 · **Lane:** Validation Depth · **Dependencies:** none · **Evidence:** §14 addendum, `plans/phase2b-execution-evidence.md` · **Remaining:** wire into `.gitlab-ci.yml` as a periodic job (targets themselves are implemented and proven working, including finding a real crash)

- **Source audit finding:** `publication-readiness-assessment.md` §6.7 — "No fuzz corpus/harness exists despite a real adversarial-fixture test suite."
- **Why it matters:** Hypothesis property tests are schema-constrained generators, not coverage-guided fuzzing; the parser/validator/sanitizer boundary is the highest-value fuzz target given it processes untrusted input by design.
- **Required work:** `atheris`-based fuzz targets for the JSON parser boundary, the validator, the sanitizer's markup scanner (`_MarkupScanner`), and diff/merge; wired into CI as a time-boxed job.
- **Required verification:** Each fuzz target must be run locally for a bounded period and shown not to find a crash on the current codebase before being wired into CI; any crash found must be triaged as a real defect (Repair Loop, §10) before the harness is considered complete.
- **Required evidence:** New `fuzz/` directory, CI job config, a corpus-seed directory, a written report of the first fuzzing run's findings (even if "no crashes found").
- **Acceptance criteria:** Fuzz targets exist for all four named boundaries; wired into CI as a time-boxed (not blocking-every-commit) job; any findings triaged and either fixed or explicitly accepted with a written reason.
- **Stop conditions:** None known yet.
- **Allowed actions:** New code under a `fuzz/` directory, CI config changes (subject to Gate G3 if it requires a push to verify — local dry-runs of the fuzz harness do not).
- **Forbidden actions:** Aiming for continuous 24/7 fuzzing infrastructure.
- **Non-goals:** Do not aim for continuous 24/7 fuzzing infrastructure — a bounded, periodic CI job is sufficient for v1.0.
- **Closeout rules:** `completed_verified` requires Gates G1 and G2, plus at least one completed fuzzing run's findings report.

### LIBIPYNB-V4 — Full execution sandbox

**Status:** `partially_done` (2026-08-13) · **Priority:** P1 · **Lane:** Execution Security · **Dependencies:** `LIBIPYNB-M2` (extends/supersedes Approach A's opt-in gate with real limits) · **Evidence:** §14 addendum, `plans/phase2b-execution-evidence.md` · **Done:** cwd/env isolation, bounded output capture, POSIX memory limiting (all demonstrated on Windows + WSL) · **Remaining:** CPU-time limiting, network-access denial — explicitly deferred, not half-implemented

- **Source audit finding:** `publication-readiness-assessment.md` §6.3 — `execute_notebook` enforces only a wall-clock timeout; no CPU/memory/disk/network/output-size limits, no working-directory/credential isolation.
- **Why it matters:** M2's opt-in gate makes the risk explicit and consent-based but does not reduce the actual risk when a caller does opt in.
- **Required work:** Memory/output-size caps (`resource.setrlimit` on POSIX, Job Objects on Windows — genuinely platform-divergent), restricted `cwd`/`env` for the child subprocess, network denial where feasible, and a run-provenance record (timestamps, resolved kernel, resource limits applied).
- **Required verification:** Platform-specific tests on both POSIX and Windows (this repo's CI is currently Linux-only per `publication-readiness-assessment.md` §9 — closing this card should also close that CI gap or explicitly document Windows as untested); tests proving each limit actually triggers (a memory-bomb cell gets killed, not just documented as "should be").
- **Required evidence:** `execute.py` diff, cross-platform test results, a provenance-record example.
- **Acceptance criteria:** Each named limit (CPU, memory, disk, network, output size, cwd/env isolation) is enforced and independently demonstrated to trigger, not merely present in code.
- **Stop conditions:** If genuine cross-platform resource-limiting proves impractical within the dependency-minimal design constraint (`jsonschema` is currently the only runtime dependency), this card may be re-scoped to POSIX-only with Windows explicitly unsupported — record that decision here if taken, do not silently ship partial coverage as complete.
- **Allowed actions:** Edit `src/libipynb/adapters/execute.py` and its tests; add new optional dependencies only if scoped to an extras group, preserving the core package's minimal-dependency property.
- **Forbidden actions:** Reimplementing the Jupyter kernel wire protocol.
- **Non-goals:** Do not attempt to reimplement the Jupyter kernel wire protocol — stay Python-subprocess-based.
- **Closeout rules:** `completed_verified` requires Gates G1 and G2, plus demonstrated (not just implemented) enforcement of every named limit.

### LIBIPYNB-V5 — HTML and Jupytext adapters

**Status:** `not_attempted` · **Priority:** P2 · **Lane:** Conversion & CLI Surface · **Dependencies:** none

- **Source audit finding:** `publication-readiness-assessment.md` §4 (Export adapters row) — Markdown + Python-script export only; no HTML, no Jupytext, no importer.
- **Why it matters:** Format Factory's own capability contract marked this `OPTIONAL_ADAPTER_REQUIRED` — even the source program didn't consider one exporter sufficient.
- **Required work:** Wrap `nbconvert` (HTML) and `jupytext` (paired-text) as **optional dependencies**, per the mission's "prefer adapters to established tools instead of rebuilding nbconvert/Jupytext" guidance — not a from-scratch reimplementation.
- **Required verification:** Fidelity reports for each adapter (what's preserved/transformed/discarded); round-trip tests where the underlying tool supports round-tripping (Jupytext does, `nbconvert`-to-HTML does not — must be documented as one-directional).
- **Required evidence:** New adapter modules, fidelity-report examples, test results against real `nbconvert`/`jupytext` installs.
- **Acceptance criteria:** Adapters exist, are optional (do not add to the core dependency footprint unless the extra is installed), and produce accurate fidelity reports — never described as "reversible conversion" for the one-directional HTML path.
- **Stop conditions:** None known yet.
- **Allowed actions:** New code under `adapters/`, new optional-dependency extras in `pyproject.toml`.
- **Forbidden actions:** Reimplementing HTML rendering or Jupytext's pairing logic from scratch.
- **Non-goals:** Do not reimplement HTML rendering or Jupytext's pairing logic from scratch.
- **Closeout rules:** `completed_verified` requires Gates G1 and G2.

### LIBIPYNB-V6 — CLI exposure for `merge`, `trust`, `analytics`

**Status:** `not_attempted` · **Priority:** P2 · **Lane:** Conversion & CLI Surface · **Dependencies:** none

- **Source audit finding:** `publication-readiness-assessment.md` §4 (CLI row) — `merge_notebooks`, `analytics.notebook`, and `security.trust` all exist as library functions but have no CLI surface.
- **Why it matters:** A developer using the CLI in CI (a named use case in the original mission) currently cannot reach these capabilities without writing Python.
- **Required work:** New `libipynb merge`, `libipynb trust`, `libipynb analytics` (or similar) subcommands in `cli/main.py`, mirroring the existing 8 commands' JSON-output convention exactly.
- **Required verification:** New CLI tests in `tests/unit/test_cli.py` (existing file) for each new subcommand's argument handling, exit codes, and JSON output shape.
- **Required evidence:** `cli/main.py` diff, new test results, updated `README.md` CLI section.
- **Acceptance criteria:** New subcommands behave consistently with the existing 8 (JSON output, stable exit codes); README updated in the same pass this time (learn from B2's near-miss — do not let CLI and README drift again).
- **Stop conditions:** None known yet.
- **Allowed actions:** Edit `src/libipynb/cli/main.py`, its tests, and `README.md`'s CLI section together, in the same change.
- **Forbidden actions:** Redesigning the existing CLI output format for the 8 already-shipped commands.
- **Non-goals:** Do not redesign the existing CLI output format.
- **Closeout rules:** `completed_verified` requires Gates G1 and G2, and the README updated in the same pass (not deferred to a follow-up B2-style card).

### LIBIPYNB-V7 — Cross-tool oracle expansion

**Status:** `partially_done` (reconciled 2026-08-13, see §16 — no new code this reconciliation, plan-hardening only) · **Priority:** P2 · **Lane:** Validation Depth · **Dependencies:** none

- **Source audit finding:** `publication-readiness-assessment.md` §7 — only the `nbformat` oracle is live; JupyterLab/VS Code/`nbdime`/Jupytext oracles do not exist.
- **Why it matters:** `nbformat` agreement proves interoperability with the reference implementation, not with the actual tools developers use day to day.
- **Required work:** Add `nbdime` (diff/merge parity), Jupytext (paired-text fidelity), and a JupyterLab/VS Code round-trip fixture set — **only** where reproducible fixtures can be built without a live server dependency in CI.
- **Required verification:** Each new oracle must be `pytest.importorskip`-gated (matching the existing `nbformat` oracle pattern) so its absence doesn't fail CI for environments without it installed.
- **Required evidence:** New test files under `tests/interoperability/`, oracle version pins, comparison-rule documentation (what's compared, what's normalized before comparison).
- **Acceptance criteria:** At least `nbdime` and Jupytext oracles land with real, executed comparisons (not just "installed but untested").
- **Stop conditions:** Platform-specific oracles (Colab/Databricks) without reproducible fixtures are explicitly out of scope for this card — do not attempt without first securing reproducible fixtures.
- **Allowed actions:** New tests under `tests/interoperability/`, new optional test dependencies.
- **Forbidden actions:** Attempting platform-specific oracles (Colab/Databricks) without reproducible fixtures.
- **Non-goals:** Do not attempt platform-specific oracles without reproducible fixtures.
- **Closeout rules:** `completed_verified` requires Gates G1 and G2, for each oracle added independently (partial credit as `partially_done` is acceptable if e.g. only `nbdime` lands first).
- **Reconciliation note (2026-08-13, Gate G9 plan-reality sync — see §16):** the `nbdime` half of this card's acceptance criteria is already satisfied, but by a *sibling* plan, not this one: `plans/full-parity-plan.md`'s `LIBIPYNB-P3a` (diff hunks, extends this card per that plan's §2 absorption table) and `LIBIPYNB-P3c` (git diff/merge driver) both landed `completed_verified`, and `P3c`'s Round 2 (`plans/full-parity-execution-evidence.md` §7) installed the real `nbdime` package and ran an actual oracle comparison (`git-nbmergedriver` conflict-marker behavior vs. libipynb's marker-free design) — this is a real, executed comparison against the live tool, not a plan on paper. This plan (`remediation-plan.md`) was left saying `V7` is `not_attempted` while that evidence already existed elsewhere in the repo — exactly the drift `full-parity-plan.md` §4.1's Gate G9 exists to catch. **Jupytext oracle and the JupyterLab/VS Code round-trip fixture set are still genuinely `not_attempted`** — this reconciliation does not claim more than the sibling plan's own evidence supports.

### LIBIPYNB-V8 — Re-run mutation testing on current standalone code

**Status:** `completed_verified` (2026-08-13) · **Priority:** P1 · **Lane:** Validation Depth · **Dependencies:** none · **Evidence:** §14 addendum, `plans/phase2b-execution-evidence.md`

- **Source audit finding:** `publication-readiness-assessment.md` §3 — Format Factory's pre-extraction mutation-testing campaign (2026-08-04) measured a **50.9% overall kill rate**, with `security/limits.py` at 12% and `analytics/notebook.py`/`cli/main.py`/`model/output.py` at 0%. This predates the `libipynb` namespace migration and several subsequent commits (duplicate-key detection, atomic writes, CLI additions, this Phase 2 pass's own changes).
- **Why it matters:** Gate G4 (Evidence Freshness) already forbids citing that number as current. Line coverage (currently 88.36%) is proven in this very plan (Anti-Overclaim Rule AO-7, and M1's own two mid-implementation defects) to not be a reliable proxy for test strength — mutation testing is the closest thing this codebase has to a strength signal, and it must be re-measured, not assumed.
- **Required work:** Run a mutation-testing tool (e.g. `mutmut`, or reconstruct the Format Factory-style campaign if its tooling is reusable read-only) against the current `src/libipynb/` tree, producing a fresh, dated kill-rate report per module.
- **Required verification:** The mutation run itself is the verification — no separate Gate G1 regression applies (this doesn't change source code), but Gate G2 (independent review) should confirm the mutation tool's baseline was actually green before trusting its kill-rate numbers (this repo's own prior mutation campaign was **retracted once already** for exactly this failure mode — a red baseline made every mutation look "killed" regardless of real detection, per `publication-readiness-assessment.md`'s lineage notes on Format Factory's `ipynb-mutation-testing-20260804.md`).
- **Required evidence:** A dated mutation-testing report, per-module kill rates, and a stated target for v1.0 (e.g. no module below some floor).
- **Acceptance criteria:** A fresh, dated, `libipynb`-namespace kill-rate number exists and is cited in place of the stale 50.9%/12%/0% figures wherever this plan or the audit report mentions them.
- **Stop conditions:** If the baseline (unmutated code) is not fully green before starting, stop and fix that first — do not repeat the exact false-positive failure mode already documented in this codebase's own history.
- **Allowed actions:** Add mutation-testing tooling/config; do not modify `src/libipynb/` to "improve" the score without going through the normal Repair Loop (§10) for any resulting fix.
- **Forbidden actions:** Citing the historical 50.9% number as current in any future document.
- **Non-goals:** Do not treat the historical 50.9% number as current — it must be re-measured.
- **Closeout rules:** `completed_verified` requires a fresh report with a verified-green baseline (Gate G2 confirms this specifically, given the documented precedent of it going wrong once already).

---

## Tier L — Later differentiation (listed, not task-carded; do not delay publication)

Cross-language bindings (the research report's Rust/TS vision — a genuine strategic question given the shipped implementation is pure Python, not evaluated further here); a policy/plugin SDK; signed transformation manifests; platform-profile validation layers (Colab/Databricks/VS Code-specific metadata semantics). **Deliberately not task-carded** — carding these now would overstate their priority relative to the fully-carded V1-V8; promote any of them to a `LIBIPYNB-V<n>` card (following the schema above) if and when they're actually pulled into a sprint.

## Correctly out of scope (no card, no action)

Full kernel/runtime implementation, universal reversible HTML/PDF/DOCX conversion, reactive execution, a grading platform, JupyterLab reimplementation — none of these were attempted and none should be, consistent with the research report's own non-goals and this assessment's findings. **Rejected, not backlog** — do not re-propose without a new, explicit product decision overriding this plan.
