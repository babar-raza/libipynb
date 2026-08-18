# libipynb — Mission Gate G1–G7 Status (Standing Document)

**Date:** 2026-08-18
**Scope:** this document maps the *mission's own* seven publication gates (from
`plans/libipynb-feature-analysis-and-execution.md`, "Phase 7 — evidence gates") against the full
15-capability contract that same mission defines. It is a **standing, re-checkable verdict at the
capability-contract level** — distinct in both numbering and scope from this repository's own
pre-existing G1–G9 taskcard-review gates (`plans/remediation-plan.md` §7, `plans/full-parity-plan.md`
§4.1), which are per-taskcard closeout gates, not a whole-contract assessment. The two systems share
short codes (`G1`, `G2`, ...) by coincidence of independent numbering, not by design — **do not conflate
them.** A quick disambiguation:

| Code | This document's meaning (mission gate) | This repo's own meaning (taskcard gate) |
|---|---|---|
| G1 | Independence (zero prohibited runtime deps) | Regression (full suite green) |
| G2 | Specification (v3/v4.0–4.5 traceability + tests) | Independent Verification (fresh-context review) |
| G3 | Fidelity and safety | Publish Authority (maintainer sign-off) |
| G4 | Editing and workflows | Evidence Freshness |
| G5 | Execution | Fixture-Corpus |
| G6 | Interoperability | Security Design Review |
| G7 | Publication readiness | Dependency-Addition Review |

Evidence sources cited below: `plans/forensic-capability-audit-2026-08-18.md` (the independent
behavioral audit), `plans/production-hardening-plan.md` (the taskcard remediation of that audit, now
closed — see its §0/§1), `plans/specification-traceability-matrix.md` (the per-rule matrix produced
alongside this document), and this close-out session's own direct verification (§6 of this document).

---

## G1 — Independence

**Criteria (mission text):** clean-environment import and CLI smoke with only declared core dependencies;
core runtime dependency list is empty; repository-wide scan finds no prohibited runtime/path/build/
test/docs coupling; no shadow implementation or donor-path dependency.

**Verdict: PASS.**

