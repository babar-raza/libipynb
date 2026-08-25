# libipynb Publication-Readiness — Final Evidence Report (2026-08-25)

**Branch:** `fix/publication-readiness` (103 commits ahead of `master`, working tree clean)
**Governing plan:** `plans/publication-readiness-plan-2026-08-24.md`
**Machine-readable task ledger:** `plans/state.json` (schema-validated by `tests/scripts/test_state_json_schema.py`, 10/10 passing)
**Format note:** the original mission brief referenced a "§13 15-point required final-response format." That brief predates this conversation window and was never persisted to any file in this repository — confirmed by `grep -rln "15-point\|15 point" plans/` returning zero matches across every plan document, including the governing plan itself. Rather than fabricate a 15-point structure from memory, this report follows the established format of this repository's own prior close-out report, `plans/final-report-2026-08-18.md`, scaled to this engagement's much larger scope (49 taskcards vs. that session's 5).

---

## 1. What this engagement did

Starting from a repository already carrying a `PUBLISHABLE AFTER BLOCKERS` forensic-audit verdict (`plans/forensic_audit_2026-08-18.md`-equivalent, 4 P0 blockers), this engagement:

1. Reconciled stale `.supervisor/` governance machinery with the actual current plan set (Phase 0).
2. Fixed all 8 confirmed P0 defects from the forensic audit, each via a failing-test-first repair with independent Taskcard-Gate-G2 review (Phase 1: `LIBIPYNB-Q16`–`Q23`).
3. Built out CI/CD foundations — GitHub Actions workflows for quality/test/oracle/fuzz/release, packaging metadata, changelog discipline (Phase 2: `Q26`–`Q33`).
4. Closed mandatory capability gaps — parameter injection, analytics expansion, CLI/API parity sweep, a deliberate decision *not* to build v3→v4 legacy import (Phase 3: `Q34`–`Q38`).
5. Ran adversarial hardening — property-based tests, cross-platform tests, supply-chain audit, and (by far the largest single effort in this engagement) a mutation-after-access audit that grew from "4 findings, all fixed" into 4 independent review rounds finding progressively more instances of the same bug class (Phase 4: `Q39`–`Q45`, `Q55`, `Q56`, `Q61`).
6. Verified the release candidate end-to-end from clean-room installs through real git-driver integration (Phase 5: `Q46`–`Q52`).
7. Produced this report (`Q53`) and now stops at the one mandatory human authorization gate (`Q54`, Mission-G9) before any tag or publish.

**Task ledger status:** 42 of 49 tracked taskcards `VERIFIED`; 7 `NOT_STARTED` with preserved, individually-documented reasoning (§5); 3 carried-forward legacy items correctly remain `NOT_STARTED`/`BLOCKED_EXTERNAL`/`DEFERRED_WITH_AUTHORITY` per prior-session decisions, not silently dropped.

---

## 2. Repair Loop discipline (how every fix in this engagement was verified)

Every functional taskcard followed the same loop, enforced mechanically where possible:

1. Write a failing regression test first; confirm it fails against the unfixed code (a genuine negative control, not assumed).
2. Implement the smallest correct fix.
3. Re-verify: `mypy --strict src/libipynb/`, `ruff format --check src/ tests/`, `ruff check src/ tests/`, and the relevant test suite(s).
4. Spawn a **genuinely separate** Agent (fresh context, no memory of the implementation session's reasoning) for independent review against `.supervisor/prompts/adversarial-review.md`'s 19-question checklist.
5. Repair every finding the reviewer raised; if any finding was CRITICAL or MAJOR, spawn a **second** independent review round before marking `VERIFIED` (this engagement's own stricter-than-default rule — a single clean round suffices only when zero CRITICAL/MAJOR findings exist).
6. Commit the implementation and the `plans/state.json` evidence update as **separate** commits, each citing the other's full (not abbreviated) commit hash.

`tests/scripts/test_state_json_schema.py` mechanically enforces that every `VERIFIED` row cites a `repair_commit` that actually resolves in `git log --all`, and that every `implementer+separate_reviewer`-owned `VERIFIED` row has a non-empty `review_lenses_applied` list — converting this discipline from prose convention into a rerun-proof check.

---

## 3. Major defect classes found and fixed

### 3.1 Phase 1 — the original 8 P0 defects (`Q16`–`Q23`)

| ID | Defect | Fix |
|---|---|---|
| `Q16` | Subprocess execution truncated the combined output stream *before* parsing it into per-cell results — a 374-byte stream with a 100-byte cap returned **zero** parsed results | Parse the full untruncated stream first, apply the byte budget per-cell afterward |
| `Q17` | Kernel-output truncation used `any()`, short-circuiting after the first oversized output — a second oversized output in the same cell was silently left untouched (or corrupted, for base64 binary data) | Explicit loop visiting every output; binary MIME payloads are *removed*, never marker-appended (which would corrupt base64) |
| `Q18` | Strict reader and `validate()` both accepted `NaN`/`Infinity`, non-JSON values that should never round-trip | `parse_constant` raises in strict mode; `validate()` recursively scans for non-finite floats at any depth |
| `Q19` | Atomic write lost file permissions, never called `fsync`, had no defined symlink policy | Preserve mode via `os.chmod`; `flush()`+`fsync()` on the file and its parent directory; symlink-aware atomic replace |
| `Q20` | Full-suite collection failed (`tests/__init__.py` missing while every subpackage had one) | Added the missing empty `__init__.py` |
| `Q21` | Corpus integrity hashes were computed over raw bytes, making them line-ending-dependent across platforms | Hash canonical (normalized) bytes instead; added `.gitattributes` forcing LF for `.ipynb`/fixture paths |
| `Q22` | Oracle CI could not provision its own execution oracle (no `ipykernel` in the relevant extras) | Added `ipykernel` to the `exec` extra; provisioning now baked into the CI job from the start |
| `Q23` | PDF-backend detection was `shutil.which()`-only — a present-but-broken LaTeX install produced a false positive | Real functional probe (compiles a trivial `.tex`, confirms a `.pdf` results), cached per session |

Each landed with a purpose-built regression test proving the specific cardinality/short-circuit failure mode the original bug exhibited, plus at least one independent review round.

### 3.2 The mutation-after-access saga (`Q43`, `Q61`) — this engagement's largest single effort

`Q43`'s stated mission (mirroring the actual mission brief §6B): *"no hidden mutation through supposedly immutable result objects."* A `frozen=True` dataclass in Python blocks *reassigning* a field but does **not** block mutating a `dict`/`list` value already stored in that field — `instance.field["x"] = "evil"` silently succeeds and corrupts every later read of that same object, even though the class is declared frozen. This is the single defect class this engagement spent the most review cycles closing, precisely because each review round's own investigation turned out to be incomplete:

- **Round 1** (implementation `92f8498`): a dedicated investigation swept 62 `@dataclass` definitions and found/fixed 4 instances (`InjectedParameter.value`, `model/metadata.py`'s 6 `_raw` fields, `NotebookDiff._target_snapshot`, `ExecutionOptions.extra_env`), building the shared `_internal/immutable.py` (`deep_freeze`/`deep_thaw`) helper along the way. Independent review found this fix was itself **shallow** in places — `_freeze_raw()` was only single-level `MappingProxyType`, the exact mistake a sibling module's own docstring in the same commit had warned against — plus a sibling class (`MimeRenderingMetadata`) and 3 adapter classes sharing the identical gap, all missed.
- **Round 2** (repair `2de0174`): fixed all of round 1's findings by making every fix genuinely recursive. Independent review confirmed this was correct — but found **5 more** dataclasses sharing the identical gap that neither the original sweep nor round 1's review had named (`FieldChange`/`NotebookFieldChange` in `model/diff.py`, `AttachmentChange`, `CellConflict`, and a second finding on `InjectedParameter.value` itself — round 1 had only closed the live-document-corruption *consequence*, not the field's own mutation-after-access).
- **Round 3** (repair `fffcbd0`): before applying the reviewer's list, an exhaustive `grep -rn "deepcopy(self\."` sweep found **3 more** unreported instances (`Change` in `model/cleanup.py`, `CellQuery`/`CellEdit` in `model/editor.py`) — the same "incomplete sweep" pattern recurring a second time, this time caught by the implementer before the next review round rather than by it. All required downstream fixes (CLI JSON-serialization call sites needing `deep_thaw()` before `json.dumps()`, `merge.py`'s `_apply_field` needing the same) landed in the same commit. Independent review confirmed this repair was correct — but found **2 more** instances that neither of the grep patterns used so far could have caught: `execution/results.py`'s `CellExecutionRecord.outputs` (a class with **no `__post_init__` at all**) and `diagnostics.py`'s `Diagnostic.details` (a field the same commit had explicitly re-examined and left unrepaired on reasoning that covered only internal reachability, not `Diagnostic`'s status as public, exported, documented API).
- **Round 4** (repair `0225424`): fixed both remaining instances; a dedicated audit subagent then swept every remaining `@dataclass(frozen=True)` in `src/libipynb/` and found none further live, with two edge cases explicitly triaged rather than silently dropped (`ExportResult.metadata` — a *different* taskcard's deliberate prior decision, recorded as new backlog item `Q61`; `security/trust.py`'s private `_Value.value` — confirmed to never escape its own non-exported traversal generator, genuinely out of scope). Independent review round 4 **independently re-derived the complete file list from scratch** (not trusting the audit subagent's own list), wrote live scratch tests against real public entry points (a real Jupyter kernel execution, the real `Diagnostic` constructor), and returned a **CLEAN** verdict — the first clean round in this chain.
- **`Q61`** (repair `88143e7`): picked up the triaged `ExportResult.metadata` item as its own taskcard, following the identical Repair Loop. Independent review found the fix correct but flagged (WARNING, non-blocking) that it changes `.metadata`'s runtime type for any external caller doing `json.dumps()` on it directly — addressed with a CHANGELOG entry (`ad7287a`) covering all 13 affected classes, even though not required to reach `VERIFIED`.

**Final count: 13 dataclasses, 15 field instances, across 5 repair commits and 5 independent review rounds** (4 for `Q43` + 1 for `Q61`), closing a defect class the *original* review round's own "4 findings, all fixed" claim had substantially undercounted. This is the concrete, demonstrated value of this engagement's "two consecutive CRITICAL/MAJOR findings require another round" rule — a single review pass would have shipped 8 more live mutation-after-access bugs than it caught.

### 3.3 Other notable fixes

- **`Q35`** (Papermill parameter injection): a Gate-G2 review found and closed 2 undocumented divergences from real Papermill (`comment=""` handling, bare-`tuple` value rejection) beyond the 3 already-documented ones.
- **`Q44`** (execution subprocess timeout): `subprocess.run(timeout=...)` cannot bound wall-clock time when a spawned grandchild holds the stdout/stdin pipe open. Replaced with manual `Popen` + background reader/writer threads + explicit process-tree killing (`os.killpg`/`taskkill /F /T`).
- **`Q55`** (found during `Q18`'s own review): `security/limits.py`'s `enforce_structure()` didn't walk `tuple`-shaped nesting, the same blind spot `Q18` fixed for the finiteness scanner — closed across 3 commits and 2 review rounds after round 1 found a **second** instance of the identical gap for non-`dict` `Mapping` types (`UserDict`, `MappingProxyType`).
- **`Q56`** (found while building `Q26`'s own honest verification): Gate G1 evidence (`mypy --strict`, full test suite) was not reproducible in a genuinely fresh install — fixed alongside `Q26`.

---

## 4. Phase 5 — release-candidate verification (this session, `Q46`–`Q52`)

Built `dist/libipynb-0.1.0-py3-none-any.whl` (196,969 bytes) and `dist/libipynb-0.1.0.tar.gz` (188,897 bytes) from a clean `git status`. All of the following used **real, disposable, session-scratchpad clean-room environments** — never the repository's own dev `.venv`:

| Taskcard | Result |
|---|---|
| `Q46` — wheel install | Fresh venv, wheel-only install resolved exactly the one declared dependency (`jsonschema` + its transitive deps). Imports resolve, `libipynb.exe --help` works, a real `probe`/`validate`/`inspect` workflow against a real fixture succeeds end-to-end. |
| `Q47` — sdist install | Separate fresh venv; pip's own transcript confirms a genuine from-source build (not a cached-wheel shortcut), producing a byte-identical-size wheel to `Q46`'s. Same successful CLI workflow against a different fixture. |
| `Q48` — `twine check` | Both artifacts `PASSED` — the identical validation PyPI itself runs at upload time. |
| `Q49` — `pip-audit` (resolved install) | Audited the *frozen, pinned* dependency set from the clean-room install (distinct from `Q42`'s source-tree range audit) — no known vulnerabilities across all 5 real dependencies. |
| `Q50` — examples vs. installed wheel | Confirmed `libipynb.__file__` resolves to `site-packages`, not `src/`, then ran both `examples/*.py` scripts unmodified — correct output for both. |
| `Q51` — packaged schema + `py.typed` | All 6 vendored nbformat schema files present and functionally load (`validate()` succeeds); `py.typed` proven *functional*, not just present — `mypy --strict` against a trivial consumer script correctly resolves real type stubs from the installed wheel (catches a deliberate type error, passes clean on correct usage). |
| `Q52` — real git integration | Real `git diff`/`git merge`/`git add` in a scratch repo, invoking the installed wheel's driver (confirmed via `git config` referencing that venv's own `python.exe`). Diff driver produces the structured cell-level diff; a genuinely divergent (non-fast-forward — an initial attempt accidentally fast-forwarded and was caught and redone) 3-way merge produces a real `CONFLICT`, keeps the base's value, splices zero conflict markers; the clean filter strips outputs only from what git stages, leaving the working-tree file untouched. |

---

## 5. Known remaining items — honestly disclosed, not silently dropped

| ID | Status | Why it's not done |
|---|---|---|
| `Q40` | `NOT_STARTED` | Fuzz target expansion requires `atheris`, which has no Windows wheels (the same platform constraint the existing `fuzz` extra already documents) — genuinely infeasible in this Windows sandbox, not deprioritized. |
| `Q53` | This report | — |
| `Q54` | `NOT_STARTED` | The mandatory Mission-G9 human authorization gate — see §6. |
| `Q57` | `NOT_STARTED` | 67 real-kernel integration tests are never run with a provisioned kernel in any *real* CI job today (`.github/workflows/ci.yml`'s test matrix installs `.[test]` only, not the `exec` extra + `ipykernel`) — found by `Q22`'s own review, correctly scoped as its own taskcard rather than silently folded into `Q22`. |
| `Q58` | `NOT_STARTED` | `Q31`'s mutation-testing pilot on `codec/writer.py` surfaced a real, measured 75.3% mutation score with 61 survived mutants, including all 21 of `roundtrip()`'s own mutants showing zero test coverage at all — a genuine, quantified gap deliberately left open by `Q31` (whose own scope was the tooling, not exhaustively closing everything it found). |
| `Q59` | `NOT_STARTED` | `NbconvertExporter`'s binary-output path checks only that the output file exists, never that its content is non-empty or format-plausible — found by `Q45`'s review, correctly scoped as requiring new validation logic (an implementation change), not foldable into `Q45`'s test-only diff. |
| `Q60` | `NOT_STARTED` | `validate()` can leak an uncaught `RecursionError` if a caller explicitly sets `max_nesting_depth` above 1000 (above `find_non_finite_floats`'s own hard-coded backstop) — a narrow, only-reachable-via-explicit-override edge case found while verifying `Q55`'s fix, deliberately not folded into that commit. |

**Carried forward from prior sessions** (re-confirmed still correctly deferred, per this session's own memory of that decision — not silently re-opened or dropped):

| ID | Status | Note |
|---|---|---|
| `Q2b` | `NOT_STARTED` | Wedged-kernel hard-kill escalation, a follow-on to an existing observe-only watchdog. |
| `Q13b` (legacy numbering) | `BLOCKED_EXTERNAL` | GitLab CI/CD Schedule activation for fuzz/oracle jobs — requires an out-of-band GitLab setting this session cannot create. |
| `Q13c` (legacy numbering) | `DEFERRED_WITH_AUTHORITY` | Real-world notebook corpus fixture *selection* (the tooling itself already landed) — requires a maintainer content decision, not a technical one. |

None of `Q40`/`Q57`/`Q58`/`Q59`/`Q60` block publication on their own merits — each is a scoped, documented, independently-actionable follow-up, not a defect discovered and then hidden.

---

## 6. Final verification (this session, run live, not carried over from an earlier snapshot)

```
mypy --strict src/libipynb/
  Success: no issues found in 46 source files

ruff format --check src/ tests/
  137 files already formatted

ruff check src/ tests/
  All checks passed!

pytest tests/unit/ tests/integration/ tests/security/ tests/property/ tests/scripts/ -q
  1248 passed, 11 skipped, 0 failed in 462.18s (0:07:42)

pytest tests/oracle/ tests/package/ tests/interoperability/ -q
  116 passed, 5 skipped, 0 failed in 57.88s

pytest tests/scripts/test_state_json_schema.py -q
  10 passed

python -m build --wheel --sdist
  Successfully built libipynb-0.1.0-py3-none-any.whl and libipynb-0.1.0.tar.gz

twine check dist/libipynb-0.1.0-py3-none-any.whl dist/libipynb-0.1.0.tar.gz
  PASSED, PASSED
```

**Combined: 1364 passed, 16 skipped, 0 failed** across every test tier this repository defines. All 16 skips are pre-existing, environment-conditional (POSIX-only `RLIMIT_AS`/permission-bit tests on Windows, missing PDF backend, an empty corpus-integrity parameter set) — none silently masking untested code introduced by this engagement.

**Branch summary:** 103 commits ahead of `master`, 94 files changed, +10,793/−385 lines. Working tree clean. No tag exists (`git tag -l` empty); no push to any remote has occurred.

---

## 7. Cross-check against `plans/state.json`

Every `VERIFIED` row in `plans/state.json` (42 of them) is represented above, either by name in a table (§3.1, §4) or by inclusion in the mutation-after-access narrative (§3.2, covering `Q39`, `Q41`–`Q45`, `Q55`, `Q56`, `Q61` plus the Phase 0/2/3 infrastructure rows `P0.1`, `Q1`–`Q3`, `Q25`–`Q38` implicit in §1's phase summary). Nothing in this report claims a status `plans/state.json` does not itself record — every number above (test counts, commit count, file-change stats) was reproduced live in this session, not carried over from an earlier claim. `tests/scripts/test_state_json_schema.py`'s 10 checks (valid JSON, required fields present, no duplicate IDs, controlled status vocabulary, resolvable dependencies, every `VERIFIED` `repair_commit` resolving to a real commit, every reviewed `VERIFIED` row having non-empty `review_lenses_applied`, mutation-baseline evidence or documented exception for the 4 hot modules) all pass as of the commit this report is attached to.

---

## 8. Recommendation

Every taskcard on the path to publication is closed: 42/49 `VERIFIED`, the remaining 7 are either this report, the authorization gate itself, or independently-scoped, non-blocking follow-up work with preserved reasoning. Release-candidate verification (Phase 5) confirms the built artifacts install cleanly in genuine clean-room environments, pass PyPI's own pre-flight check, resolve to a vulnerability-free dependency set, and work correctly end-to-end including real git-driver integration. This engagement's own heaviest-scrutiny defect class (mutation-after-access) went through 5 independent review rounds before the first clean verdict, closing 15 field instances a single review pass would have missed 8 of.

This report does not itself authorize publication. That is `Q54` — the one mandatory human stop in this entire engagement, described next.
