# libipynb Publication-Readiness Assessment — Phase 1 (Baseline + Verdict)

> **Update 2026-08-13 (same day, Phase 2 execution):** Blockers B1, B2, B5 and
> MVP items M1, M2 from §10/§11 below have been implemented and verified —
> see [plans/remediation-plan.md](remediation-plan.md)'s execution-status
> table and [plans/phase2-execution-evidence.md](phase2-execution-evidence.md)
> for full evidence. B3 (publish) and B4 (real CI run) remain open, blocked
> on explicit maintainer authority to push/tag, not on missing work. The
> capability-depth and other findings below still describe the code as it
> was *before* that remediation and have not been rescored; the execution
> evidence bundle documents what changed.

**Date:** 2026-08-13
**Scope:** `c:\Users\prora\OneDrive\Documents\GitHub\libipynb`, package `libipynb` 0.1.0, pure Python (≥3.11)
**Method:** Fresh, independent re-execution of the full test/lint/type/build/install/interop baseline on this machine (Windows, Python 3.13.2), plus direct source reads of the highest-stakes modules, plus reconciliation against the sibling `format-factory` monorepo's ipynb-specific acquisition/task-card/oracle/certification history. Every claim below is either a command I ran with recorded output, or a file:line citation.

---

## 1. Executive verdict

**Conditionally ready.** The core notebook-processing engine (parse, model, version detection/upgrade/downgrade, cell-ID handling, validation, diff, merge, atomic write, sanitizer classification, HMAC trust) is genuinely production-capable, defensively written, and — as of this assessment — independently re-verified, not just self-reported. It is not held back by stubs, TODOs, or happy-path-only logic.

What keeps this from an unconditional "ready" is a short, concrete list (§20): an execution adapter whose real security posture (no sandboxing, full-environment subprocess) is undocumented anywhere a user would see it before calling it; stale/self-authored certification evidence that (now) partially disagrees with what actually ships; a CI pipeline that has apparently never executed against a real server; a stale README; and the absence of any actual publication (no git tag, no PyPI/registry push). None of these require redesign — they are finishing work, not rearchitecture.

---

## 2. Reproduced baseline (executed today, not assumed from historical records)

All commands run from `c:\Users\prora\OneDrive\Documents\GitHub\libipynb` using the repo's existing `.venv` (Python 3.13.2, Windows 11), except the clean-install step which used a fresh scratch venv.

| Check | Command | Result |
|---|---|---|
| Unit+integration+security+property+package | `pytest tests/unit tests/integration tests/security tests/property tests/package -v` | **601 passed**, 0 failed |
| Interoperability (vs. installed `nbformat==5.10.4`) | `pytest tests/interoperability -v` | **65 passed, 2 skipped**, 1 `PytestUnknownMarkWarning` |
| Full suite + coverage | `pytest tests/ --cov=libipynb --cov-report=term-missing` | **666 passed, 2 skipped**, **88.28% coverage** (required 85.0%) — reproduces the CHANGELOG's "88%/666 tests" claim exactly, independently, on a different OS than CI targets |
| Format check | `ruff format --check .` | **1 file would be reformatted**: `examples/load_and_inspect.py:11` (a `FIXTURE = ...` line-wrap). Not a defect, but the repo's own "ruff clean" claim is currently false by one file. |
| Lint | `ruff check .` | **All checks passed** |
| Strict typing | `mypy src/libipynb` | **Success: no issues found in 33 source files** |
| Build | `python -m build` | Wheel + sdist built cleanly; schemas (`validation/schemas/*.json`) confirmed present in the wheel |
| Clean-venv install | fresh venv, `pip install dist/libipynb-0.1.0-py3-none-any.whl` (no `--no-index`, so the one real dependency resolves from PyPI) | Installs with exactly **4 packages** beyond libipynb itself: `jsonschema`, `jsonschema-specifications`, `attrs`, `referencing`, `rpds-py` — matches the "single runtime dependency" claim |
| Import smoke test | `from libipynb import NotebookDocument, load, validate, NotebookError` | OK |
| CLI smoke test | `libipynb --help` | Lists all **8** commands: `probe, inspect, validate, sanitize, upgrade, normalize, convert, diff` |
| Examples (against the clean install) | `python examples/load_and_inspect.py`, `python examples/validate_notebook.py` | Both ran correctly against `tests/fixtures/`; validator produced accurate, specific diagnostics (`IPYNB_SCHEMA_REQUIRED`, `IPYNB_PARSE`, `IPYNB_VERSION`, `IPYNB_SCHEMA_ADDITIONALPROPERTIES`) for each of 4 invalid fixtures |
| Independence re-check | `grep -rni "format_factory\|format factory" src/` | **0 hits** — independently confirms the repo's own (previously unverifiable-as-written) `independence-grep-check.txt` claim |
| Internal-path leakage check | `grep -rni "recruitize\|C:\\Users\\prora" src/` | Only hit: the declared `Repository` URL (`gitlab.recruitize.ai/...`) in packaging metadata — this is the project's actual (private) repo URL, not Format Factory leakage, but see §18 |
| Version/tag consistency | `python -c "import libipynb; print(libipynb.__version__)"`, `git tag -l`, `git describe --tags` | `0.1.0`; **no git tags exist**; `git describe` fails with "No names found" |
| Repo cleanliness | `git status --short` | Only untracked item is `plans/` (as before) — this baseline run left no stray files in the working tree |

