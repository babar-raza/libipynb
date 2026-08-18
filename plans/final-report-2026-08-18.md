# libipynb Close-Out Session — Final Report (2026-08-18)

**Execution plan:** `C:\Users\prora\.claude\plans\libipynb-required-capabilities-joyful-wind.md`
**Evidence bundle:** `c:\Users\prora\OneDrive\Documents\GitHub\libipynb\plans\evidence-bundle-2026-08-18.md`

## What this session did

Closed the five remaining open taskcards in `plans/production-hardening-plan.md` (a same-day
remediation of `plans/forensic-capability-audit-2026-08-18.md`'s ~25 findings), and produced the mission
(`plans/libipynb-feature-analysis-and-execution.md`)'s standing deliverables a dedicated investigation
found were still missing beyond that taskcard remediation.

## Governing-plan cards closed

| Card | Before | After |
|---|---|---|
| `LIBIPYNB-Q3` (diff/merge on pre-4.5 notebooks) | `completed_but_weakly_verified` | `completed_verified` — a third, independent fresh-context review ran 12 adversarial scenarios, confirmed correct, zero defects |
| `LIBIPYNB-Q7` (resource-limit defaults) | `completed_but_weakly_verified` | `completed_verified` — Gate G6 review found and closed a real gap (token-budget bypass on closing tags/comments) |
| `LIBIPYNB-Q8` (sanitizer markdown blind spot) | `completed_but_weakly_verified` | `completed_verified` — Gate G6 review found and closed a real gap (MIME-parameter bypass) |
| `LIBIPYNB-Q12c` (nbformat pin) | `completed_but_weakly_verified` | `completed_verified` — Gate G7 checks re-confirmed |
| `LIBIPYNB-Q12a` (internal URL leak) | `blocker` | `completed_verified` — maintainer decision obtained ("omit the field entirely"), applied, verified against a fresh build |

All 21 taskcards in `plans/production-hardening-plan.md` are now `completed_verified` except the three
items below, which remain accurately described as deferred/blocked, not silently resolved.

## New gaps found and fixed this session (not present in the original remediation)

1. **`ruff format --check` was failing on 13 files** — a real, standing CI quality-stage gate
   (`.gitlab-ci.yml`'s `ruff-format` job) that neither the original audit nor the original remediation
   ever ran. Fixed before any review work began, so no reviewer's line-number references were invalidated
   mid-session.
2. **Sanitizer token-budget bypass (Q7 follow-up):** `max_scan_tokens` only counted HTML start-tags;
   a payload dominated by closing tags, comments, or declarations bypassed the CPU-DoS protection
   entirely (independently measured: 20+ seconds of CPU for 16 million closing tags, limit never
   engaged). Fixed by wiring the existing token counter into `handle_endtag`/`handle_comment`/
   `handle_decl`/`handle_pi`.
3. **Sanitizer MIME-parameter bypass (Q8 follow-up):** a MIME type with an RFC 2046 parameter (e.g.
   `text/markdown; charset=utf-8`) bypassed scanning entirely via exact-string comparison — affecting
   both the new markdown fix and the pre-existing `text/html` active-MIME check. Fixed with a
   `_media_type_base()` helper stripping parameters before comparison.

Both security gaps were found by independently-dispatched, fresh-context review agents specifically
briefed to check security *adequacy*, not just correctness — the same review discipline the original
forensic audit found had been skipped once before (the P4a-1 execution-engine blocker shipping on
self-review alone).

## New standing deliverables produced

| Document | Absolute path |
|---|---|
| Specification traceability matrix (26 rows, per-normative-rule) | `c:\Users\prora\OneDrive\Documents\GitHub\libipynb\plans\specification-traceability-matrix.md` |
| Gate G1-G7 status document (mission's own gate numbering) | `c:\Users\prora\OneDrive\Documents\GitHub\libipynb\plans\gate-status-g1-g7.md` |
| Architecture/execution-boundary documentation | `c:\Users\prora\OneDrive\Documents\GitHub\libipynb\ARCHITECTURE.md` |
| Benchmark/compatibility standing report | `c:\Users\prora\OneDrive\Documents\GitHub\libipynb\plans\benchmarks-2026-08-18.md` |
| Packaging/independence standing audit | `c:\Users\prora\OneDrive\Documents\GitHub\libipynb\plans\independence-audit-2026-08-18.md` |
| Reproducible evidence bundle | `c:\Users\prora\OneDrive\Documents\GitHub\libipynb\plans\evidence-bundle-2026-08-18.md` |

The traceability matrix surfaced one significant, previously-undocumented finding: **v3→v4 notebook
conversion (worksheets flattening, `pyout`/`prompt_number`/`input` field renames) is genuinely
unimplemented** — confirmed by direct grep, zero matches for `worksheets`/`pyout`/`pyerr`/
`prompt_number` anywhere in `src/`. This is new-feature-scale work, correctly left out of this
close-out session's scope, and recorded here as a named next action.

## Commits (local only — no push occurred)

```
1ac93de fix(execution): normalize list-source cells before nbclient handoff; harden safety surface
c21126c fix(diff-merge): synthesize stable cell ids for pre-4.5 notebooks; detect notebook-metadata conflicts
104fdfe fix(security): close resource-limit, sanitizer, and surrogate-handling gaps
1157d4c fix(model): deep-copy leaking accessors; validate attachment names/base64 at write time
28ec7a6 fix(cli): shared exception boundary, __main__ entry point; export/editor fidelity
0abff10 test(validation): schedule-gated oracle/package CI job; broaden property/fixture coverage; remove dead exception
49c8466 docs(release): remove internal GitLab URL; correct SECURITY.md/README claims; drop dead dependency
```
(An 8th commit, `docs(evidence): ...`, follows this report, adding the 6 new standing documents.)

## Final verification

`pytest tests/ -q` → **1022 passed, 5 skipped** (up from 1017 at session start — 5 new regression tests,
0 regressions). `pytest tests/oracle/ tests/package/ -v` → 28/28. `mypy --strict` clean, 42 files.
`ruff check` clean. `ruff format --check` clean. Both of the original audit's headline reproductions
re-confirmed fixed (list-source execution; pre-4.5 git-driver diff/merge). Wheel/sdist build clean, zero
matches for the internal URL string.

## Remaining items (deliberately deferred, not blocked on missing agent capability except where noted)

1. **`LIBIPYNB-Q2`'s execution-engine timeout-watchdog redesign** — scope deferral, not blocked. Any
   future session can pick this up; it needs its own Gate G6 security-design review once attempted.
2. **`LIBIPYNB-Q13b` (GitLab CI/CD Schedule)** — genuinely blocked. No GitLab project-settings or API
   access is available to this environment (checked directly: no GitLab MCP/API tool present, repository
   has no configured remote push target yet). Resume condition: a maintainer with GitLab access creates
   the schedule.
3. **Real-world notebook corpus sourcing** (`LIBIPYNB-Q13c` item 3, and the corresponding row in the new
   traceability matrix) — investigated concretely this session, not just re-asserted: local
   already-installed packages' bundled fixtures were checked and found to be synthetic test data, not
   real authored work; fetching genuine third-party notebooks over the network was considered and
   rejected as an unauthorized provenance/licensing judgment call, the same class of decision `Q12a`'s
   URL choice needed explicit maintainer authority for. Resume condition: a maintainer decision on
   source, license, and selection.
4. **v3→v4 notebook conversion** (new finding, `REQ-SPEC-CONV-008` in the traceability matrix) — confirmed
   genuinely absent, new-feature-scale work. Resume condition: a dedicated future implementation
   taskcard, not a close-out fix.

## Evidence bundle

**Absolute path:** `c:\Users\prora\OneDrive\Documents\GitHub\libipynb\plans\evidence-bundle-2026-08-18.md`
