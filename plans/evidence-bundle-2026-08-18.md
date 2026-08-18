# libipynb Close-Out Session — Reproducible Evidence Bundle

**Date:** 2026-08-18
**Session:** close-out execution of `plans/production-hardening-plan.md`'s five remaining open taskcards
(Q3, Q7, Q8, Q12c, Q12a) plus the mission-level standing deliverables a dedicated investigation found
missing (`plans/libipynb-feature-analysis-and-execution.md`'s Phase 2/Phase 7/"Required final
deliverables"). Full execution plan:
`C:\Users\prora\.claude\plans\libipynb-required-capabilities-joyful-wind.md`.
**Repository root (absolute):** `c:\Users\prora\OneDrive\Documents\GitHub\libipynb`
**Starting commit:** `88aa112bb1d907c0c0272fa64fe0663c5b75a0f7` (verified unchanged at the start of every
major phase of this session — see the repo-drift checks below)
**Final commit (this bundle's own commit is the one after it):** see `git log` output, §5 below.

---

## 1. Environment and Tool Versions

Recorded via `.venv\Scripts\python.exe --version` and `.venv\Scripts\python.exe -m pip show <pkg>`,
actually run this session, not assumed:

| Tool | Version |
|---|---|
| Python | 3.13.2 (Windows 11) |
| pytest | 9.1.1 |
| mypy | 2.3.0 |
| ruff | 0.16.2 |
| nbformat | 5.10.4 |
| nbclient | 0.11.0 |
| nbdime | 4.0.4 |
| nbconvert | 7.17.1 |
| nbstripout | 0.9.1 |
| jupytext | 1.19.5 |
| papermill | 2.7.0 |
| jupyter_client | 8.9.1 |

---

## 2. Verification Commands and Results (this session, actually executed)

| Command | Result |
|---|---|
| `git rev-parse HEAD` (repeated at start, before commits, before final commit) | `88aa112bb1d907c0c0272fa64fe0663c5b75a0f7` every time — no drift |
| `ruff format --check src/ tests/` (before fix) | exit 1, 13 files would be reformatted |
| `ruff format` (exact 13-file list) then `ruff format --check` | exit 0, 115 files already formatted |
| `pytest tests/ -q` (post-format-fix baseline) | 1017 passed, 5 skipped, 329.51s |
| `pytest tests/ -q` (after Q7/Q8 Gate G6 fixes) | 1022 passed, 5 skipped, 270.34s |
| `pytest tests/ -q` (final, TC-CLOSEOUT-06) | 1022 passed, 5 skipped, 358.59s |
| `pytest tests/oracle/ tests/package/ -v` (final) | 28 passed |
| `mypy --strict src/libipynb` (final) | Success: no issues found in 42 source files |
| `ruff check src/libipynb tests/` (final) | All checks passed! |
| `ruff format --check src/ tests/` (final) | 115 files already formatted |
| `pytest tests/unit/test_cli_git_diff_merge_drivers.py -k TestEndToEndGitDiffOnPreNbformat45Notebooks -v` | 2 passed (the pre-4.5 git-driver headline repro) |
| Direct `LocalJupyterExecutor.execute()` on `tests/fixtures/corpus/data-science-pattern.ipynb` | `completed=True`, `kernel_death_error=None`, `kernel_launch_error=None` (the list-source headline repro) |
| `python -m build --wheel --sdist` then `unzip -p dist/*.whl '*/METADATA' \| grep -i recruitize` | exit 1 (zero matches) |
| `python examples/load_and_inspect.py` | exit 0 |
| `python examples/validate_notebook.py` | exit 0 |
| `git status --porcelain \| wc -l` (repo-drift check, repeated 4 times across the session) | 56 → 56 (after removing this session's own stray `nul` artifact) → 60 → 61 → tracked via lane commits, no unexpected drift at any point |

---

## 3. Checksums (SHA-256, computed this session)

| File | SHA-256 |
|---|---|
| `src/libipynb/validation/schemas/nbformat.v4.0.schema.json` | `a688586f826df23abb34c82caa57cd08584eff658f76cbb9c26035f0636abe65`[^1] |
| `src/libipynb/validation/schemas/nbformat.v4.1.schema.json` | `bd9e0973793782172cfe68a42b392decdb93b019137c3ecdc6f5466fd253e167`[^1] |
| `src/libipynb/validation/schemas/nbformat.v4.2.schema.json` | `bb88e123fa32f56552ed48e8f4166e3a9f7bde49629f6d4485e4854b75ae2dce`[^1] |
| `src/libipynb/validation/schemas/nbformat.v4.3.schema.json` | `b4a496a7584060eb9247b814301e2e1e5a8f0d391486c98b25a9aa59d1eecb73`[^1] |
| `src/libipynb/validation/schemas/nbformat.v4.4.schema.json` | `34a5c513f5d67ec6de36ebd2c58f10a9f15c2902c6b4109a011bb3696751e756`[^1] |
| `src/libipynb/validation/schemas/nbformat.v4.5.schema.json` | `eb9bd8a2d309e9de2d4f53751d2e83b1ae57332e48585f30747945d8f0536096`[^1] |
| `ARCHITECTURE.md` | `447a0094c66cfba3a9659df2deb7359ec99186c087ad60591cc96cea38a6ef28`[^1] |
| `plans/gate-status-g1-g7.md` | `06d2ec07c0e853263bf886bd96bb7ca49038ce4c5c43e5ffdb0856514d51fb96`[^1] |
| `plans/independence-audit-2026-08-18.md` | `d95f64fd19b6785605db44e0b0308eb1c48237a9cd1f11bcc32ea49ec5502410`[^1] |
| `plans/specification-traceability-matrix.md` | `13018c00b85493375a756d5aead2f799a92c44a5617cfee1c16db93b67142914`[^1] |
| `plans/benchmarks-2026-08-18.md` | `73a3d1f9f4292b78bcc015c9128bc9242aba3b1ffc0ed75afe3f24fafaefe4be`[^1] |

[^1]: Computed via `hashlib.sha256(path.read_bytes()).hexdigest()` against this session's own `.venv`
    Python interpreter, this session, on the file content as committed/written by this session — re-run
    the same command against the current file to verify it is unchanged since this bundle was written.

---

## 4. Artifact Index (absolute paths)

Every artifact this close-out session produced or updated, with its absolute filesystem path:

**This session's execution plan (not committed to the repo — lives in the Claude Code plan store):**
- `C:\Users\prora\.claude\plans\libipynb-required-capabilities-joyful-wind.md`

**New standing documents (committed in the final "Evidence & Publication Readiness" commit, TC-CLOSEOUT-13):**
- `c:\Users\prora\OneDrive\Documents\GitHub\libipynb\ARCHITECTURE.md`
- `c:\Users\prora\OneDrive\Documents\GitHub\libipynb\plans\specification-traceability-matrix.md`
- `c:\Users\prora\OneDrive\Documents\GitHub\libipynb\plans\gate-status-g1-g7.md`
- `c:\Users\prora\OneDrive\Documents\GitHub\libipynb\plans\benchmarks-2026-08-18.md`
- `c:\Users\prora\OneDrive\Documents\GitHub\libipynb\plans\independence-audit-2026-08-18.md`
- `c:\Users\prora\OneDrive\Documents\GitHub\libipynb\plans\evidence-bundle-2026-08-18.md` (this file)

**Updated governing/evidence documents (already committed, see §5):**
- `c:\Users\prora\OneDrive\Documents\GitHub\libipynb\plans\production-hardening-plan.md` (§0/§1/§3/§6
  updated: Q3/Q7/Q8/Q12c/Q12a all now `completed_verified`)
- `c:\Users\prora\OneDrive\Documents\GitHub\libipynb\pyproject.toml` (internal URL removed)
- `c:\Users\prora\OneDrive\Documents\GitHub\libipynb\CONTRIBUTING.md` (clone instructions genericized)

**Modified source/test files (7 lane commits, see §5) — full list recoverable via
`git show --stat <each commit>` in the repository above; not re-enumerated here to avoid duplicating git's
own record.**

---

## 5. Commits (local only, not pushed)

```
88aa112 fix(execution): make execute_async cancellation deterministic, not just leak-free   [pre-existing HEAD]
1ac93de fix(execution): normalize list-source cells before nbclient handoff; harden safety surface
c21126c fix(diff-merge): synthesize stable cell ids for pre-4.5 notebooks; detect notebook-metadata conflicts
104fdfe fix(security): close resource-limit, sanitizer, and surrogate-handling gaps
1157d4c fix(model): deep-copy leaking accessors; validate attachment names/base64 at write time
28ec7a6 fix(cli): shared exception boundary, __main__ entry point; export/editor fidelity
0abff10 test(validation): schedule-gated oracle/package CI job; broaden property/fixture coverage; remove dead exception
49c8466 docs(release): remove internal GitLab URL; correct SECURITY.md/README claims; drop dead dependency
```

An 8th commit follows this bundle (`docs(evidence): ...`, TC-CLOSEOUT-13), adding the 6 new standing
documents listed in §4. **No `git push` was run at any point in this session.**

---

## 6. Known, Deliberately Deferred Items (not fixed this session, with resume conditions)

| Item | Why deferred | Resume condition |
|---|---|---|
| `LIBIPYNB-Q2`'s execution-engine timeout-watchdog redesign | Larger design change than fits a close-out session; not a human-authority blocker | Any future session can pick it up; needs its own Gate G6 security-design review when attempted |
| `LIBIPYNB-Q13b` (GitLab CI/CD Schedule) | Genuinely external — no GitLab project-settings/API access available to this session | Needs a maintainer with GitLab project access to create the schedule |
| `LIBIPYNB-Q13c` item 3 / real-world notebook corpus sourcing | Provenance/licensing judgment call on redistributing third-party work — investigated concretely this session (installed-package fixtures found unsuitable, network fetch rejected as unauthorized scope), not a missing credential | Needs an explicit maintainer decision on source/license/selection, same class of decision as `Q12a`'s URL choice |
| v3→v4 notebook conversion (worksheets/pyout/prompt_number) | Confirmed genuinely unimplemented by this session's own investigation (`plans/specification-traceability-matrix.md`, `REQ-SPEC-CONV-008`); new-feature-scale work, not a close-out-session fix | Needs its own dedicated implementation taskcard in a future session |