**Not reproduced in this pass (flagged, not fabricated):** the historical Format Factory mutation-testing campaign (50.9% overall kill rate; `security/limits.py` 12%; `analytics/notebook.py`/`cli/main.py`/`model/output.py` 0%) was **not re-run** — it predates several of libipynb's own commits and used a different (donor-namespace) module path. It is cited below as historical signal about test *strength* (as opposed to coverage), not as a current number.

---

## 3. Repository identity and lineage (established in reconnaissance, reconfirmed)

- Package `libipynb` 0.1.0, Apache-2.0, single runtime dependency (`jsonschema>=4.23,<5`), src-layout, ~6,880 LOC across 27 modules under `src/libipynb`.
- Git remote is a private GitLab instance (`gitlab.recruitize.ai/sialkot/cantt-smallize/libipynb`), not GitHub, despite living in a local `GitHub/` folder.
- Documented extraction from the sibling monorepo `format-factory` (`NOTICE`, `tests/fixtures/PROVENANCE.md`, git log: `fc9101b feat(core): migrate production IPYNB source to libipynb namespace`, `a7ef899 test(migration): classify and adapt donor test files to libipynb namespace`). No live code coupling (§2 independence re-check, above).
- Format Factory's own capability contract for ipynb (`format-factory/plans/strategic/ff6/capabilities/ipynb.yaml`, `contract_id: FC-IPYNB-V1`) declares 25 capabilities / 68 obligations (65 MUST, 3 SHOULD, 0 MAY), and classifies `IPYNB-EXEC-001` as **`EXCLUDED_WITH_AUTHORITY`** — with the explicit text *"The format-factory-ipynb distribution never executes code."* **This is now factually wrong about what libipynb ships** (see §11) — `src/libipynb/adapters/execute.py` is a real, tested, working execution adapter. This is not a defect in libipynb; it means the Format Factory authority contract and certification evidence for ipynb predate a scope decision that was made during or after extraction, and none of Format Factory's certification work (mutation testing, gate reviews) ever assessed the execution adapter, because its own contract assumed it didn't exist.
- Format Factory's own certification status for ipynb as of 2026-08-04 was **"0/6" / "UNASSESSED"** (`format-factory/reports/skills-rff6/certification-gates/ipynb-mutation-campaign-20260804.md`), with only the reproducible-build gate passing. This has not been updated since libipynb's extraction; it should not be cited as current certification for the standalone package.

---

## 4. Capability-depth matrix (0 Absent – 5 Certified)