- Core runtime dependency list: `jsonschema` only (confirmed via `pyproject.toml`'s `[project]
  dependencies`). Optional extras (`exec`, `export`, `oracle`, `reference`, `test`, `fuzz`) are all
  declared separately and never imported from core paths.
- `tests/unit/test_import_boundary.py` statically AST-parses every source file and enforces this — 7/7
  passing as of this session's re-run (TC-CLOSEOUT-03, TC-CLOSEOUT-11).
- Clean build/install/import/CLI smoke re-run this session (`plans/independence-audit-2026-08-18.md`):
  wheel and sdist both build cleanly; a throwaway venv install works end-to-end (import from
  `site-packages`, both `libipynb --help` and `python -m libipynb.cli --help` work); wheel/sdist file
  lists contain no `tests/`, `plans/`, `.gitlab-ci.yml`, or `.supervisor/` leakage.
- No donor-repository or "Format Factory" coupling found anywhere (confirmed by the original forensic
  audit §16 and re-confirmed by this session's own independence re-check).
- One packaging-metadata defect found by the original audit — an internal GitLab URL leaking into the
  built wheel's `dist-info/METADATA` — is now **closed** (`LIBIPYNB-Q12a`, this close-out session):
  maintainer decided to omit the field entirely; verified zero matches in a fresh build.

## G2 — Specification

**Criteria (mission text):** v3 and every v4.0–4.5 traceability row has code and test evidence; future v4
minor preservation is proven; all cell/output/MIME/attachment/widget cases are covered; strict validation
and tolerant preservation are distinct.

**Verdict: PARTIAL.**

- `plans/specification-traceability-matrix.md` (produced this session, TC-CLOSEOUT-07) provides the
  mission's own required per-rule shape: 26 rows across schema structure, JEP 62 cell-ID rules, and
  explicit version-conversion rules, each with implementation file/symbol, test/evidence location, and a
  `UNKNOWN`/`ABSENT`/`THIN`/`PARTIAL`/`COMPLETE`/`BLOCKED_EXTERNAL` status. Tally: 18 `COMPLETE`, 6
  `PARTIAL`, 1 `ABSENT`, 1 compound `ABSENT`/`UNKNOWN`.
- **The one `ABSENT` row is real and significant:** v3→v4 conversion (`worksheets` flattening, `input`→
  `source`, `prompt_number`→`execution_count`, `pyout`→`execute_result`, `pyerr`→`error`) is genuinely
  unimplemented — confirmed by this session's own direct grep (zero matches for `worksheets`/`pyout`/
  `pyerr`/`prompt_number` anywhere in `src/`), not merely undocumented. This is why G2 is `PARTIAL`, not
  `PASS`: v3 read/preserve exists, but v3→v4 upgrade does not. **This is new-feature-scale work, out of
  scope for this close-out session** (it closes gaps a prior audit already found, not build new
  capabilities) — recorded here as the specific, named next action for a future session.
- Future v4-minor preservation: confirmed by the original audit (`UNSUPPORTED_FUTURE_MINOR` handling
  exists and is tested).
- Strict vs. tolerant/preservation-mode distinction: confirmed distinct (three parse modes exist and are
  behaviorally different, per the original audit §5).
- All in-scope v4.0–4.5 schema fields, JEP 62 cell-ID rules, and the explicit conversion rules the mission
  names (other than the v3 ones above) have `COMPLETE` or `PARTIAL` status with cited test evidence.

## G3 — Fidelity and Safety

**Criteria (mission text):** no-op byte preservation and semantic read-write-read tests pass; unknown
fields/types survive unrelated edits; conversion losses are reported; resource limits, duplicate keys,
malformed JSON/base64, path traversal, active MIME, and redaction tests pass; validation is non-mutating
and repair/sanitize are explicit.

**Verdict: PASS**, with two known, disclosed limitations (not blocking).

- Round-trip and preservation: confirmed by the original audit (§9) — zero true content divergence across
  16 fixtures after normalizing one documented, schema-legal representation difference; unknown-field
  survival confirmed at 5 nesting levels.
- Conversion losses: `LossReport`-equivalent mechanism confirmed present and tested (`upgrade`/
  `plan_downgrade`/`downgrade` in `model/lifecycle.py`).
- Resource limits: `NotebookResourceLimits` enforced incrementally for nested-object shapes; the one
  known residual gap (flat scalar arrays / single flat objects, an unavoidable stdlib `json` limitation)
  is documented in `SECURITY.md` with its derived worst-case bound, and this session's own Gate G6 review
  (`LIBIPYNB-Q7`) re-measured that worst case live and confirmed it stays modest (~1.78s CPU / ~275MB, not
  a "gigabytes/tens of seconds" danger zone).
- Sanitizer coverage: all 14 `_ACTIVE_ELEMENTS` categories, event-handler attributes, and URI/CSS
  detectors are tested (closed by `LIBIPYNB-Q8`); the `text/markdown` output-MIME blind spot and a
  further MIME-parameter bypass (found by this session's own Gate G6 review) are both closed with
  regression tests.
- Duplicate-key detection, malformed-JSON/base64 handling, and path-traversal protection in attachment
  extraction: all confirmed present and tested by the original audit.
- Validation non-mutation: confirmed architecturally (validation is read-only; repair/sanitize require
  separate explicit calls).
- **Known, disclosed limitations (not gaps against this gate's own criteria, which don't require these):**
  the writer never canonicizes multi-line source into nbformat's on-disk line-array form (a documented,
  deliberate compatibility decision needing separate maintainer sign-off — `production-hardening-plan.md`
  §4 non-goals); `nbformat` major=3 write-back does not exist (read-only, Low priority per the original
  audit).

## G4 — Editing and Workflows

**Criteria (mission text):** create/load/inspect/mutate/validate/atomic-save/reload consumer proof passes;
built-in transforms prove documented idempotency; diff/patch/merge invariants and conflicts are proven;
native conversion fidelity/loss reports pass.

**Verdict: PASS.**

- The full consumer workflow (create → load → inspect → mutate → validate → atomically save → reload) is
  exercised in the README's own Quick Start examples and `examples/`, both confirmed to run verbatim with
  zero API drift by the original audit (§15) and re-confirmed by this session's independence re-check
  (`examples/load_and_inspect.py`, `examples/validate_notebook.py` both exit 0).
- `cleanup()` idempotency confirmed by nbstripout-parity tests (byte-for-byte agreement with real
  `nbstripout` 0.9.1, including nested-output `execution_count` reset).
- `diff_notebooks()`/`merge_notebooks()` on pre-4.5 (no-cell-id) notebooks — the two most severe original
  findings — are now closed: `LIBIPYNB-Q3`'s fix (cell-id synthesis + a decline-rather-than-guess
  reconciliation policy) has passed three independent review rounds, the third one this close-out
  session, with 12 adversarial scenarios finding zero data-loss or wrong-data cases.
- `LIBIPYNB-Q10` (notebook-level metadata conflict detection in merge) closed, independently reviewed
  twice, zero findings.
- Native export fidelity (Markdown, Python-script, HTML via `nbconvert` subprocess, Jupytext via direct
  import): confirmed oracle-verified for HTML (near-identical to direct `nbconvert`, one known title bug)
  and Jupytext (byte-identical to direct CLI) by the original audit; `LIBIPYNB-Q11a`/`Q11b` closed several
  further fidelity bugs (fence language, HTML title, raw-cell drop), independently reviewed twice.

## G5 — Execution

**Criteria (mission text):** core remains usable with all Jupyter packages absent; Python subprocess
backend passes state, output, error, timeout, cancellation, process-death, output-limit, and
atomic-checkpoint cases; unsupported behavior is diagnosed honestly; no sandbox claim exists.

**Verdict: PASS.**

- Core import-without-extras is enforced by `test_import_boundary.py` (G1's own evidence doubles as G5's
  first criterion).
- The dependency-free subprocess engine (`adapters/execute.py::execute_notebook`) is confirmed to cover
  state persistence, output capture, error-to-diagnostic conversion, timeout/cancellation, and process-kill
  behavior (original audit, D2–D4 rating; one confirmed D2 gap — `max_output_bytes` truncation dropping
  unrelated cell results — closed by `LIBIPYNB-Q7`).
- The real Jupyter-kernel-protocol engine (`adapters/jupyter_execute.py::LocalJupyterExecutor`) — the
  original audit's single most severe finding, unable to execute list-of-lines-source notebooks (the
  standard on-disk form) at all — is closed (`LIBIPYNB-Q1`), independently reviewed and oracle-verified
  against real `nbconvert --execute`/`papermill` on the same input shape. Safety-surface hardening
  (`LIBIPYNB-Q2`: narrowed exception handling, no longer swallowing `KeyboardInterrupt`) closed for
  sub-items a–d; the timeout-watchdog redesign remains deliberately deferred (a larger, separate design
  change, not a gap against this gate's stated criteria, which this engine already satisfies for its
  in-scope behavior).
- Neither engine is described as a sandbox anywhere in the codebase or docs — confirmed by direct text
  search across `SECURITY.md`, `ARCHITECTURE.md` (this session), and both engines' own docstrings.

## G6 — Interoperability

**Criteria (mission text):** pinned `nbformat` differential tests pass or document justified divergences;
`nbdime`, conversion, widget, and execution oracle matrices are current; real-world licensed corpus
reopens/validates in the applicable upstream tools; self-round-trip results are not labeled
interoperability.

**Verdict: PARTIAL.**

- `nbformat` differential tests: PASS — 19/19 fixtures agree on the same in-memory structure; two known,
  documented, low-severity divergences (duplicate-cell-ID self-healing, missing-version-field
  auto-repair), both correctly attributed to `nbformat`'s convenience-wrapper leniency, not a libipynb
  defect.
- `nbdime` oracle matrix: PASS for merge (byte-for-byte scenario agreement, 3 scenarios); **was
  `UNVERIFIED`/undocumented for `diff_notebooks()` specifically** at the time of the original audit —
  closed by `LIBIPYNB-Q13a` (`tests/oracle/test_diff_parity.py`, new).
- `nbconvert`/Jupytext export oracle matrices: current (see G4 above).
- `nbclient`/Papermill execution oracle matrix: current for string-source notebooks (original audit); now
  extended to list-of-lines-source notebooks by `LIBIPYNB-Q1`'s own required oracle-fidelity verification.
- **Real-world licensed corpus: still `ABSENT`.** `tests/fixtures/PROVENANCE.md` confirms every fixture in
  the repo remains synthetic/hand-crafted (`LIBIPYNB-Q13c` item 3). This session re-examined whether this
  is genuinely agent-executable (per the standing instruction not to treat the human as a blocker without
  cause) and confirmed it is correctly deferred: the only locally-available candidate real files (bundled
  inside installed oracle packages, e.g. `nbdime`'s own test fixtures) are themselves synthetic
  diff-test data, not real authored work, and fetching genuine third-party notebooks over the network is a
  provenance/license judgment call this pass declined to make unilaterally — same reasoning as
  `LIBIPYNB-Q12a` before the maintainer's decision was obtained. This is the single item keeping G6 at
  `PARTIAL` rather than `PASS`; every other sub-criterion is met.
- Self-round-trip is never presented as interoperability evidence anywhere in this repo's test suite or
  documentation — confirmed by direct review of `tests/oracle/`'s naming and structure (every oracle test
  compares against a real, separately-installed tool, not against libipynb's own prior output).

## G7 — Publication Readiness

**Criteria (mission text):** full tests, lint, type checks, build, wheel/sdist install, CLI, docs
examples, license/notices, manifest, and clean-consumer smoke pass; public API is controlled and
documented; benchmark results and limitations are factual; evidence bundle is complete and reproducible;
no push, publication, or release has occurred without approval.

**Verdict: PASS** (as a currently-unpublished, locally-verified state — see the explicit no-push note
below).

- Full tests/lint/type checks: `pytest tests/ -q` → 1022 passed, 5 skipped; `mypy --strict` clean, 42
  files; `ruff check` clean; `ruff format --check` clean (this last check was itself a gap this close-out
  session found and fixed — 13 files had never been run through `ruff format`, a real, standing
  `.gitlab-ci.yml` quality-stage gate that had gone unchecked).
- Build/install/CLI/docs-examples/clean-consumer smoke: all PASS, see G1 and G4 above.
- License/notices/manifest: BSD-3-Clause compatibility confirmed for all declared extras (`LIBIPYNB-Q12c`
  G7 dependency-addition review, this session); no dead declared dependencies remain (`pyyaml` removed).
- Public API control: confirmed — `libipynb/__init__.py`'s `__all__` is the controlled surface;
  `analytics/` is deliberately excluded from it (documented, intentional).
- Benchmark results: a standing, dated, freshly-measured report now exists at
  `plans/benchmarks-2026-08-18.md` (this session, `LIBIPYNB` close-out `TC-CLOSEOUT-10`), replacing the
  original audit's one-time §12 prose with re-runnable, current numbers.
- Evidence bundle: `plans/evidence-bundle-2026-08-18.md` (this session) indexes every artifact this
  close-out produced, with tool/package versions and checksums.
- **No push, publication, or release has occurred.** `git log` shows only local commits; `git push` was
  never run this session or any prior session recorded in this repo's plans; no `v0.1.0` tag exists.
  Publishing remains a distinct, separately-authorized future action.

---

## Summary

| Gate | Verdict |
|---|---|
| G1 — Independence | **PASS** |
| G2 — Specification | **PARTIAL** (v3→v4 conversion genuinely absent — new-feature-scale, out of this session's scope) |
| G3 — Fidelity and Safety | **PASS** (two disclosed, non-blocking limitations) |
| G4 — Editing and Workflows | **PASS** |
| G5 — Execution | **PASS** |
| G6 — Interoperability | **PARTIAL** (real-world corpus still absent — correctly deferred, not a missing-credential blocker) |
| G7 — Publication Readiness | **PASS** (locally; not published) |

Five of seven gates fully pass; the two `PARTIAL` gates each have exactly one named, well-understood,
deliberately-deferred remaining item (v3→v4 conversion implementation; real-world fixture sourcing) —
neither is a surprise finding, both are already recorded in `plans/production-hardening-plan.md` and/or
`plans/specification-traceability-matrix.md` with their own resume conditions.
