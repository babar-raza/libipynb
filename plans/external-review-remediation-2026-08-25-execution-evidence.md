# External publication-readiness review remediation — execution evidence

**Engagement:** autonomous remediation of an external "deep publication-readiness review"
handed to the maintainer on 2026-08-25, run against the plan at
`C:\Users\prora\.claude\plans\plan-based-on-below-witty-aurora.md` (a copy of the plan text
is not duplicated here; this document is the evidence trail for its execution).

**Baseline:** repo root `c:\Users\prora\OneDrive\Documents\GitHub\libipynb`, branch `master`,
starting HEAD `a25db9752f021518e56bdf3a7ac9e25e9e6fdd73` (clean working tree, no
staged/unstaged/untracked changes). Local baseline test run before any change:
`pytest tests/unit tests/integration tests/security tests/property tests/scripts` →
**1275 passed, 11 skipped**.

**Final HEAD:** `10fc896c7b5bc6162c6d8312fe2a3a6fee375ece` (17 commits ahead of baseline, all
local — nothing pushed; `git status --short` clean).

---

## 1. Claim verification (before writing any fix)

Every claim in the external review was independently checked against live repo state before
acting on it — this repo's own `forensic-audit-2026-08-18` history documents a case where a
severe bug survived under a `completed_verified` label specifically because a review step was
self-review, not independent, so the same discipline was applied here from the start.

| Review claim | Verdict | Evidence |
|---|---|---|
| Real GitHub Actions run on `a25db97` is red | **CONFIRMED** | `gh api .../actions/runs/32818539511` — `head_sha` matches, `conclusion: failure`, exactly 3 failing jobs (`coverage`, `macos-latest` test, `ubuntu-latest/3.11` test), `package` skipped |
| `add_cell()`/`edit_cells()` break nbformat 4.0–4.4 | **CONFIRMED**, live-reproduced against all 5 real fixtures | `document.py`/`editor.py` |
| Execution `total_timeout` is soft, can't kill a hung cell | **CONFIRMED**, but already tracked (carried-forward `LIBIPYNB-Q2b`, deferred 2026-08-18) | not a new finding |
| PDF capability probe is a false positive | **STALE** — already fixed | `LIBIPYNB-Q23`/`Q59` |
| `pyproject.toml` leaks an internal GitLab URL | **STALE** — already fixed | `LIBIPYNB-Q32` |
| Release evidence unexercised | Already tracked, untouched by this work | `LIBIPYNB-Q54`, `NOT_STARTED`, unaffected |
| Broad "one-stop IPYNB" capability wishlist | Real gaps, **out of scope** | deliberately deferred per the plan |

Net result: the actual confirmed, net-new work was much smaller than the raw review implied —
4 distinct root causes behind the one red CI run, plus one genuinely new correctness bug.

## 2. Work completed

Registered as taskcards `LIBIPYNB-Q62`–`LIBIPYNB-Q69` in `plans/state.json` (see that file for
full per-taskcard detail: root cause, fix, verification command, Gate G1/G2 evidence,
rollback). Summary:

| Taskcard | What | Status |
|---|---|---|
| Q62 | CI `coverage` job's shallow checkout broke `tests/scripts/test_state_json_schema.py`'s git-history commit check | `IMPLEMENTED_UNVERIFIED` |
| Q63 | macOS `/var` vs `/private/var` symlink mismatch in `execute_notebook`'s `work_dir` | `IMPLEMENTED_UNVERIFIED` |
| Q64 | macOS `RLIMIT_AS`/`preexec_fn` crashed instead of refusing cleanly | `IMPLEMENTED_UNVERIFIED` |
| Q65 | `RecursionError` leaked from a test's own JSON encoding **and** from the library's real `dumps()`/`dump()` write path (found by round-1 Gate G2 review, not the original external review) | `IMPLEMENTED_UNVERIFIED` |
| Q66 | `add_cell()`/`edit_cells()` not version-aware for nbformat 4.0–4.4 (the core correctness bug) | **`VERIFIED`** |
| Q67 | `release.yml`'s `verify` job was a weaker duplicate of `ci.yml`'s gates | **`VERIFIED`** |
| Q68 | Governance: require real CI evidence for future `VERIFIED` status on CI-relevant taskcards (closes the systemic gap that let this exact remediation batch's own motivating discrepancy happen) | **`VERIFIED`** |
| Q69 | Coverage-instrumented CI jobs never provisioned a kernel, silently skipping 67 real-kernel tests (found by round-1 Gate G2 review of Q67, affects `ci.yml` too, not just `release.yml`) | `IMPLEMENTED_UNVERIFIED` |

`LIBIPYNB-Q2b` (carried-forward): no code written. A concrete design (supervising thread,
hard-kill via a helper mirroring `execute.py`'s existing tree-kill logic, proposed strawman
`ExecutionOptions.hard_timeout`/`grace_period` defaults) was produced and recorded as the
resume condition for its still-required Taskcard-Gate-G6 security-design sign-off — that gate
is a hard stop before implementation, by design, not a formality this session could satisfy on
its own authority.

`LIBIPYNB-Q54` (publication authorization): untouched, `NOT_STARTED`, as before.

## 3. Independent review — two full rounds

Every taskcard received a Gate G2 review from a **separate agent invocation** (not
self-review), using this repo's own `.supervisor/prompts/adversarial-review.md` template.
Round 1 covered Q62–Q68 (6 reviews); it found 2 CRITICAL findings (Q65, Q66) and one taskcard
(Q67) with 2 CRITICAL findings of its own, all independently reproduced by the reviewing agent
before being accepted — not taken on the implementer's word:

- **Q65 CRITICAL** (round 1): the library's own `dumps()`/`dump()`/`roundtrip()` write path
  shared the identical uncaught-`RecursionError` vulnerability the original fix only closed for
  a test's fixture construction. Repaired: `writer.py`'s `dumps()` now catches `RecursionError`
  and converts it to `NotebookWriteError`.
- **Q66 CRITICAL** (round 1): ephemeral cell-ids for pre-4.5 documents were recomputed fresh
  (by re-hashing content) on every separate `CellEditor` call — for content-duplicate cells, an
  id captured from one call could silently resolve to a *different* physical cell after a
  reordering operation, with no error. Reproduced live via a minimal move-based scenario.
  Repaired: ephemeral ids are now computed once per `CellEditor` instance and carried forward
  as stable state (`self._shadow`), updated only after a successful, non-dry-run commit.
- **Q67 CRITICAL ×2** (round 1): (a) the new coverage-instrumented `verify` step never
  provisioned a kernel, silently skipping 67 real-kernel tests (also found to affect `ci.yml`'s
  own pre-existing `coverage` job — tracked as new taskcard Q69); (b) Q67's own
  `resume_condition` claimed an exemption from Q68's rule that wasn't actually written into the
  rule itself (a Gate G9 plan/reality drift) — resolved by adding an explicit, precisely-scoped
  carve-out to Q68's governing note for tag-only-triggered workflows.

Round 2 re-reviewed every taskcard with a repaired CRITICAL (Q65, Q66, Q67) plus a first review
of the newly-discovered Q69 — 4 more independent reviews. All 3 round-1 CRITICALs were
**confirmed genuinely repaired** by reproducing both the original failure (against real
pre-repair code, via git worktree checkouts in one case) and the fix. Round 2 found one further
WARNING-level instance of the same ephemeral-id-leak class in Q66 (`CellEditBatch`'s individual
methods returned their own un-stripped `CellEdit` directly, bypassing the stripping already
applied to `.changes`) — repaired immediately, with a new regression test, and verified clean
in the same pass.

Total: **12 independent Gate G2 review invocations**, 3 CRITICAL findings found and repaired
(all confirmed closed), roughly a dozen WARNING/INFO findings found and either repaired or
explicitly, non-silently left as documented non-blocking items.

## 4. Whole-session independent verification

A 13th, final review pass — explicitly scoped as a whole-session audit, not another
per-taskcard re-review — checked for gaps a taskcard-scoped review structurally can't see:
plan-vs-reality drift, cross-file consistency, git hygiene, and whether every WARNING/INFO
finding across all 12 prior reviews was genuinely closed or honestly left open (none were
silently dropped). It found and this session repaired 2 more real, narrow gaps:

1. `LIBIPYNB-Q68`'s own scope required mirroring its CI-evidence rule into
   `.supervisor/prompts/prompt4-close-task.md`'s closeout checklist — never actually done.
2. The mechanical hot-module mutation-baseline check
   (`tests/scripts/test_state_json_schema.py::test_verified_hot_module_tasks_have_a_mutation_
   baseline_or_a_documented_exception`) has a hard-coded task-id allowlist that was never
   extended as this batch's taskcards landed — so it silently stopped applying to `LIBIPYNB-Q66`
   (now `VERIFIED`), which added new logic to `codec/reader.py`, one of the 4 designated hot
   modules, with no documented mutation-baseline exception. Fixed: allowlist extended, missing
   `partial_evidence_note` fields added to Q63 and Q66 (Q64/Q65 already had one).

## 5. Verification evidence (independently reproduced, not self-reported)

- Full local suite (`tests/unit tests/integration tests/security tests/property tests/scripts`):
  **1324 passed, 12 skipped, 0 failed** (final run, this session).
- `pytest tests/ --cov=libipynb --cov-report=term-missing` (the exact command `ci.yml`'s
  `coverage` job and `release.yml`'s `verify` job both run): **1425–1435 passed** across
  several runs at different points in the batch, **90.4–90.5% coverage** against the 85% gate
  — always comfortably clear; the small pass-count drift between runs is fully explained by
  intervening commits adding new tests, confirmed by a reviewing agent, not flakiness.
- `mypy --strict src/libipynb/`: clean (46 source files) at every checkpoint.
- `ruff check src/ tests/` / `ruff format --check src/ tests/`: clean at every checkpoint.
- `pytest tests/scripts/test_state_json_schema.py`: 10/10 passed, including after every
  `plans/state.json` edit in this session.
- `tests/integration/test_obligation_jupyter_execution_adapter.py` (the 67 real-kernel tests
  Q69 concerns): 67 passed, 0 skipped, confirmed genuinely executing (not module-skipping) in
  this session's own environment.
- YAML validity of both edited workflow files confirmed via `yaml.safe_load`; `actionlint`
  (where available to a reviewing agent) reported zero findings.
- `pip-audit --progress-spinner=off` (after `pip install --upgrade pip`, matching the
  already-documented `LIBIPYNB-Q42` fix): clean, no known vulnerabilities.

## 6. Commits (chronological, all local, nothing pushed)

```
8ec2668 fix(ci): give the coverage job full git history (LIBIPYNB-Q62)
cd7a74e fix(execute): fix macOS temp-dir path mismatch and memory-limit crash (LIBIPYNB-Q63, LIBIPYNB-Q64)
d2c936f fix(test): stop RecursionError leaking from a test's own JSON encoding (LIBIPYNB-Q65)
ca9c894 fix(model): make add_cell()/edit_cells() version-aware for nbformat 4.0-4.4 (LIBIPYNB-Q66)
22af728 fix(ci): give release.yml's verify job the same gates ci.yml enforces (LIBIPYNB-Q67)
da5f3e6 chore(plan): register LIBIPYNB-Q62 through Q68, resume Q2b context (external review remediation)
32100c8 chore(plan): populate LIBIPYNB-Q68's repair_commit now that it exists
e1b70ef docs(changelog): record Q63/Q64/Q66 as user-visible fixes
fc10946 fix(writer): catch RecursionError from json.dumps() (LIBIPYNB-Q65 Gate-G2 repair, CRITICAL)
e4b5147 fix(editor): make ephemeral cell-ids stable across a CellEditor's own call sequence (LIBIPYNB-Q66 Gate-G2 repair, CRITICAL)
541bcab docs+test: fix stale max_memory_bytes platform claims, add coverage for the new macOS/symlink paths (LIBIPYNB-Q63/Q64 Gate-G2 repair, WARNING)
86ea5b8 fix(ci): provision a kernelspec in coverage-instrumented jobs, not just the test matrix (LIBIPYNB-Q69, Q67 Gate-G2 finding, CRITICAL)
761a733 chore(plan): record round-1 Gate G2 results for Q62-Q68, register Q69, mark Q68 VERIFIED
66443f0 fix(editor): strip ephemeral ids from CellEditBatch's own per-call return values (LIBIPYNB-Q66 Gate-G2 round-2 finding, WARNING)
cafc9e0 chore(plan): record round-2 Gate G2 results, mark Q66/Q67 VERIFIED (51/57)
10fc896 fix(governance): close 2 gaps found by whole-session independent verification
```

## 7. Remaining external blockers (not oversights — exact resume conditions recorded)

1. **Push authorization** (`LIBIPYNB-Q62`, `Q63`, `Q64`, `Q65`, `Q69`): all fully implemented,
   locally verified, and independently reviewed clean (0 CRITICAL each). Their specific bugs
   are platform/CI-specific (macOS runners, Python 3.11, GitHub's shallow-clone behavior) and
   cannot be confirmed from this local Windows environment. Resume condition: maintainer grants
   explicit push authorization for this specific push (the scope approval that authorized this
   work is not, per this repo's own standing convention, the same as push authorization); push;
   confirm each fix on the resulting real Actions run; cite that run's URL per `LIBIPYNB-Q68`;
   mark `VERIFIED`.
2. **Gate G6 security-design sign-off** (`LIBIPYNB-Q2b`): a concrete design and proposed
   strawman defaults now exist (see `plans/state.json`'s carried-forward entry), but this is a
   security-sensitive widening of the execution engine's control surface — implementation does
   not begin without a dated maintainer sign-off, by design, not a formality.
3. **Publication authorization** (`LIBIPYNB-Q54`): unaffected by this work, `NOT_STARTED`,
   as before — requires explicit, dated maintainer authorization before any tag/push/publish.

No further session-side action is possible or appropriate on any of these three without that
external authority being granted.