| Capability | Level | Evidence | Biggest gap |
|---|---:|---|---|
| Parse / duplicate-key / resource limits | **4** | `codec/reader.py`, `security/limits.py` (read directly: iterative depth/entry/byte bounding, `bounded_object_pairs_hook`); `tests/security/test_adversarial_input.py`, `test_resource_limits.py`, `test_duplicate_keys.py` all pass | No true streaming parser (full-load then bound); base64 payloads not validated as base64 anywhere in the parse/validate path, only shape-checked |
| Notebook/cell/output model, unknown-field preservation | **4** | `model/document.py`: views backed by the raw dict, `to_dict()` returns `deepcopy(self._data)`; `UnknownCell`/`UnknownOutput` fallbacks | "Preserve unknown cell/output *types*" only applies under permissive read modes — official-schema `validate()` correctly still rejects them under strict profiles (this is correct behavior, but worth being precise about in docs) |
| Version detection / v4.0–4.5 support | **4** | 6 vendored, digest-pinned official schemas; `tests/integration/test_obligation_official_schema_validation.py` (differential vs. live `nbformat`) — reran today, all pass | v3 is explicitly unsupported (by design, not a silent gap) — a real scope limitation for any user with legacy v3 files |
| Cell IDs | **4** | Deterministic content-hash generation (`reader.py`), uniqueness enforced in 4 independent places, audit trail (`CellIdRewrite`) | None material found |
| Validation (schema + semantic) | **4** | `validation/rules.py`, `validation/schema.py` read directly; official-schema + hand-written semantic rules; live differential test against `nbformat` reran today, all pass | Base64 payload *validity* is not checked (confirmed by direct read of `rules.py:204-247` — only JSON-compatibility and image-MIME string-shape are checked) |
| Cleanup / governance (output/metadata) | **4** for what exists | `model/cleanup.py`: allow-list only, "never remove unknown keys" by design, dry-run, deterministic `ChangeReport` | No secret/PII scanning exists anywhere (confirmed: only grep hit for "secret" in `src/` is the HMAC `secret:` parameter name) — this is a differentiator the research report calls out and it is simply absent |
| Write / atomic output | **4** | Read directly: `tempfile.mkstemp` + `os.replace` + cleanup-on-failure (`codec/writer.py:133-145`); `tests/security/test_atomic_writes.py` reran, all pass; canonical `sort_keys=True` JSON | None material found |
| Diff | **4** | LIS-based move detection, fingerprint-guarded patch preconditions (per source-survey citations; diff tests pass) | Not independently re-read line-by-line this pass (spot-check budget prioritized security modules) |
| Merge | **3** | Genuine 3-way merge, marker-free by design (base wins on conflict, recorded not silently resolved) | Not exposed via CLI; Format Factory's own contract classifies this capability as `PREVIEW_ISOLATED`, one notch below the MUST-level capabilities |
| Sanitizer (active-content classification) | **4** | Read directly in full (`security/sanitizer.py`): HTML-parser-based classification, explicit "does not rewrite arbitrary HTML/SVG/JS into a safe subset" disclaimer, 4 handling modes, budget-bounded | No MIME/attachment-specific payload-size cap (only aggregate resource limits apply) |
| Trust / HMAC notary | **3** | Real HMAC notary mirroring nbformat's notary interface; strong-hash-only; excludes `metadata.signature` from signed bytes | Bundled signature store is **process-local memory only** — no persistent store ships, so "trusted" status does not survive process restart unless a caller supplies their own store; not exposed via CLI |
| Export adapters | **2–3** | Markdown + Python-script export only; defensive path-traversal-safe resource extraction (confirmed via `test_path_safety.py`, `test_export_resource_path_safety.py`, all pass) | No HTML/Jupytext/importer — Format Factory's own contract marks this `OPTIONAL_ADAPTER_REQUIRED`, i.e., even the source program didn't consider one exporter sufficient |
| **Execution adapter** | **3, with an unresolved security-communication gap** | Read directly in full (`adapters/execute.py`): real OS-subprocess isolation, non-Python kernels refused, core module verified (by a dedicated test with a CPython audit hook) to never import this module or call it implicitly | **Not sandboxed** — only a wall-clock timeout is enforced; no CPU/memory/disk/network/output-size limit, no working-directory or credential isolation, no explicit provenance record beyond kernel path + results. The subprocess inherits the parent's full environment, filesystem permissions, and network access. Neither README nor CHANGELOG says this. See §11. |
| CLI | **3** | 8 real commands, JSON output, exit codes tied to result (validate/diff), reran `--help` and both examples successfully | `merge`, `trust`, and `analytics` exist as library functions but have no CLI surface; README documents only 3 of 8 commands |

---

