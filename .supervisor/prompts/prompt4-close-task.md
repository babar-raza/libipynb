Close this task cleanly.

1. Review everything changed in this session.
2. Commit all completed changes. If the work spans clearly different change groups, use
   logically separated commits. Otherwise use one clean commit. Follow CONTRIBUTING.md's
   Conventional Commits format.
3. Identify the governing plan file for the taskcard(s) closed this session:
   `plans/remediation-plan.md` for Tier B/M/V work, `plans/full-parity-plan.md` for Tier P
   work. **Re-read that file fresh right before editing it — not from an earlier read
   earlier in this session.** This is not a hypothetical precaution: a real concurrent-edit
   collision on this exact kind of file happened once already (two sessions both added a
   new section, both numbered it the same way, caught only because the second session
   re-read the file immediately before writing — see `plans/full-parity-plan.md` §14/§15
   and `plans/remediation-plan.md` §1's "Full-Parity lineage" changelog row for the full
   account). Amend, in place, in the file you just re-read:
   - the taskcard's own `Status` line
   - its row in that file's Taskcard Register
   - its row(s) in the Verification Matrix and Unresolved Work Register (or Resolved/
     Preserved Work, once closed)
   Do not overwrite other sections' history. Do not create a separate index file, closure
   record, or state file for narrative/evidence detail — this repo's plan files remain the
   single record for that. **UPDATE 2026-08-24**: `plans/state.json` is an exception, added
   for the 2026-08-24 publication-readiness engagement as a machine-readable status
   complement (not a narrative replacement) — if the taskcard being closed has a row there,
   amend it too, re-reading immediately before writing per the same concurrency discipline
   as the files above.
4. **CHANGELOG.md guidance (superseded 2026-08-24 — do not follow the version below as
   written):** the original instruction here said to keep appending everything to the
   still-open `[0.1.0]` entry until `LIBIPYNB-B3` ships, with no `[Unreleased]` section.
   That guidance is now stale: the `[0.1.0]` entry is 12+ days and two major work rounds
   behind HEAD, and the 2026-08-24 mission brief explicitly requires a real `[Unreleased]`
   section rather than backdating ongoing work into a historical release date (see
   `plans/publication-readiness-plan-2026-08-24.md` section M5 for the full reasoning).
   **Current instruction:** append user-visible changes to `## [Unreleased]`; leave the
   `[0.1.0]` entry's historical content alone. Re-open this decision only if the maintainer
   objects.
5. Mark the task closed only if implementation, verification (Gate G1), independent review
   (Gate G2), the commit, and the plan file's own row are all complete.
6. In the final response, provide:
   - files changed
   - commit hash(es)
   - exact plan file + section/row updated
   - closure status: CLOSED or NOT CLOSED

Rules:
- Do not claim closure without verifying the final repo state (`git status --short`).
- Do not leave uncommitted relevant changes behind.
- Do not create ad hoc summary files unless the plan file's own evidence-bundle convention
  calls for one (a new `plans/<topic>-execution-evidence.md`, matching the existing
  `phase2-execution-evidence.md` / `phase2b-execution-evidence.md` / `full-parity-execution-evidence.md` pattern).
- Never `git tag`, push a tag, or publish without a dated authorization already recorded in
  `plans/remediation-plan.md` §13 (Gate G3) — closing a taskcard is not itself that
  authorization.
- Prefer existing governed workflows (`.supervisor/prompts/*`) and repo conventions over
  inventing new ones.
