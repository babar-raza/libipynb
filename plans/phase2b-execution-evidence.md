# libipynb Phase 2b Execution — V-Tier Batch Evidence Bundle

**Date:** 2026-08-13
**Governing plan:** [plans/remediation-plan.md](remediation-plan.md) §14
**Scope:** `LIBIPYNB-V1` (secret scanning), `LIBIPYNB-V3` (fuzzing), `LIBIPYNB-V4` (execution isolation), `LIBIPYNB-V8` (mutation testing)
**Baseline before this batch:** 704... (actually 693 passed, 2 skipped — see `plans/phase2-execution-evidence.md`); Tier B/M complete, B3/B4 blocked

---

## 1. LIBIPYNB-V1 — Secret/PII scanning

### Implementation

`src/libipynb/security/secrets.py` (new module), exported from `security/__init__.py`. `scan_for_secrets(document, *, rules=None, extra_rules=(), scan_metadata=True, limits=None) -> SecretScanReport`. 10-rule `DEFAULT_SECRET_RULES`: `aws_access_key_id`, `aws_secret_access_key_assignment`, `github_token`, `slack_token`, `google_api_key`, `private_key_block`, `jwt_shaped_token`, `bearer_token`, `generic_credential_assignment`, `url_embedded_credentials`, plus a structural `sensitive_metadata_key` heuristic (checks metadata key *names*, not just value content, since JSON metadata separates key from value unlike source-code text).

### Root-cause repair during implementation

First version's `_walk_metadata_strings`-based scan didn't detect `{"password": "hunter2hunter2"}` because `generic_credential_assignment`'s regex expects `key = value` in one string (source-code shape), but metadata separates key and value structurally. Fixed by adding a key-name-based check (`_is_sensitive_metadata_key`) applied alongside the content-pattern rules, deduplicated into a shared `_scan_metadata_tree` helper (initially written twice, once per metadata scope, then refactored to one function called twice — the duplication itself is what caused the first fix to only land in one of the two call sites).

### Independent review finding and fix

An agent that did not implement this module found, via direct execution (not just reading), that `_redact()`'s original "first 4 … last 4" scheme leaked most of any match under ~17 characters:

```
url_embedded_credentials | full-match: 'ab://c:d@' | preview: 'ab:/…c:d@'
```

8 of 9 real characters shown. Root-caused and fixed: `_redact()` now returns only a coarse length bucket (`<redacted:short|medium|long>`), revealing zero characters and not even the exact length. Three regression tests added: `test_short_matches_reveal_no_characters_or_exact_length`, `test_nine_character_url_credential_match_does_not_leak_most_of_itself` (the exact scenario the review found), `test_generic_credential_short_password_does_not_leak_via_preview`.

### Test evidence

`pytest tests/security/test_secret_scanning.py -v` → **18 passed** (final count, after the redaction fix and its regression tests).

---

## 2. LIBIPYNB-V3 — Fuzzing

### Platform investigation

- Native Windows: `pip install atheris` → `error: [WinError 193] %1 is not a valid Win32 application` (build failure, no published wheels).
- WSL Ubuntu 22.04 system Python (3.10.12): codebase requires `enum.StrEnum`, a genuine Python 3.11 language feature (not just a `requires-python` metadata floor) — `ImportError: cannot import name 'StrEnum' from 'enum'`.
- No `sudo` access in WSL (`sudo -n apt-get ...` → "a password is required"); `ensurepip` absent from the base `python3` package.
- Resolved via `pip`'s official `get-pip.py` bootstrap (no sudo needed) for pip itself, then a **portable, self-contained Python 3.11.13 build** from the `python-build-standalone` project (a plain tarball download + extract, no system package manager involved) for the language-version requirement.
- `atheris` then installed cleanly in a venv built from that portable Python 3.11.

### Fuzz targets (all in `fuzz/`, outside `tests/` so pytest never auto-collects them)

| Target | What it fuzzes | 15s smoke-run result |
|---|---|---|
| `fuzz_parser.py` | `loads()` on raw bytes, all 3 recovery modes | 1,061,835 executions, 0 crashes |
| `fuzz_validator.py` | `validate()` on structurally-plausible fuzzed notebooks | 14,088 executions, 0 crashes, 575 coverage edges reached |
| `fuzz_sanitizer.py` | `sanitize()`'s HTML/markup scanner on fuzzed cell/output text | 109,612 executions, 0 crashes |
| `fuzz_diff_merge.py` | `diff_notebooks()`/`merge_notebooks()` on fuzzed cell sets | **crashed within ~1s** (see §3) |

### Remaining gap

Not wired into `.gitlab-ci.yml` as an actual periodic CI job — `LIBIPYNB-V3` is recorded as `partially_done`, not `completed_verified`, for this reason.

---

## 3. LIBIPYNB-V8 (and the crash V3 found) — Mutation testing + a real bug fix

### The crash