## 5. Version-support matrix

| Format | Detect | Read | Write | Modify | Validate | Upgrade | Downgrade | Preserve unknowns | Tests | Oracle result |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| v1–v3 | — | — | — | — | — | — | — | — | none | **Not supported by design** — no `worksheets` unwrap logic anywhere in `src/`; treated as a documented non-goal, not a silent gap |
| v4.0 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ (→4.5) | ✅ | ✅ | parametrized across unit/integration/interop suites, reran today | `test_load_produces_same_structure_as_nbformat[nbformat-4-0]`, `test_write_roundtrip_matches_nbformat[nbformat-4-0]` — **PASS** |
| v4.1 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | same | **PASS** |
| v4.2 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | same | **PASS** |
| v4.3 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | same | **PASS** |
| v4.4 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | same | **PASS** |
| v4.5 | ✅ | ✅ | ✅ | ✅ | ✅ | n/a (target) | ✅ | ✅ | cell-ID specific matrix in `test_obligation_cell_identity.py` | **PASS**, incl. `TestCellIdHandling` parity checks |
| Future 4.x (4.6+) | partial | preserved w/ warning | — | — | flags as `IPYNB_FORWARD_VERSION` | — | — | ✅ (per source-survey citation `validation/rules.py:85-107`) | not independently re-verified this pass | no live oracle (no such notebooks exist yet) |

Note on oracle completeness: the interoperability "invalid notebook" parity suite reran today at **2 passed, 2 skipped** — `missing-nbformat` and `wrong-nbformat-version` are skipped rather than compared against `nbformat`'s own rejection behavior, so rejection-parity oracle coverage is 50%, not 100%, for the invalid-fixture set. Not investigated further this pass (deferred to Phase 2 if pursued).

---

## 6. Security and trust — the most consequential findings

1. **Sanitizer is honest about its limits.** Read in full: it classifies and either reports, removes, quarantines, or digest-marks active payloads; it explicitly does **not** claim to produce safe-to-render HTML/SVG/JS (`security/sanitizer.py:3-6`). This is the correct posture per the mission brief's "do not describe as safe" instruction, and it is a real, working implementation, not a stub.
2. **No execution happens on the core path**, and this is independently enforced, not just claimed: `tests/integration/test_obligation_core_path_no_execution.py` uses a CPython audit hook to prove `load`/`validate`/`diff`/`upgrade`/`save` never execute cell source, even against actively hostile payloads (`exec(...)`, `urllib.request.urlopen(...)` embedded as cell source) — reran today, all pass.
3. **The execution adapter, where it does exist, is not a sandbox.** Read `adapters/execute.py` in full: it runs notebook code in a **separate OS process** (good — crash containment, killable on timeout) via `subprocess.run([sys.executable or explicit kernel, "-c", <driver script>], timeout=..., capture_output=True)`. It enforces **one thing**: a wall-clock timeout (default 30s). It does **not** enforce CPU limits, memory limits, disk limits, network restrictions, output-size caps, or working-directory/credential isolation — the child inherits the parent's full environment and filesystem/network access. This matches the mission's definition of "isolated" only in the weakest sense (process boundary), not the stronger sense it asks auditors to check for (resource and credential isolation). **Neither the README nor the CHANGELOG mentions this limitation** where `execute_notebook` is described.
4. **Trust ≠ safety, and the code already knows this.** The HMAC notary mirrors nbformat's own trust-signature interface (sign/verify/revoke), explicitly excludes the signature field from the signed payload, and only supports strong hash algorithms. But per the mission's own framing, a valid signature here proves only "this exact byte content was signed by whoever holds this HMAC secret" — nothing about authorship, safety, or reproducibility. This isn't stated in the README.
5. **Resource limits are real and independently verified**: reran `tests/security/test_resource_limits.py` (huge input, deep nesting, excessive entries all correctly rejected) and confirmed the enforcement code directly in `security/limits.py` — iterative (not recursive) structure walking, so the bounding check itself can't be trivially stack-overflowed by the input it's supposed to reject.
6. **No secret/PII scanning exists.** Confirmed absent, not stubbed — `cleanup()` is allow-list-only metadata/output stripping with no content-pattern scanning of source, outputs, tracebacks, or URLs.
7. **No fuzz corpus/harness** (atheris, cargo-fuzz-equivalent) exists despite a real adversarial-fixture test suite; Hypothesis property tests exist but are schema-constrained generators, not coverage-guided fuzzing.

