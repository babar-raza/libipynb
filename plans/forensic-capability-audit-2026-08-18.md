# libipynb Forensic Capability and Publication-Readiness Audit

**Date:** 2026-08-18
**Auditor:** Claude (Sonnet 5), via a multi-agent workflow (`wf_b8d3fa68-c4d`, run twice — a full
24-agent pass followed by a broader ~28-agent re-verification pass after a mid-run stub result and an
under-scoped adversarial-verification filter were caught and corrected) — 9 capability domains each run
as a static-inventory pass followed by an independent behavioral-probe pass, plus 4 independent-oracle
audits, a test-quality audit, a plans/gate reconciliation pass, and a packaging/independence audit,
followed by adversarial re-verification of the highest-severity findings. The two passes converged on
the same D4–D5 hardened-core findings; the second pass's broader adversarial pressure additionally
surfaced several new high-severity defects (notably a blocker in the execution engine) that the first
pass missed — see [§22](#22-evidence-paths-and-reproduction) for both runs' journals.
**Repository audited:** `libipynb`, local branch `master` at commit `4fdb295` (10 commits ahead of
`origin/master`, unpublished; see [Independence & Packaging](#16-independence-and-packaging-assessment)).
**Environment:** Windows 11, Python 3.13.2, project `.venv` with `nbformat==5.10.4`,
`nbconvert==7.17.1`, `nbdime==4.0.4`, `nbstripout==0.9.1`, `papermill==2.7.0`, `jupyter_client==8.9.1`,
`nbclient==0.11.0`, `jupytext==1.19.5`, `hypothesis==6.165.3`, `jsonschema==4.26.0`, `mutmut==3.7.0`,
`ipykernel==7.3.0`, and `libipynb==0.1.0.dev0` installed editable.

> **Standard of proof applied throughout:** a method existing is not proof a feature exists; a passing
> unit test is not proof of format correctness; a successful round trip through libipynb alone is not
> proof of interoperability; a self-generated expected value is not independent certification. Every
> depth rating below is grounded in *behavioral* evidence — an agent actually running code against real
> or adversarial notebooks with the project's own `.venv` interpreter, not just reading source. Every
> finding cites the exact reproduction command. Items that could not be behaviorally verified are marked
> `UNVERIFIED` rather than guessed.

---

## 1. Executive Verdict

**libipynb is a substantially real, substantially working, non-trivial notebook manipulation library —
not a thin wrapper and not a facade.** Its "hardened tier" (schema validation, version
upgrade/downgrade, three-way merge, diff/merge algorithmics, cleanup/nbstripout parity, HMAC trust
signing byte-identical to `nbformat.sign.NotebookNotary`, and the deterministic-output half of the real
Jupyter-kernel execution engine) is D4–D5 by direct behavioral and independent-oracle evidence, not
self-report.

At the same time, the audit found a consistent pattern: **the seams where the library hands off between
its own real-world I/O boundary (a genuine on-disk notebook, the CLI, the git driver) and its
internally-validated core are meaningfully weaker than the core itself**, and three of those gaps are
severe enough to block calling either the CLI or the execution engine production-ready today:

1. **`LocalJupyterExecutor` — the real Jupyter-kernel execution engine — cannot execute any notebook
   whose code cells use list-of-lines source**, the standard on-disk representation JupyterLab itself
   writes by default (confirmed present in 40% of this project's own test fixtures). The entire run
   fails (zero cells execute) and is misreported as a generic kernel-death error. This is the single
   most severe finding in the audit: it makes the flagship, newly-shipped kernel-execution feature
   unusable for a large fraction of real notebooks, and the one existing test that constructs this exact
   input never actually checks whether execution succeeded — only that the (untouched) source field was
   preserved. **Confirmed via three independent reproduction paths and cross-validated by two separate
   audit domains** (execution, CLI) plus a real end-to-end `git diff` failure.
2. **`libipynb diff`/`libipynb merge` (and the real git diff/merge driver) crash on any notebook lacking
   nbformat 4.5's mandatory cell IDs** — i.e. nbformat 4.0–4.4, which the README's own "Supported
   Versions" table lists as supported. Reproduced not just via the plain CLI but via a real git
   repository with the driver installed: `git diff` itself fails with `fatal: external diff died` and
   exit code 128.
3. **CLI commands have no top-level exception handling**, so the two failures above (and most other
   non-happy-path input) surface as raw, multi-frame Python tracebacks rather than the clean
   JSON-error/exit-2 convention the codebase already implements for some commands.

A default resource limit that rejects legitimate large notebooks `nbformat` itself accepts, and an
uncaught `RecursionError` in `upgrade()`/`downgrade()` on moderately deep (but entirely realistic)
notebook metadata, round out the P0/P1 list — see [§17](#17-publication-blockers).

The project's own planning system (`plans/full-parity-plan.md`, `plans/remediation-plan.md`) is
unusually honest and evidence-heavy by industry norms — most of its "completed_verified" claims held up
under this audit's independent re-verification. Where they didn't — specifically the two P0 functional
blockers above — the cause is traceable and specific (see the "Plan and Gate Reconciliation" callout
before [§17](#17-publication-blockers)), not systemic overclaiming.

**Classification: `PUBLISHABLE AFTER BLOCKERS`** — see [§17](#17-publication-blockers) for the specific,
bounded list of fixes required before this can honestly be called production-ready, and
[§18](#18-mvp-capability-contract) for what's already there.

---

## 2. Repository and Revision Audited

- Path: `c:\Users\prora\OneDrive\Documents\GitHub\libipynb`
- Branch: `master`, HEAD `4fdb295` ("feat(execution): add real Jupyter-kernel-protocol execution engine")
- `git status`: clean except an untracked `.supervisor/` directory (an autonomous-orchestration
  scaffold, not audited as product code)
- `git log --oneline | wc -l`: local history well ahead of `origin/master` (10 commits ahead, `git tag
  -l` empty — **no `v0.1.0` tag exists and nothing has been published**, independently confirmed via
  direct `git` commands, not trusted from `plans/remediation-plan.md`'s own status text)
- Source: `src/libipynb/` — 34 `.py` files across `codec/`, `model/`, `validation/`, `security/`,
  `execution/`, `adapters/`, `analytics/`, `cli/`, `_internal/`; ~9,500 LOC, ~324 public symbols
- Tests: `tests/` — 69 files across `unit/`, `integration/`, `interoperability/`, `oracle/`,
  `property/`, `security/`, `package/`; `pytest tests/ -q` → **879 passed, 4 skipped, 0 failed**
  (~234–294s), **89.11% line+branch coverage** (repo's own configured gate is 85%)
- Planning system: `plans/full-parity-plan.md`, `plans/remediation-plan.md`,
  `plans/publication-readiness-assessment.md`, `plans/research.md`, plus three execution-evidence
  documents — all read in full and reconciled against this audit's independent findings (§10)

---

## 3. Official Specifications and Oracle Versions Used

| Oracle | Version | What it independently proves | What it cannot prove |
|---|---|---|---|
| `nbformat` (official reference impl.) | 5.10.4 | Schema/structural fidelity, official validation semantics, version-conversion reference behavior | Real-world authoring-tool quirks beyond its own test corpus |
| `nbconvert` | 7.17.1 | HTML export fidelity (real tool, invoked as subprocess by libipynb's `HtmlExporter` and directly by this audit) | — |
| `nbdime` | 4.0.4 | Real notebook diff/merge semantics (`nbdiff`/`nbmerge` CLI) | — |
| `nbstripout` | 0.9.1 | Real output/metadata-stripping semantics | — |
| `papermill` | 2.7.0 | Independent, nbclient-based real-kernel execution reference | — |
| `jupytext` | 1.19.5 | Real paired-text export semantics | — |
| `nbclient` | 0.11.0 | The actual kernel-protocol execution library libipynb's `LocalJupyterExecutor` wraps | — |
| Vendored nbformat 4.0–4.5 JSON schemas (`src/libipynb/validation/schemas/*.json`) | — | Confirmed **byte-identical** (mod CRLF) to the schemas shipped inside the installed `nbformat` package | — |

All five real independent-tool oracles (`nbformat`, `nbconvert`, `nbdime`, `nbstripout`, `papermill`)
were genuinely installed and genuinely invoked in this audit's environment — confirmed by re-running
`tests/oracle/` (16/16 passed, 0 skipped) and by this audit's own additional oracle scripts, not
inferred from `importorskip` guards.

---

## 4. Architecture and Public API Inventory

Full per-symbol inventory tables (purpose / location / native-vs-delegated / input constraints /
output contract / error behavior / tests / documentation / status) were produced for all ~324 public
symbols across all 9 domains during Stage 1 of the audit; the complete tables are preserved in the
workflow's journal (`subagents/workflows/wf_b8d3fa68-c4d/journal.jsonl`) and are too large to
reproduce in full here. Summary by subsystem:

| Subsystem | Native or delegated | Headline verified depth |
|---|---|---|
| `codec/` (reader, writer, probe) | Native (bounded custom JSON parser, not delegated to nbformat) | D3–D4 core; D1 `probe()`; D0 write-path for legacy nbformat major=3 |
| `model/` (document, editor, attachments, output, cleanup, lifecycle, diff, merge, metadata) | Native | D4 hardened tier (CellEditor, AttachmentManager structural ops, diff/merge, downgrade); D2 accessor layer (`to_dict`/`.metadata` leak) |
| `validation/` (validator, schema, rules) | Native orchestration over vendored official schemas + `jsonschema` | D5 `validate()`; D2 legacy wrappers |
| `security/` (limits, sanitizer, secrets, trust) | Native | D4 sanitizer; D5 trust notary (oracle-matched vs `nbformat.sign`); D2 resource limits (shape-dependent); D0 `NotebookSecurityError` (dead code) |
| `execution/` + `adapters/execute.py` + `adapters/jupyter_execute.py` | Delegated to `nbclient`/`jupyter_client` (kernel engine) + fully native (subprocess engine) | D5 deterministic-output oracle agreement; D2 on two confirmed safety/fidelity gaps |
| `adapters/export.py` (Markdown, Python-script, Html, Jupytext) | Native (Markdown/Python) + delegated (Html via subprocess to real `nbconvert`, Jupytext via direct `jupytext` import) | D3–D4; D0 for PDF/slides/docx (don't exist) |
| `analytics/` | Native, deliberately excluded from `import libipynb`'s top-level namespace (confirmed intentional per `plans/publication-readiness-assessment.md:126`) | D2 — real, documented, CLI-exposed, but has one confirmed CLI-reachable crash |
| `cli/` | Native (`argparse`, 12 public subcommands) | D3 for help/examples/docs fidelity; D2 for error handling and diff/merge on legacy notebooks |

---

## 5. Capability-Width Map

Using the mission's own capability taxonomy (parsing/serialization, data model, validation/
normalization, version conversion, attachments/rich output, manipulation, execution, conversion/
export, trust/security, performance, developer experience):

| Area | Present? | Native or delegated | Notes |
|---|---|---|---|
| File/bytes/stream/string I/O | Yes | Native | 5-way input-API agreement confirmed byte-identical on identical content |
| Format version detection | Yes | Native | `probe()` exists but is untested anywhere (D1) |
| Strict/preservation/recovery parsing modes | Yes | Native | All three modes behaviorally distinguished and confirmed |
| Unknown-field preservation | Yes | Native | Confirmed via round trip at 5 nesting levels in preservation mode |
| Deterministic serialization | Yes | Native | 20/20 repeated dumps byte-identical, independent of input key order |
| Atomic writes | Yes | Native | Survived a real simulated hard process kill (`os._exit(137)` mid-`os.replace`) — target file never corrupted (temp file is leaked on crash, a separate minor finding) |
| Cell types, metadata, execution counts, attachments, outputs, MIME bundles | Yes | Native | Full coverage confirmed |
| Cell insert/remove/replace/move/reorder | Yes | Native | D4, hardened |
| Cloning / immutability semantics | Partial | Native | `copy.deepcopy(doc.raw)` gives true isolation; 4 built-in accessors (`to_dict`, `.metadata`, `Cell.metadata`, `Cell.outputs`) do not (HIGH finding, §7) |
| Official schema validation | Yes | Native, vendored official schemas | D5, oracle-verified |
| Semantic validation beyond schema | Yes | Native | Duplicate cell IDs, forward-version handling, etc. |
| Normalization / repair | Yes (opt-in via `normalize` CLI) | Native | — |
| Version upgrade/downgrade | Yes | Native | D5, tamper-resistant, oracle-cross-validated at every step |
| Structural diff / semantic diff | Yes | Native | D4, but never oracle-compared to `nbdime diff` (only merge was) — MEDIUM finding |
| Three-way merge with conflict reporting | Yes | Native | D4–D5, oracle-verified vs real `nbdime`/`nbmerge` |
| Trust/signature (Jupyter-compatible HMAC) | Yes | Native | D5, byte-identical to `nbformat.sign.NotebookNotary` |
| Sanitization of active content | Yes | Native | D4, 4 modes, network-access-never-attempted proven |
| Real kernel execution | Yes | Delegated to `nbclient`/`jupyter_client` | D5 deterministic-output agreement **for string-source notebooks only**; D0/BLOCKER — cannot execute list-of-lines-source notebooks (the standard on-disk form) at all, see §7 |
| Subprocess-based lightweight execution | Yes (pre-existing, narrower) | Native | D2–D4, not kernel-protocol-fidelity comparable by design |
| Export to Markdown / Python script | Yes | Native | D2 (several confirmed fidelity bugs) |
| Export to HTML | Yes | Delegated (subprocess to real `nbconvert`) | D3, byte-identical to direct `nbconvert` except one title bug |
| Export to Jupytext paired text | Yes | Delegated (direct `jupytext` import) | D4, byte-identical to direct `jupytext` CLI |
| Export to PDF/slides/docx | **No** | — | D0, confirmed absent |
| Notebook analytics (cell/output histograms) | Yes | Native | D2, documented, deliberately not on top-level namespace |
| CLI | Yes, 12 subcommands | Native | Help/examples/docs all accurate; error handling and legacy-notebook support are the weak points |

---

## 6. Capability-Depth Matrix

Depths are the **final, behaviorally-confirmed** ratings from Stage 2 probing (not Stage 1 static
inventory). D0=Absent, D1=Surface only, D2=Happy path, D3=Functional, D4=Production hardened,
D5=Independently verified.

| Capability | Depth | Evidence class |
|---|---:|---|
| `validate()` / schema validation | **D5** | Oracle diff vs `nbformat.validate()` across full fixture corpus + 20 hand-crafted edge cases, 20/20 agreement |
| `plan_downgrade()`/`downgrade()` | **D5** | 5 hand-crafted tamper attacks all correctly refused; full upgrade↔downgrade round trip oracle-cross-validated at every checkpoint |
| `cleanup()`/`CleanupPolicy` | **D5** | Byte-for-byte agreement vs real `nbstripout` 0.9.1 including nested-output `execution_count` reset |
| `HmacNotebookNotary` (trust) | **D5** | Byte-identical signatures vs real `nbformat.sign.NotebookNotary`; thread-safe under 24 concurrent threads |
| `LocalJupyterExecutor` (deterministic paths, string-source notebooks only) | **D5** | Output/execution_count/error agreement vs both direct `nbconvert --execute` and real `papermill`, success + error paths |
| `merge_notebooks()` | **D4–D5** | Oracle-verified vs real `nbdime`/`nbmerge` (3 scenarios); D4 for the broader unit-tested-only conflict-category matrix |
| `CellEditor` / `AttachmentManager` structural ops | **D4** | Adversarial cell-id collision, in-place-mutation, dry-run-atomicity, 64-char boundary all directly confirmed |
| `diff_notebooks()` move detection | **D4** | 200-trial property test vs brute-force LIS reference, 0 mismatches |
| Diagnostic path precision | **D4** | Multi-defect notebook produced correctly-pathed diagnostics for every defect simultaneously |
| Atomic file writes (path destination) | **D4** | Survived a real simulated hard process crash |
| `mypy --strict` / "Typing :: Typed" claim | **D4** | `Success: no issues found in 40 source files`, independently run |
| `diff_notebooks()` (general, non-oracle-verified half) | **D3** (was D4 for the algorithm, D1/UNVERIFIED for the README's "oracle-verified" claim, which only actually covers merge) | See §10 |
| `HtmlExporter` / `JupytextExporter` | **D3–D4** | Byte-identical (Jupytext) / near-identical (HTML, 1 title bug) vs direct CLI invocation |
| `LocalJupyterExecutor` on list-of-lines-source notebooks (the standard on-disk Jupyter form) | **D0, BLOCKER** | Confirmed via 3 independent reproduction paths + a real end-to-end `git`/CLI failure; entire run fails, misreported as `kernel_death_error` |
| `upgrade()`/`plan_downgrade()`/`downgrade()` on already-parsed dict input | **D2** | Adversarially verified: uncaught `RecursionError` at ~495+ levels of nested metadata, bypassing the documented resource-limit guarantee; `upgrade()` specifically has **zero** structural-limit enforcement below the crash threshold |
| Lone UTF-16 surrogate handling (reader + writer) | **D3** | Adversarially verified: crashes all 3 parse modes with an undocumented `UnicodeEncodeError`; writer-side crash confirmed conditional on `profile='declared'` — which is exactly the profile the shipped CLI always uses |
| Active-content detector coverage (13 of 14 element types, event-handler attributes, CSS/markdown URI schemes) | **D1 for test coverage** (D3-ish for the underlying implementation, confirmed working by direct execution) | Adversarially verified via coverage instrumentation: only `<script>` has any test; the other 13 hazard categories are implemented and functionally correct but completely unguarded by any regression test |
| `NotebookDocument.load/dump/loads/dumps` | **D3–D4** | 5-way input-API agreement; deterministic; default-profile write cost is a confirmed HIGH performance trap (not a correctness bug) |
| `roundtrip()` | **D3** (functional) / **D1** (regression protection) | 21/21 fixtures round-tripped identically; zero committed tests exercise it at all |
| `execute_notebook` (subprocess engine) | **D2–D4** | D4 for most behavior; **D2** for `max_output_bytes` specifically (confirmed silent multi-cell data loss) |
| `LocalJupyterExecutor` safety surface | **D2** | Confirmed: swallows `KeyboardInterrupt`; no output-size cap at all; `timed_out` signal unreliable under the library's own default options |
| `NotebookDocument.to_dict()`/`.metadata`/`Cell.metadata`/`Cell.outputs` | **D2** | Confirmed shallow-copy leak, contrasted against a working `deepcopy`-based clone that IS isolated |
| `AttachmentManager.add()`/`.rename()` input validation | **D2** | Zero base64/path-safety validation confirmed; downstream export consumer independently defends against it, the API itself does not |
| CLI error handling (`main()`) | **D2** | Confirmed: `diff`/`merge`/`execute`/`trust`/`convert`(downgrade) all crash with raw uncaught tracebacks on ordinary bad input |
| `libipynb diff`/`libipynb merge` on real-world notebooks | **D2** | Confirmed crash on any pre-4.5 (no cell-id) notebook — the majority of real existing `.ipynb` files |
| `NotebookResourceLimits` (`max_entries` default) | **D2** | Confirmed to reject a legitimate, nbformat-valid 4 MiB notebook under default settings |
| `analytics/notebook.py` (4 functions) | **D2** | Happy path solid; 1 confirmed real CLI-reachable crash; 1 confirmed CLI-vs-direct-call value divergence |
| `probe()` (format sniffing) | **D1** | Zero test coverage anywhere; confidence heuristic is trivial (confirmed live) |
| Legacy `validate_notebook`/`validate_notebook_schema` wrappers | **D1–D2** | Functionally correct but zero test coverage and confirmed information-lossy by design |
| `model/output.py` free functions | **D1** | Zero MIME-shape validation; live-reference leak confirmed |
| `NotebookSecurityError` | **D0** | Documented, exported, never raised anywhere, zero test references |
| PDF/slides/docx export | **D0** | Confirmed absent |
| nbformat major=3 write-back | **D0** | Confirmed: readable but categorically unwritable in every profile |
| `python -m libipynb.cli` | **D0** | Confirmed: package has no `__main__.py`, this invocation style fails immediately |

---

## 7. Thin-Feature Findings (Concrete Behavioral Evidence)

For every D1/D2 item above, here is precisely what makes it thin and what D3/D4/D5 would require.
(Full evidence — exact repro scripts and commands — is in the workflow journal; the essential facts
are reproduced here.)

### `LocalJupyterExecutor` cannot execute list-of-lines-source notebooks — D0, **BLOCKER**
**What's thin:** `_build_client()` converts the raw notebook dict via `nbformat.from_dict()`, which —
unlike an `nbformat.writes()`/`reads()` round trip — does **not** normalize a list-form `source` field
to a string. `nbclient` then crashes at `cell.source.strip()` with `AttributeError: 'list' object has
no attribute 'strip'`. The **entire run fails** (every cell shows `executed=False`, not just the
offending one), and `ExecutionResult` reports `completed=False`/`kernel_death_error` — indistinguishable
from a genuine kernel crash, with no signal pointing at the real cause.
**Confirmed via three independent paths:** a hand-built dict, a real on-disk fixture loaded through
`NotebookDocument.from_file()`, and both `execute()`/`execute_async()`. **Independently reproduced a
second time** by the CLI domain, including a minimal isolated repro (string-source succeeds, list-source
fails on otherwise-identical notebooks) and against a real project fixture (`data-science-pattern.ipynb`,
2 of 3 code cells use list-form source). **Not an edge case:** 10 of 25 code cells (40%) across this
project's own `tests/fixtures/**/*.ipynb` corpus use list-form source — it is what JupyterLab writes by
default. The older subprocess engine (`adapters.execute.execute_notebook`) already normalizes this
correctly via its own `_cell_source()` helper and executes the identical fixture without incident.
**Root cause of the blind spot:** the one existing test that constructs this exact input
(`test_list_of_lines_source_form_is_preserved_unchanged`) only asserts the source field is preserved
unchanged — it never checks `completed`, `outputs`, or the absence of `kernel_death_error` — so it has
been passing green the entire time this defect existed.
**To reach D3:** normalize `cell['source']` (and any other fields `nbclient`/`nbformat` assume are
strings) to a joined string before calling `nbformat.from_dict()`, mirroring
`adapters/execute.py`'s `_cell_source()` helper exactly.
**To reach D4/D5:** strengthen the existing test to assert on execution success, not just field
preservation, on a list-source fixture; add the same case to the CLI's own `TestExecute` suite.

### `NotebookDocument.to_dict()` / `.metadata` / `Cell.metadata` / `Cell.outputs` — D2, HIGH
**What's thin:** all four accessors return **shallow** copies (`dict(...)`/`list(...)`) of nested
structure. Confirmed live: `doc.to_dict()['cells'][0]['source'] = 'MUTATED'` changes
`doc.raw['cells'][0]['source']` too. Contrast-verified: `NotebookDocument(copy.deepcopy(doc.raw))` **is**
correctly isolated — this is specifically a bug in these four accessors, not an inherent limitation.
**To reach D3:** deep-copy consistently in these four accessors (matching `Cell.to_dict()`/
`NotebookOutput.to_dict()`'s existing correct behavior one level down), or explicitly document which
accessors are live-reference vs snapshot.
**To reach D4/D5:** add regression tests asserting mutation-after-access does not affect the source
document, for all four accessors, plus a property test.

### CLI error handling (`main()`) — D2, HIGH
**What's thin:** no top-level exception handling. Directly confirmed this session (beyond what any
prior review caught): `diff`, `merge`, `execute`, `trust` (missing-file case), and `convert`
(downgrade-without-`--accept-loss`) all crash with a raw, uncaught Python traceback and exit code 1 —
not the clean JSON-to-stderr/exit-2 convention the codebase demonstrably already implements elsewhere
(e.g. `trust`'s own secret-length checks).
**To reach D3:** wrap dispatch (or at minimum every `load()` call and the downgrade `accept_loss` path)
in a shared handler translating `NotebookError`/`OSError`/`ValueError` into the established convention.
**To reach D4/D5:** a regression test per command exercising the missing-file/bad-input case.

### `libipynb diff` / `libipynb merge` on real-world notebooks — D2, **BLOCKER**
**What's thin:** both commands raise an uncaught `ValueError: cell at index 0 is missing a stable
non-empty ID` on **any** notebook predating nbformat 4.5's mandatory cell IDs — confirmed against two
genuine nbformat-4.4 fixtures already in the repo's own corpus. Since nbformat 4.5's cell-ID mandate is
relatively recent, this is the **common** case, not an edge case, for real notebooks — and the README's
own "Supported Versions" table lists nbformat 4.0–4.4 (no cell IDs) as fully supported. Every diff/merge
test in the suite uses hand-built or already-4.5 fixtures, so this was never caught.
**Confirmed end-to-end with a real git repository:** creating a scratch repo, running
`libipynb diff --install-git`, committing an nbformat-4.4 fixture, editing it, then running `git diff --
notebook.ipynb` reproduces the identical traceback and **`fatal: external diff died, stopping at
notebook.ipynb`, git exit 128** — i.e. this breaks `git diff` itself for anyone using libipynb as their
configured driver, not just the standalone CLI command. This is the flagship differentiator the README's
first feature bullet advertises versus `nbdime`.
**To reach D3:** either transparently auto-assign cell IDs before diffing/merging (without mutating the
caller's file) or catch the `ValueError` and emit a clean, actionable error naming `libipynb upgrade` as
the fix.
**To reach D4/D5:** add a pre-4.5 fixture to the CLI test suite for both commands *and* the real
git-driver integration test; document the prerequisite in the README.

### `NotebookResourceLimits` default `max_entries` — D2, HIGH
**What's thin:** the default (100,000) rejects a completely ordinary, nbformat-valid, 4.08 MiB
single-cell notebook (150,000 short lines) that `nbformat.validate()` accepts without complaint —
confirmed via a clean, minimal repro building the notebook with `nbformat.v4.new_code_cell()` and
loading it with both libraries. Root cause: `enforce_structure` counts every JSON array element
cumulatively across the whole document, and libipynb's own writer never canonicalizes source into the
line-array form real Jupyter tooling always produces, so this failure mode is invisible until a
notebook has passed through real Jupyter/nbformat at least once.
**To reach D3:** raise the default substantially and/or make the limit proportional to actual
decoded byte size (there's already a much more generous `max_decompressed_bytes` at 2 GiB to align
against).
**To reach D4/D5:** a regression test using a real large notebook (not just adversarial payloads), plus
documentation of the interaction in `SECURITY.md`.

### `execute_notebook` `max_output_bytes` truncation — D2, HIGH
**What's thin:** truncating the shared combined stdout stream at a byte boundary doesn't just shorten
the oversized cell's own text — it **silently drops every cell result that lands after the truncation
point**, including small, unrelated, already-fully-written cells, with no per-cell error. Confirmed:
`total_code_cells=3`, `len(results)==1`.
**To reach D3:** truncate at the parsed-record level, not the raw byte stream.

### `LocalJupyterExecutor` safety surface (string-source notebooks) — D2, HIGH
**What's thin:** three confirmed gaps in the default-recommended configuration: (1) synchronous
`execute()` swallows `KeyboardInterrupt`/`SystemExit` via an overly broad except clause — reconfirmed at
current HEAD; (2) **no output-size or memory cap of any kind, on any platform** — reconfirmed with a
cell writing 50,000,000 bytes of stdout (captured whole, 3.7s, no truncation field anywhere on
`ExecutionResult`) and a cell allocating a 300MB `bytearray` (completed unimpeded, ~6s); `ExecutionOptions`
has no `max_output_bytes`/`max_memory_bytes`-equivalent field at all — a real regression in safety-knob
coverage versus the older subprocess engine's tested (if Windows-inert) `max_memory_bytes`; (3)
`ExecutionResult.timed_out` is structurally almost always `False` under the library's own default
`interrupt_on_timeout=True`, because a timeout in that mode surfaces only as an ordinary
`KeyboardInterrupt` cell error — technically matches the docstring, but leaves no structured way to
distinguish "my `cell_timeout` fired" from "the user's own code raised `KeyboardInterrupt`."
**To reach D3:** narrow the except clause; add an output-size cap or explicitly document its absence
next to the existing "not a sandbox" disclosure; add a per-cell `timed_out` flag or a distinguishable
`ExecutionEvent` kind.

### `upgrade()`/`plan_downgrade()`/`downgrade()` on already-parsed dict input — D2, HIGH (adversarially confirmed)
**What's thin:** all three entry points call Python's *recursive* `copy.deepcopy()` on the caller-supplied
input (`lifecycle.py`'s `_copy_source()`) **before** the library's own bounded, iterative
`enforce_structure()` traversal ever runs. Adversarial re-verification built nested-metadata payloads at
depths 100/1000/5000/20000 and confirmed: at ~495+ levels (well under Python's default recursion limit of
1000, and easily producible in well under a kilobyte of JSON), all three functions raise an **uncaught
`RecursionError`** instead of the graceful `NotebookResourceLimitError`/`IPYNB_RESOURCE_LIMIT` diagnostic
`validate()` correctly produces for the identical dict. The verification pass found the underlying gap is
**worse than first described**: `upgrade()` specifically enforces *no* structural limit at all below the
crash threshold — it silently succeeds on deeply-nested-but-sub-crash input rather than failing gracefully.
No test in the repository (including the dedicated `test_obligation_security_limits.py`) exercises
`upgrade`/`plan_downgrade`/`downgrade` at all.
**User impact:** any service accepting notebook content as an already-parsed dict (an API request body, a
database row, another tool's output) rather than routing it through libipynb's own bounded `load()` path,
and then calling any of these three conversion functions, can be crashed by a small, trivially-crafted
payload — a genuine, easily-triggered denial-of-service vector against a documented safety guarantee.
**To reach D3:** call `enforce_structure()` (or an iterative deep-copy) inside `_copy_source()` before any
further processing in all three entry points; add a regression test mirroring the existing
`max_nesting_depth` test but targeting `upgrade`/`plan_downgrade`/`downgrade` directly.

### Lone UTF-16 surrogate crashes the reader and (conditionally) the writer — D3, HIGH (adversarially confirmed, nuanced)
**What's thin:** a syntactically-valid JSON payload containing an unpaired UTF-16 surrogate escape (e.g.
`\ud800` — legal per RFC 8259, and handled cleanly by both Python's `json.loads()` and the real `nbformat`
package used as oracle) crashes `loads()`/`load()` with an **uncaught `UnicodeEncodeError`** from
`security/limits.py`'s `_utf8_size` helper, in **all three parse modes including `recovery`** — whose
entire documented purpose is to never crash on malformed input. Adversarial re-verification independently
reproduced this exactly and additionally clarified the writer-side half of the original finding, which
had overstated its generality: `writer.dumps()`/`dump()` crash the same way **only** when called with
`profile='declared'` (the default `profile=None`/numeric-profile path happens to route through `validate()`
first, which incidentally catches the same exception via an unrelated broad `except` clause and re-raises
it as a clean `NotebookWriteError` — accidental protection, not a defended path). Critically, **every
write call the shipped CLI makes uses `profile='declared'`** (`execute`, `upgrade`, `convert`, `merge`,
`diff`, the git-merge-driver) — so the CLI's actual, real-world write path is exactly the vulnerable one,
despite the general `dumps()` API not being universally vulnerable.
**To reach D4:** wrap the UTF-8 byte-counting walk in both `_utf8_size` and `writer.py`'s equivalent
`enforce()` call in a handler that catches `UnicodeEncodeError` and re-raises as
`NotebookParseError`/`NotebookWriteError` with a clear code, across all three parse modes and all write
profiles.

### `probe()` (format sniffing) — D1
**What's thin:** zero test coverage anywhere in the repository (confirmed by grep, not inference); its
confidence heuristic is trivial — `probe('{"nbformat": 999}')` returns `matched=True`.
**To reach D3:** add direct tests; tighten the confidence heuristic or document it as a rough signal
only.

### `NotebookSecurityError` — D0
**What's thin:** it's dead code. Documented ("Raised for security constraint violations"), publicly
exported, but `grep -rn "raise NotebookSecurityError" src/` matches only the class definition.
**To reach D1+:** either wire it into an actual enforcement site (e.g. an opt-in strict mode for
exporters) with tests, or remove it from the public exception hierarchy.

### `AttachmentManager.add()`/`.rename()` — D2 (security), MEDIUM
**What's thin:** zero base64 or path-safety validation on attachment payloads/names — confirmed
`add('m2', '../../etc/passwd', {...})` succeeds and stores the literal traversal name verbatim. The one
identified downstream consumer (`adapters/export.py`) independently defends against this, so today's
actual risk is contained — but the safety guarantee lives entirely in one downstream module, not in the
API that creates the data.
**To reach D3:** move (or share) the export layer's `_is_safe_resource_filename`-equivalent check into
`AttachmentManager` itself.

---

## 8. Missing-Feature Findings

| Missing capability | Confirmed via | Severity | Notes |
|---|---|---|---|
| PDF / slideshow / docx export | Source inspection (`export.py:189-248` hardcodes `['--to','html']`) | Low | `nbconvert` supports these formats; libipynb's subprocess-wrapper pattern could be trivially parametrized |
| `merge_notebooks()` notebook-level metadata conflict detection | Live repro: divergent `kernelspec.name` on both sides silently resolves to base's value with `has_conflicts=False` | Medium | Explicit, documented scope exclusion — but zero signal anywhere that a divergence occurred |
| nbformat major=3 (legacy IPython) write-back | Live repro: `probe()`/`load(mode='preservation')` accept it; `dumps()`/`dump()`/`roundtrip()` unconditionally fail in every profile | Low | Read-only dead end for an entire real-world notebook generation |
| `python -m libipynb.cli` invocation | Live repro: fails immediately, no `__main__.py` | Low | Console-script and `from libipynb.cli import main` both work fine |
| `NotebookSecurityError` real enforcement | See §7 | Medium | Currently a documentation lie, not a missing capability in the security sense — the actual security behavior (sanitization) exists, just doesn't use this exception |
| Oracle-verified `diff_notebooks()` vs `nbdime diff` | Confirmed: zero test compares them; README bundles a "diff/merge Oracle-verified" checkmark that only actually covers merge | Medium | See §14 |
| CLI `export` subcommand for `HtmlExporter`/`JupytextExporter` | Confirmed: neither has a CLI entry point | Medium | Real, working, oracle-quality features that are only reachable via direct Python import |
| `LocalJupyterExecutor` execution of list-of-lines-source notebooks | Confirmed via 3 independent reproduction paths + real git-driver end-to-end failure | **Blocker** | See §7 — the standard on-disk Jupyter source form is entirely unexecutable |
| Resource-limit enforcement on already-parsed dict input to `upgrade()`/`downgrade()` | Adversarially confirmed uncaught `RecursionError` | High | See §7 — `enforce_structure()` only runs on the `load()` path, not the lifecycle-conversion path |
| `nbformat.sign.NotebookNotary.mark_cells()`/`check_cells()` equivalent (per-cell trust fallback) | Source inspection: `grep mark_cells\|check_cells src/` — zero matches | Low | libipynb's trust module correctly ports the HMAC digest primitive (oracle-verified, §14) but not this separate per-cell render-decision policy |
| `text/markdown` output-MIME sanitization coverage | Live repro: identical hazardous payload delivered as `text/markdown` output data is invisible to `sanitize()` in every mode; the same payload as `text/html` or as markdown cell *source* is correctly caught | Medium | Isolated precisely to "markdown delivered via an output's MIME bundle" |

---

## 9. Round-Trip and Information-Loss Report

**Strong core fidelity, confirmed against the real oracle:** a full `libipynb → nbformat.reads/
validate → nbformat.writes → libipynb.load` round trip on 16 valid fixtures showed **zero true content
divergence** after normalizing the one known, schema-legal string-vs-list-of-lines source/text
representation difference. All 19 in-repo valid/corpus fixtures, loaded by libipynb in strict mode,
pass `nbformat.validate()` on the *same in-memory structure* with zero exceptions.

**Known, confirmed lossy or divergent points:**

1. **libipynb's writer never canonicalizes multi-line source/output text into nbformat's on-disk
   line-array form** (real Jupyter/nbformat always does via `split_lines()`). Not lossy in isolation
   (round-tripping purely through libipynb preserves whatever shape it was given), but it means
   libipynb-authored files are not byte-representationally identical to real Jupyter output for the
   same content, and this is the direct root cause of the `max_entries` false-rejection finding (§7)
   when a notebook has passed through real Jupyter tooling.
2. **`upgrade()` omits `metadata.orig_nbformat_minor`**, the provenance field `nbformat.v4.upgrade()`
   always records — the audit-trail information exists in libipynb's own `ConversionResult.actions`
   ledger, just not written into the notebook itself the way the reference implementation does.
3. **`AttachmentManager.rename()` corrupts list-form source segment boundaries on any length-changing
   rename** — confirmed live: renaming an attachment reference inside a list-of-lines source produces
   a joined text that's byte-correct but a two-element list whose items no longer represent the
   original line boundaries.
4. **Corrupt base64 payloads (in both attachments and outputs) are silently skipped during export**
   with zero diagnostic — confirmed live: 2 of 12 constructed adversarial attachments/outputs vanished
   from the exported resource list with no warning, no exception, no counter.
5. **Cross-cell attachment filename collisions silently overwrite each other on disk** — two attachments
   in different cells sharing an attachment key produce identical export filenames; writing them to
   disk (the exact usage the exporter's own docstring anticipates) silently loses one.
6. **`PythonScriptExporter` silently drops raw-cell content** while `metadata.cell_count` still counts
   it — confirmed with a real 4-cell notebook.
7. **`MarkdownExporter` hardcodes ` ```python ` code fences** regardless of the notebook's actual kernel
   language — confirmed on a real Julia-kernel notebook.
8. **`HtmlExporter`'s exported `<title>`** is always the literal string `"notebook"`, never the source
   file's real name, because the temp file it hands to `nbconvert` is hardcoded.

**Idempotency:** confirmed for `upgrade()`→`downgrade()`→`upgrade()` (exact same content-hash cell IDs
regenerated); confirmed for `roundtrip()` (`roundtrip(roundtrip(x))` byte-identical across the full
26-file fixture corpus); confirmed for `cleanup()` (nbstripout-parity tests assert idempotency).

---

## 10. Validation and Version-Compatibility Report

`validate()` is the single most rigorously verified capability in the library: **D5**, confirmed via
20/20 hand-crafted schema-edge-case agreement with `nbformat.validate()` (matching both verdict *and*
diagnostic path), 100% agreement across the full in-repo invalid/adversarial fixture set, and safe
rejection (no crash, no hang) of cyclic-reference and deeply-nested (500-level) adversarial `Mapping`
inputs fed directly to it bypassing JSON parsing entirely.

Two genuine, narrow divergences from the reference implementation were found, both low-severity and
arguably in libipynb's *favor*:

- **nbformat's own tooling (`nbformat.read()` + `validate()`) silently auto-repairs a missing/malformed
  `nbformat` version field before validating**, while libipynb correctly and loudly rejects it. (Note:
  `nbformat.validate()` called directly on the same raw parsed dict, without going through
  `nbformat.read()`'s auto-upgrade first, is exactly as strict as libipynb — the leniency is in
  `nbformat.read()`'s convenience wrapper, not `nbformat.validate()` itself.)
- **`nbformat.validate()` silently self-heals duplicate cell IDs** (mutating the notebook in-place with
  only a Python warning) and reports the notebook valid; libipynb correctly and non-destructively
  reports it as an error. Undocumented divergence, not currently captured in the interoperability test
  suite (the other two known leniency gaps are).

Version conversion (`upgrade()`/`plan_downgrade()`/`downgrade()`) is **D5** for its central safety
promise: a five-attack tamper-resistance suite (stale-plan reuse after mutation, forged plans hiding a
real loss, fabricated extra issues, silently-retargeted plans) was refused correctly in every case, and
a full upgrade↔downgrade↔upgrade round trip was cross-validated against `nbformat.validate()` at every
checkpoint with confirmed idempotent, content-hash-based cell-ID regeneration.

`SchemaArtifactError` (the corrupted-vendored-schema failure path) now has confirmed **behavioral**
correctness (forced via a runtime digest tamper, correctly surfaces as a clean diagnostic, no crash) but
still has **zero committed regression test** for this path — a test-quality gap, not a correctness gap.

---

## 11. Security and Untrusted-Input Assessment

The dedicated security domain ran 112 existing tests (all pass, run twice for confirmation) plus 10+
independently-authored adversarial probes covering `sanitizer.py` (4 modes: LOSSLESS/REMOVE/QUARANTINE/
MARK_UNTRUSTED), `limits.py`, `secrets.py`, and `trust.py`.

**Sanitizer — real detection confirmed, two real gaps found:**
- SVG-embedded-script, SVG-`onload`, and HTML-embedded-`<script>` are all correctly detected and
  correctly handled across all four sanitization modes — `REMOVE` verified to actually delete the
  payload key, `QUARANTINE` verified to move it into `metadata.notebook_security.quarantine`,
  `MARK_UNTRUSTED` verified to leave the payload byte-identical while recording metadata.
- **The `text/markdown` output-MIME blind spot is real**, isolated precisely: the identical hazardous
  payload delivered as an output's `text/markdown` data produces zero findings in every mode, while the
  same payload as `text/html` output data, or as a markdown-typed **cell's source**, is correctly caught
  — the gap is specific to markdown delivered via an output's MIME bundle, not markdown scanning broadly.
- **New finding: `sanitize()`'s `max_entries` limit only counts hazard *observations*, not total markup
  tokens parsed.** A payload dense with harmless tags (`'<p>'*300000`, zero attributes, zero active
  elements) is fully tokenized by the pure-Python `HTMLParser` at proportional CPU cost with **zero**
  resource-limit engagement, because it produces no hazard observations to count. Measured 4.4s of CPU
  time to scan a 6 MB harmless-tag-dense payload; linear extrapolation to the library's own default
  `max_decompressed_bytes` ceiling (2 GB) suggests **over 10 minutes of single-threaded blocking CPU
  time** for one `sanitize()` call that is fully within documented default limits. The byte-based limits
  bound *input size*, not *wall-clock scan time* — a real DoS-shaped gap for any service exposing
  `sanitize()` on untrusted payloads with a time budget in mind. (Severity: medium.)
- The event-handler heuristic (`if name.startswith("on")`) is confirmed false-positive-only (flags
  benign attributes like `online=`/`onward=`) — fails safe, degrades fidelity only. **Adversarial
  re-verification separately confirmed this entire detector, plus 13 of the 14 active-element categories
  and the CSS/markdown URI-scheme detectors, have zero test coverage** despite being implemented and
  functionally correct (confirmed via coverage instrumentation, not just grep) — see §13.

**Trust — independently oracle-verified beyond the shipped test:**
- A freshly-authored differential probe (not reusing the shipped test file) loaded 10 real fixture
  notebooks via both `nbformat.read()` and `libipynb.load()`, computed HMAC-SHA256 signatures with the
  same secret via both `nbformat.sign.NotebookNotary` and `HmacNotebookNotary`, and got **byte-identical
  digests on all 10**, plus lockstep trust-invalidate-on-edit/restore-on-revert parity.
- **Gap found:** libipynb's trust module has no equivalent of `nbformat.sign.NotebookNotary.mark_cells()`/
  `check_cells()` — the per-cell "is this cell's output safe to render even without a valid whole-notebook
  signature" fallback logic real Jupyter frontends use. Low severity, modest real-world impact.
- `SqliteSignatureStore`'s owner-only file-permission restriction is confirmed a genuine no-op on Windows
  (`os.stat` on a live-created store showed mode `0o666`, world read+write) — exactly as its own
  docstring warns; not a full compromise (forging a signature still requires the HMAC secret) but
  empirically inactive on this platform.

**Secrets scanning — strong on both axes:**
10/10 realistic true-positive secret shapes (AWS keys, GitHub/Slack/Google tokens, PEM blocks, JWTs,
Bearer tokens, URL-embedded credentials) correctly matched; 6/6 benign look-alikes correctly produced
zero findings; the ruleset's regexes were adversarially checked for ReDoS/catastrophic backtracking up
to 200,000-character near-miss inputs and scaled linearly throughout (sub-10ms), no quadratic blowup
found.

**Resource limits — genuinely enforced on the `load()` path, with one adversarially-confirmed gap
elsewhere:** 1,000-level-deep nesting, 200k-cell arrays, and an 80MB oversized input all raise typed
`NotebookResourceLimitError` in well under 50ms via the public `loads()`/`load()` API; at depths beyond
libipynb's own check (~5,000+), CPython's own JSON-parser recursion guard fires first and is correctly
reclassified into a typed error rather than leaking a raw `RecursionError`. **However, adversarial
re-verification found the equivalent guarantee does not extend to `upgrade()`/`plan_downgrade()`/
`downgrade()`** on already-parsed dict input — see §7 for the confirmed uncaught-`RecursionError` DoS
gap in that sibling code path, which the `enforce_structure()` guarantee above does not cover.

**Cross-cutting security findings independently confirmed by other domains:**

- **Resource limits are shape-dependent, not type-dependent.** A 2,000,000-element array of small
  objects (structurally like a notebook's own `cells` list) is rejected almost instantly (0.007s,
  aborting at 1,001 entries) — genuine incremental protection. A 2,000,000-element **flat** array of
  scalars, or a single giant **flat** object, both fully materialize (0.86–1.18s) before rejection —
  a real, precisely-characterized gap for those shapes specifically, not for JSON arrays/objects in
  general as a first-pass reading might suggest.
- **`TextIO`/stream sources are read to complete EOF before `max_input_bytes` is checked** — confirmed
  with an instrumented counting stream: a 30 MB payload against a 1 KB limit was fully read (all 30M
  characters pulled, 60 MB tracemalloc peak) before rejection. The `Path`-based load path checks size
  first and does not have this gap.
- **Deeply nested JSON (5,000 and 100,000 levels) is safely rejected in ~0ms** via a
  `RecursionError`→`NotebookParseError` conversion at both depths tested — genuine hardening, no hang,
  no raw exception leak.
- **Path-traversal filename safety holds** for the one identified consumer (`export.py`'s
  `_collect_resources`), tested against 4 traversal/absolute-path variants end-to-end through the real
  exporter classes — but the guarantee is bypassable by constructing `AncillaryResource` directly
  (confirmed live), and does not exist at all in `AttachmentManager`'s own write API (§7).
- **`SECURITY.md`'s "no subprocess execution" claim is false** and directly contradicted by the
  project's own enforced allowlist test (`tests/integration/test_obligation_security_baseline.py`,
  which explicitly names and tests three files that do use `subprocess`). This is a documentation
  accuracy defect, not a behavioral one — the subprocess usage itself (git-driver install, HTML export,
  the legacy execution adapter) is intentional, tested, and allowlisted.
- **Trust/signing is genuinely thread-safe under real concurrent load** — 24 threads sharing one
  `MemorySignatureStore` via `HmacNotebookNotary.sign()`/`verify()`, 0 errors.
- **General concurrent mutation of a single shared `NotebookDocument` is explicitly UNVERIFIED**, not
  confirmed safe — a `list.append()`-only stress test showed no lost writes, but this is flagged as a
  likely CPython-GIL artifact (single-bytecode-atomic operation) rather than evidence of a designed
  guarantee; a read-modify-write pattern was not tested and would very plausibly corrupt state.

---

## 12. Performance and Large-Notebook Assessment

No dedicated performance/stress/concurrency test file exists anywhere in the repository (confirmed by
search, not grep alone). This audit built fresh stress fixtures. Headline results on a realistic
25.14 MB / 3,000-cell / 400-image-output synthetic notebook (not an extreme pathological case):

- A single strict-mode **load→validate→write cycle costs ~25–30 seconds of wall time**, dominated by
  repeated full-tree jsonschema validation (confirmed: **two separate full validation passes happen by
  default** — once on a strict-mode load, and again on `writer.dumps(doc)` with no explicit `profile=`
  argument, because the un-parametrized default silently resolves to the schema-validating `'4.5'`
  profile rather than the cheap `'declared'` passthrough — a **16×–70× slowdown** for the single most
  natural way to call the writer, confirmed by direct timing: 0.134s vs 2.17s (warm) / 9.6s (cold)).
- Memory growth is modest and roughly linear (~2.3× notebook size) — **the bottleneck is CPU, not
  memory.**
- `CellEditor` operations cost **~700ms–3.5s per edit** on a multi-thousand-cell notebook because every
  mutation deep-copies the whole notebook and unconditionally runs full validation before checking
  `dry_run` — confirmed by a 20-edit sequential timing loop (14.85s total) and a direct comparison
  against `NotebookDocument.add_cell()` (0.0004s, no validation).
- **`dry_run=True` provides zero performance benefit** over an applied edit (1.28s vs 1.44s on a
  4,000-cell notebook) because validation runs before the `dry_run` check, not after — the "preview"
  API costs exactly as much as committing.
- At realistic (not extreme) scale, `diff_notebooks()` (0.41s), `merge_notebooks()` (0.88s),
  `sanitize()` (0.05s), and `scan_for_secrets()` (0.04s) are all comfortably sub-second — this
  **downgrades** the practical severity of the same operations' cost at the far more extreme 500+ MB
  scale a prior static pass had used; the underlying architectural inefficiencies (redundant
  serialization, unconditional double-deepcopy) remain real code-quality issues but are not a practical
  bottleneck for realistic notebooks.

---

## 13. Test-Quality and Obligation-Coverage Matrix

**Baseline is substantive, not rubber-stamped:** `pytest tests/ -q` → 879 passed / 4 skipped (all 4
legitimate: 2 POSIX-only tests correctly skipped on Windows, 2 documented nbformat-leniency
divergences with an explanatory skip message). 89.11% coverage against an 85% gate. At least three
regression tests in the current suite trace directly to a real bug an adversarial/fuzz pass found
(a secret-preview redaction leak, a `merge_notebooks()` `KeyError` crash found by fuzzing, and a
live-dict-mutation false-pass bug in an earlier version of a diff test) — genuine evidence of a
test-writing discipline that responds to real failures, not just happy-path coverage.

**Specific, well-evidenced gaps** (not systemic):

| Gap | Evidence | Severity |
|---|---|---|
| `validate_notebook()`/`validate_notebook_schema()` — **zero test coverage** | `--cov-report=term-missing` shows their full bodies uncovered; grep confirms zero references anywhere in `tests/` | Medium |
| `NotebookResourceLimits.max_output_bytes` — never triggered by any test; none of the 5 numeric defaults are pinned by any assertion | Corroborates a prior, independently-dated mutation-testing finding (`security/limits.py`: 20% kill rate, "NEEDS_HARDENING") | Medium |
| `NotebookSecurityError` — dead code, zero test references | See §7 | Medium |
| Fixture corpus is **100% synthetic/hand-crafted** — no real notebook captured from an actual authoring tool | `tests/fixtures/PROVENANCE.md` classifies every one of 27 fixtures as synthetic or hand-crafted | Low |
| Property-test (`hypothesis`) strategy only exercises `mode='recovery'`/`profile='declared'`; never generates error/`display_data` outputs, attachments, or explicit cell IDs | Direct reading of the strategy definitions | Low |
| Secret scanner: strong true-positive coverage, **almost no false-positive coverage** | Exactly one clean-notebook test exists, using a trivially benign string | Low |
| `diff_notebooks()` has **zero** oracle-comparison coverage (only `merge_notebooks()` got the 3 `nbdime` oracle tests) | Confirmed by exhaustive grep and by reading `test_nbdime_parity.py` in full | Medium |
| Mutation testing (`mutmut`) — **environment-blocked on native Windows**, confirmed directly (`mutmut run` exits immediately: "please use the WSL") | Not run by this audit; a prior dated campaign's results (in `plans/phase2b-execution-evidence.md`) are corroborating-but-unverified-by-this-pass |Info |
| Fuzzing (`atheris`) — **environment-blocked on native Windows**, confirmed directly (no Windows wheels) | Static review of all 4 fuzz targets: reasonable, structure-aware; the one historically-found crash has verified regression tests in the current green suite | Info |
| **Event-handler attribute (`onerror=`, `onclick=`, etc.) XSS detection — zero test coverage** (adversarially CONFIRMED) | Coverage instrumentation independently confirms lines 184-185 of `sanitizer.py` are never executed by any test; live repro confirms the detector itself works correctly today (`onerror=` on an `<img>` tag is correctly flagged) — a regression here would ship silently | **High** |
| **13 of 14 active-element hazard categories (iframe/object/embed/meta/frame/form/link/style/…) plus `javascript:` URI and CSS `url()` detectors — implemented but entirely untested** (adversarially CONFIRMED) | Coverage instrumentation independently confirms; only `<script>` has any test; a differential probe confirmed all 13 untested categories are in fact correctly detected by the current implementation — this is a coverage gap, not a functional bug | **High** |
| `tests/oracle/` (5 files, 747 lines — the repo's highest-value independent-oracle tests) and `tests/package/` are **never executed by CI** (`.gitlab-ci.yml` only runs `unit/integration/security`, `property`, and `interoperability`) | Confirmed via direct grep of `.gitlab-ci.yml`; corroborated independently by the plans-reconciliation domain, which notes the project's own P7 taskcard already discloses this | **High** |

---

## 14. Independent-Oracle Results

| Comparison | Result | Verdict |
|---|---|---|
| `libipynb.load()` output → `nbformat.validate()` (same in-memory structure) | 19/19 fixtures agree | libipynb defect: none |
| `nbformat`-built notebook → `libipynb.load()` → field diff | Content-identical after string-vs-list-of-lines normalization | libipynb defect: none (documented divergence) |
| `libipynb` → `nbformat` → `libipynb` full round trip (15 fixtures) | Byte-for-byte identical except the same known normalization | libipynb defect: none |
| Invalid-input agreement (20 hand-crafted + all in-repo invalid/adversarial fixtures) | 20/20 + all fixtures agree except duplicate-cell-ID handling | Real, low-severity, previously-undocumented divergence (nbformat self-heals; libipynb rejects) |
| Version-migration agreement (`upgrade()` vs `nbformat.v4.upgrade()`) | Both schema-valid; libipynb omits `orig_nbformat_minor` | Real, low-severity fidelity gap |
| Ordinary large-notebook agreement (4 MiB / 150k-line single cell) | **nbformat accepts, libipynb rejects by default** | **Real, HIGH-severity divergence** — see §7 |
| `merge_notebooks()` vs real `nbdime`/`nbmerge` (3 scenarios) | Full agreement + 2 correctly-documented intentional divergences (marker-splicing, `use-base` silent resolution) | Genuinely oracle-verified |
| `diff_notebooks()` vs real `nbdime diff` | **Never compared by the repo's own test suite** — this audit ran the comparison itself and found a real, undocumented id-vs-content cell-matching divergence | Real, medium-severity, undocumented — and a doc-drift issue (README bundles it under a merge-only "oracle-verified" claim) |
| `cleanup()` vs real `nbstripout` 0.9.1 | Byte-for-byte agreement including nested-output `execution_count` reset | Genuinely oracle-verified |
| `HtmlExporter` vs direct `nbconvert --to html --stdout` | Byte-identical except one hardcoded-`<title>` bug | Genuinely oracle-verified (with 1 known minor gap) |
| `JupytextExporter` vs direct `jupytext --to py:percent` | **Byte-identical**, exact match | Genuinely oracle-verified |
| `HmacNotebookNotary` vs real `nbformat.sign.NotebookNotary` (10 real fixtures, independently-authored probe) | **Byte-identical HMAC-SHA256 digests on all 10**, plus lockstep trust-invalidate-on-edit/restore-on-revert parity | Genuinely oracle-verified, independently reproduced beyond the shipped test |
| `LocalJupyterExecutor` vs direct `nbconvert --execute` and real `papermill` (string-source notebooks) | Deterministic fields agree exactly (success + error paths) | Genuinely oracle-verified — **but see §7: the executor cannot run list-of-lines-source notebooks at all**, so this agreement covers a narrower input space than the notebooks most users actually have |

---

## 15. Developer-Usability Assessment

**Strong, verified-not-assumed:**
- All 12 CLI subcommands' `--help` succeed; every subcommand ran cleanly against a real, non-trivial
  fixture with correct output (`sanitize` genuinely detected a real hazard, not a zero-hazard fixture).
- Both `examples/` scripts and all 4 README Quick Start Python snippets ran **verbatim, with zero API
  drift**, pulled directly from the docs and executed.
- `mypy --strict` passes clean on the full 40-file source tree, substantiating the "Typing :: Typed"
  packaging classifier.

**Weak points, all confirmed by direct execution, not inference:**
- CLI error handling is broken for the majority of non-happy-path input (§7).
- `libipynb diff`/`libipynb merge` don't work on the majority of real-world existing notebooks, and this
  breaks the real `git diff`/`git merge` integration end-to-end, not just the standalone CLI (§7).
- `libipynb execute` (the flagship real-kernel feature) fails completely on notebooks whose code cells
  use the standard on-disk list-of-lines source form (§7) — confirmed at the CLI layer independently of
  the execution-engine domain's own finding of the same root defect.
- **README's own "Round-trip a notebook" Quick Start snippet, run verbatim, crashes with an uncaught
  `NotebookWriteError`** against a realistic nbformat-4.4 notebook (the exact same fixture format the
  adjacent "Supported Versions" table documents as supported) — `dump()`'s default profile always
  targets 4.5, so the snippet only works if the input already happens to be 4.5. Succeeds cleanly
  against a 4.5 control fixture.
- `python -m libipynb.cli` doesn't work — a one-line fix (add `__main__.py`).
- Two real, working, oracle-quality features (`HtmlExporter`, `JupytextExporter`) are invisible to
  anyone reading only the README or `--help` (§14) — a genuine discoverability gap for otherwise-solid
  code.

---

## 16. Independence and Packaging Assessment

- **Clean build verified:** `python -m build --wheel`/`--sdist` succeeds from a clean checkout; the
  sdist contains only the correct files (no `tests/`, `plans/`, `.gitlab-ci.yml`, `.supervisor/`
  leakage).
- **Clean install verified:** the built wheel installs into a fresh, throwaway venv and works
  end-to-end (import, load, validate, dump, CLI) resolved from `site-packages`, not the source tree —
  confirmed via `Path(libipynb.__file__).resolve()`.
- **Import-boundary enforcement is real:** `tests/unit/test_import_boundary.py` statically AST-parses
  every source file and fails on a forbidden import; independently cross-checked by grep. The core
  library genuinely has zero runtime import dependency on any oracle/exec/export-extra tool.
- **Internal-URL leak, confirmed in the actual built artifact, not just source, re-confirmed on a second
  independent build:** `pyproject.toml`'s `[project.urls] Repository` field
  (`gitlab.recruitize.ai/sialkot/cantt-smallize/libipynb`, a private internal GitLab instance) is present
  verbatim in the built wheel's `dist-info/METADATA`; the same URL also appears in `CONTRIBUTING.md`'s
  clone instructions. Already flagged as "undecided" in `plans/publication-readiness-assessment.md:140`;
  still unresolved. The second audit pass classified this as a publication **blocker** (not merely
  medium) — any public PyPI release would publish an unreachable internal path and organizational
  codenames in machine-readable metadata scraped by pip/SBOM/license tooling. No other internal-
  terminology leakage was found in the actual code payload (sdist/wheel file lists inspected directly,
  twice, independently).
- **`SECURITY.md`'s "no subprocess execution" claim is false** (§11) — real, executed `subprocess.run()`
  calls exist in `adapters/execute.py`, `adapters/export.py` (`HtmlExporter`), and `cli/main.py` (git
  integration). A security reviewer scoping the package's attack surface before allowing it into a
  restricted environment would be materially misled. (Severity: high.)
- `pyyaml` is declared in the `test` extra and described in `CONTRIBUTING.md` but is never imported
  anywhere — a dead declared dependency.
- `nbformat` is imported directly inside `adapters/jupyter_execute.py` but is not explicitly declared in
  the `exec` extra — works today only because `nbclient` happens to depend on it transitively; no direct
  pin protects against a future `nbclient` release dropping that dependency.
- No published release exists: `git tag -l` is empty, local `master` is 10 commits ahead of
  `origin/master` — nothing has actually shipped yet.

---

## Plan and Gate Reconciliation

The repository's own planning system (`plans/full-parity-plan.md`, `plans/remediation-plan.md`, plus
three execution-evidence documents) was read in full and cross-checked against every domain finding
above, including independently re-reading the plan's own cited evidence files rather than trusting the
status line alone. **Most taskcard statuses reconcile cleanly**: V1 (secrets), V2 (persistent trust
store), and V5 (HTML/Jupytext export) `completed_verified` claims all check out against this audit's
independent findings; V3 (fuzz harness)/V7 (oracle expansion) `partially_done`/environment-blocked
statuses are honestly reported and independently reconfirmed as genuine, not silently-skipped, Windows
constraints; B3/B4's `blocker` status (nothing published, no `v0.1.0` tag) is accurate.

**Two real, traceable contradictions were found, both root-caused to a specific, narrow process gap
rather than general overclaiming:**

- **P4a-1/P4b/P4c** (the real Jupyter-kernel execution engine) are marked `completed_verified` with
  Gates G1/G2/G6/G8 all claimed satisfied. This audit found `LocalJupyterExecutor` cannot execute
  list-of-lines-source notebooks at all (§7, §17 blocker #1). Root cause: the plan's own cited Gate G2
  review for this round was explicitly **self-review only** — the execution-evidence document states
  verbatim that the review "was not separately delegated to another agent invocation this round," unlike
  prior rounds' genuinely independent reviews — and the one test built to cover this exact input shape
  (`test_list_of_lines_source_form_is_preserved_unchanged`) only asserts field preservation, never
  execution success.
- **P3a/P3b/P3c** (diff/merge/git-driver) are marked `completed_verified` with Gate G2 (and G8 for P3c)
  satisfied. This audit found `diff_notebooks()`/`merge_notebooks()` unconditionally require every cell
  to carry a non-empty string id — structurally incompatible with 5 of the 6 nbformat minor versions the
  README's own "Supported Versions" table lists as supported (§7, §17 blocker #2). Root cause: P3b's
  Gate G2 review was genuinely adversarial and found 9 real, reproduced defects in that round — but never
  tested against a pre-4.5, cell-id-less fixture, and no P3a/P3b/P3c taskcard's required-test list names
  one.

**A softer, cross-cutting reconciliation finding:** Gate G8's oracle-comparison evidence is genuinely
executed and genuinely passing, but `tests/oracle/`/`tests/package/` are never wired into
`.gitlab-ci.yml` — confirmed independently by both the plans-reconciliation and test-quality-audit
domains (§13, §17 item 14). "`completed_verified`"/"Gate G8 PASSED" is accurate as a one-time,
human-verified claim; it does not function as a continuous regression gate, a limitation the plan itself
discloses but that is easy to over-read as permanent protection.

---

## 17. Publication Blockers

`P0` items — must be fixed before this can honestly be called production-ready for its advertised
feature set (real-kernel execution and CLI git-workflow integration are both currently broken for
common, not edge-case, real-world input):

1. **`LocalJupyterExecutor` cannot execute any notebook whose code cells use list-of-lines source** —
   the standard on-disk Jupyter form (40% of this project's own fixtures). This is the single most
   severe finding in the audit: it makes the newly-shipped, flagship kernel-execution feature unusable
   for a large fraction of real notebooks, misreports the failure as a generic kernel crash, and the one
   existing test built to catch this never actually checks execution success.
2. **`libipynb diff`/`libipynb merge` crash on the majority of real-world (pre-4.5) notebooks** —
   confirmed to break the real `git diff`/`git merge` integration end-to-end (`git diff` itself exits
   128), not just the standalone CLI command. This directly undermines the CLI's core marketed
   differentiator vs. `nbdime`.
3. **CLI has no top-level exception handling** across `diff`/`merge`/`execute`/`trust`/`convert`
   (downgrade)/`inspect`/`analytics` — raw tracebacks instead of the clean-error convention the codebase
   already knows how to implement elsewhere (`trust`'s own secret-length checks).
4. **Internal private GitLab URL and organizational codenames are baked into the published wheel's
   `dist-info/METADATA`** — confirmed present in a real built artifact, twice, independently. A public
   PyPI release today would publish an unreachable internal repository path in machine-readable package
   metadata.

`P1` items — should be fixed before or shortly after a first public release, not blocking but high-risk
if deferred:

5. **Default `max_entries` resource limit rejects legitimate large notebooks** that the official
   `nbformat` reference implementation accepts without complaint — a false-positive DoS guard that will
   surprise real users with real (if uncommon) large notebooks.
6. **Uncaught `RecursionError` in `upgrade()`/`plan_downgrade()`/`downgrade()`** on already-parsed dict
   input at ~495+ levels of nested metadata — a trivially-triggered DoS gap in a documented safety
   guarantee, with `upgrade()` specifically enforcing no structural limit at all below the crash
   threshold, and zero test coverage for any of the three functions.
7. **Lone UTF-16 surrogate escapes crash the reader in all three parse modes** (including `recovery`,
   whose entire purpose is graceful degradation) and crash the writer specifically under
   `profile='declared'` — which is the profile every shipped CLI write path actually uses.
8. `to_dict()`/`.metadata` shallow-copy leak (silent data corruption risk for any consumer).
9. `execute_notebook`'s `max_output_bytes` truncation silently drops unrelated cell results.
10. `LocalJupyterExecutor` swallows `KeyboardInterrupt`; has no output-size or memory cap on any
    platform (confirmed: 50MB stdout, a 300MB in-kernel allocation, both unimpeded).
11. `SECURITY.md`'s false "no subprocess execution" claim.
12. `sanitize()`'s resource limits bound input bytes but not wall-clock scan time — a harmless-tag-dense
    payload well within default limits can block a worker for minutes.
13. `HtmlExporter`/`JupytextExporter` undocumented in README/CHANGELOG despite being real, tested, and
    marked `completed_verified` internally.
14. `tests/oracle/` and `tests/package/` — the repository's highest-value independent-oracle evidence —
    are never executed by CI; "Gate G8 PASSED"/`completed_verified` labels are accurate as one-time,
    hand-verified claims but are not continuously regression-protected.
15. The event-handler-attribute and 13-of-14-active-element sanitizer detectors are implemented and
    confirmed working, but have zero test coverage — a regression would ship silently.

---

## 18. MVP Capability Contract

What's **already genuinely there** at D3+ and can be honestly advertised today: file/bytes/stream/
string I/O with 5-way agreement; strict/preservation/recovery parsing; deterministic serialization;
atomic writes; the full nbformat 4.x data model (cells, metadata, outputs, MIME bundles, attachments);
D4-hardened cell manipulation (insert/remove/replace/move/reorder) via `CellEditor`; D5 schema
validation with structured diagnostics; D5 tamper-resistant version upgrade/downgrade; D4–D5
oracle-verified diff and merge algorithmics on nbformat-4.5 (cell-ID-bearing) notebooks (for the merge
half — see §14 caveat on diff); D5 nbstripout-parity cleanup; D5 Jupyter-compatible HMAC trust signing,
independently oracle-verified across 10 real fixtures; a D5-verified real Jupyter-kernel execution
engine **for notebooks whose cell source is a plain string** (not the on-disk list-of-lines form —
see the P0 blocker in §17); oracle-verified HTML and Jupytext export; strong true/benign secret-scanning
discrimination with no ReDoS exposure; active-content detection that correctly catches the common attack
shapes (`<script>`, SVG `onload`, event-handler attributes) even though most of that detector surface
lacks regression tests.

What should **not** yet be advertised without the P0 fixes in §17: real-kernel execution as
"just execute your notebook"; the CLI's `diff`/`merge`/`execute` commands, or the git driver integration,
as "just works on your existing notebooks"; any claim about resilience to malformed CLI input; the
default resource limits as tuned for legitimate large notebooks rather than only adversarial ones, or as
covering the `upgrade`/`downgrade` code path; `sanitize()`'s resource limits as a wall-clock time bound.

---

## 19. Professional and Competitive Capability Roadmap

**Professional completeness (P2), beyond MVP:**
- Structured CLI error handling across all commands (closes P0 #2).
- Oracle-comparison coverage for `diff_notebooks()` (closes the diff/merge documentation-claim gap).
- Boundary tests pinning `NotebookResourceLimits`' numeric defaults; a real notebook (not just
  adversarial payloads) in the resource-limit test suite.
- `AttachmentManager`-level base64/path-safety validation (moving the safety guarantee from one
  downstream consumer into the API that creates the data).
- A CLI `export` subcommand exposing `HtmlExporter`/`JupytextExporter`.

**Competitive enhancements (P3):**
- Deep-copy-consistent accessor layer (closes the `to_dict()`/`.metadata` leak as a designed guarantee,
  not just a patch).
- A real batch/bulk-edit mode for `CellEditor` that validates once per batch instead of per edit (closes
  the performance gap without sacrificing the atomic-commit guarantee).
- `writer.dumps()`'s default profile changed to the cheap `'declared'` path (or the cost clearly
  surfaced), removing an easy-to-hit performance trap from the library's most natural call.
- PDF/slideshow export via the same subprocess-wrapper pattern already proven for HTML.

**Optional integrations (P4) / explicit non-goals:** resource-isolation/sandboxing for
`LocalJupyterExecutor` (the project's own plan already correctly scopes this as a non-goal for the
current card — this audit's finding that no output cap exists is *consistent with*, not a gap missed
by, that pre-declared scope); a general concurrent-mutation guarantee for a single shared
`NotebookDocument` (current evidence neither confirms nor denies safety here — treat as unsupported
until deliberately designed and tested, not as a bug).

---

## 20–21. Prioritized, Dependency-Aware Implementation Backlog and Waves

**Wave -1 (the two functional blockers — highest priority, independent of each other, no shared
dependency):**
- `GAP-00a` Normalize `cell['source']` (list→joined string) before handing the execution copy to
  `nbclient` in `_build_client()`, mirroring `adapters/execute.py`'s existing `_cell_source()` helper;
  strengthen `test_list_of_lines_source_form_is_preserved_unchanged` to assert on `completed`/outputs,
  not just field preservation (closes P0 blocker #1 — the single most severe finding in this audit).
  *Dependencies: none. Tests: list-source fixture through both `execute()`/`execute_async()` and the CLI
  `execute` command. P0.*
- `GAP-00b` Fix `diff`/`merge` crash on pre-4.5 (no cell-id) notebooks — either transparent internal
  cell-ID synthesis (mirroring `upgrade()`'s existing content-hash logic) or a clean error naming
  `libipynb upgrade` as the fix (closes P0 blocker #2). *Dependencies: none. Tests: pre-4.5 fixture
  through the plain CLI *and* the real git diff/merge driver end-to-end. P0.*

**Wave 0 (foundation — do first, everything else depends on document-model correctness):**
- `GAP-01` Deep-copy the 4 leaking accessors (`to_dict`, `.metadata`, `Cell.metadata`, `Cell.outputs`).
  *Dependencies: none. Tests: mutation-after-access regression + property test. P1.*
- `GAP-02` Fix `AttachmentManager.rename()`'s list-source segment-boundary corruption.
  *Dependencies: none. Tests: length-changing rename regression. P2.*
- `GAP-02b` Guard `lifecycle.py`'s `_copy_source()` with `enforce_structure()` (or an iterative deep
  copy) before `upgrade()`/`plan_downgrade()`/`downgrade()` do any further processing — closes the
  adversarially-confirmed uncaught-`RecursionError` DoS gap. *Dependencies: none. Tests: the same
  `max_nesting_depth` pattern already used for `validate()`, targeting all three lifecycle entry points
  directly. P1.*
- `GAP-02c` Catch `UnicodeEncodeError` in `security/limits.py`'s `_utf8_size` and in `writer.py`'s
  equivalent `enforce()` call, re-raising as `NotebookParseError`/`NotebookWriteError`, across all three
  parse modes and (critically) the `profile='declared'` write path the CLI always uses. *Dependencies:
  none. Tests: lone-surrogate fixture through `loads()` in all 3 modes and `dumps(profile='declared')`.
  P1.*

**Wave 1 (CLI robustness — depends on nothing new, pure error-handling work):**
- `GAP-03` Add shared exception handling to `main()` dispatch (closes P0 blocker #3).
  *Tests: missing-file/bad-input regression per command. P0.*
- `GAP-05` Add `src/libipynb/cli/__main__.py` (one-line fix).
  *P3.*
- `GAP-05b` Either have `dump()`'s default profile target the document's own declared version rather
  than always 4.5, or add an explicit `upgrade()` call/caveat to the README's "Round-trip a notebook"
  Quick Start snippet, so it doesn't crash verbatim on a realistic nbformat-4.4 input. *P2.*

**Wave 2 (resource limits — depends on measuring real-world notebook sizes, not code changes to the
document model):**
- `GAP-06` Raise/redesign default `max_entries` to not reject legitimate large notebooks (closes P1
  item #5). *Tests: the exact 150k-line repro from §7 as a regression fixture. P1.*
- `GAP-07` Bound `TextIO` source reads (chunked read-and-check instead of unbounded `.read()`).
  *P2.*
- `GAP-08` Extend `bounded_object_pairs_hook`'s incremental protection to flat scalar arrays / single
  large flat objects. *P2.*
- `GAP-08b` Add a total-token counter to `sanitizer.py`'s `_MarkupScanner` (not just hazard
  observations) and enforce it against `max_entries` or a dedicated limit, so a harmless-tag-dense
  payload can't consume unbounded wall-clock CPU time within documented byte limits. *P1.*

**Wave 3 (execution safety — beyond Wave -1's blocker fix; depends on Wave 0's document-model fixes
being in place first, since execution results reference the document):**
- `GAP-09` Narrow `LocalJupyterExecutor.execute()`'s except clause (stop swallowing
  `KeyboardInterrupt`/`SystemExit`). *P1.*
- `GAP-10` Fix `execute_notebook`'s `max_output_bytes` per-record truncation. *P1.*
- `GAP-11` Add an output-size cap (or explicit documentation of its absence) to `LocalJupyterExecutor`.
  *P2.*
- `GAP-12` Add a structured timeout signal independent of `KeyboardInterrupt` string-matching. *P2.*

**Wave 4 (packaging/publication — independent of the above, can run in parallel):**
- `GAP-13` Resolve the internal GitLab URL in `pyproject.toml`'s `Repository` field and
  `CONTRIBUTING.md`'s clone instructions before any public release (closes P0 blocker #4).
  *P0 for publication, though not a functional blocker.*
- `GAP-14` Correct `SECURITY.md`'s "no subprocess execution" claim. *P1.*
- `GAP-15` Document `HtmlExporter`/`JupytextExporter` in README/CHANGELOG; add a CLI `export`
  subcommand. *P1/P2.*
- `GAP-16` Remove the dead `pyyaml` test-extra dependency. *P3.*
- `GAP-16b` Add an explicit `nbformat` entry to the `exec` extra rather than relying on `nbclient`'s
  transitive dependency. *P3.*

**Wave 5 (test-quality hardening — can proceed independently, informed by all of the above):**
- `GAP-17` Add tests for `validate_notebook`/`validate_notebook_schema`, `max_output_bytes`, and
  `NotebookResourceLimits`' pinned defaults. *P2.*
- `GAP-18` Add a real `diff_notebooks()`-vs-`nbdime diff` oracle test (mirroring the existing merge
  pattern) and document the id-vs-content matching divergence. *P2.*
- `GAP-19` Either wire up `NotebookSecurityError` or remove it from the public exception hierarchy.
  *P2.*
- `GAP-19b` Parametrize `test_active_content.py` over the full 14-element `_ACTIVE_ELEMENTS` set, the
  event-handler-attribute path, and the `javascript:`/CSS `url()` detectors — currently only `<script>`
  is tested, though all 13 other categories are confirmed working. *P1 (security-critical silent-
  regression risk).*
- `GAP-19c` Add `text/markdown` to `sanitizer.py`'s active-MIME handling (or extend the output-data loop
  to pass `markdown=True` for that media type), closing the confirmed output-MIME blind spot. *P2.*
- `GAP-19d` Wire `tests/oracle/` and `tests/package/` into a real (even schedule-gated) CI job — the
  highest-value independent-oracle evidence in the repository is currently unprotected by CI. *P1.*
- `GAP-20` Add a small number of real-world (not purely synthetic) fixture notebooks. *P3.*
- `GAP-21` Broaden property-test strategy space (error/`display_data` outputs, attachments, explicit
  cell IDs, all three parse modes). *P3.*
- `GAP-22` Add false-positive coverage to the secret scanner test suite. *P3.*
- `GAP-23` Re-run mutation testing (`mutmut`) and fuzzing (`atheris`) from a Linux/WSL CI environment,
  targeting `security/limits.py` specifically given its previously-recorded low kill rate. *P3, blocked
  on CI environment work, not code.*

---

## 22. Evidence Paths and Reproduction

Full per-finding reproduction commands are embedded in each finding above and, in complete unabridged
form (including every scratch probe script's exact contents and output), in the workflow's transcript:

- Journal (one line per completed agent, full return value): `subagents/workflows/wf_b8d3fa68-c4d/journal.jsonl`
- Full aggregated JSON results, both runs: preserved under this session's task-output directory
  (referenced in the originating conversation as `tasks/wbsf7v2hy.output` for the first pass and
  `tasks/w7es14h1w.output` for the second, broader re-verification pass whose findings this document
  is based on)
- The 4-item adversarial-verification pass (§7's `RecursionError`/surrogate/event-handler/
  active-elements findings) is recorded in `w7es14h1w.output`'s `adversarialVerification` array, with
  each verifier's independent re-derivation and its own exact repro commands inline
- All scratch reproduction scripts referenced throughout (organized by domain) were written under the
  session scratchpad's `audit/` subdirectory and are individually re-runnable with the project's own
  `.venv\Scripts\python.exe` interpreter; none were committed to the repository (per the mission's
  read-only-investigation constraint) and none modified any tracked file — confirmed via `git status`
  before and after by every domain agent
- All existing repository test commands cited throughout (e.g. `pytest tests/ -q`,
  `pytest tests/oracle/ -rs`) are reproducible directly from the repository root with the project's
  `.venv`

---

## 23. Final Publication-Readiness Classification

**`PUBLISHABLE AFTER BLOCKERS`**

The evidence does not support `PRODUCTION READY` or `HARDENED AND INDEPENDENTLY CERTIFIED` — the four
P0 blockers in §17 are real, behaviorally confirmed, user-facing defects, cross-validated by independent
domains and (where flagged) by a dedicated adversarial-verification pass: the flagship real-kernel
execution feature cannot run the standard on-disk notebook format at all, the CLI's git-workflow
integration crashes on the majority of existing real notebooks (reproduced through an actual `git diff`
failure, not just the standalone command), the CLI has no top-level exception handling, and the built
package currently leaks internal infrastructure details into public-facing metadata. None of these are
edge-case nitpicks, and none require architectural rework — each has a scoped, understood fix (§20–21).

It does not support `NOT PUBLISHABLE` either — the hardened core (schema validation, version conversion,
merge algorithmics, cleanup, HMAC trust signing, and the *deterministic-output* half of the execution
engine) is genuinely D4–D5 by independent-oracle evidence that this audit re-derived itself rather than
trusting the project's own prior certification; the package builds and installs cleanly from a fresh
environment; import boundaries are real and enforced; and the test suite is substantive rather than
rubber-stamped, with real evidence of a test-writing discipline that responds to fuzzing- and
audit-found bugs rather than just covering happy paths.

Once the Wave -1/Wave 0/Wave 1 P0 and P1 items are fixed, `MINIMUM VIABLE RELEASE READY` is a realistic
near-term target — this audit found no evidence of a deeper, structural problem that scoped fixes cannot
address.

---

*Methodology note: this document is based on two full runs of the underlying audit workflow. The first
run's security-trust-sanitization domain returned a malformed placeholder result (caught and re-run via
the workflow's cache-aware resume), and its adversarial-verification pass used an under-scoped filter
that excluded `fidelity`/`performance`-kind findings — which is where most HIGH-severity items land, so
that pass verified almost nothing. Both issues were corrected and the workflow re-run broadly (not just
the broken call), which surfaced substantially more — including the execution engine's list-of-lines-
source blocker, the single most severe finding in this report. The two runs converged tightly on every
D4/D5 "hardened core" finding, which is itself corroborating evidence for those ratings; the second run's
additional findings reflect broader adversarial coverage, not disagreement with the first run.*
