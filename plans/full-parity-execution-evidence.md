# libipynb Full-Parity Execution — Round 1 Evidence Bundle

**Date:** 2026-08-13
**Governing plan:** [plans/full-parity-plan.md](full-parity-plan.md)
**Scope this round:** `LIBIPYNB-P1`, `P2`, `P3a`, `P3b`, `P3c`, `P6`, `P7`, `P8`, `P9` — every taskcard independent of Gate G6 (security sign-off) and the maintainer-authority dependency it carries. `P4a-1`, `P4a-2`, `P4b`, `P4c`, `P5a`, `P5b`, `P5c` were **not attempted** — see "Blocked work" below.
**Baseline before this round:** 704 passed, 4 skipped, `ruff check`/`ruff format --check`/`mypy --strict` all clean (reproduced live at the start of this session, not assumed from a prior document — see §1).

---

## 1. Baseline (reproduced live, this session, before any change)

```
git rev-parse --abbrev-ref HEAD  -> master
git rev-parse HEAD                -> 7eed4d8397dd940197fdbcdc55302a73311767ae
git status --short                -> matches the working-tree state already described in
                                      remediation-plan.md/phase2b-execution-evidence.md
                                      (Tier B/M/V1/V3/V4/V8 work already in the tree, uncommitted)
pytest tests/ -q                  -> 704 passed, 4 skipped
ruff check .                      -> All checks passed!
ruff format --check .             -> 105 files already formatted
mypy src/libipynb                 -> Success: no issues found in 34 source files
pip list (relevant)               -> jsonschema, nbformat, pytest*, ruff, mypy installed;
                                      none of nbdime/nbconvert/papermill/nbstripout/
                                      jupyter_client/nbclient installed
```

## 2. Work executed, per taskcard

### LIBIPYNB-P1 — doc/API accuracy fixes
- Fixed README's false "remove empty cells" claim and the `NotebookVersion.upgrade()/downgrade()`-as-methods claim (verified against `model/lifecycle.py:20,210,316,431` directly).
- Fixed a stale docstring path in `adapters/execute.py` (`tests/python/ipynb/...` → the real `tests/integration/...` path).
- Docs-only; no test changes required. Verified by re-reading the corrected text against actual source.