---

## 7. Oracle inventory

| Oracle | What it actually checks | Status |
|---|---|---|
| `nbformat==5.10.4` (installed, live) | Structural parity on load, write-roundtrip parity, version-detection parity, cell-ID handling parity, valid-notebook dual-acceptance, invalid-notebook dual-rejection (partial) | **Executed today**, 65 passed / 2 skipped |
| Vendored official nbformat 4.0–4.5 JSON Schemas, SHA-256 digest-pinned | Schema acceptance/rejection incl. 11 targeted mutation functions (`test_obligation_official_schema_validation.py`) | **Executed today**, all pass; digest pinning defends against silent schema drift/corruption |
| Format Factory's `oracle/formats/ipynb` package | Pinned to official `nbformat` commit `60b6151f...`; profiles STRUCTURAL_VALIDITY/PARSE_VALIDITY/DOMAIN_MODEL_MAPPING/ROUNDTRIP_SEMANTIC_EQUIVALENCE/SAME_FORMAT_SERIALIZATION/INTEROPERABILITY | **Historical, marked `STATUS: STALE`** by Format Factory itself (non-promoting); explicitly marks SECURITY_ROBUSTNESS and LOSSLESS_TRANSFORMATION as not-applicable at that oracle version. Not re-executed by me; not authoritative for current libipynb. |
| JupyterLab / VS Code Jupyter / `nbdime` / Jupytext / `nbconvert` | Cross-tool fidelity/rendering/diff-merge parity | **None exist.** No fixtures, no scripts, no CI jobs reference any of these tools. |

---

## 8. API, CLI, and documentation usability

- Public API surface is deliberately curated (`__init__.py` re-exports ~33 names; `adapters`, `analytics`, and `security.trust` require explicit submodule imports) — a defensible, intentional design, not an oversight.
- Diagnostics are genuinely structured and specific: reran `examples/validate_notebook.py` against 4 invalid fixtures and got distinct, correct codes (`IPYNB_SCHEMA_REQUIRED`, `IPYNB_PARSE`, `IPYNB_SCHEMA_TYPE`, `IPYNB_VERSION`, `IPYNB_SCHEMA_ADDITIONALPROPERTIES`) rather than one generic "invalid" error.
- **README is stale relative to the shipped CLI**: documents `validate`, `inspect`, `probe` only; the actual CLI (confirmed via `--help` today) has 8 commands including `diff`, `upgrade`, `normalize`, `convert`, `sanitize`.
- **README does not mention `execute_notebook`'s actual isolation limits** (§6.3) even though it lists the function in the API overview table.
- No `docs/` site exists; documentation is README + docstrings only. Docstrings are present on 30 of 33 source files and are unusually good at explaining *why* (e.g., the worked nbformat-schema-defect note in `metadata.py`, the execution-boundary rationale in `execute.py`).
- Both `examples/*.py` scripts run correctly against a genuinely clean install (verified today, not assumed).

---

## 9. Independence and packaging readiness

- **Independence: verified, not just claimed.** `grep -rni "format_factory" src/` → 0 hits, run directly today. The repo's own `_extraction_evidence/independence-grep-check.txt` doesn't contain this output as written, but the underlying fact is now independently confirmed.
- **Packaging is clean**: wheel/sdist build correctly, schemas are bundled, clean-venv install pulls in exactly the declared minimal dependency set, `py.typed` marker present, license/notice files present and correctly attributed (Apache-2.0 for the code, BSD-3-Clause attribution for the vendored Jupyter schemas).
- **Not actually published anywhere.** No git tags exist for 0.1.0 (`git tag -l` empty, `git describe --tags` fails). The GitLab CI pipeline (`.gitlab-ci.yml`) builds and smoke-tests wheel/sdist but has no publish/deploy stage, and per the repo's own release-gate record, the GitLab push itself is still "pending (requires transient credential)" — meaning as far as could be determined, this pipeline has never actually executed against a real GitLab server. No OS matrix beyond `python:3.1x-slim` Linux containers; this assessment's from-scratch Windows run is the first independent cross-platform signal on record.
- One minor identity note, not a Format Factory leak: the packaged `Repository` URL points to a private GitLab instance (`gitlab.recruitize.ai`) that public PyPI consumers won't be able to reach — fine for now, but worth deciding deliberately before a real public release (either make it reachable or point elsewhere).