```
Traceback (most recent call last):
  File "fuzz_diff_merge.py", line 69, in TestOneInput
    merge_notebooks(base, ours, theirs)
  File "...site-packages\libipynb\model\merge.py", line 268, in merge_notebooks
    cell_id, base_cells[cell_id], ours_change, theirs_change, conflicts
             ~~~~~~~~~~^^^^^^^^^
KeyError: 'a'
```

### Root cause

`merge_notebooks()` checked `.removed` on both sides' `CellChange` before falling through to `_reconcile_present_cell(cell_id, base_cells[cell_id], ...)`, but never checked `.added` (`before_index is None` — the cell never existed in `base` at all). When a cell is added independently on both `ours` and `theirs` with the same ID (e.g. via content-derived deterministic cell-ID generation), `base_cells[cell_id]` doesn't exist and the lookup raises `KeyError` instead of merging.

### Fix

Added an explicit `if ours_change.added and theirs_change.added:` branch before the `base_cells[cell_id]` lookup: identical content on both sides merges with no conflict; differing content produces a new `EDIT_EDIT` conflict (no base value exists to fall back on for an add/add conflict, so `ours` is kept as an explicit, reported placeholder — never silently treated as resolved, consistent with this module's existing design principle for every other conflict category).

### Verification

- `pytest tests/unit/test_obligation_notebook_merge.py -v` → **19 passed** (17 pre-existing + 2 new: `test_identical_cell_added_independently_on_both_sides_is_not_a_conflict`, `test_cell_added_independently_on_both_sides_with_different_content_conflicts`).
- Re-ran `fuzz_diff_merge.py` after the fix: **31,570 executions in 16s, 0 crashes** (was: crash within ~1s before the fix).
- Independent review traced `CellChange.added`/`.removed` in `diff.py` and proved the new guard is logically complete — `ours_change.added` and `theirs_change.added` are provably always equal whenever both changes are non-None (both diffs share the same `base`), so no residual `KeyError` path remains, including the "added-then-removed-elsewhere" edge case the review specifically checked for (structurally impossible within one before→after diff).

### Mutation-testing campaigns

Tool: `format-factory/tools/certification/mutation_tester.py` (sibling repo, reused read-only — a lightweight AST-mutation tester explicitly built for this exact situation: its own docstring says "mutmut requires WSL" and it has built-in `--repo-root`/`--pytest-bin` overrides for "an externally-checked-out standalone library"). Simple mutation operators: comparison negation, boolean negation, True/False swap, off-by-one, return→None.

**Environment pitfall found and fixed:** copying a Windows venv wholesale for parallel sandbox isolation does not produce an independent `pytest.exe` — Windows console-script launchers embed an absolute path to their creating `python.exe` at build time. Two of three copied sandboxes silently ran every "mutated" test against the **original, unmutated** sandbox's code, producing fabricated-looking 0%/7.1% kill-rate numbers. Caught by a manual sanity check (deliberately apply one mutation by hand, confirm `pytest.exe` actually observes it) before trusting any result. Fixed via `pip install --force-reinstall pytest pytest-cov pytest-timeout` per affected sandbox; one sandbox additionally had corrupted `~ytest`/`~pytest` remnants from an earlier failed reinstall requiring a full wipe-and-reinstall of the test toolchain, plus repinning `nbformat==5.10.4` (a `>=5.10` reinstall had pulled a newer, unpinned nbformat that broke an oracle-version-match test unrelated to any mutation).

**Verified-correct final results** (each re-confirmed via direct manual mutation + `pytest.exe` run before trusting the automated campaign):

```
security/limits.py:   20 mutations, 4 killed, 16 survived → 20.0% (NEEDS_HARDENING)
  survivors mostly off-by-one on default resource-limit constants (e.g. 64*1024*1024 -> 64*1024*1023)

cli/main.py:          20 mutations, 14 killed, 6 survived → 70.0% (STRONG)

model/output.py:       3 mutations, 3 killed, 0 survived → 100.0% (STRONG)

analytics/notebook.py: 14 mutations, 10 killed, 4 survived → 71.4% (STRONG)
```

Compare to the stale, pre-migration Format Factory campaign (2026-08-04, different/retired module namespace, cited in `publication-readiness-assessment.md` §3): 12% / 0% / 0% / 0% respectively. Three of four modules the historical campaign called completely untested are, on current code, genuinely well-covered — the historical figures must not be cited as current (Gate G4).

---

## 4. LIBIPYNB-V4 — Execution isolation hardening

### Implementation

`execute_notebook()` new keyword parameters: `isolate_cwd: bool = True`, `isolate_env: bool = True`, `extra_env: dict[str, str] | None = None`, `max_memory_bytes: int | None = None`, `max_output_bytes: int | None = 10 * 1024 * 1024`. New `ExecutionReport` fields: `work_dir`, `memory_limit_bytes`, `output_limit_bytes`, `output_truncated`.

- **cwd isolation:** `tempfile.TemporaryDirectory` created before the subprocess call, passed as `cwd=`, `.cleanup()` called in a `finally` block covering every code path (including OSError/TimeoutExpired).
- **env isolation:** `_minimal_env()` keeps only `PATH`/`TEMP`/`TMP`/`HOME`/`SYSTEMROOT`/`SYSTEMDRIVE`/`PATHEXT`/`COMSPEC`/`LANG`/`LC_ALL` from the caller's environment, plus anything in `extra_env`.
- **Output cap:** post-capture truncation (bounds what's *returned*, not necessarily peak memory during capture — documented honestly as a trade-off, not oversold as streaming-bounded).
- **Memory limit:** `resource.setrlimit(RLIMIT_AS, ...)` via `preexec_fn`, POSIX-only; `_memory_limit_preexec_fn` returns `None` on `win32`, and a `max_memory_bytes is not None and sys.platform == "win32"` guard raises `NotebookExecutionError` *before* `preexec_fn` is even computed, so a non-None `preexec_fn` can never reach `subprocess.Popen` on Windows (which would otherwise raise `ValueError`).

### Bug found and fixed during implementation

Output truncation can land mid-JSON-record (the driver's newline-delimited protocol has no reason to align with an arbitrary byte cutoff), which crashed `_parse_results` with `json.decoder.JSONDecodeError: Unterminated string`. Fixed: `_parse_results` now catches `JSONDecodeError` per-line and drops an incomplete trailing record, extending the exact precedent already established for timeout-kill partial output (an incomplete record was always a possible, accepted outcome; byte-truncation is just a second way to produce one).

### Verification (both platforms)

Windows (`pytest tests/integration/test_obligation_execution_adapter.py -v`): **29 passed, 2 skipped** (the 2 skips are the POSIX-only memory tests).
WSL/Linux (same file, synced): **30 passed, 1 skipped** (the 1 skip is the Windows-only refusal test) — confirming the memory-limit enforcement tests (`test_max_memory_bytes_is_enforced_on_posix`, `test_max_memory_bytes_none_does_not_limit_normal_allocation_on_posix`) actually pass when run where they can, not just skip everywhere.

### Independent review finding and fix

`README.md`/`CHANGELOG.md` (both edited during the earlier Tier-B `LIBIPYNB-B1` pass) still described pre-V4 defaults — "no CPU, memory, disk, or output-size limit is enforced" and "the subprocess inherits the caller's full environment" — now false. Both updated to describe the actual current defaults (`isolate_cwd`/`isolate_env`/`max_output_bytes` all on by default; `max_memory_bytes` POSIX-only, Windows-refuses).

### Explicitly deferred, not implemented

CPU-time limiting, network-access denial. No clean, dependency-minimal, genuinely cross-platform primitive was available within this pass's scope; recorded here per this card's own Stop Conditions rather than shipped as a partial, unverifiable claim.

---

## 5. Final regression (this batch, both platforms)

```
Windows:
  pytest tests/ -q                 -> 704 passed, 4 skipped
  ruff check .                     -> All checks passed
  ruff format --check .            -> 103 files already formatted
  mypy src/libipynb                -> Success: no issues found in 34 source files
  python -m build                  -> wheel + sdist built
  clean-venv install smoke test    -> import OK (incl. security.secrets, adapters.execute new symbols); CLI --help OK

WSL/Linux (reduced test set — 4 files were removed from this specific copy earlier
for unrelated mutmut-tooling-compatibility reasons, not a regression):
  pytest tests/ -q                 -> 635 passed, 3 skipped
```

## 6. Independent verification summary

A separate agent that did not implement this batch reviewed the full diff and independently re-ran all checks. Verdicts: V1 **DISPUTED → fixed → re-verified clean**; V3 **CONFIRMED**; V4 **CONFIRMED** (with one doc-accuracy issue found and fixed); V8 **CONFIRMED** for the code deliverable (the merge.py fix), **PLAUSIBLE** for the specific kill-rate percentages (not independently re-runnable after the fact since the sandbox copies were temporary) — both findings addressed as described above.

## 7. Changed files (this batch, on top of the Tier B/M batch already evidenced in `plans/phase2-execution-evidence.md`)

`src/libipynb/security/secrets.py` (new), `src/libipynb/security/__init__.py`, `src/libipynb/adapters/execute.py`, `src/libipynb/model/merge.py`, `fuzz/` (new: `README.md`, `fuzz_parser.py`, `fuzz_validator.py`, `fuzz_sanitizer.py`, `fuzz_diff_merge.py`), `tests/security/test_secret_scanning.py` (new), `tests/integration/test_obligation_execution_adapter.py`, `tests/unit/test_obligation_notebook_merge.py`, `README.md`, `CHANGELOG.md`, `pyproject.toml` (new `fuzz` extras group). None committed — working tree only, per this session's authority boundary (no push/commit without explicit authorization, per Gate G3).