### LIBIPYNB-P8 — extras + import-boundary check
- `pyproject.toml`: added `exec = ["jupyter_client>=8.6", "nbclient>=0.10"]` and `oracle = ["nbdime>=4.0", "nbconvert>=7.16", "papermill>=2.6", "nbstripout>=0.7"]`, both outside core `dependencies`.
- New `tests/unit/test_import_boundary.py`: AST-based static scan of every `src/libipynb/**/*.py` file, asserting none imports the six forbidden names. Includes 3 self-tests proving the checker can actually detect a violation (Gate G7's own requirement) — not just that it currently passes.
- `pytest tests/unit/test_import_boundary.py -v` → **4 passed**.

### LIBIPYNB-P7 — oracle scaffolding
- New `tests/oracle/conftest.py`: one `pytest.importorskip`-gated fixture per reference tool (`nbstripout_available`, `nbdime_available`, `nbconvert_available`, `nbclient_available`, `papermill_available`), plus `representative_notebook()`/`parameterizable_notebook()` builders and an `oracle_tmp_notebook` fixture, reusing the exact pattern already proven in `tests/interoperability/conftest.py`.
- New `tests/oracle/test_scaffolding_smoke.py`: proves the fixtures are schema-valid and that the `importorskip` skip path actually works on this machine (none of the five tools are installed here).
- `pytest tests/oracle/ -v` → **3 passed, 5 skipped** (the 5 skips are exactly the five `*_available` fixtures, confirmed skipping for the right reason — tool not installed — not erroring).

### LIBIPYNB-P3a — line-level diff hunks
- `model/diff.py`: new `DiffHunk` dataclass; new, additive `FieldChange.source_hunks: tuple[DiffHunk, ...] | None = None` field, populated only for `CellField.SOURCE` changes where both sides are present text (str or nbformat's list-of-lines form), via `difflib.SequenceMatcher`. Nothing existing was removed or reshaped; `merge_notebooks()` (built on `diff_notebooks()`) needed zero changes.
- New `tests/unit/test_obligation_diff_hunks.py`: 11 tests, including a Hypothesis property test that reconstructing `after`/`before` from the hunks always reproduces the original text exactly, across arbitrary generated strings (excluding surrogates).
- `pytest tests/unit/test_obligation_diff_hunks.py -v` → **11 passed**, including the property test.

### LIBIPYNB-P3b — CLI `merge` subcommand
- `cli/main.py`: new `merge` subcommand (`libipynb merge base ours theirs [-o PATH]`), mirroring `diff`'s existing JSON-output/exit-code convention exactly (`0` if no conflicts, `1` if conflicts — merged document still written either way).
- README CLI section updated in the same change (not deferred — the base plan's own `LIBIPYNB-B2` near-miss was explicitly used as the reason not to repeat that mistake).
- New `TestMerge` class in `tests/unit/test_cli.py`: 3 tests (no-conflict, conflicting — asserts the merged output keeps base's value not either side's — and file-output).

### LIBIPYNB-P2 — nbstripout parity
- `model/cleanup.py`: new `CleanupPolicy.respect_keep_output_marker: bool = True` (default on) — a cell with `metadata.keep_output = true` or a `keep_output` tag is exempted from output/execution-count stripping, independent of any cell-metadata-key stripping (verified as a separate test case).
- `cli/main.py`: `normalize` gains `--keep-output`/`--keep-count`/`--extra-keys`/`--keep-metadata-keys` (nbstripout's own `metadata.KEY`/`cell.metadata.KEY` path syntax, verified against nbstripout's real README before implementation — see `full-parity-plan.md` §3); an nbstripout-compatible CLI-layer default strip set (`signature`/`widgets` notebook-level, `ExecuteTime`/`collapsed`/`execution`/`heading_collapsed`/`hidden`/`scrolled` cell-level); `[tool.libipynb.normalize]` `pyproject.toml` config support (CLI flags override config, config overrides the built-in default); `--install`/`--uninstall`/`--status` git clean-filter management (repo-local `.git/info/attributes` default, `--global`, or `--attributes=PATH` for a versioned file); `-` as `source` to read from stdin (what the installed filter itself invokes).
- **Real defect found and fixed during this card's own testing, not shipped blind:** the first version of the clean-filter command was the bare string `"libipynb normalize -"`, which resolved fine when this process ran it directly but failed with "command not found" once git's own shell invoked it (PATH is not reliably inherited that way). Fixed by invoking the exact same Python interpreter directly (`sys.executable -c "..."`), proven by an end-to-end `git add` test that failed under the first implementation and passes now.
- **Security-baseline invariant found and correctly extended, not bypassed:** `tests/integration/test_obligation_security_baseline.py` enforces that `subprocess` is imported by exactly one file in the whole package. Rather than weaken that check, `cli/main.py` was added to the allowlist with equal documentation rigor to the file's existing three exceptions, **and** a new test (`test_cli_subprocess_usage_only_ever_invokes_git`) statically proves every `subprocess.run()` call site in `cli/main.py` invokes `git` as its first argument and nothing else — the exception cannot silently widen into "cli/main.py may spawn anything" without this test catching it.
- New `tests/unit/test_cli_normalize_parity.py` (14 tests) and 4 new tests in `tests/unit/test_obligation_cleanup.py`: default stripping, each keep/extra/config flag, config-file precedence, stdin filter use, and a **real end-to-end test**: `git init` a scratch repo, install the filter, `git add` a notebook with `signature`/`widgets`/`ExecuteTime` metadata, and assert the **staged blob** has them stripped while the **working-tree file** is untouched (proving the clean filter actually ran, and ran correctly, not just that the install step reported success).
- `pytest tests/unit/test_cli_normalize_parity.py tests/unit/test_obligation_cleanup.py tests/integration/test_obligation_security_baseline.py -v` → **26 passed** (cleanup 6, normalize-parity 14, security-baseline 6). This exact sentence originally contained a self-contradictory count (asserted 24, then recomputed 26 in the same breath) — caught and corrected during Gate G2 independent review, see §6.

### LIBIPYNB-P3c — git diff/merge driver integration
- `cli/main.py`: new internal `_git-diff-driver` (7 positional args, git's own `gitattributes(5)` diff-driver contract) and `_git-merge-driver` (`%O %A %B %P`, git's own merge-driver contract — `%A` doubles as the file git expects overwritten with the result) subcommands, plus `diff --install-git`/`--uninstall-git`/`--git-status` wiring both drivers in one step (nbdime `config-git --enable` equivalent, verified against nbdime's real docs before implementation — see `full-parity-plan.md` §3).
- The diff driver's output uses `diff_notebooks()`'s new `source_hunks` (P3a) to print real `+`/`-` line hunks per changed cell, not just "cell changed."
- The merge driver reuses `merge_notebooks()` unchanged: conflicts leave the ancestor's value in place (never a marker splice) and the driver exits `1` so git correctly marks the path conflicted.
- **Real bug found and fixed during implementation:** the first version of `_cmd_git_diff_driver` referenced `CellField` without importing it — caught immediately by its own new unit test, not by the end-to-end test (which would also have caught it, but the unit test caught it first and pinpointed the exact line).
- New `tests/unit/test_cli_git_diff_merge_drivers.py` (8 tests) including two genuine end-to-end tests: a real `git diff` on a scratch repo showing actual `-x = 1`/`+x = 2` hunks (not git's default binary-diff fallback), and a real `git merge` producing a real conflict whose resolution is libipynb's ancestor-wins value (not git's own text-conflict-marker merge).
- `pytest tests/unit/test_cli_git_diff_merge_drivers.py -v` → **8 passed**.

### LIBIPYNB-P9 — CI/platform disclosure
- Per this session's own standing operating rule (CI/CD pipeline edits require explicit confirmation, not assumed authorization), took the plan's own documented alternative path: added a permanent "Platform support" section to `README.md` stating plainly that CI is Linux-only and Windows/macOS are best-effort, rather than editing `.gitlab-ci.yml` unreviewed.
- Docs-only; no test changes required.

### LIBIPYNB-P6 — unified docs pass
- README: updated Features list (diff/merge/cleanup capabilities, CLI count 8→9), added a new "Compared to the wider notebook toolchain" table and Roadmap section stating plainly which capabilities are proven-by-test vs. designed-but-not-yet-oracle-verified vs. not-yet-implemented — deliberately not claiming nbconvert/papermill parity, since neither was attempted this round.
- CHANGELOG: updated Cleanup/Diff-and-merge/CLI bullets, added Import-boundary-test and Cross-tool-oracle-scaffolding bullets, replaced the stale "666 tests" figure with a freshly re-measured, dated count and coverage percentage (see §3).

## 3. Final regression (this round, reproduced live)

```
pytest tests/ -q                              -> 752 passed, 9 skipped in ~28-35s (stable across reruns)
pytest tests/ --cov=libipynb --cov-report=term-missing -q
                                                -> 87.92% coverage (threshold 85.0%, met);
                                                   TOTAL 3733 stmts, 332 miss, 1326 branch, 257 brpart
ruff check .                                   -> All checks passed!
ruff format --check .                          -> 112 files already formatted
mypy src/libipynb                              -> Success: no issues found in 34 source files
```

Net change this round: **+48 tests** (704 → 752 passed), **+5 skips** (4 → 9, all five new oracle-tool `importorskip` fixtures), **zero regressions** in any previously-passing test, confirmed by full-suite reruns after every individual taskcard (not only once at the end).

## 4. Real defects found and fixed during this round (Repair Loop evidence, not shipped blind)

1. **Test-authoring bug** (`tests/unit/test_obligation_diff_hunks.py`, caught before commit-worthy): a Hypothesis property test didn't guard against `before == after` inputs, which would have hit the wrong assertion path — fixed with `hypothesis.assume(before != after)`.
2. **Live-dict-mutation test bug** (`tests/unit/test_obligation_diff_hunks.py`): two tests mutated `NotebookDocument.raw` in place without `deepcopy`, which — because `.raw` returns the *live* backing dict, a documented behavior — silently mutated the "before" document too, making the "after" comparison vacuous. Caught by an `IndexError` when the expected field-change didn't materialize, not a silent false-pass.
3. **Misdiagnosed edit boundary** (`tests/unit/test_obligation_cleanup.py`) — this bullet originally, incorrectly, described this as a copy/paste artifact in a *new* test. Gate G2 review proved that account false: the `assert document.cells[0]["metadata"]["transient"] == 1` line was the final line of the **pre-existing, already-passing** `test_default_cleanup_clears_all_outputs_and_counts_but_not_metadata`. An `Edit` whose `old_string` boundary ended one line short of that assertion (because the file was read in a truncated range that stopped just before it) caused the line to be textually relocated to the end of the newly-inserted block instead of staying in its original function — Python happily parsed it as one more statement in whichever function preceded it in the new layout, so nothing errored at collection time. It was then misread as a stray artifact in the new test and deleted, silently dropping real, previously-passing coverage. Restored to its original location during repair; see §6.
4. **Cross-shell PATH resolution bug** (`cli/main.py`, `normalize --install`'s clean-filter command) — described in §2 P2 above; the real, load-bearing fix of this round.
5. **Missing import** (`cli/main.py`, `_cmd_git_diff_driver`'s use of `CellField`) — described in §2 P3c above.
6. **Security-baseline invariant collision** (`tests/integration/test_obligation_security_baseline.py`) — described in §2 P2 above; resolved by extension-with-added-rigor, not by weakening the check.

None of these were caught by a separate, later review pass in this round — all were caught by the same implementing session's own regression loop (test failures surfaced immediately on the first `pytest` run after each change). Independent verification (Gate G2) is recorded separately — see `full-parity-plan.md`'s updated taskcard statuses and the independent-review note appended after this bundle was first written.

## 5. Blocked work (not attempted this round, by design)

`LIBIPYNB-P4a-1`, `P4a-2`, `P4b`, `P4c` (real kernel-protocol execution engine and its dependents) and `P5a`, `P5b`, `P5c` (papermill-style parameter injection, which depends on P4b) were **not attempted**. This is the full-parity plan's own Gate G6: any taskcard that widens the execution surface requires a dated, explicit maintainer security sign-off recorded in that plan's §7 **before implementation starts** — not merely before shipping. That log is still empty. No executing session may satisfy this gate on the maintainer's behalf, exactly matching the base plan's own treatment of Gate G3 (publish authority). This is recorded as a true external blocker, not a symptom of remaining engineering effort: every taskcard independent of this gate (9 of 17) was completed and verified in this round.

## 6. Independent verification (Gate G2) and repair cycle

An independent reviewer (a separate agent invocation that did not implement any of the above, briefed only on what to check and told explicitly to be adversarial) inspected the real diff, re-ran every check itself, and actively tried to break the new functionality — not merely re-confirm what was claimed. It reproduced the baseline exactly (752 passed/9 skipped, 87.92% coverage, `ruff`/`mypy` clean) and then found **real, material problems**, not stylistic nitpicks. Full findings and reproduction steps are preserved in this session's own record; summarized here by disposition.

**Confirmed clean on first review, no changes needed:** `P1`, `P3a`, `P3b`, `P8`, `P9` (P3c needed two small fixes, folded in below).

**Findings that required repair, all fixed in this same cycle:**

1. **[Critical] Fail-open git filter** (`P2`) — `filter.libipynb.required` was set to `"false"`, meaning any failure of the clean filter (stale interpreter path, moved venv, import error) silently staged the raw, unstripped notebook instead of aborting `git add`. The reviewer reproduced this directly (a malformed `pyproject.toml` config crashing the filter, then `git add` reporting success with the raw notebook staged), fetched nbstripout's actual installer source to confirm the divergence, and noted the CHANGELOG explicitly called this an "nbstripout `--install` equivalent" while it diverged on exactly this dimension. **Fixed:** `required` set to `"true"`, matching nbstripout's own `install()` exactly; new regression test proves a failing filter now aborts `git add` rather than staging anything.
2. **[High] Unhandled crash on bad input** (`P2`) — an invalid `--extra-keys`/`--keep-metadata-keys` path, or a malformed `[tool.libipynb.normalize]` config (e.g. a bare string where a list was expected), raised a raw Python traceback instead of the structured JSON-to-stderr error every other CLI failure path uses. **Fixed:** a new `NormalizeConfigError` is caught at the call site and reported cleanly (exit 2); config values are now type-validated (list-of-strings, bool) before use, with three new regression tests.
3. **[High] Inverted config/CLI precedence** (`P2`) — the documented and intended behavior ("CLI flags take precedence over config") was backwards for the metadata-key lists: keeps were applied after adds in one merged pass regardless of source, so a config `keep_metadata_keys` always beat a CLI `--extra-keys` for the same key. The one test that claimed to cover this (`test_cli_flag_overrides_config_file`) passed no CLI flag at all and tested the opposite of its own name. **Fixed:** config and CLI are now applied as two separate, ordered passes (config first, then CLI), so the last-applied source always wins per key; the misnamed test was split into an honestly-named "config alone" test plus two new tests that actually exercise CLI-overrides-config in both directions.
4. **[Medium] Asymmetric `--uninstall`** (`P2`) — an attributes file written by `--install --attributes .gitattributes` (a versioned, repo-local file) was not found by a later `--uninstall --global`, which only searched the scope-matching location and reported `{"uninstalled": true}` regardless, leaving an orphaned filter-attribute line. Separately, `--install --uninstall` together silently ran install (first-checked-wins) instead of erroring, and `--global`+`--attributes` was accepted as a nonsensical half-global/half-local combination. **Fixed:** uninstall now searches every plausible attributes-file location regardless of the scope flag passed to that specific invocation (attribute files are location-based, not scope-based); the three action flags (`--install`/`--uninstall`/`--status`) are now mutually exclusive with a clean error; `--global`+`--attributes` together is now a clean error. Git *config* unset still correctly respects `--global` exactly (unlike the attributes search) since unsetting the wrong config scope would actively break other repositories relying on a global install.
5. **[High] Real data loss in the test suite itself** — see §4 item 3 above: a pre-existing, previously-passing assertion was silently dropped due to a misjudged `Edit` boundary, and the original defect writeup incorrectly blamed it on a copy/paste artifact in new code. Restored to its original location; the false account in §4 corrected.
6. **[Medium] Inverted oracle-scaffolding smoke tests** (`P7`) — the five `test_*_available_skips_cleanly_when_not_installed` tests asserted `raise AssertionError(...)` whenever `pytest.importorskip` did *not* skip — i.e. they were designed to **fail** the moment the real reference tool is installed, which is exactly backwards and would have produced 5 hard failures on the first CI job that installs `libipynb[oracle]` (the entire reason this scaffolding exists). The reviewer proved this by placing a stub `nbstripout` module on `PYTHONPATH` and showing the test failed. **Fixed:** each test now performs a genuine, minimal positive check (the module imports and is non-`None`) when the tool is present, relying on `pytest.importorskip` itself (trusted stdlib behavior) for the skip path; independently re-verified with the same stub-module technique the reviewer used, now passing instead of failing.
7. **[Medium] Security-baseline check too narrow** — `test_cli_subprocess_usage_only_ever_invokes_git` (added this round to compensate for widening the subprocess-import allowlist) only matched `subprocess.run(...)`. The reviewer proved `subprocess.Popen`/`.call`/`.check_call`/`.check_output`, and a `from subprocess import run as _r` bare-name call all passed through unflagged, using a copy of `main.py` with those forms appended. **Fixed:** the check now resolves both `import subprocess` (attribute-call) and `from subprocess import ...` (bare-name-call, including aliasing) forms across all five spawn functions, with three new "can the checker actually fail" self-tests (mirroring the same discipline already applied to the import-boundary check in `P8`) proving it now catches exactly what the reviewer demonstrated.
8. **[Low] `P6` doc-drift check named as required but never built** — the taskcard's own closeout rule required "a passing doc-drift check" and named it an implicit prerequisite; none existed, and README's "9 commands" claim had already drifted from `--help`'s actual (accidentally 11-command, due to two internal git-driver commands leaking into the usage listing) output within the same round. **Fixed:** the internal commands no longer appear in `--help` (an argparse `metavar=`+choice-list-filtering fix, verified directly against real `--help` output), and a new `tests/unit/test_doc_drift.py` statically asserts every public CLI command is named in README.md, the internal ones are not, and README's stated command count matches reality.
9. **[Low] Two cosmetic `P3c` nits** — a hardcoded `git merge master` in one end-to-end test would fail on a machine configured with `init.defaultBranch=main`; fixed by pinning the scratch repo's initial branch name explicitly (`git init -b master`). The internal driver commands leaking into `--help` is covered by item 8 above.

**Post-repair verification (reproduced live, this session):**

```
pytest tests/ -q                              -> 767 passed, 9 skipped (up from 752; +15 net new
                                                   regression tests from the repair cycle)
pytest tests/ --cov=libipynb --cov-report=term-missing -q
                                                -> 88.25% coverage (threshold 85.0%, met)
ruff check .                                   -> All checks passed!
ruff format --check .                          -> 114 files already formatted
mypy src/libipynb                              -> Success: no issues found in 34 source files
```

Additionally spot-verified directly (not just via the suite): the original, pre-existing simple CLI forms (`libipynb diff a.ipynb b.ipynb`, `libipynb normalize a.ipynb -o out.ipynb`) still work unmodified after making their positional arguments optional to support the new `--install-git`/`--install` flag paths — both exit 0 with correct output.

**Verdict: Gate G2 passed after one repair cycle.** All 9 executed taskcards (`P1`, `P2`, `P3a`, `P3b`, `P3c`, `P6`, `P7`, `P8`, `P9`) are promoted to `completed_verified` in `full-parity-plan.md`. No further review cycle was requested by the independent reviewer's own criteria (every material finding traced to a specific, verified fix; no new findings surfaced on the fixes themselves during this write-up's own re-verification).

## 7. Round 2 — Gate G8: real oracle installation and comparison

**Trigger:** user-directed, after this session's Round 1 handoff explicitly noted "no oracle tool is installed on this machine" as a known limitation. Instruction: install them and use `.venv` for everything.

**Installed** (`.venv/Scripts/python.exe -m pip install nbstripout nbdime "nbconvert>=7.16" papermill nbclient jupyter_client ipykernel`): `nbstripout-0.9.1`, `nbdime-4.0.4`, `nbconvert-7.17.1`, `papermill-2.7.0`, `nbclient-0.11.0`, `jupyter_client-8.9.1`, `ipykernel-7.3.0`, plus their transitive dependencies. All installed into the project's own `.venv`, matching the `oracle`/`exec` extras groups defined in `pyproject.toml` (P8) — nothing installed system-wide.

**`tests/oracle/test_scaffolding_smoke.py` re-run with real tools present:** all 5 `test_*_fixture_imports_the_real_package_when_available` tests now genuinely PASS (previously skipped) — independently confirming, in the real target environment rather than a simulated stub, that Gate G2's fix to these tests (§6 item 6) actually works in both directions.

**New real oracle-comparison test suites built** (the sub-task every P2/P3c status note had explicitly deferred pending tool availability):

### `tests/oracle/test_nbstripout_parity.py` (4 tests, all passing)

Ran real `nbstripout` (via `python -m nbstripout`) against the same fixture notebook `libipynb normalize`'s nbstripout-compatible policy processes, and diffed the results field-by-field. Two intentional divergences confirmed and documented (not gaps):

1. **Cell IDs** — real nbstripout regenerates them by default (sequential `"0"`, `"1"`, ... unless `--keep-id`); libipynb's `normalize` never touches them, by design (they are the content-derived stability guarantee the diff/merge engine depends on).
2. **`source`/output-text serialization form** — nbstripout's underlying nbformat writer canonicalizes multi-line text fields from a plain string to a list-of-lines; libipynb's writer preserves whichever form was read. Both are valid nbformat per the spec.

**One real, third divergence found that was NOT intentional — fixed, not just documented:** with `--keep-output`, real nbstripout still resets an `execute_result` output's own embedded `execution_count` field (confirmed separately: `--keep-output --keep-count` together preserves it, proving the two are coupled in nbstripout's own implementation). libipynb's `cleanup()` only ever reset the cell-level `execution_count`, leaving a kept output's own embedded copy untouched — a real, if minor, gap: keeping an output's stale execution count while resetting the cell's own is inconsistent and defeats part of the point of resetting at all.

**Fix:** `model/cleanup.py`'s `cleanup()` now also resets `execution_count` on every *retained* output when `reset_execution_counts=True` (the default), recorded as a new `reset_output_execution_count` `Change` per output. Purely additive to the existing `ChangeReport` shape; `reset_execution_counts=False` leaves output-level counts alone too, proven by a dedicated new test. Two new regression tests added to `tests/unit/test_obligation_cleanup.py`; full existing cleanup suite re-run, zero regressions. After the fix, all 4 oracle tests pass with zero unexplained divergence.

### `tests/oracle/test_nbdime_parity.py` (3 tests, all passing)

Ran real `nbmerge` (`python -m nbdime merge`) against the same base/ours/theirs fixtures `merge_notebooks()` is tested against.

- **No-conflict case:** both tools agree exactly (once nbdime's list-of-lines source form is accounted for, same divergence as above).
- **Conflict case, major finding:** real `nbmerge`'s *default* merge strategy ("inline") splices literal git-style conflict markers (`<<<<<<< local` / `=======` / `>>>>>>> remote`) directly into the conflicted cell's `source` field, confirmed by directly running it and inspecting the output — proving this is real reference-tool behavior, not a hypothetical worst case. This is precisely the practice `model/merge.py`'s own docstring calls an "outright prohibition": embedding such markers into executable source would "silently turn a merge conflict into a syntax error at best and a foreign string literal at worst." libipynb never does this, and this comparison is the first time that design choice was checked against the real tool it's implicitly positioned against, rather than only against libipynb's own tests.
- **Subtler finding:** `nbmerge --merge-strategy use-base` reaches the *same resolved value* as libipynb (base wins) without marker-splicing, but does so by not reporting a conflict at all (exit code 0, no warning) — a silent resolution. libipynb's `MergeReport.has_conflicts` always surfaces the conflict regardless of which value was chosen, combining the safe value choice of one nbdime strategy with the always-report behavior of the other. No code change needed here — this is a validation of already-correct, already-tested behavior, now backed by a direct comparison against both of the real tool's relevant strategies instead of asserted from the module's own docstring alone.

**Final regression after Round 2** (reproduced live):

```
pytest tests/ -q                              -> 781 passed, 4 skipped (up from 767/9; the 5 fewer
                                                   skips are exactly the 5 oracle-tool fixtures that
                                                   now genuinely run instead of skipping)
pytest tests/ --cov=libipynb --cov-report=term-missing -q
                                                -> 88.30% coverage (threshold 85.0%, met)
ruff check .                                   -> All checks passed!
ruff format --check .                          -> clean after one auto-format pass
mypy src/libipynb                              -> Success: no issues found in 34 source files
```

**Documentation updated to reflect real, evidence-backed status:** `README.md`'s comparison table promoted `nbstripout` and `nbdime` from 🚧 to ✅, each with a specific note naming what was actually verified and what remains an intentional, proven divergence — not a blanket "matches" claim. `plans/full-parity-plan.md`'s `P2`/`P3c` status lines updated to record Gate G8 as closed for both cards.