---

## 10. Publication blockers (must fix before any public release)

| # | Gap | Why it blocks | Effort |
|---|---|---|---|
| B1 | `execute_notebook`'s real isolation limits (no sandbox, full-environment subprocess, timeout-only) are not documented anywhere a caller would see before using it | A trust-accuracy problem exactly analogous to the mission's "do not describe as safe" rule — an undocumented capability that looks safe (isolated, structured report) but isn't sandboxed is worse than an absent one | Low — add explicit warnings to README, CHANGELOG, and the top-level docstring/`__init__` gate; consider requiring an explicit opt-in flag |
| B2 | README documents 3 of 8 CLI commands and omits execution-adapter caveats | A new developer's primary onboarding document is materially incomplete/misleading | Low |
| B3 | No actual publication artifact exists (no git tag, GitLab push "pending", no PyPI presence) | "Publication readiness" cannot be "ready" while nothing has been published | Low–medium (process, not code) |
| B4 | CI pipeline is configured but has apparently never executed against a real server | "Tested in CI" is currently an aspiration, not a fact in evidence | Low–medium (get one green run) |
| B5 | `_extraction_evidence/independence-grep-check.txt` doesn't contain the grep output it claims to evidence | Self-audit artifacts that don't actually contain their evidence undermine trust in the rest of the evidence bundle | Trivial |

## 11. Confirmed minimum publishable scope (MVP) — what's already met vs. still needed

**Already met, independently verified today:** bounded non-executing parsing; v4.0–4.5 read/write/validate/upgrade/downgrade with official-schema + live-`nbformat` oracle agreement; unknown-field preservation; cell-ID-safe manipulation; layered validation (schema + semantic); MIME/attachment structural validation; output/metadata cleaning with deterministic change reports; atomic, canonical, deterministic writes; a focused CLI; independent packaging with minimal dependencies.

**Still needed for a credible MVP (beyond the blockers above):** close the base64-validity gap in the validator (or document it as a known limitation); decide and document the execution adapter's fate (harden with real resource limits, or explicitly mark it experimental/separate from the core trust model); one real green CI run; README CLI section brought up to date.

## 12. Version 1.0 and later (not blocking, tracked for Phase 2)

**v1.0 candidates:** secret/PII scanning hooks; persistent (not just in-memory) trust/signature store; fuzz harness (coverage-guided, not just Hypothesis property tests) targeting parser/validator/sanitizer/diff-merge; resource-limited execution sandbox (cgroups/container/restricted subprocess) if execution stays in scope; HTML and Jupytext adapters; CLI exposure for `merge`, `trust`, `analytics`; cross-tool oracle expansion (`nbdime`, Jupytext, JupyterLab round-trip); mutation-testing re-run on current standalone code with a stated kill-rate target.

**Later differentiation:** cross-language bindings (the research report's Rust/TS vision — a real strategic question, not evaluated further in this phase since it wasn't built); policy/plugin SDK; signed transformation manifests; platform-profile validation (Colab/Databricks/VS Code specific metadata semantics).

**Correctly out of scope, no action needed:** full kernel/runtime, universal reversible HTML/PDF/DOCX conversion, reactive execution, grading platform, JupyterLab reimplementation — none of these were attempted, consistent with the research report's own non-goals.

---

## 13. What Phase 2 would cover (not started — pending your review of this report)

Detailed remediation task cards for each blocker/MVP/v1.0 item above, written into `libipynb/plans/` (per your direction), each with objective, exact files, dependencies, required tests/oracle evidence, and acceptance criteria — loosely following the structural pattern already used by Format Factory's `TC-FF6-IPYNB-*` task cards (Defect / Why it stayed hidden / RED scenarios / exact writable paths / acceptance criteria), adapted to a standalone libipynb ID scheme since this plan lives in libipynb's own repo rather than Format Factory's task-card system.
