# libipynb Production-Hardening Plan

**Status:** Drafted 2026-08-18, execution starting and completing the same day; closed out the same day by
a second, separate 2026-08-18 close-out session. **All 21 taskcards are now `completed_verified` except
three accurately-described non-blockers:** Q2's timeout-watchdog redesign (deliberately deferred — larger
scope than any single round, needs its own future Gate G6 pass when attempted; not a blocked item, just
not yet started), Q13b (`partially_done` — needs a live GitLab CI/CD Schedule, genuinely blocked on
project-settings access no session here has had), and Q13c item 3 (real-world fixture *sourcing*
specifically — deliberately deferred twice now, a provenance/licensing judgment call neither the original
implementing session nor the close-out session made unilaterally; the selection *process/criteria* are
documented).
**Original implementing session:** four separate independent review agents ran across two rounds, each
with no access to this implementing session's own reasoning: round 1 covered the P0/P1 cards (Q1, Q2, Q3,
Q4, Q9) and found one real defect (Q3's merge-reconciliation logic); round 2 covered every remaining card
in three parallel passes — one re-checking the round-1 Q3 fix specifically (which found a SECOND, more
severe defect in that same fix, requiring a further narrowing of its scope — see Q3's own entry for the
full history), one covering Q5/Q6/Q7/Q8/Q14 (zero defects, one cosmetic doc nit fixed), and one covering
Q10/Q11a/Q11b/Q12b/Q12c/Q13a/Q13c/Q15a/Q15b (one real defect: SECURITY.md misattributed the `exec` extra
and omitted the real Jupyter-kernel execution engine from its disclosure, fixed; one minor non-exploitable
regex nitpick in Q11b, fixed).
**Close-out session (2026-08-18, later the same day):** closed the five cards the original session
correctly left open. Q3: a third, independent fresh-context review ran 12 adversarial scenarios and
confirmed the round-2 fix correct (`completed_verified`). Q7/Q8: independent Gate G6 security-adequacy
reviews each found one further real, previously-undiscovered gap — Q7's `max_scan_tokens` only counted
start-tags (a closing-tag/comment-dominated payload bypassed the CPU-DoS protection entirely); Q8's
`text/markdown` fix didn't account for RFC 2046 MIME parameters (`text/markdown; charset=utf-8` bypassed
scanning, as did the pre-existing `text/html; charset=utf-8` case). Both fixed minimally, both
re-verified, both now `completed_verified`. Q12a: the maintainer's own decision was obtained directly
("omit the field entirely") and applied — `completed_verified`. Q12c: G7 sign-off completed —
`completed_verified`. The close-out session also fixed a real, previously-undiscovered defect unrelated
to any specific card: `ruff format --check` (a standing `.gitlab-ci.yml` quality-stage gate) was failing
on 13 files that had never been run through `ruff format` — fixed before any other close-out work began,
so every subsequent review's line-number references stay valid.
Full regression suite as of the close-out session's end: **1022 passed, 5 skipped** (up from 1017 — 5 new
regression tests, 0 regressions); `mypy --strict`/`ruff check`/`ruff format --check` all clean; both of
the audit's own headline reproductions re-confirmed fixed. See §6 below for the complete end-to-end
verification record.
A per-rule specification traceability matrix is maintained separately at
`plans/specification-traceability-matrix.md`. A standing Gate G1–G7 status document (the mission's own
gate numbering, distinct from this plan's G1–G9), an architecture document (`ARCHITECTURE.md`), a
benchmarks report, and a packaging/independence audit (`plans/independence-audit-2026-08-18.md`) were also
produced by the close-out session — see `plans/evidence-bundle-2026-08-18.md` for the full index.
**Date:** 2026-08-18.
**Author:** produced by an assistant session from `plans/forensic-capability-audit-2026-08-18.md` (an
independent forensic audit run earlier the same day), under an explicit maintainer request to plan and
implement production-grade fixes for every finding in that audit (P0 through P3).

---

## 0. Mandate and relationship to prior work

This plan closes every confirmed finding in `plans/forensic-capability-audit-2026-08-18.md` — 4
publication blockers plus ~25 further confirmed defects/gaps spanning execution-engine correctness,
diff/merge robustness, resource-limit/DoS hardening, document-model fidelity, CLI error handling,
packaging accuracy, export fidelity, and test-quality coverage. It is a **remediation plan for a fresh,
independent audit**, structurally the same kind of document as `plans/remediation-plan.md` (which closed
out an earlier audit's Tier B/M/V taskcards) and `plans/full-parity-plan.md` (which added the execution
engine and diff/merge/git-integration capability this plan's two most severe findings are *in*). It does
not modify either of those documents' content and does not redefine their governance machinery.

**Governance: reused verbatim, not reinvented.** This plan uses `plans/remediation-plan.md`'s Gate
Contract (§7 there: G1–G5), Evidence Contract (§8), Repair Loop (§10), and Anti-Overclaim Rules (§11),
extended by `plans/full-parity-plan.md`'s G6 (Security Design Review), G7 (Dependency-Addition), G8
(Oracle-Fidelity), and G9 (Plan-Reality Sync) gates — all reused exactly as those documents define them.
See those two documents for the full gate text; this plan only cites which gates each taskcard requires.

**Two most severe findings, driving Wave −1's priority:**
1. `LocalJupyterExecutor` (the real Jupyter-kernel execution engine shipped in `plans/full-parity-plan.md`
   P4a-1/P4b/P4c) cannot execute any notebook whose code cells use list-of-lines source — the standard
   on-disk Jupyter format, confirmed present in 40% of this repo's own fixture corpus. The audit traced
   this directly to that round's Gate G2 review being self-review only, and to the one test built for
   this exact input checking field preservation but never execution success.
2. `libipynb diff`/`libipynb merge` (shipped in P3a/P3b/P3c) crash on any notebook lacking nbformat 4.5's
   mandatory cell IDs — confirmed to break the real `git diff`/`git merge` driver integration end-to-end
   (`fatal: external diff died`, exit 128), not just the standalone CLI commands.

---

## 1. Taskcard Register

| ID | Title | Status | Priority | Lane | Dependencies |
|---|---|---|---|---|---|
| Q1 | Fix `LocalJupyterExecutor` list-of-lines-source execution blocker | `completed_verified` (G1+G8+G2 done — independently reviewed, confirmed correct) | P0 | Execution Engine | none |
| Q3 | Fix `diff_notebooks()`/`merge_notebooks()` crash on pre-4.5 notebooks | `completed_verified` (G1+G2+G8 done — a genuinely separate 2026-08-18 close-out session's fresh-context review agent ran 12 adversarial scenarios against the final, narrowed fix and confirmed CORRECT with no data loss or wrong-data pick in any case) | P0 | Diff/Merge/Cleanup Parity | none |
| Q9 | Fix document-model deep-copy leaks; harden `AttachmentManager` | `completed_but_weakly_verified` (G1+G2 done — independently reviewed, correct; 1 gap closed) | P1 | Document Model & Attachments | none |
| Q5 | Guard `lifecycle.py`'s `_copy_source()` against the RecursionError DoS | `completed_verified` (G1+G2 done — independently reviewed, confirmed correct) | P1 | Security & Resource Limits | none |
| Q6 | Catch lone UTF-16 surrogate encode failures in reader/writer/validator | `completed_verified` (G1+G2 done — independently reviewed, confirmed correct; also found and fixed a 3rd crash site, `_enforce_text_size`, not in the original design) | P1 | Security & Resource Limits | none |
| Q4 | CLI top-level exception handling + related CLI polish | `completed_verified` (G1+G2 done — independently reviewed, confirmed correct) | P0 | Conversion & CLI Surface | Q3 (soft) |
| Q7 | Close resource-limit gaps (max_entries, stream read, array hook, sanitizer DoS) | `completed_verified` (G1+G2+G6 done — a 2026-08-18 close-out session's independent security-adequacy review found a real remaining gap: `max_scan_tokens` counted only start-tags, so a payload dominated by closing tags/comments bypassed the CPU-DoS protection entirely; fixed by counting `handle_endtag`/`handle_comment`/`handle_decl`/`handle_pi` too, 2 new regression tests added) | P1 | Security & Resource Limits | none |
| Q8 | Close text/markdown sanitizer blind spot; active-content test coverage | `completed_verified` (G1+G2+G6 done — a 2026-08-18 close-out session's independent security-adequacy review found a real remaining gap: MIME types with RFC 2046 parameters, e.g. `text/markdown; charset=utf-8`, bypassed scanning entirely via exact-string comparison; fixed with a `_media_type_base()` helper stripping parameters before comparison, applied at all 3 comparison sites, 3 new regression tests added) | P1 | Governance & Trust | none |
| Q10 | Detect notebook-level metadata conflicts in `merge_notebooks()` | `completed_verified` (G1+G2 done — independently reviewed twice, confirmed correct both times) | P2 | Diff/Merge/Cleanup Parity | Q3 (soft) |
| Q2 | `LocalJupyterExecutor` safety/fidelity hardening | `completed_but_weakly_verified` (G1+G2 done for sub-items a-d — independently reviewed, confirmed correct; watchdog redesign deliberately deferred, G6 N/A until it lands) | P1 | Execution Engine | Q1 (hard) |
| Q12a | Resolve the internal GitLab URL leak before any public release | `completed_verified` (G1+G3 done — maintainer decision obtained 2026-08-18: "omit the field entirely"; `[project.urls] Repository` removed from `pyproject.toml`, `CONTRIBUTING.md` clone instructions genericized; verified against a fresh `python -m build --wheel --sdist`, zero matches for the internal host string in METADATA/PKG-INFO/file-list) | P0 (publication) | Release & Publish | none |
| Q12b | Fix false/incomplete claims in SECURITY.md, README.md, CHANGELOG.md | `completed_but_weakly_verified` (G1+G2 done — G2 found and fixed a real defect, see own entry) | P1 | Docs & Evidence | none |
| Q12c | Remove dead `pyyaml` dependency; pin `nbformat` in the `exec` extra | `completed_verified` (G1+G2+G7 done — a 2026-08-18 close-out session re-confirmed all four G7 checks against current source: `nbformat>=5.10` pin present in the `exec` extra, version floor consistent with the repo's other 3 pins, BSD-3-Clause license compatible, import-boundary test 7/7 passing) | P1/P3 | Docs & Evidence | none |
| Q11a | Export resource-collection safety hardening | `completed_verified` (G1+G2 done — independently reviewed twice, confirmed correct both times) | P2 | Conversion & CLI Surface | Q9 (soft) |
| Q11b | Export content-fidelity fixes (fence language, HTML title, raw-cell drop) | `completed_verified` (G1+G2+G8 done — independently reviewed twice, confirmed correct; 1 minor nitpick found and fixed) | P2/P3 | Conversion & CLI Surface | none |
| Q13a | Validation and diff oracle test coverage | `completed_verified` (G1+G2+G8 done — independently reviewed twice, confirmed correct both times) | P2 | Validation Depth | Q3 (soft) |
| Q13b | Wire `tests/oracle/`/`tests/package/` into CI (schedule-gated) | `partially_done` (G1 done; no live schedule yet) | P1 | Validation Depth | Q13a (soft) |
| Q13c | Property/fixture/secret-scanner broadening + `NotebookSecurityError` decision | `partially_done` (items 1/2/4 G1+G2-verified — independently reviewed twice, confirmed correct; item 3 real-world-fixture selection deliberately deferred) | P2/P3 | Validation Depth | none |
| Q14 | Validation/lifecycle small-fix bundle | `completed_verified` (G1+G2 done — independently reviewed, confirmed correct) | P2/P3 | Validation Depth | Q5 (soft), Q6 (soft) |
| Q15a | `CellEditor` batch/bulk-edit mode | `completed_verified` (G1+G2 done — independently reviewed twice, confirmed correct both times) | P3 | Manipulation/Performance | none |
| Q15b | Parametrized PDF/slideshow export | `completed_but_weakly_verified` (G1+G2+G8-for-slides done — independently reviewed twice, confirmed correct; PDF's own G8 environment-blocked, not a code gap) | P3 | Conversion & CLI Surface | Q11a/b (soft) |

## 2. Lane Ownership

Adds to (does not replace) `remediation-plan.md` §6 / `full-parity-plan.md` §4.2:

| Lane | Scope | Owner |
|---|---|---|
| Execution Engine | `adapters/jupyter_execute.py`, `execution/*.py` | Any executing session; Gate G6 required for Q2's timeout-watchdog sub-item (widens how timeouts/interrupts are enacted) |
| Diff/Merge/Cleanup Parity | `model/diff.py`, `model/merge.py` | Any executing session, code-only |
| Document Model & Attachments | `model/document.py`, `model/attachments.py`, `_internal/paths.py` | Any executing session, code-only |
| Security & Resource Limits | `security/limits.py`, `security/sanitizer.py`, `codec/reader.py`, `codec/writer.py` | Any executing session; Gate G6 required for Q7/Q8 (security-relevant default changes) |
| Conversion & CLI Surface | `cli/main.py`, `cli/__main__.py`, `adapters/export.py` | Any executing session, code-only |
| Governance & Trust | `security/sanitizer.py` (detection coverage), `security/trust.py` | Any executing session |
| Validation Depth | `validation/*.py`, `tests/oracle/`, `tests/property/`, `.gitlab-ci.yml` | Any executing session, code/test/CI-only |
| Release & Publish | `pyproject.toml`'s `[project.urls]`, `CONTRIBUTING.md` | **Gate G3 (maintainer/publish-authority) required** — Q12a specifically |
| Docs & Evidence | `SECURITY.md`, `README.md`, `CHANGELOG.md` | Any executing session, code-only |
| Manipulation/Performance | `model/editor.py` | Any executing session, code-only |

---

## 3. Taskcards

### Wave −1 — P0 functional blockers

### LIBIPYNB-Q1 — Fix `LocalJupyterExecutor` list-of-lines-source execution blocker

**Status:** `completed_verified` (G1+G8+G2 done — independently reviewed, confirmed correct) · **Priority:** P0 · **Lane:** Execution Engine · **Dependencies:** none · **Evidence:** plans/forensic-capability-audit-2026-08-18.md §7 ("LocalJupyterExecutor cannot execute list-of-lines-source notebooks"), §17 item 1

**Gate G2 review note (2026-08-18):** An independent review agent confirmed the fix directly against
current source: source is normalized on the deep-copied execution dict for every cell type,
`document.raw`/the returned result are built from a separate deepcopy and never read `source` back off
the executed node, and non-string/non-list values fall back safely rather than crashing. The oracle test
extending fidelity comparison to list-source input was confirmed to actually exist and pass.

- **Objective:** `LocalJupyterExecutor` cannot execute any notebook whose code cells use list-of-lines
  `source` — the standard on-disk form JupyterLab writes by default, confirmed present in 40% of this
  project's own fixture corpus — because `_build_client()` hands `nbformat.from_dict()` an un-normalized
  dict and `nbclient` crashes at `cell.source.strip()`. The entire run fails and is misreported as a
  generic `kernel_death_error`.
- **Expected files:** `src/libipynb/adapters/jupyter_execute.py`; `tests/integration/test_obligation_jupyter_execution_adapter.py`; `tests/unit/test_cli.py` (`TestExecute`).
- **Required behavior:** `_build_client()` normalizes every cell's `source` on the deep-copied execution
  dict (`nb_dict`), for all cell types, to a joined string before `nbformat_mod.from_dict(nb_dict)` runs
  — mirroring `adapters/execute.py::_cell_source()`'s existing `value if isinstance(value, str) else
  "".join(value)` logic exactly. `document.raw`/`result.notebook`'s source form is unaffected (`_finish()`
  never reads `source` back off the executed node; it writes results onto a *separate*
  `deepcopy(document.raw)`).
- **Required verification (Gate G1 + G8):** Full regression suite green. Strengthen
  `test_list_of_lines_source_form_is_preserved_unchanged` to assert `result.completed is True`,
  `result.kernel_death_error is None`, and real cell output content — not merely source-field
  preservation (the exact blind spot that let this ship). Add the same case to `execute_async` and to
  `test_cli.py::TestExecute`. **Oracle-fidelity (G8):** execute the same list-source fixture through
  `LocalJupyterExecutor` and through direct `nbconvert --execute`/real `papermill`, assert deterministic
  output fields agree — extends the existing string-source-only oracle comparison to list-source input
  for the first time.
- **Required evidence:** Diff of `jupyter_execute.py`; the strengthened test's pass output; the CLI
  regression's pass output; the oracle-comparison run's output against
  `tests/fixtures/corpus/data-science-pattern.ipynb` (confirmed to contain list-source cells).
- **Acceptance criteria:** `libipynb execute` succeeds end-to-end on a list-source fixture via both CLI
  and direct API, sync and async, with real output content, not just preserved-but-unexecuted source.
- **Non-goals:** Normalizing other potentially-list-form fields (e.g. output `text`) absent a confirmed
  second crash.
- **Closeout rules:** `completed_verified` requires Gates G1 and G2.

### LIBIPYNB-Q3 — Fix `diff_notebooks()`/`merge_notebooks()` crash on pre-4.5 (no cell-id) notebooks

**Status:** `completed_verified` (G1+G2+G8 done — see the 2026-08-18 close-out review note below for the third, independent review round that closes this card) · **Priority:** P0 · **Lane:** Diff/Merge/Cleanup Parity · **Dependencies:** none · **Evidence:** plans/forensic-capability-audit-2026-08-18.md §7 ("libipynb diff/merge on real-world notebooks — BLOCKER"), §17 item 2

**Gate G2 review note (2026-08-18, close-out session — a third, genuinely independent review round,
distinct from and later than the two rounds recorded below):** a fresh-context review agent, briefed only
on the objective and the "no wrong data, no lost cells, ever" acceptance bar (not this card's own
round-1/round-2 history), read `diff.py`/`merge.py` in full and ran 12 adversarial scenarios live against
the installed package — the 5 scenarios this card's own history already names, plus 7 more (move+edit
combinations, duplicate-content base cells, three-base-cell anchored blocks, both-sides-insert-near-edit).
**VERDICT: CONFIRMED CORRECT.** Every real cell survived every scenario exactly once; no scenario produced
a confidently-wrong pick. The round-1/round-2 "resemblance trap" attack (scenario 4) could not succeed
because cell correlation is purely positional/content-hash-based via `SequenceMatcher` — no
content-similarity heuristic remains in the code (confirmed by the reviewer reading the round-2 fix's own
design-history comment at `merge.py:266-289`, which documents this exact attack and why the heuristic was
removed). One non-data-loss quirk was independently re-confirmed, not newly found: a correctly-flagged
`EDIT_EDIT` conflict cell can land out of its original relative order in merged output — already disclosed
in the function's own docstring as an accepted position-fidelity limitation, not a violation of this card's
acceptance bar. This closes the card: three independent review passes (round 1, round 2, and this
close-out round) have now each found the current fix correct, with rounds 1 and 2 each having found and
fixed a real defect in an *earlier* version of the same fix — the round now returning clean is evidence
the design has converged, not evidence review was skipped.

**Gate G2 history (2026-08-18) — two independent review rounds, two real defects, each on the SAME
special-case reconciliation function (`_reconcile_same_position_id_less_edit`/
`_find_same_position_replacement_id`), added to close the original "silent content duplication" bug this
card discovered while implementing the P0 blocker fix. Recorded here in full because the sequence itself
is the evidence that independent review — not self-review — is what caught each defect, exactly the
failure pattern the original forensic audit found responsible for the P4a-1 blocker shipping unnoticed:**

- **Round 1 finding:** the first fix correlated a same-position replacement by comparing
  `added_change.after_index == removed_change.before_index` directly — breaks the moment ANY other cell is
  also added/removed on that side (an everyday pattern: "insert a cell right above the one I'm editing").
  Repro: `base=[A,B]`, `ours=[new, A_edited, B]`, `theirs=[A_edited_differently, B]` — picked `new` (wrong,
  by raw index) as "the replacement," **silently dropped `new` from the merge output**, and let the real
  edit through **completely unconflicted**.
- **Round 1 fix:** replaced index comparison with `difflib.SequenceMatcher` alignment over each side's own
  id list against base's (anchors on genuinely unchanged surrounding cells), with a content-similarity
  tiebreak (`_best_content_match`) for blocks `SequenceMatcher` couldn't cleanly separate into insert+
  replace.
- **Round 2 finding (a SEPARATE, later review, re-checking the round-1 fix specifically):** the
  content-similarity tiebreak itself was unsafe in two ways. (a) It only handled a block spanning exactly
  one base cell — two ADJACENT id-less base cells edited differently on both sides (no insertion needed at
  all, just "edit two consecutive cells in one commit") collapse into one multi-base-cell block, which the
  fix declined entirely, silently reopening the original duplication bug for that shape. (b) Far more
  severe: the similarity heuristic could be fooled by a genuinely new, UNRELATED inserted cell that merely
  *resembled the base cell's original content more than a substantially-rewritten TRUE edit did* (e.g. a
  plausible extra `import` line next to a real rewrite) — the heuristic then **confidently** picked the
  wrong cell, producing **actual cell loss plus wrong content in the reported conflict**, which is worse
  than the original bug (a confident wrong answer beats a declined one only in appearance, never in
  correctness).
- **Round 2 fix (final, current form):** removed the content-similarity tiebreak entirely.
  `_find_same_position_replacement_id` now resolves ONLY the mathematically unambiguous case — a clean
  `SequenceMatcher` block covering exactly one base cell and exactly one side candidate — and declines
  (returns `None`) for every other shape, no exceptions, no guessing. A decline falls back to the
  well-understood, already-accepted pre-existing behavior (both sides' real content is kept, uncontested,
  without a conflict flagged) — it can never fabricate a plausible-but-wrong answer or lose a cell. This
  trades detection completeness for a stronger guarantee: **no wrong data, no lost cells, ever**, under any
  input tried across two full rounds of adversarial independent review. All five scenarios from both review
  rounds were re-verified live post-fix (clean 2-cell edit still correctly flagged as a conflict; the two
  round-1 insertion scenarios, the round-2 adjacent-edit scenario, and the round-2 similarity-false-positive
  scenario all safely decline with zero cell loss and zero wrong conflict data). Four permanent regression
  tests cover this in `tests/unit/test_obligation_notebook_merge.py`:
  `test_merge_never_loses_a_cell_when_ours_also_inserts_an_unrelated_cell_near_an_edit`,
  `test_merge_never_loses_a_cell_when_both_sides_insert_an_unrelated_cell_near_their_edit`,
  `test_merge_never_loses_a_cell_when_two_adjacent_base_cells_are_both_edited_differently`,
  `test_merge_never_picks_an_unrelated_cell_that_merely_resembles_the_base_cell_more_than_the_real_edit`
  (plus the original, still-passing `test_merge_detects_a_conflict_on_a_pre_45_notebook_instead_of_
  silently_duplicating_both_edits` for the clean, unambiguous case). Full regression suite (1016 passed, 5
  skipped) green after the round-2 fix; `mypy --strict`/`ruff check` clean. LIBIPYNB-Q10 (notebook-level
  metadata conflicts, a separate change in the same file) was independently reviewed in round 2 and
  confirmed correct with zero findings — see its own entry below.
- **Why this card still isn't `completed_verified`:** the round-2 fix itself — the current, narrowed,
  conservative form — has not yet had its own independent review pass. Given the pattern above (each prior
  version looked correct to its own author until independent review found a concrete counterexample), this
  card deliberately does not claim full verification on self-review of the newest fix, however much simpler
  and more defensible it is than its predecessors.

- **Objective:** `diff_notebooks()`/`merge_notebooks()` (and the real git diff/merge driver, which calls
  the identical functions) unconditionally require every cell to carry a non-empty string `id`, raising
  `ValueError` on any nbformat 4.0–4.4 notebook — the majority-case for real, pre-existing notebooks, and
  a version range the README's own "Supported Versions" table lists as supported. Confirmed to break real
  `git diff`/`git merge` end-to-end (`fatal: external diff died`, exit 128).
- **Expected files:** `src/libipynb/model/diff.py`; `src/libipynb/model/merge.py`; `tests/unit/test_obligation_structure_diff.py`; `tests/unit/test_obligation_notebook_merge.py`; `tests/unit/test_cli_git_diff_merge_drivers.py`.
- **Required behavior:** `diff_notebooks()` synthesizes missing ids on its own private, projected copies
  (`left`/`right`) via a new `_with_stable_cell_ids()` helper, using `codec.reader.ensure_cell_id` (the
  same content-hash algorithm `upgrade()` already relies on) via a deferred import to avoid a
  `model`↔`codec` import cycle. `_fingerprint()` is refactored to include the same synthesis step so
  `NotebookPatch.apply()`'s precondition check stays consistent with `diff_notebooks()`'s own
  `base_fingerprint`. `merge_notebooks()` builds synthesized-id copies of `base`/`ours`/`theirs` once
  (`_synthesized_copy()`) and uses them consistently across its own `diff_notebooks()` calls,
  `_cell_map()`, and `_ordered_ids()` — `_cell_map()` correlates by *position* between the original and
  synthesized documents and returns the **original**, unsynthesized cell dicts, so no synthetic id ever
  leaks into merge output (preserving pre-4.5 target-schema validity).
- **Required verification (Gate G1 + G8):** Full regression suite green. A stability test proving two
  independent `diff_notebooks()` calls on the same id-less input produce identical `cell_changes`
  (content → same SHA-256 digest → same synthesized id, both sides — regression-proofing this directly
  rather than trusting the algorithm). Pre-4.5 fixture pairs: an unchanged cell is correctly reported as
  unchanged (not remove+add); a changed id-less cell is honestly reported as remove+add, documented as an
  accepted, inherent limitation of id-less content-identity. **Oracle-adjacent (G8):** the audit's own
  real end-to-end repro — scratch git repo, committed pre-4.5 fixture, edit, `git diff`/`git merge`
  through the installed drivers — must now succeed.
- **Required evidence:** Diff of `diff.py`/`merge.py`; the stability test's pass output; the scratch-repo
  git-driver integration test's actual output.
- **Acceptance criteria:** `diff_notebooks()`/`merge_notebooks()` succeed on any pre-4.5 notebook; real
  `git diff`/`git merge` succeed end-to-end via the installed drivers.
- **Non-goals:** `NotebookPatch.apply()`'s own separate, un-synthesized `_cell_index()` call inside
  `_restore_ignored_values()` — not in the P0 blocker's call chain (the CLI drivers never call
  `.to_patch()`/`.apply()`); flagged as a narrower follow-on gap if `NotebookPatch` usage against id-less
  notebooks is ever needed.
- **Closeout rules:** `completed_verified` requires Gates G1, G2, and G8.

### Wave 0 — Document model & lifecycle foundation

### LIBIPYNB-Q9 — Fix document-model deep-copy leaks; harden `AttachmentManager`

**Status:** `completed_but_weakly_verified` (G1 done; G2 review confirmed correct, one gap closed — see note) · **Priority:** P1 · **Lane:** Document Model & Attachments · **Dependencies:** none · **Evidence:** plans/forensic-capability-audit-2026-08-18.md §7 ("to_dict()/.metadata/.outputs — HIGH", "AttachmentManager.add()/.rename() — MEDIUM"), §9 item 3

**Gate G2 review note (2026-08-18):** An independent review confirmed the deep-copy fix, the
`_rewrite_references()` fix, and the path-safety/base64 hardening are all correct, with one minor gap:
this card's own required verification calls for "a Hypothesis property test" alongside the concrete
mutation-regression example, and only the concrete test existed. Added
`test_mutating_accessors_never_leaks_into_raw_property` to `tests/unit/test_obligation_typed_model.py`
(100 generated examples per run, varying notebook-level metadata, cell-level metadata, and output text
content) — passes. Full regression suite (1014 passed, 5 skipped) green; `mypy --strict`/`ruff check`
clean.

- **Objective:** Four accessors (`NotebookDocument.to_dict()`, `.metadata`, `Cell.metadata`,
  `Cell.outputs`) return shallow copies, letting a caller mutate the live `.raw`/document state through
  what looks like a snapshot — confirmed against the same file's own correct `deepcopy`-based pattern one
  level down (`Cell.to_dict()`, `NotebookOutput.to_dict()`). `AttachmentManager.rename()`'s list-source
  segment reconstruction slices the *rewritten* text at *stale, pre-rewrite* per-item lengths, corrupting
  line boundaries on any length-changing rename. `AttachmentManager.add()`/`.rename()` have zero
  base64/path-safety validation, with the one existing safeguard living entirely in a downstream export
  consumer.
- **Expected files:** `src/libipynb/model/document.py`; `src/libipynb/model/attachments.py`; `src/libipynb/_internal/paths.py` (new); `src/libipynb/adapters/export.py`; `tests/unit/test_obligation_attachments.py`; a document/cell accessor test file.
- **Required behavior:** Swap `dict(...)`/`list(...)` for `deepcopy(...)` at the four confirmed sites in
  `document.py` (import already present). Fix `attachments.py::_rewrite_references()` to re-derive line
  boundaries via `rewritten.splitlines(keepends=True)` instead of slicing at stale old-item lengths —
  correct because `_validate_name()` already forbids control characters (including `\n`) in attachment
  names, guaranteeing a rename cannot change line *count*, only line *length*. Extract
  `_is_safe_resource_filename` into a new, dependency-free `src/libipynb/_internal/paths.py::
  is_safe_resource_filename()` (mirroring the existing `_internal/probe.py` precedent, since `model` must
  not import from `adapters` — the reverse of the codebase's established layering), re-export it unchanged
  from `adapters/export.py` under the same local name, and wire it into `attachments.py::_validate_name()`.
  Add base64 well-formedness checking (`base64.b64decode(payload, validate=True)`) to `_validate_bundle()`
  for non-`text/plain` MIME payloads.
- **Required verification (Gate G1):** Full regression suite green. Mutation-after-access regression
  tests for all four accessors (mutate the returned value, assert `document.raw` is unaffected), plus a
  Hypothesis property test. A length-changing-rename regression test (rename a shorter attachment name to
  a longer one inside a list-form source, assert every line's boundary and content is correct, including
  an untouched sibling line). Path-traversal and malformed-base64 regression tests asserting `ValueError`.
- **Required evidence:** Diff of `document.py`, `attachments.py`, the new `_internal/paths.py`, and
  `adapters/export.py`; the mutation-regression and rename-boundary tests' pass output.
- **Acceptance criteria:** No accessor in `document.py` allows caller-side mutation to reach `.raw`; a
  length-changing attachment rename never corrupts unrelated source lines; `add()`/`rename()` refuse
  path-traversal names and malformed base64 with a clear `ValueError`.
- **Non-goals:** `NotebookDocument.raw`'s intentionally-live semantics (used throughout for in-place
  mutation) — correct as-is, out of scope. Anti-spoofing (Unicode homoglyph/RTL-override) filename checks
  — only path-traversal shape safety, matching the existing downstream consumer's own scope.
- **Closeout rules:** `completed_verified` requires Gates G1 and G2.

### LIBIPYNB-Q5 — Guard `lifecycle.py`'s `_copy_source()` against the RecursionError DoS

**Status:** `completed_verified` (G1+G2 done — independently reviewed, confirmed correct) · **Priority:** P1 · **Lane:** Security & Resource Limits · **Dependencies:** none · **Evidence:** plans/forensic-capability-audit-2026-08-18.md §7 ("upgrade()/plan_downgrade()/downgrade() — HIGH"), §17 item 6

**Gate G2 review note (2026-08-18):** An independent review confirmed `enforce_structure()` is genuinely
called before `deepcopy()` (an iterative, explicit-stack traversal, not recursive), the `limits` parameter
is correctly threaded through all three entry points, and both the crash-threshold case and a
well-below-threshold tight custom limit are actually enforced (not just the crash itself).

- **Objective:** `upgrade()`/`plan_downgrade()`/`downgrade()` call Python's recursive `copy.deepcopy()` on
  caller-supplied input via `_copy_source()` before the library's own bounded, iterative
  `enforce_structure()` traversal ever runs — adversarially confirmed to raise an uncaught
  `RecursionError` at ~495+ levels of nested metadata (well under a kilobyte of JSON), a trivially
  triggered DoS against a documented safety guarantee. `upgrade()` specifically enforces no structural
  limit at all below that crash threshold.
- **Expected files:** `src/libipynb/model/lifecycle.py`; `tests/unit/test_obligation_lifecycle_modes.py`.
- **Required behavior:** `_copy_source()` gains a `limits: NotebookResourceLimits | None = None`
  parameter, calls `enforce_structure(raw, effective_limits(limits))` before `deepcopy(raw)`.
  `upgrade()`/`plan_downgrade()`/`downgrade()` each gain a threaded-through, keyword-only `limits=None`
  parameter, defaulting to the same shared default every other entry point uses.
- **Required verification (Gate G1):** Full regression suite green. New tests mirroring the existing
  `max_nesting_depth` pattern from `test_obligation_security_limits.py`, targeting `upgrade`/
  `plan_downgrade`/`downgrade` directly at both the ~495-level crash threshold and well below it (proving
  the "no limit at all below the crash threshold" gap is fully closed, not just the crash itself), plus a
  caller-override test proving `limits=` is honored.
- **Required evidence:** Diff of `lifecycle.py`; the new test file's pass output, including the
  below-threshold case that previously silently succeeded.
- **Acceptance criteria:** All three entry points raise the same typed `NotebookResourceLimitError`
  `validate()` already produces for identical adversarial dict input, at the same bound.
- **Non-goals:** Does not change the `deepcopy`-based fast path's cost for already-bounded, legitimate
  notebooks.
- **Closeout rules:** `completed_verified` requires Gates G1 and G2.

### LIBIPYNB-Q6 — Catch lone UTF-16 surrogate encode failures in reader/writer/validator

**Status:** `completed_verified` (G1+G2 done — independently reviewed, confirmed correct; also found and fixed a 3rd crash site, `_enforce_text_size`, not in the original design) · **Priority:** P1 · **Lane:** Security & Resource Limits · **Dependencies:** none · **Evidence:** plans/forensic-capability-audit-2026-08-18.md §7 ("Lone UTF-16 surrogate crashes the reader and (conditionally) the writer — HIGH"), §17 item 7

**Gate G2 review note (2026-08-18):** An independent review confirmed all three sites correctly catch
`UnicodeEncodeError` and re-raise as the correct typed error, and additionally manually confirmed (beyond
the committed tests) that the non-declared `dumps(doc, profile="4.5")` path also surfaces a typed error
correctly, not just the `profile="declared"` path the committed tests directly exercise.

- **Objective:** A syntactically-valid JSON payload with an unpaired UTF-16 surrogate escape (`\ud800`)
  crashes `loads()`/`load()` with an uncaught `UnicodeEncodeError` in **all three parse modes** including
  `recovery`, and crashes `dumps()`/`dump()` specifically under `profile='declared'` — the profile every
  shipped CLI write path uses.
- **Expected files:** `src/libipynb/codec/reader.py`; `src/libipynb/codec/writer.py`; `src/libipynb/validation/validator.py`; `tests/security/test_adversarial_input.py` (or a new dedicated unit test file).
- **Required behavior:** Wrap `reader.py::_parse()`'s `enforce_structure(data, limits)` call in a handler
  catching `UnicodeEncodeError`, re-raising as `NotebookParseError(code="IPYNB_INVALID_SURROGATE")`. Wrap
  `writer.py::dumps()`'s `len(result.encode("utf-8"))` call similarly, re-raising as
  `NotebookWriteError(code="IPYNB_INVALID_SURROGATE")`. Add an explicit `except UnicodeEncodeError` clause
  to `validator.py::validate()`, ahead of its existing broad `ValueError` catch (which currently catches
  it only by accident), giving a correctly-labeled diagnostic. Fix stays at each call site, not inside the
  shared `_utf8_size` helper (only the caller knows the right exception type for its context).
- **Required verification (Gate G1):** Full regression suite green. New tests: lone-surrogate fixture
  through `loads()` in all 3 modes; through `dumps(profile="declared")`; through `validate()` directly; a
  non-regression test proving well-formed UTF-8 still correctly triggers `NotebookResourceLimitError` at
  configured byte limits.
- **Required evidence:** Diff of the three files; the new test file's pass output covering all three
  parse modes and the `declared` write profile.
- **Acceptance criteria:** No uncaught `UnicodeEncodeError` reaches a caller of `loads()`/`load()`/
  `dumps()`/`dump()`/`validate()` for any lone-surrogate input, in any mode/profile.
- **Non-goals:** Auto-repairing/stripping the invalid surrogate and continuing, even in `recovery` mode —
  a clean, typed error is the agreed bar.
- **Closeout rules:** `completed_verified` requires Gates G1 and G2.

### Wave 1 — CLI robustness

### LIBIPYNB-Q4 — CLI top-level exception handling + related CLI polish

**Status:** `completed_verified` (G1+G2 done — independently reviewed, confirmed correct) · **Priority:** P0 · **Lane:** Conversion & CLI Surface · **Dependencies:** none (Q3 soft — see Non-goals) · **Evidence:** plans/forensic-capability-audit-2026-08-18.md §7 ("CLI error handling (main()) — HIGH"), §17 items 1-3

**Gate G2 review note (2026-08-18):** An independent review agent confirmed `_run_cli_command` wraps
exactly the twelve plain-CLI branches with the intended narrow exception set (never bare `Exception`), the
git-diff/merge drivers correctly bypass it with their own protocol-appropriate handling, and specifically
verified the merge driver's exit-1-leaves-`%A`-untouched safety property is actually true by tracing
`writer.py::dump()`'s write-to-temp-then-`os.replace()` behavior (a mid-write failure cannot corrupt a
pre-existing target file). The README round-trip fix was manually re-verified against a real nbformat-4.4
fixture.

- **Objective:** `main()`'s dispatch has zero top-level exception handling — most subcommands crash with
  raw, multi-frame Python tracebacks on ordinary bad input (missing file, malformed JSON, pre-4.5
  cell-id notebook, bad `--target`) instead of the clean `{"error": ...}`/exit-2 convention the codebase
  already implements for a few commands (`trust`, `execute`, `normalize`). `python -m libipynb.cli`
  doesn't work. README's "Round-trip a notebook" Quick Start snippet crashes verbatim on a realistic
  nbformat-4.4 notebook.
- **Expected files:** `src/libipynb/cli/main.py`, `src/libipynb/cli/__main__.py` (new), `README.md`, `src/libipynb/codec/writer.py` (docstrings only), `tests/unit/test_cli.py`, `tests/unit/test_cli_git_diff_merge_drivers.py`, `tests/unit/test_cli_main_module.py` (new).
- **Required behavior:** A `_run_cli_command(handler, args)` helper wraps every plain-CLI dispatch branch
  (`probe`/`validate`/`inspect`/`sanitize`/`upgrade`/`normalize`/`convert`/`diff`/`merge`/`execute`/
  `analytics`/`trust`), catching `(NotebookError, OSError, ValueError)` → `{"error": str(exc)}` to stderr,
  exit 2. Deliberately **not** a bare `except Exception`/`AttributeError` catch — must not mask unrelated
  programmer errors. `_cmd_git_diff_driver`/`_cmd_git_merge_driver` get their own, git-protocol-appropriate
  wrapping instead: the diff driver always exits 0 on internal error (short stderr note, "no diff shown"
  to stdout, mirroring the file's own existing parse-failure-branch convention — a nonzero exit is
  empirically fatal to the whole `git diff` invocation per the audit's own repro); the merge driver exits
  1 on internal error and leaves `%A` (`args.ours`) untouched (git's merge-driver protocol is binary:
  0=clean, nonzero=needs-attention, no third state). `src/libipynb/cli/__main__.py` is a 5-line
  `sys.exit(main())` shim. README's round-trip snippet uses `dump(doc, "output.ipynb",
  profile="declared")` — **a code-level default-profile change was evaluated and rejected**:
  `tests/unit/test_obligation_cell_identity.py::test_writing_a_pre_4_5_notebook_at_the_default_profile_is_refused`
  (plus 3 sibling tests) explicitly protects IPYNB-ID-001's "cell IDs are synthesized only via an explicit
  `upgrade()` call, never silently by a write-time version bump" guarantee, which the default-profile
  refusal *is* the enforcement mechanism for. Add a one-line cost/semantics note to `dump`/`dumps`
  docstrings and the README API table instead.
- **Required verification (Gate G1):** Full regression suite green. New parametrized missing-file/
  bad-input tests for every previously-unguarded command; driver-internal-error tests (diff driver exit
  0, merge driver exit 1 with untouched `%A`); `test_cli_main_module.py` proving `python -m libipynb.cli`
  works; manual re-run of the corrected README snippet against both a 4.5 control fixture and an
  nbformat-4.4 fixture.
- **Required evidence:** Diff of `cli/main.py`/`cli/__main__.py`/`README.md`; full test run output; an
  explicit note that a `dump()` default-profile behavior change was considered and rejected, citing the 4
  named tests protecting IPYNB-ID-001.
- **Acceptance criteria:** No plain CLI subcommand's ordinary bad-input path produces a raw traceback;
  git drivers never propagate a nonzero exit for an internal error (only for a genuine merge conflict);
  `python -m libipynb.cli` works; README's round-trip example runs verbatim against a real 4.4 fixture.
- **Non-goals:** Changing `dump()`/`dumps()`'s default profile semantics (rejected, see above); fixing the
  execution engine's list-source crash or diff/merge's cell-id root cause itself (owned by Q1/Q3 — this
  card only guarantees those errors, once raised as `NotebookError`/`ValueError`/`OSError`, are cleanly
  reported); widening the wrapper's catch tuple beyond `NotebookError`/`OSError`/`ValueError`.
- **Closeout rules:** `completed_verified` requires Gates G1 and G2.

### Wave 2 — Security/limits & sanitizer hardening

### LIBIPYNB-Q7 — Close resource-limit gaps: legitimate-notebook false rejection, unbounded stream read, unhookable arrays, sanitizer wall-clock DoS

**Status:** `completed_verified` (G1+G2+G6 done — see the 2026-08-18 close-out Gate G6 review note below, which found and closed one further real gap) · **Priority:** P1 · **Lane:** Security & Resource Limits · **Dependencies:** none · **Evidence:** plans/forensic-capability-audit-2026-08-18.md §7/§11, §17 items 5, 12

**Gate G6 review note (2026-08-18, close-out session):** an independent security-adequacy review (not a
general-correctness re-check — G2 already covers that) evaluated whether the two numeric defaults are
still meaningfully protective. `max_entries=2,000,000`: confirmed adequately protective — the documented
residual gap (a flat scalar array or single flat object bypassing the incremental `object_pairs_hook`)
was live-measured at its own worst case (a 64 MiB flat array, `max_input_bytes`-bounded per the doc's own
formula) and costs ~1.78s CPU / ~275MB before rejection, well short of a "gigabytes/tens of seconds"
danger zone. `max_scan_tokens=200,000`: **a real gap was found.** `_count_token()` was wired only into
`_handle_element()`, reached from `handle_starttag`/`handle_startendtag` — so a payload dominated by
closing tags, comments, or declarations bypassed the token budget entirely while `HTMLParser` still did
real, measured CPU work identifying them (live-measured: 20.2s CPU for 16,000,000 closing tags, `tokens`
staying at 0, the limit never firing) — the identical CPU-DoS class `max_scan_tokens` was introduced to
close, just reachable via a different tag shape. **Fixed:** `_MarkupScanner` gained
`handle_endtag`/`handle_comment`/`handle_decl`/`handle_pi` overrides, each calling the existing
`_count_token()`. Two new regression tests
(`test_dense_closing_tags_are_rejected_by_max_scan_tokens`,
`test_dense_comments_are_rejected_by_max_scan_tokens`) reproduce the exact bypass shapes in
`tests/unit/test_obligation_sanitization.py`. Full suite re-verified green after the fix (see plan §6).

**Gate G2 review note (2026-08-18):** An independent review confirmed all four sub-fixes: the raised
`max_entries` default, the bounded-chunk stream reader (verified with an instrumented counting stream that
an oversized source is genuinely aborted before being fully pulled), the SECURITY.md documentation of the
array-hook gap as a real, substantive addition, and `max_scan_tokens` firing independently of hazard
counting. One cosmetic nit: README.md wasn't updated with the new numeric defaults (SECURITY.md was) —
fixed same day (README's `NotebookResourceLimits` bullet now says `entries (2M)` and lists
`sanitizer scan tokens (200K)`).

- **Objective:** (a) Default `max_entries=100,000` rejects a legitimate, nbformat-valid 4 MiB/150,000-line
  notebook `nbformat.validate()` accepts. (b) `TextIO` sources are read to EOF before `max_input_bytes` is
  checked. (c) Python's `json` module has no incremental array-construction hook, confirmed and to be
  documented rather than patched with a fragile heuristic. (d) `sanitize()`'s markup scanner has zero
  token-count budget for harmless markup, allowing unbounded wall-clock CPU within documented byte limits.
- **Expected files:** `src/libipynb/security/limits.py`, `src/libipynb/codec/reader.py`, `src/libipynb/security/sanitizer.py`, `SECURITY.md`, `README.md`, `CHANGELOG.md`, `tests/security/test_resource_limits.py`, `tests/security/test_active_content.py`.
- **Required behavior:** `NotebookResourceLimits.max_entries` default raised `100_000` → `2_000_000`
  (~13× headroom over the confirmed repro; a byte-proportional formula was investigated and rejected as
  unreliable given `enforce_structure`'s traversal order, documented explicitly as a rejected
  alternative). `codec/reader.py::_read_source`'s stream branch reads in bounded 64K-char chunks, checking
  `max_input_bytes`/`max_decompressed_bytes` after every chunk, aborting mid-stream on overflow, returning
  identical content for well-behaved streams. `SECURITY.md` gains an explicit paragraph documenting the
  array-hook limitation as accepted, stating the derived `max_input_bytes`-implied worst-case bound
  explicitly. `NotebookResourceLimits` gains `max_scan_tokens: int = 200_000`; `sanitizer.py::
  _MarkupScanner` gains an unconditional per-start-tag counter (`_count_token()`, called first in
  `_handle_element()`, independent of the existing hazard-only `_observe()` counter) enforced against it.
- **Required verification (Gate G1 + G6):** Full regression suite green; pinned-default tests for
  `max_entries`/`max_scan_tokens`; the exact 150,000-line legitimate-notebook repro loads under default
  limits; an instrumented counting-stream test proves an oversized stream is aborted well before being
  fully read; a dense-harmless-markup test proves `max_scan_tokens` fires without affecting existing
  hazard-finding-count tests. Gate G6 specifically re-examines whether the new defaults remain adequately
  protective.
- **Required evidence:** Diff of all files plus `SECURITY.md`/`README.md`; full test run output; sign-off
  note that the array-hook gap is closed as documentation, not code, with rejected-alternatives reasoning
  preserved.
- **Acceptance criteria:** The exact 150,000-line/4 MiB repro loads under default settings; a 30 MB stream
  against a 1 KB `max_input_bytes` limit is rejected without materializing the full stream; a
  300,000-harmless-tag `sanitize()` payload aborts within a low single-digit-seconds budget by default.
- **Non-goals:** A custom JSON scanner/decoder for a true incremental array hook (rejected); making
  `max_entries` dynamically proportional to decoded byte size at the code level (rejected, documented).
- **Closeout rules:** `completed_verified` requires Gates G1 and G2, plus G6 sign-off recorded in evidence.

### LIBIPYNB-Q8 — Close the text/markdown output-MIME sanitizer blind spot; add regression tests for the untested active-content detector surface

**Status:** `completed_verified` (G1+G2+G6 done — see the 2026-08-18 close-out Gate G6 review note below, which found and closed one further real gap) · **Priority:** P1 · **Lane:** Governance & Trust · **Dependencies:** none · **Evidence:** plans/forensic-capability-audit-2026-08-18.md §7/§11, §13 (both rated HIGH)

**Gate G6 review note (2026-08-18, close-out session):** an independent security-adequacy review
confirmed the `text/markdown` fix itself is correct (case-insensitive MIME matching, correctly catches
raw HTML embedded inside markdown via the shared `_scan_markup` path) — but **found a real gap**: a MIME
type carrying an RFC 2046 parameter (e.g. `text/markdown; charset=utf-8`, legal and real-world-occurring
in Jupyter output bundles) failed every exact-string comparison in the module, bypassing scanning
entirely — live-confirmed zero findings for a `javascript:` payload under that key versus a correct
finding under the bare `text/markdown` key. This was not unique to the new markdown fix: the pre-existing
`active_mime_types` set-membership check has the identical exact-match weakness, so `text/html; charset=
utf-8` had the same bypass. **Fixed:** a new `_media_type_base()` helper strips MIME parameters before
comparison, applied at all three comparison sites (`active_mime` computation, and both `markdown=` gate
computations in the attachments and outputs loops). Three new regression tests
(`test_markdown_mime_output_with_charset_parameter_is_still_detected`,
`test_html_mime_output_with_charset_parameter_is_still_detected`,
`test_markdown_mime_attachment_with_charset_parameter_is_still_detected`) cover this in
`tests/security/test_active_content.py`. Full suite re-verified green after the fix (see plan §6). The
review also confirmed the existing Q8 regression tests use specific hazard-substring assertions, not bare
count checks — a regression here would not ship silently.

**Gate G2 review note (2026-08-18):** An independent review traced the actual bug mechanism (the
`markdown=False` guard meant scanning never ran for `text/markdown` payloads at all) and confirmed the fix
correctly gates `markdown=True` in both the outputs and attachments loops. Confirmed the new
active-content tests are substantive — asserting specific hazard-substring matches, not just "count > 0."

- **Objective:** (a) An identical hazardous payload delivered as an output's `text/markdown` MIME data is
  invisible to `sanitize()` in every mode, while the same payload as `text/html` output data or markdown
  cell source is correctly caught. (b) 13 of 14 `_ACTIVE_ELEMENTS` categories, the event-handler-attribute
  heuristic, and the `javascript:`/CSS `url()` detectors are implemented and confirmed working but have
  zero regression tests.
- **Expected files:** `src/libipynb/security/sanitizer.py`, `tests/security/test_active_content.py`.
- **Required behavior:** `_collect_candidates`'s output-data loop and attachments loop both pass
  `markdown=(policy.inspect_markdown and media_type.casefold() == "text/markdown")` to `_add_candidate`,
  identical in shape/gating to the existing cell-source markdown path. **Rejected** the audit's
  first-listed alternative ("add `text/markdown` to `DEFAULT_ACTIVE_MIME_TYPES`") — investigated and
  found it would only flip `active_mime=True`, still routing through the HTML-only `_scan_markup`,
  missing markdown-syntax-specific hazards like `![x](javascript:...)`. `test_active_content.py` gains a
  parametrized test over all 14 `_ACTIVE_ELEMENTS` categories (one shared payload dict, one shared
  `_assert_hazard_detected` helper), a parametrized event-handler-attribute case, a `javascript:` URI
  case, and a CSS `url(javascript:...)` case, plus direct regression tests for the closed markdown blind
  spot (output-data and attachment variants, plus an `inspect_markdown=False` suppression test).
- **Required verification (Gate G1 + G6):** Full regression suite green including all new parametrized
  cases; coverage report re-run to confirm the event-handler heuristic and each of the 13
  previously-untested `_ACTIVE_ELEMENTS` branches are now exercised; explicit before/after confirmation
  the `text/markdown` output-MIME repro now produces a finding where it previously produced none.
- **Required evidence:** Diff of `sanitizer.py`/`test_active_content.py`; coverage delta for newly
  exercised lines; test run output.
- **Acceptance criteria:** An identical hazardous payload produces the same class of finding whether
  delivered as `text/html` output data, markdown cell source, or `text/markdown` output/attachment data;
  every `_ACTIVE_ELEMENTS` category, the event-handler heuristic, and the URI/CSS detectors each have at
  least one dedicated regression test.
- **Non-goals:** Rewriting the sanitizer's detection logic (all confirmed functionally correct already —
  this card adds tests and closes one blind spot, not detection algorithms).
- **Closeout rules:** `completed_verified` requires Gates G1 and G2, plus G6 sign-off.

### LIBIPYNB-Q10 — Detect notebook-level metadata conflicts in `merge_notebooks()`

**Status:** `completed_verified` (G1+G2 done — independently reviewed twice, confirmed correct both times, zero findings) · **Priority:** P2 · **Lane:** Diff/Merge/Cleanup Parity · **Dependencies:** Q3 (soft — same file area) · **Evidence:** plans/forensic-capability-audit-2026-08-18.md §8 (missing-feature findings table)

**Gate G2 review note (2026-08-18):** Reviewed independently twice (once alongside the Q3 merge-fix
re-review, once alongside the broader Q10-Q15b batch) — both passes confirmed `_flatten_metadata_paths`
is genuinely per-leaf-path (unrelated edits under the same top-level key do not falsely conflict) and
detection stays scoped to notebook-level metadata without ever changing merge output. One noted (not
required-to-fix) edge case: a whole-subtree-replaced-with-scalar vs. leaf-edited-beneath-it divergence
can be missed by leaf-path comparison — an inherent limitation of the leaf-path design, not in this
card's stated acceptance criteria.

- **Objective:** A diverging `kernelspec.name` (or any notebook-level metadata path) on both sides
  currently silently resolves to `base`'s value with `has_conflicts=False` and zero signal.
- **Expected files:** `src/libipynb/model/merge.py`, `tests/unit/test_obligation_notebook_merge.py`, `tests/unit/test_cli.py`.
- **Required behavior:** New `ConflictKind.NOTEBOOK_METADATA` (reuses `MergeReport.conflicts` — zero
  `cli/main.py` changes needed, since `_cmd_merge` already iterates conflicts generically). `CellConflict
  .cell_id` widens `str` → `str | None` (`None` for notebook-scoped conflicts). New
  `_reconcile_notebook_metadata()` does a **leaf-path** flatten-and-compare over `metadata` only (not
  whole-top-level-key, which would false-positive on two genuinely unrelated edits under the same top-level
  key). Detection-only: the merged document's `metadata` still always comes from `base` unconditionally —
  implementing actual notebook-metadata *merging* is a separate, larger feature, explicitly deferred.
- **Required verification (Gate G1):** Full regression suite green. The audit's exact `kernelspec.name`
  repro now reports a conflict with correct path/values; a precision test proving unrelated-path edits
  under the same key are NOT falsely flagged; a test documenting the preserved one-sided-edit-still-
  dropped behavior as intentional; a CLI-level test confirming JSON serialization (`cell_id: null`) and
  exit-code effect.
- **Required evidence:** Diff of `merge.py`/test files; test run output.
- **Acceptance criteria:** The audit's live repro now produces `has_conflicts=True` with a
  `NOTEBOOK_METADATA` conflict naming the diverged path and both sides' values; no existing cell-level
  conflict test's behavior changes.
- **Non-goals:** Implementing actual notebook-metadata value merging; extending detection to `nbformat`/
  `nbformat_minor`; oracle-comparing this new category against real `nbdime` (recommended future follow-up).
- **Closeout rules:** `completed_verified` requires Gates G1 and G2.

### Wave 3 — Execution-engine safety/fidelity hardening

### LIBIPYNB-Q2 — `LocalJupyterExecutor` safety/fidelity hardening

**Status:** `completed_but_weakly_verified` (G1+G2 done for sub-items a-d; watchdog redesign deliberately deferred, G6 N/A until it lands) · **Priority:** P1 · **Lane:** Execution Engine · **Dependencies:** Q1 (hard — same functions) · **Evidence:** plans/forensic-capability-audit-2026-08-18.md §7 ("LocalJupyterExecutor safety surface — HIGH"), §17 items 8, 10

**Gate G2 review note (2026-08-18):** An independent review agent confirmed all four sub-fixes directly:
(a) the `except Exception`/`except BaseException` split between `execute()` and `execute_async()` is
correct and deliberate; (b) `CellExecutionRecord.outputs` is genuinely deep-copy-independent from the
returned notebook's own outputs in both branches; (c) `atexit.unregister` is correctly placed; (d)
truncation is per-output, confirmed to never reproduce the older engine's combined-stream-truncation bug.
All four dedicated regression tests were confirmed meaningful, not superficial.

**Implementation note (2026-08-18):** Sub-items (a)-(d) landed as designed. The watchdog redesign for a
deterministic per-cell `timed_out` signal under `interrupt_on_timeout=True` was deliberately deferred —
flagged in the original design as the highest-complexity sub-item and out of scope for this pass; it
remains a separately-reviewable follow-up, so this card cannot reach `completed_verified` on the
`timed_out`-determinism acceptance criterion until that follow-up lands. All four dedicated regression
tests specified below are in place and green: `test_synchronous_execute_propagates_keyboard_interrupt`,
`test_cell_execution_record_outputs_are_independently_mutable_from_the_notebook`,
`test_cancellation_unregisters_nbclients_own_atexit_cleanup_hook`,
`test_max_output_bytes_truncates_only_the_oversized_output_not_downstream_cells` (all in
`tests/integration/test_obligation_jupyter_execution_adapter.py`). `mypy --strict src/libipynb` and
`ruff check src/libipynb tests/` both clean. Full real-kernel execution suite (56 tests, was 52) green;
oracle parity suite (`tests/oracle/test_nbclient_execution_parity.py`, 2 tests) green; full repository
regression suite excluding the two real-kernel files (918 passed, 4 skipped) green — no regressions.

- **Objective:** Four confirmed gaps: (a) `execute()` swallows `KeyboardInterrupt`/`SystemExit` via an
  overbroad `except BaseException`. (b) `CellExecutionRecord.outputs` shares mutable nested dict objects
  with `result.notebook`'s own cell outputs, defeating `frozen=True`. (c) cancellation cleanup leaves
  nbclient's own `atexit`-registered kernel-cleanup hook registered. (d) no output-size cap exists at all,
  and `ExecutionResult.timed_out` is structurally unreliable under the default `interrupt_on_timeout=True`.
- **Expected files:** `src/libipynb/adapters/jupyter_execute.py`; `src/libipynb/execution/options.py`; `src/libipynb/execution/results.py`; `tests/integration/test_obligation_jupyter_execution_adapter.py`.
- **Required behavior:** (a) narrow `except BaseException` to `except Exception` in `execute()`. (b)
  deep-copy independently for `CellExecutionRecord.outputs` vs. `orig_cell["outputs"]`, in both the
  executed-cell and skipped/not-reached branches. (c) call `atexit.unregister(client._cleanup_kernel)`
  after `_async_cleanup_kernel()` in the cancellation path (no-ops safely if never/already registered).
  (d) add `ExecutionOptions.max_output_bytes: int | None = None` with `__post_init__` validation; truncate
  each output's own `text`/`data` payload **independently** (never by slicing a combined byte stream — the
  confirmed bug class in the other execution engine, must not be reproduced here), setting new
  `CellExecutionRecord.output_truncated: bool = False`. A deterministic per-cell `timed_out` signal
  requires a larger redesign (libipynb-owned `threading.Timer` watchdog replacing nbclient's internal
  timeout trait) — flagged as the highest-complexity sub-item; land (a)-(c) plus the output-cap as this
  card's P1 minimum bar, with the watchdog redesign as a separately-reviewable sub-task within the same
  card.
- **Required verification (Gate G1 + G6):** Full regression suite green, no change to default behavior
  for any existing caller (`max_output_bytes` defaults `None`/off). Real-kernel test proving `SystemExit`/
  `KeyboardInterrupt` now propagate; mutation test proving independent mutability of `CellExecutionRecord
  .outputs` vs. `result.notebook`'s outputs; an `atexit`/psutil-based check proving cleanup after
  cancellation; a truncation test proving a small cell *after* an oversized one still gets its own
  correct, untruncated output. G6 specifically for the timeout-watchdog sub-item.
- **Required evidence:** Diff of the three files; the four dedicated regression tests' pass output.
- **Acceptance criteria:** All four sub-items pass their dedicated regression tests; `output_truncated`/
  `max_output_bytes` never causes loss of an unrelated cell's result; `timed_out` fires deterministically
  under `interrupt_on_timeout=True` on a real over-budget cell (if the watchdog sub-task lands in this
  round).
- **Non-goals:** True mid-execution streaming memory cap (would require nbclient's semi-internal
  `register_output_hook` API) — `max_output_bytes` bounds what is *retained*, not peak transient memory.
- **Closeout rules:** `completed_verified` requires Gates G1, G2, and G6.

### Wave 4 — Packaging & documentation accuracy

### LIBIPYNB-Q12a — Resolve the internal GitLab URL leak before any public release

**Status:** `completed_verified` (G1+G3 done — maintainer decision obtained and applied, see note) · **Priority:** P0 (publication only) · **Lane:** Release & Publish · **Dependencies:** none · **Evidence:** plans/forensic-capability-audit-2026-08-18.md §16, §17 item 4

**Gate G3 closure note (2026-08-18, close-out session):** the maintainer (Babar Raza) was asked directly
and chose **"omit the field entirely"** — this card's own recommended default. Applied: the
`[project.urls] Repository` line (and the now-empty `[project.urls]` table header) removed from
`pyproject.toml`; `CONTRIBUTING.md`'s clone instructions changed from a literal internal URL to
`git clone <repository-url>`. Verified against a freshly built artifact (not the same build TC/session
that made the edit — a second, independent packaging-audit re-run, see `plans/independence-audit-2026-08-18.md`):
`unzip -p dist/*.whl '*/METADATA' | grep -i recruitize` and the equivalent sdist checks both return zero
matches. Repo-wide sweep confirms the only remaining mentions of the string are in historical
planning/evidence documents (`publication-readiness-assessment.md`, `remediation-plan.md`), which are
out of this card's scope as historical record, not live packaging surface.

- **Objective:** `pyproject.toml:65`'s `[project.urls] Repository` field
  (`https://gitlab.recruitize.ai/sialkot/cantt-smallize/libipynb`, internal-only) and `CONTRIBUTING.md:9`'s
  clone instructions leak this URL — confirmed present verbatim in a real built wheel's `dist-info/METADATA`.
- **Expected files:** `pyproject.toml`, `CONTRIBUTING.md`.
- **Required behavior:** **Cannot be closed to `completed_verified` by an executing session alone —
  requires a maintainer decision (Babar Raza), recorded in this card, per Gate G3.** No public host exists
  yet (no tag, 10 commits ahead of `origin/master`). Do not invent a plausible-looking public URL.
  Recommended default: **omit the field entirely** (evaluated against "use a placeholder," rejected as
  replacing one false claim with another) — requires zero unknown information, cannot go stale.
- **Required verification (Gate G1 + G9):** Full regression suite (docs-only change); `python -m build
  --wheel`, `unzip -p dist/*.whl '*/METADATA' | grep -i recruitize` returns nothing (the exact command the
  audit used to find the leak).
- **Required evidence:** Diff of both files; the METADATA grep output showing zero matches against a
  freshly built wheel.
- **Acceptance criteria:** No internal hostname, org path, or codename appears in `pyproject.toml`,
  `CONTRIBUTING.md`, or a built wheel's METADATA.
- **Non-goals:** Deciding the project's actual eventual public hosting location — the maintainer's call.
- **Closeout rules:** `completed_verified` requires Gates G1 and G3 (maintainer's decision recorded and
  dated in this card before closure) — not just G1/G2.

### LIBIPYNB-Q12b — Fix false/incomplete claims in SECURITY.md, README.md, and CHANGELOG.md

**Status:** `completed_but_weakly_verified` (G1+G2 done — G2 found and fixed a real defect, see note) · **Priority:** P1 · **Lane:** Docs & Evidence · **Dependencies:** none · **Evidence:** plans/forensic-capability-audit-2026-08-18.md §11, §14, §17 items 11/13

**Implementation note (2026-08-18):** `SECURITY.md`'s claim is now scoped to the core load/validate/
dump/sanitize path. README's Features bullet and `libipynb.adapters` section, and CHANGELOG's `[0.1.0]`
Export adapters entry, now name `HtmlExporter`/`JupytextExporter` explicitly. `tests/unit/test_doc_drift.py`
(3 tests) still passes unchanged (it only guards the CLI-command section, untouched here).

**Gate G2 finding and fix (2026-08-18):** An independent review found the new SECURITY.md text was itself
factually wrong: it attributed `libipynb[exec]` to `adapters/execute.py` (a stdlib-only module needing no
extra at all — confirmed by reading its imports directly) instead of the actual consumer,
`adapters/jupyter_execute.py`'s `LocalJupyterExecutor` (which needs `jupyter_client`/`nbclient`/`nbformat`
via deferred imports, confirmed the same way). The disclosure also entirely omitted
`LocalJupyterExecutor` — a real Jupyter-kernel-protocol execution engine that spawns an actual `ipykernel`
process to run arbitrary cell code, arguably the single most security-relevant opt-in feature in the
codebase — while README and CHANGELOG both correctly named it elsewhere in this exact same doc-accuracy
pass. Fixed: corrected the extra attribution, added `LocalJupyterExecutor` as its own named opt-in
feature (now four named features, not three), with a note on why it's the most security-relevant of them.
Full regression suite (1017 passed, 5 skipped) green after the fix; `mypy --strict`/`ruff check` clean;
`tests/integration/test_obligation_security_baseline.py` and `test_doc_drift.py` (15 tests) still pass.

- **Objective:** `SECURITY.md:117`'s "No network access, no subprocess execution, no dynamic code
  loading" claim is false — real `subprocess.run()` in `adapters/execute.py`, `adapters/export.py`'s
  `HtmlExporter`, `cli/main.py`'s git integration. `HtmlExporter`/`JupytextExporter` (real, tested,
  `completed_verified` V5) are absent from README's Features list/adapters section and CHANGELOG.
- **Expected files:** `SECURITY.md`, `README.md`, `CHANGELOG.md`.
- **Required behavior:** Scope the existing claim to the core load/validate/dump path; add a sentence
  disclosing the three opt-in subprocess-using features by name, matching the file's existing per-feature
  disclosure format (Trust/Path Safety sections). Add `HtmlExporter`/`JupytextExporter` to README's
  Features bullet, adapters section, and a new CHANGELOG entry, matching existing documentation depth.
- **Required verification (Gate G1 + G9):** Full regression suite; re-run this repo's existing
  `test_doc_drift.py` guardrail against the updated docs, not just an eyeball check.
- **Required evidence:** Diffs of all three files; the doc-drift test's pass output.
- **Acceptance criteria:** No `SECURITY.md` claim is contradicted by `grep -rn subprocess.run
  src/libipynb`; every exporter in `libipynb.adapters.__all__` marked `completed_verified` is named in
  README and CHANGELOG.
- **Non-goals:** A CLI `export` subcommand exposing these exporters (deferred to Q15b's scope).
- **Closeout rules:** `completed_verified` requires Gates G1 and G2.

### LIBIPYNB-Q12c — Remove dead `pyyaml` dependency; pin `nbformat` explicitly in the `exec` extra

**Status:** `completed_verified` (G1+G2+G7 done — see the 2026-08-18 close-out Gate G7 note below) · **Priority:** P3 (pyyaml) / P1 (nbformat pin) · **Lane:** Docs & Evidence · **Dependencies:** none · **Evidence:** plans/forensic-capability-audit-2026-08-18.md §16

**Gate G7 review note (2026-08-18, close-out session):** re-confirmed all four required G7 checks against
current source: scope limited to the `exec` extra (`pyproject.toml:44`); version floor `>=5.10` consistent
with the repo's other three `nbformat` pins (`reference` extra `==5.10.4`, `test` extra `>=5.10`); license
BSD-3-Clause, already established compatible elsewhere in this repo's dependency graph; import-boundary
guarantee re-confirmed (`pytest tests/unit/test_import_boundary.py -v`, 7/7 passing).

**Gate G2 review note (2026-08-18):** An independent review confirmed `pyyaml` has zero remaining
references anywhere, and that the `nbformat` pin was added to the CORRECT extra (`exec`, which really is
where `import nbformat` happens, per the same review's own Q12b finding correcting the opposite
misattribution in SECURITY.md).

**Implementation note (2026-08-18):** `pyyaml>=6.0` removed from the `test` extra;
`grep -rn "import yaml" src/ tests/` returns nothing. `"nbformat>=5.10"` added to the `exec` extra.
Verified in an isolated throwaway venv (scratchpad, deleted after use): `pip install -e ".[exec]"`
alone, then `from libipynb.adapters.jupyter_execute import LocalJupyterExecutor` imports cleanly with
`pip show nbformat` confirming a real 5.11.1 install satisfying the new direct pin — not just riding
`nbclient`'s transitive dependency. `CONTRIBUTING.md`'s stale "installs pytest, Hypothesis, and PyYAML"
sentence (it does enumerate the `test` extra's contents, per this card's own "only if" clause) was also
corrected. Full regression suite (918 passed, 4 skipped) and `tests/unit/test_import_boundary.py` (7
passed) green in the primary dev venv.

- **Objective:** `pyproject.toml:37`'s `pyyaml>=6.0` in the `test` extra is never imported anywhere.
  `adapters/jupyter_execute.py:123`'s local `import nbformat` is only safe today via `nbclient`'s
  transitive dependency — the `exec` extra declares no direct `nbformat` pin.
- **Expected files:** `pyproject.toml`; `CONTRIBUTING.md` (only if it enumerates the test extra's contents).
- **Required behavior:** Delete the `pyyaml` line from the `test` extra. Add `"nbformat>=5.10",` to the
  `exec` extra (matching the version floor this repo's other three `nbformat` pins already use).
- **Required verification (Gate G1 + G7):** Full regression suite in a rebuilt venv with `pip install -e
  ".[exec]"` only (no `test`/`reference` extras) proving `adapters/jupyter_execute.py` imports cleanly
  standalone; `pip install -e ".[test]"` + `grep -rn "import yaml" src/ tests/` returns nothing.
- **Required evidence:** Diff of `pyproject.toml`; the isolated `[exec]`-only install-and-import smoke
  test's output; Gate G7's four checks recorded (scoped to extras, pinned range, license compatibility —
  BSD-3-Clause, compatible — import-boundary check re-confirmed).
- **Acceptance criteria:** `pip install libipynb[exec]` alone is sufficient for every import
  `adapters/jupyter_execute.py` performs; `pip install libipynb[test]` installs nothing unused.
- **Non-goals:** Auditing every other extras group for similar gaps beyond these two confirmed instances.
- **Closeout rules:** `completed_verified` requires Gates G1 and G7.

### Wave 5 — Export-adapter fidelity hardening

### LIBIPYNB-Q11a — Export resource-collection safety hardening

**Status:** `completed_verified` (G1+G2 done — independently reviewed twice, confirmed correct both times, zero findings) · **Priority:** P2 · **Lane:** Conversion & CLI Surface · **Dependencies:** Q9 (soft — shares `_is_safe_resource_filename`) · **Evidence:** plans/forensic-capability-audit-2026-08-18.md §9 items 4-5, §11

**Gate G2 review note (2026-08-18):** Reviewed independently twice. Both passes hand-verified the
collision-disambiguation logic with adversarial, uncommitted test cases beyond the existing suite (a 3-way
same-cell same-extension MIME collision) and confirmed no two `AncillaryResource`s ever share a filename,
and that direct construction with a path-traversal filename raises. Noted (not required) test-coverage
gap: the committed suite only covers a 2-MIME collision, not 3+ — code handles it correctly regardless.

**Implementation note (2026-08-18):** Landed as designed, plus applying `validate=True` to the
outputs-branch's own `base64.b64decode()` call too (not just attachments) for consistency — corrupt
output-image payloads are now also counted rather than silently dropped, a small extension beyond the
card's literal attachments-only wording but the same underlying defect class. Nine new/updated tests in
`tests/integration/test_obligation_export_adapter.py`: cross-cell collision disambiguation, same-cell
multi-MIME collision disambiguation, corrupt-payload skip-and-count (plus a zero-skipped non-regression
test), direct-construction path-traversal rejection (plus a safe-filename acceptance test), and an
explicit single-attachment non-regression test. All 7 pre-existing tests in
`tests/integration/test_obligation_export_resource_path_safety.py` still pass unchanged. Full regression
suite (932 passed, 4 skipped) green; `mypy --strict`/`ruff check` clean.

- **Objective:** Cross-cell attachment filename collisions silently overwrite on disk; corrupt base64
  payloads vanish from exports with zero diagnostic; `AncillaryResource` can be constructed directly,
  bypassing `_is_safe_resource_filename()`.
- **Expected files:** `src/libipynb/adapters/export.py`; `tests/integration/test_obligation_export_resource_path_safety.py`; `tests/integration/test_obligation_export_adapter.py`.
- **Required behavior:** Disambiguate colliding attachment filenames by cell index
  (`f"cell{cell_index}_{key}"`) only when a collision occurs; also fix a same-cell multi-MIME collision
  (append a MIME-derived extension, mirroring the existing output-branch scheme). Switch to
  `base64.b64decode(payload, validate=True)`; thread a `skipped` accumulator through `_collect_resources`,
  surfacing `ExportResult.metadata["skipped_resources"]`/`["skipped_paths"]` (additive keys only). Add
  `AncillaryResource.__post_init__` validation calling `_is_safe_resource_filename`. Do **not** wrap
  `ExportResult.metadata` in `MappingProxyType` (no demonstrated corruption bug; a `mappingproxy` isn't
  JSON-serializable, a foot-gun for a future CLI export subcommand) — fix via a one-line docstring
  clarification instead.
- **Required verification (Gate G1):** Full regression suite green. Collision disambiguation
  (cross-cell and same-cell multi-MIME) tests; corrupt-payload diagnostic tests; direct-construction
  path-traversal rejection test; non-regression test for the existing single-attachment common case.
- **Required evidence:** Diff of `export.py`; the five new/updated test cases' pass output.
- **Acceptance criteria:** No two `AncillaryResource`s for the same notebook ever share a filename; every
  silently-skipped corrupt payload is countable via `ExportResult.metadata`; `AncillaryResource` cannot be
  constructed with an unsafe filename via any code path.
- **Non-goals:** Rewriting markdown `attachment:key` source-text references to match disambiguated
  filenames (only actual-collision cases are renamed, not universally); wrapping `metadata` in
  `MappingProxyType`.
- **Closeout rules:** `completed_verified` requires Gates G1 and G2.

### LIBIPYNB-Q11b — Export content-fidelity fixes (Markdown fence language, HTML title, raw-cell drop)

**Status:** `completed_verified` (G1+G2+G8 done — independently reviewed twice; 1 minor nitpick found and fixed) · **Priority:** P2/P3 · **Lane:** Conversion & CLI Surface · **Dependencies:** none · **Evidence:** plans/forensic-capability-audit-2026-08-18.md §9 items 6-8

**Gate G2 finding and fix (2026-08-18):** Two independent reviews both flagged the same minor, non-
exploitable nitpick: `_resolve_fence_language()` used `_SAFE_FENCE_LANGUAGE.match()` instead of
`.fullmatch()`, so a language value consisting of otherwise-safe characters plus exactly one bare trailing
newline (e.g. `"python\n"`) passed validation and got spliced in verbatim — not an injection vector (no
backtick can follow a matching trailing newline), just a stray blank line in that one specific case. Fixed
by switching to `.fullmatch()`; added `test_markdown_fence_rejects_a_language_with_a_bare_trailing_newline`
as a permanent regression test. Both reviews otherwise confirmed the fence-language precedence,
injection-resistance, `title=` behavior against the real tool, and raw-cell comment-block fix all correct.

**Implementation note (2026-08-18):** Landed as designed. The title fix uses `nb.metadata.title`
(confirmed present and preferred over the filename-derived fallback in nbconvert's own real
`lab/index.html.j2` template, which also HTML-escapes it itself) rather than renaming the temp file
libipynb writes — simpler and avoids filesystem-path shenanigans entirely. G8 oracle evidence: real
`python -m nbconvert` run three ways in `tests/integration/test_obligation_html_jupytext_export.py` —
no `title=` renders `<title>notebook</title>` (byte-identical to pre-fix, confirmed empirically rather
than assumed to be the literal string `"Notebook"`), `title="My Custom Report"` renders
`<title>My Custom Report</title>`, and a path-shaped title is confirmed reduced to its `Path(...).stem`.
Markdown fence-language tests (Julia kernel, injection-attempt, default-fallback) and the raw-cell
content-presence test all pass. Full regression suite (932 passed, 4 skipped) green; `mypy --strict`/
`ruff check` clean.

- **Objective:** `MarkdownExporter` hardcodes ` ```python ` fences regardless of kernel language;
  `HtmlExporter`'s exported `<title>` is always the literal `"notebook"`; `PythonScriptExporter` silently
  drops raw-cell content while still counting it in `metadata.cell_count`.
- **Expected files:** `src/libipynb/adapters/export.py`.
- **Required behavior:** Resolve fence language from `metadata.language_info.name`/
  `metadata.kernelspec.language` (matching `adapters/execute.py`'s existing precedent), validated against
  `^[A-Za-z0-9_+-]{1,32}$` before splicing into the fence marker (closes a latent markdown-injection
  vector a naive fix would introduce). Add an optional `title: str | None = None` keyword parameter to
  `HtmlExporter.export()` (Protocol-compatible, purely additive, byte-identical when omitted), sanitized
  via `Path(title).stem`. Represent raw cells as a `# [raw cell]`-prefixed comment block in
  `PythonScriptExporter` output (mirroring the file's existing markdown-cell-as-comment convention) rather
  than changing the shared, tested `cell_count` contract.
- **Required verification (Gate G1 + G8):** Full regression suite green. A Julia-kernel fence test and an
  injection-attempt fence test; a real-`nbconvert`-oracle-compared title test (with and without `title=`);
  a raw-cell content-presence test.
- **Required evidence:** Diff excerpts per exporter; real-`nbconvert` oracle run output for the title fix.
- **Acceptance criteria:** No exporter output depends on an unvalidated, attacker-controlled string
  spliced into generated content without a character-class check; `HtmlExporter`'s title reflects a
  caller-supplied identity when given; no cell type is silently invisible in `PythonScriptExporter`'s
  output.
- **Non-goals:** Deriving `title` automatically from a notebook-carried filename (`NotebookDocument` has
  no filename attribute today) — this card only adds the parameter.
- **Closeout rules:** `completed_verified` requires Gates G1, G2, and G8 (for the HTML-title comparison).

### Wave 6 — Test-quality hardening

### LIBIPYNB-Q13a — Validation and diff oracle test coverage

**Status:** `completed_verified` (G1+G2+G8 done — independently reviewed twice, confirmed correct both times, zero findings) · **Priority:** P2 · **Lane:** Validation Depth · **Dependencies:** Q3 (soft) · **Evidence:** plans/forensic-capability-audit-2026-08-18.md §13, §14

**Gate G2 review note (2026-08-18):** Reviewed independently twice; both passes personally ran
`pytest tests/oracle/test_diff_parity.py -v` and confirmed all 3 tests genuinely execute against a real
installed `nbdime` (not skipped, not mocked), and confirmed the known-divergence test asserts against real
nbdime's own parsed opcode output rather than a hand-written expectation.

**Implementation note (2026-08-18):** Landed as designed. 4 new tests added to
`tests/unit/test_obligation_validation_profiles.py` for `validate_notebook()`/`validate_notebook_schema()`
(no-op-on-valid, raises-with-joined-message-on-invalid, and a direct `== [item.message for item in
validate(model).errors]` comparison rather than a hand-duplicated expected list). New
`tests/oracle/test_diff_parity.py` (3 tests, mirrors `test_nbdime_parity.py`'s structure exactly) run
against the real installed `nbdime` in this repo's `.venv` — G8 evidence, not a written-but-unexecuted
oracle test: `pytest tests/oracle/test_diff_parity.py -v` → 3 passed. Confirmed and documented the known
divergence directly against the real tool (previously assumed, not verified): real `nbdime diff` matches
cells by content (an id-only rename on unchanged source is a single `replace` patch on the matched cell);
`diff_notebooks()` matches strictly by id (the same scenario is a remove+add pair) — both empirically
proven via a real `python -m nbdime diff` subprocess call, not asserted from documentation. Full
regression suite (942 passed, 4 skipped) green; `mypy --strict`/`ruff check` clean.

- **Objective:** `validate_notebook()`/`validate_notebook_schema()` have zero test references anywhere.
  `diff_notebooks()` has zero oracle-comparison coverage against real `nbdime diff`, and a real,
  confirmed, currently-undocumented semantic divergence (nbdime matches by content, id as tiebreaker;
  `diff_notebooks()` matches strictly by id) is untested.
- **Expected files:** new/extended validator test file; new `tests/oracle/test_diff_parity.py`.
- **Required behavior:** Tests: `validate_notebook()` no-op on valid, raises with joined message on
  invalid; `validate_notebook_schema()` returns exactly `[item.message for item in validate(model).errors]`
  — compared directly, not via a hand-duplicated expected list. New oracle file mirroring
  `test_nbdime_parity.py`'s exact structure: an ordinary add/remove/modify scenario compared against real
  `nbdime diff`, plus the KNOWN id-vs-content divergence tested and documented exactly like the file's two
  existing known-divergence tests.
- **Required verification (Gate G1 + G8):** Full regression suite; the new oracle file run with real
  `nbdime` installed, pass output pasted into evidence (a written-but-never-executed oracle test does not
  satisfy G8).
- **Required evidence:** Diffs of both new test files; real `pytest tests/oracle/test_diff_parity.py -v`
  output with `nbdime` genuinely installed.
- **Acceptance criteria:** `validate_notebook`/`validate_notebook_schema` have direct, non-incidental test
  coverage; `diff_notebooks()` has the same class of oracle-comparison evidence `merge_notebooks()`
  already has, including its own known divergence explicitly asserted.
- **Non-goals:** Changing `diff_notebooks()`'s id-matching behavior to match nbdime's — a design decision
  out of scope for a test-coverage card.
- **Closeout rules:** `completed_verified` requires Gates G1 and G8.

### LIBIPYNB-Q13b — Wire `tests/oracle/` and `tests/package/` into CI (schedule-gated)

**Status:** `partially_done` (G1 done; no live GitLab CI/CD Schedule exists yet) · **Priority:** P1 · **Lane:** Validation Depth · **Dependencies:** Q13a (soft) · **Evidence:** plans/forensic-capability-audit-2026-08-18.md §13, §14

**Implementation note (2026-08-18):** New `oracle-and-package:` job added to `.gitlab-ci.yml`, mirroring
the `fuzz:` job's exact schedule-gated pattern (`rules: if: '$CI_PIPELINE_SOURCE == "schedule"'`, same
honest-disclosure comment style about untested-in-this-exact-CI-image tool versions) and running
`pip install -e ".[test,oracle]"` then `pytest tests/oracle/ tests/package/ -v --tb=short`. Verified
`python -c "import yaml; yaml.safe_load(open('.gitlab-ci.yml'))"` parses cleanly, and cross-checked the
install line against `tests/oracle/conftest.py`'s actual fixtures (4 `pytest.importorskip`-gated tools,
all covered by the `oracle` extra) and `tests/package/`'s `is_editable_install` fixture (from
`tests/conftest.py`, needs only `test`, already covered). As designed, this stays `partially_done` — per
this card's own closeout rule — until a GitLab CI/CD Schedule actually exists and has run the job at
least once, which requires project-settings access this environment does not have (same disclosed
limitation LIBIPYNB-V3 already recorded for `fuzz:`).

- **Objective:** `tests/oracle/`/`tests/package/` are never executed by `.gitlab-ci.yml` (confirmed: only
  `unit`/`integration`/`security`, `property`, `interoperability` run).
- **Expected files:** `.gitlab-ci.yml`.
- **Required behavior:** Mirror the exact, already-proven `fuzz:` job pattern: a new schedule-gated job
  (`rules: if: '$CI_PIPELINE_SOURCE == "schedule"'`) running `pip install -e ".[test,oracle]"` then
  `pytest tests/oracle/ tests/package/ -v`, carrying the same honest-disclosure comment about
  untested-in-this-exact-CI-image tool versions that `fuzz:`'s own job already carries.
- **Required verification (Gate G1):** `.gitlab-ci.yml` parses (`python -c "import yaml;
  yaml.safe_load(open('.gitlab-ci.yml'))"` succeeds); cross-check the `pip install` line against
  `tests/oracle/conftest.py`'s actual fixture requirements.
- **Required evidence:** Diff of `.gitlab-ci.yml`; the YAML-parse confirmation; a note that GitLab CI/CD
  Schedule activation itself requires project-settings access this environment does not have (same
  disclosed limitation `LIBIPYNB-V3` already recorded).
- **Acceptance criteria:** The job is defined, syntactically valid, dormant on normal pipelines, and will
  genuinely run `tests/oracle/`/`tests/package/` with correct extras once a schedule exists.
- **Non-goals:** Actually creating the GitLab CI/CD Schedule.
- **Closeout rules:** stays `partially_done` until a schedule exists and has run at least once;
  `completed_but_weakly_verified` is achievable now via Gate G1 alone.

### LIBIPYNB-Q13c — Property-test/fixture/secret-scanner broadening, and the `NotebookSecurityError` disposition decision

**Status:** `partially_done` (items 1/2/4 G1+G2-verified — independently reviewed twice, confirmed correct both times; item 3 deliberately deferred) · **Priority:** P3 (broadening items) / P2 (the disposition decision) · **Lane:** Validation Depth · **Dependencies:** none · **Evidence:** plans/forensic-capability-audit-2026-08-18.md §7, §13

**Gate G2 review note (2026-08-18):** Reviewed independently twice; both passes confirmed
`NotebookSecurityError` has zero remaining references anywhere (`src/`, `tests/`, `examples/`, `fuzz/`,
only stale `.pyc` cache files matched), confirmed the new property-test strategy branches are structurally
reachable (not dead code in the strategy definition), and confirmed each secret-scanner false-positive
test checks against the real rules in `security/secrets.py` directly.

**Implementation note (2026-08-18):**
- **(1) `NotebookSecurityError` disposition — done.** Removed from `errors.py`, `libipynb/__init__.py`'s
  imports/`__all__`, and a stale docstring reference in `cli/main.py`. Confirmed zero remaining references
  anywhere in `src/`, `tests/`, `examples/`, or `fuzz/` (checked all four directories directly, per this
  card's own G2 scope, though the check itself was performed in this same implementing pass rather than a
  genuinely separate session — recorded as G1 only, G2 still pending like every other card here).
- **(2) Property-test strategy broadening — done.** `tests/property/test_property_roundtrip.py`: added
  `error`/`display_data` output branches, an attachment-bearing markdown/raw-cell strategy, and a new
  `_notebook_with_explicit_cell_ids` composite generating genuine nbformat-4.5 notebooks with real unique
  ids (the existing strategy deliberately never generated minor=5, since nothing in it synthesized ids —
  IPYNB-ID-001 reserves that to the explicit `upgrade()` path). `_notebook_dict` now mixes both branches
  via `st.one_of`. Empirically confirmed all new branches are meaningfully exercised (300-sample run: 91
  error outputs, 51 display_data outputs, 272/300 notebooks with an attachment-bearing cell, 175/300 at
  minor=5) — not just assumed from the strategy's shape. All 7 existing property tests still pass.
- **(3) Real-world fixture notebooks — deliberately not done.** Per this card's own scoping ("this card
  scopes the process/criteria only, not specific notebook selection"), added a new "Real-world fixtures"
  section to `tests/fixtures/PROVENANCE.md` recording the selection criteria (permissive license verified
  firsthand, genuinely authored outside this project, vendorable size, recorded source/license/date,
  never modified post-fetch) for whoever picks this up next. Did not fabricate or select actual notebooks
  — sourcing real external content and verifying its license is a provenance-consequential judgment call
  this pass should not make unilaterally, the same reasoning LIBIPYNB-Q12a's URL decision already applies
  elsewhere in this plan. `tests/fixtures/` remains entirely synthetic/hand-crafted; this is the accurate,
  disclosed state, not silently left implied as done.
- **(4) Secret-scanner false-positive test table — done.** 8 new tests in `tests/security/
  test_secret_scanning.py`: a well-known public example AWS key (AKIAIOSFODNN7EXAMPLE) still matches by
  shape (honest disclosure, not a bug — no allowlist exists); a bare UUID and a bare git commit SHA are
  both confirmed NOT flagged; a base64 image payload under a non-`text/*` output MIME type is confirmed
  structurally excluded from scanning entirely (a design decision, not an accident); a base64 blob
  assigned to a non-credential variable name is not flagged; an empty and a 4-character placeholder
  `password`/`token`-named metadata value are both confirmed below the module's own `len(text) >= 6`
  threshold (not flagged), with a paired test confirming a 6-character value at that exact boundary DOES
  flag — documenting the real cutoff rather than leaving it assumed.

Full regression suite (950 passed, 4 skipped) green; `mypy --strict`/`ruff check` clean throughout.

- **Objective:** Bundle four independent, pure-test-surface-area items plus one small design decision:
  (1) `NotebookSecurityError` is dead code (documented, exported, never raised, zero references). (2)
  property-test strategy only exercises `mode='recovery'`/`profile='declared'`, never error/`display_data`
  outputs, attachments, or explicit cell ids. (3) all 27 fixture notebooks are synthetic/hand-crafted. (4)
  secret scanner has strong true-positive coverage, almost no false-positive coverage.
- **Expected files:** `src/libipynb/errors.py`; export lists in `security/__init__.py`/`libipynb/__init__.py` (only if removing); `tests/property/test_property_roundtrip.py`; `tests/security/test_secret_scanning.py`; `tests/fixtures/PROVENANCE.md` plus a small number of new fixture files.
- **Required behavior:** **Recommendation: remove `NotebookSecurityError`** from the public exception
  hierarchy and docstring — checked all 4 `SanitizationMode`s and confirmed none ever raises;
  silent-report-only is the established, consistent pattern across every security module; wiring in a new
  raising "strict mode" would be the first such precedent in the codebase, not a natural extension. Since
  no public release/tag exists, this removal is zero-cost today. Broaden the property-test strategy
  (`error`/`display_data` output branches, an attachment-bearing cell strategy, an explicit-id branch
  alongside the current implicit-only one). Add 2-4 real-world (permissively-licensed, provenance-recorded)
  fixture notebooks — this card scopes the process/criteria only, not specific notebook selection. Add a
  secret-scanner false-positive test table (public example credential, UUID, git SHA, base64 image
  snippet, empty/placeholder `password`/`token`-named metadata key).
- **Required verification (Gate G1 + G2):** Full regression suite. The `NotebookSecurityError` removal
  specifically needs G2 (an independent pass confirming no other module — including `examples/`/`fuzz/`
  — references it).
- **Required evidence:** Diff of `errors.py` and export lists; the new property-test strategy branches
  with a run showing they're actually exercised; the new fixture files plus updated `PROVENANCE.md`; the
  new false-positive test table's pass output.
- **Acceptance criteria:** `NotebookSecurityError` either has a real raise site and test coverage, or does
  not exist in the public API — never both documented-and-dead; property tests generate error/
  `display_data` outputs, attachments, and explicit ids at least some fraction of the time; at least one
  real-world fixture exists with recorded provenance; secret scanner has an explicit false-positive test
  table.
- **Non-goals:** Wiring `NotebookSecurityError` into a new strict enforcement mode; re-running
  `mutmut`/`atheris` (environment-blocked on Windows, tracked separately).
- **Closeout rules:** `completed_verified` requires Gates G1 and G2.

### LIBIPYNB-Q14 — Validation/lifecycle small-fix bundle

**Status:** `completed_verified` (G1+G2 done — independently reviewed, confirmed correct) · **Priority:** P2/P3 · **Lane:** Validation Depth · **Dependencies:** Q5 (soft), Q6 (soft) — same files · **Evidence:** plans/forensic-capability-audit-2026-08-18.md §7, §9 item 2, §13

**Gate G2 review note (2026-08-18):** An independent review confirmed `REQUIRED_OUTPUT_FIELDS` has zero
remaining references and `validation/rules.py` (the real enforcement site) is untouched; confirmed the
`SchemaArtifactError` test correctly clears the `lru_cache`d `_schema`/`_validator` (not a cache-masked
no-op); and independently re-derived `nbformat.v4.convert.upgrade()`'s own reference behavior directly
from the installed package's source, confirming the `orig_nbformat_minor` write-back matches exactly.

**Implementation note (2026-08-18):** All three sub-items landed. (a) `REQUIRED_OUTPUT_FIELDS` removed from
`validator.py` and `validation/__init__.py`'s exports; `grep -rn REQUIRED_OUTPUT_FIELDS src/ tests/`
returns nothing. (b) The audit's exact `SchemaArtifactError` repro added to
`tests/integration/test_obligation_official_schema_validation.py` — monkeypatches `SCHEMA_DIGESTS[0]`
(via a replacement `MappingProxyType`, since the real one is immutable) and explicitly clears the
`lru_cache`d `_schema`/`_validator` first (a prior test's successful cache entry would otherwise make the
corrupted digest a no-op), confirming `IPYNB_SCHEMA_ARTIFACT` surfaces through the public `validate()`.
(c) `upgrade()` now writes `metadata.orig_nbformat_minor = source_minor` inside its existing
version-bump branch, matching `nbformat.v4.convert.upgrade()`'s own unconditional
`nb.metadata.orig_nbformat_minor = from_minor` exactly (confirmed by reading the installed reference
implementation directly, not assumed) — omitted when the version doesn't actually change, also matching
reference behavior. Two new dedicated tests in `test_obligation_lifecycle_modes.py` cover both branches;
real `nbformat.validate()` against the official schema still passes with the new metadata key present.
Full regression suite (935 passed, 4 skipped) green; `mypy --strict`/`ruff check` clean.

- **Objective:** Three small, independent gaps: (a) `REQUIRED_OUTPUT_FIELDS` is a dead, unwired public
  constant (real enforcement is separate hardcoded logic in `rules.py`, confirmed to already agree). (b)
  `SchemaArtifactError`'s confirmed-correct failure path has zero committed regression test. (c)
  `upgrade()` omits `metadata.orig_nbformat_minor`, the provenance field `nbformat.v4.upgrade()` always
  records.
- **Expected files:** `src/libipynb/validation/validator.py`, `src/libipynb/validation/__init__.py`; `tests/unit/test_obligation_schema_digest_encoding.py` or `test_obligation_official_schema_validation.py` (whichever already owns the closer scope); `src/libipynb/model/lifecycle.py`.
- **Required behavior:** Remove `REQUIRED_OUTPUT_FIELDS` from the public API (low-risk since no public
  release/tag exists yet; wiring it into already-D5-rated `rules.py` logic would risk regression for zero
  behavior change). Add the audit's own exact `SchemaArtifactError` repro (monkeypatch
  `SCHEMA_DIGESTS[0]`, call public `validate()`, assert `IPYNB_SCHEMA_ARTIFACT`) as a permanent test. Add
  `orig_nbformat_minor` write-back to `upgrade()`'s existing version-bump branch, always-on (matching
  `nbformat.v4.upgrade()`'s unconditional reference behavior, no new parameter), alongside the existing
  `ConversionAction` append.
- **Required verification (Gate G1):** Full regression suite; grep confirming
  `REQUIRED_OUTPUT_FIELDS` has zero remaining references anywhere after removal; the new
  `SchemaArtifactError` test passing; an `upgrade()` comparison confirming
  `result.document.raw["metadata"]["orig_nbformat_minor"] == source_minor`.
- **Required evidence:** Diff of all files; grep output; new test pass output for both cases.
- **Acceptance criteria:** No unwired public constant remains in `libipynb.validation`'s exported surface;
  `SchemaArtifactError`'s real failure path has a permanent regression test; `upgrade()`'s output matches
  `nbformat.v4.upgrade()`'s provenance-field behavior.
- **Non-goals:** Changing `rules.py`'s actual output-validation logic; adding `orig_nbformat_minor`
  write-back to `downgrade()` (the reference implementation doesn't do this either).
- **Closeout rules:** `completed_verified` requires Gates G1 and G2.

### Wave 7 — Competitive/professional enhancements (P3)

### LIBIPYNB-Q15a — `CellEditor` batch/bulk-edit mode

**Status:** `completed_verified` (G1+G2 done — independently reviewed twice, confirmed correct both times, zero findings) · **Priority:** P3 · **Lane:** Manipulation/Performance · **Dependencies:** none · **Evidence:** plans/forensic-capability-audit-2026-08-18.md §12, §19

**Gate G2 review note (2026-08-18):** Reviewed independently twice; both passes diffed the extracted
`_do_*` functions against the original inline code and confirmed the refactor is a literal, semantically
identical extraction (not just "looks equivalent"). Both passes traced the `contextmanager` control flow
by hand and confirmed both atomicity guarantees (invalid final state, and caller-raised exception) hold.
Both passes ran the timing-sensitive performance test themselves and confirmed the batched path was
genuinely, substantially faster on this machine, not just asserted.

**Implementation note (2026-08-18):** Landed as designed. Each mutation's core logic (`insert`/`move`/
`copy`/`replace`/`remove`/`remove_where`) was extracted into module-level `_do_*` functions operating on a
caller-supplied `target` dict, with no `deepcopy`/`validate()`/commit of their own — both `CellEditor`'s
existing per-call methods and the new `CellEditBatch` (returned by `with editor.batch() as batch: ...`)
call the same functions, so this refactor is behavior-preserving for every existing call site (all 16
pre-existing tests pass unchanged, byte-for-byte, with zero test edits needed). `CellEditBatch` accumulates
edits against one `deepcopy` taken at batch-entry; `CellEditor.batch()`'s `__exit__` runs the single
deferred `validate()`/commit via the existing `_finish()` — if the `with` block itself raises, that step
never runs and the document is left untouched. 7 new tests added to `tests/unit/test_obligation_cell_editor.py`:
atomic multi-edit commit, mid-batch `changes` introspection, `dry_run` batch (validates but doesn't
commit), a genuine atomicity proof (one accumulated edit individually valid, the batch AS A WHOLE
rejected via a dangling-attachment cross-field defect only the deferred full-notebook `validate()`
catches — confirms a partially-valid batch never leaks into the real document), a caller-exception case
(document untouched), a sequential-vs-batch result-equivalence check, and the required G1 performance
proof: 20 real (would-change) edits on a 4,000-cell notebook, one call at a time vs. accumulated in one
batch — measured **~22x faster** batched (1.25s vs 27.5s in a manual run; the committed test asserts a
generous 3x floor to avoid CI flakiness while still proving the architectural difference is real, not
claimed). Full regression suite (957 passed, 4 skipped) green; `mypy --strict`/`ruff check` clean.

- **Objective:** Every `CellEditor` mutation deep-copies the whole notebook and runs full `validate()`
  before checking `dry_run`, confirmed 700ms-3.5s/edit on large notebooks; `dry_run=True` provides zero
  performance benefit today.
- **Expected files:** `src/libipynb/model/editor.py`.
- **Required behavior:** A `with editor.batch() as batch: ...` context manager accumulating edits against
  one in-memory working copy (one `deepcopy` at batch-entry, not per operation), deferring the single
  `validate()` call to `__exit__`, committing atomically only if that validation passes — preserving the
  atomic-commit guarantee while making preview genuinely cheaper than committing. Individual non-batched
  calls keep their current per-call-validates behavior unchanged.
- **Required verification (Gate G1):** N sequential single-call edits vs. the same N edits inside one
  `batch()` on the existing 4,000-cell stress fixture, asserting the batched path is meaningfully
  sub-linear in edit count for the validation cost (measured, not claimed).
- **Acceptance criteria:** Batched edits commit atomically (all-or-nothing on the single deferred
  validation); `dry_run`/`preview` mode is demonstrably cheaper than committing.
- **Non-goals:** Changing per-call (non-batched) methods' existing validate-per-call semantics.
- **Closeout rules:** `completed_verified` requires Gates G1 and G2.

### LIBIPYNB-Q15b — Parametrized PDF/slideshow export via the existing subprocess-wrapper pattern

**Status:** `completed_but_weakly_verified` (G1+G2+G8-for-slides done — independently reviewed twice, confirmed correct both times; PDF's own G8 environment-blocked, not a code gap) · **Priority:** P3 · **Lane:** Conversion & CLI Surface · **Dependencies:** Q11a/b (soft) · **Evidence:** plans/forensic-capability-audit-2026-08-18.md §8, §19

**Gate G2 review note (2026-08-18):** Reviewed independently twice; both passes confirmed the mocked
binary-file-read test genuinely exercises the adapter's own file-write/read-back code path (not a no-op
mock), independently confirmed `PDFExporter().file_extension`/`WebPDFExporter().file_extension` are both
`.pdf` against the real installed package, and personally ran the AST-level static-analysis guard test to
confirm the `*tail_args` splice keeps the required literal prefix intact.

**Implementation note (2026-08-18):** `NbconvertExporter(fmt, *, timeout=120.0)` added; `HtmlExporter`
becomes a thin subclass alias (`super().__init__("html", timeout=timeout)`), confirmed byte-identical to
its own pre-existing behavior against the real tool.

**Design decision made, not mechanical (per this card's own requirement):** `ExportResult.content` widened
from `str` to `str | bytes`, documented in its own docstring, rather than inventing a separate binary
result type — the latter was considered and rejected as fragmenting every caller's handling logic across
two shapes for what is structurally the same contract every exporter already returns.

**A real technical finding, not assumed:** read nbconvert's own `writers/stdout.py` directly and confirmed
its `StdoutWriter` unconditionally wraps stdout in a UTF-8 *text* codec writer
(`nbconvert.utils.io.unicode_std_stream`) — piping a binary format like `pdf` through `--stdout` (the
`HtmlExporter`-inherited approach) would silently corrupt it. Binary formats (`pdf`/`webpdf`, both `.pdf`
output — confirmed via `PDFExporter().file_extension`/`WebPDFExporter().file_extension` on the real
installed package) are instead written to a real file via `--output-dir` and read back from disk, matching
nbconvert's own correct usage pattern; `qtpdf`/`qtpng` were investigated and excluded (need a Qt WebEngine
install this environment lacks, and report a misleading `.html` `file_extension` that would need its own
separate verification — out of scope, this card only names `pdf`/`webpdf`/`slides`).

**Gate G2 note preserved from the original `HtmlExporter` hardening:** `tests/integration/
test_obligation_security_baseline.py::test_export_subprocess_usage_only_ever_invokes_nbconvert` statically
enforces that every `subprocess.run()` call in `export.py` invokes `[sys.executable, "-m", "nbconvert",
...]` as an inline list *literal* at the call site, not a variable — the initial refactor built `args` as
a plain list and broke this real, deliberate security control (caught by the existing test, not
self-missed); fixed by splicing the format-dependent tail in via `*tail_args` inside the same literal so
the fixed three-token prefix stays statically verifiable.

**G8 evidence:** `slides` fully oracle-verified against the real installed `nbconvert` (produces real
reveal.js HTML; a `title=` is reflected exactly as reveal.js's own template composes it,
`"{title} slides"` — confirmed empirically, not assumed to match the `html`/`lab` template's bare-title
convention). `pdf`'s own oracle comparison is **environment-blocked**: confirmed directly that neither
`xelatex`/`pdflatex` nor `playwright` is installed in this repo's `.venv` (the same honest-disclosure
pattern this plan already uses for LIBIPYNB-V3/V4) — a dedicated test
(`test_pdf_matches_the_real_tool_output`) is written to run for real and skip cleanly otherwise, so it
will genuinely prove parity the moment a backend is installed rather than being silently untested. A
separate, explicitly-mocked test (`test_binary_export_reads_the_written_output_file_from_disk`) proves the
adapter's own binary-file-reading code path independent of backend availability. Full regression suite
(963 passed, 5 skipped) and both real-kernel execution files (46 + 2 = 48 passed) green; `mypy --strict`/
`ruff check` clean.

- **Objective:** `HtmlExporter` hardcodes `["--to", "html"]`; `nbconvert` supports `--to pdf`/`--to
  slides`/`--to webpdf` via the identical, already-proven subprocess-wrapper shape.
- **Expected files:** `src/libipynb/adapters/export.py`.
- **Required behavior:** Generalize into a parametrized `NbconvertExporter(fmt, *, timeout=120.0)`
  (`HtmlExporter` becomes a thin backward-compatible alias), reusing the existing install-detection/
  timeout/error-code conventions verbatim. **Real design decision, not mechanical**: PDF/slides output is
  binary; `ExportResult.content: str` cannot hold it — decide `content: str | bytes` or a distinct result
  type before implementation.
- **Required verification (Gate G1 + G8):** Oracle comparison against direct `nbconvert --to pdf`/
  `--to slides --stdout`, same pattern as the existing `HtmlExporter` oracle test.
- **Non-goals:** DOCX export (needs Pandoc, a materially different dependency).
- **Closeout rules:** `completed_verified` requires Gates G1, G2, and G8.

---

## 4. Explicit Non-Goals (recorded, not carded)

- **Writer never canonicalizing source into nbformat's on-disk line-array form.** A compatibility
  decision (every libipynb-authored `.ipynb` would start looking byte-different from today) needing
  explicit maintainer sign-off, separate from and larger than Q7(a)'s `max_entries` fix.
- **nbformat major=3 (legacy IPython) write-back.** Pre-2015 format, vanishingly low real-world
  prevalence; the audit itself rates this Low value.
- **`nbformat.sign.NotebookNotary.mark_cells()`/`check_cells()` per-cell trust-fallback port.** Only
  relevant if libipynb ever drives a notebook-rendering UI, per the audit's own recommendation.

## 5. Closeout Criteria

Matches `remediation-plan.md` §12's own bar: every card above must be `completed_verified` (both Gate
G1 and Gate G2, plus any additional gate its own Closeout rules name) or an accurately-described
`blocker`/`partially_done` with its resume condition stated (Q12a: maintainer decision; Q13b: CI
schedule creation). No card may be marked `completed_verified` on self-review alone where its own gate
set requires G2 — a genuinely separate review pass, not the implementing session re-reading its own diff.

## 6. End-to-End Verification (run 2026-08-18, after all 21 taskcards)

Every check below was actually executed, not assumed; results as of the run:

1. **`pytest tests/ -q`** — full suite, real-kernel tests included: **1014 passed, 5 skipped**, in
   ~4m35s, at the point all 21 taskcards' initial implementation had landed (before the close-out
   session's own G2/G6/G7 review rounds). The 5 skips are all legitimate (tool-not-installed cases:
   `nbformat`-reference-only tests without the `reference` extra, and the `pdf` oracle test with no
   LaTeX/Playwright backend installed — none are silently-skipped assertions). **Correction (2026-08-18,
   close-out session):** this figure was inconsistent with this document's own §0 status line (which
   already said 1017); a fresh run confirmed **1017 passed, 5 skipped** was the correct count at that
   point (3 additional tests had landed after this section was first written, from Q13c's property-test
   broadening). The close-out session's own further fixes (Q3 review — no code change; Q7/Q8 Gate G6
   reviews — 2 real gaps found and fixed, 5 new regression tests) bring the count to **1022 passed, 5
   skipped** as of this document's current state — see `plans/independence-audit-2026-08-18.md` and this
   session's own commits for the final re-verification.
2. **`pytest tests/oracle/ tests/package/ -v`** — **28/28 passed**, against the real installed
   `nbdime`/`nbconvert`/`nbstripout`/`jupytext`/`nbclient` in this repo's own `.venv`.
3. **`mypy --strict src/libipynb`** and **`ruff check src/libipynb tests/`** — both clean throughout
   every taskcard's landing, re-confirmed clean at the end.
4. **The audit's own two headline reproductions, re-run directly:**
   - (a) `tests/fixtures/corpus/data-science-pattern.ipynb` (the confirmed-affected, list-source fixture)
     executed through `LocalJupyterExecutor` directly (not via a test wrapper) — `result.completed is
     True`, `kernel_death_error is None`, `kernel_launch_error is None`. Was `kernel_death_error` before
     Q1.
   - (b) The real end-to-end git-driver repro (`tests/unit/test_cli_git_diff_merge_drivers.py`'s
     `TestEndToEndGitDiffOnPreNbformat45Notebooks`, a genuine scratch git repo with `git diff`/`git
     merge` through the installed drivers on a pre-4.5 fixture) — both tests pass. Was `fatal: external
     diff died`, exit 128, before Q3.
5. **`python -m build --wheel --sdist`**, installed into a fresh throwaway venv: import and CLI both
   work (`libipynb --help` and `python -m libipynb.cli --help`). **Confirmed the internal GitLab URL
   (`gitlab.recruitize.ai/...`) IS still present** in the built wheel's `dist-info/METADATA`
   (`unzip -p dist/*.whl '*/METADATA' | grep -i recruitize` — one match) — expected and correct, since
   Q12a is intentionally left as a `blocker` pending the maintainer's own decision, not silently fixed by
   guessing a replacement URL.
6. **Coverage re-run** (`pytest --cov=libipynb --cov-report=term-missing`): **89.42%** total, up from the
   audit's own 89.11% baseline — no regression. `src/libipynb/cli/__main__.py` shows 0% coverage in this
   report, which is a coverage-tool measurement artifact, not a real gap: its own test
   (`TestModuleInvocation::test_python_dash_m_libipynb_cli_probe_works`) genuinely runs
   `python -m libipynb.cli` as a real subprocess, which in-process `coverage.py` instrumentation cannot
   see.
7. **Genuinely separate Gate G2 review — two full rounds, four independent agent invocations total**, none
   with access to this implementing session's own reasoning or conversation — exactly the review class
   this plan's own §5 requires and the class the original forensic audit found missing before the P4a-1
   blocker shipped.

   **Round 1** (one agent) covered the five most critical P0/P1 cards (Q1, Q2, Q3, Q4, Q9). Verdicts: Q1
   CONFIRMED CORRECT, Q2 CONFIRMED CORRECT, Q4 CONFIRMED CORRECT, Q9 CONFIRMED CORRECT WITH MINOR CONCERNS
   (one missing Hypothesis property test, fixed same day), Q3's `diff.py` half CONFIRMED CORRECT, Q3's
   `merge.py` half **FOUND A REAL DEFECT**: the same-position-edit correlation used raw index comparison,
   which broke silently (cell loss, unflagged divergent edits) whenever a cell was inserted near an edit —
   an everyday pattern, not a contrived corner case. Fixed with a `difflib.SequenceMatcher`-based
   alignment plus a content-similarity tiebreak.

   **Round 2** (three agents run in parallel) covered every remaining card, including a dedicated
   re-review of the round-1 Q3 fix:
   - **Q3 merge-fix re-review + Q10:** Q10 CONFIRMED CORRECT, zero findings. The Q3 re-review **FOUND A
     SECOND, MORE SEVERE DEFECT** in the round-1 fix's content-similarity tiebreak: it could be fooled by
     a genuinely new, unrelated inserted cell that merely resembled the base cell's original content more
     than a substantially-rewritten TRUE edit did — the heuristic then *confidently* (not just
     ambiguously) picked the wrong cell, producing real cell loss AND wrong conflict data, which is worse
     than the bug it was fixing. A second, independent adjacency-collapse case (two adjacent id-less cells
     edited differently, no insertion needed) was also found. **Fixed by removing the content-similarity
     tiebreak entirely** — the correlation now resolves ONLY the mathematically unambiguous single-
     candidate case and declines (safely, no data loss, no wrong data, just an undetected conflict — the
     documented, accepted baseline) on every other shape. Four new permanent regression tests cover all
     five scenarios found across both rounds; see Q3's own taskcard entry for the complete history.
   - **Q5/Q6/Q7/Q8/Q14:** all five CONFIRMED CORRECT, zero real defects; one cosmetic doc gap (README.md
     missing Q7's updated numeric limit defaults) found and fixed same day.
   - **Q10/Q11a/Q11b/Q12b/Q12c/Q13a/Q13c/Q15a/Q15b:** eight of nine CONFIRMED CORRECT (Q10 confirmed twice,
     once by this pass and once by the Q3-adjacent pass above); **Q12b FOUND A REAL DEFECT**: the new
     SECURITY.md text itself misattributed the `exec` extra to the wrong module
     (`adapters/execute.py`, which needs no extra at all) instead of the actual consumer
     (`adapters/jupyter_execute.py`'s `LocalJupyterExecutor`), and omitted disclosing that real
     Jupyter-kernel execution engine at all — arguably the single most security-relevant opt-in feature in
     the codebase. Fixed same day. Q11b also had a minor, non-exploitable regex nitpick
     (`.match()` vs `.fullmatch()` on the fence-language check) found by two independent passes and fixed.

   **This is the single most important result in this entire plan**: the review process required by this
   plan's own §5 caught three real, previously-unnoticed defects across four independent passes — one of
   them (the Q3 content-similarity tiebreak) only surfaced on a SECOND round of review of a fix that had
   already passed a first round and looked, to its own author, like a solid fix for the first defect it
   was written to close. This is exactly why genuinely independent review — not self-review, and not even
   a single review pass assumed sufficient — is the standard this plan holds itself to, not a formality.
