# Supervisor Prompt: Memory Sync
# libipynb — cross-session continuity only. Not a second evidence trail: plans/*.md already
# owns that (see plans/remediation-plan.md §8's Evidence Contract).
# IMPORTANT: append only. Do not overwrite history. Idempotent.

---

At the end of a session, do two small things:

1. **Update `.supervisor/memory/session_context.json`**: set `last_sync` to the current
   timestamp. Leave `supervisor_version` and `authoritative_plans` alone unless this session
   actually changed `.supervisor/`'s own structure.

2. **Append one line to `.supervisor/README.md`'s "Session Handoff Log" section**:
   ```
   - YYYY-MM-DD: <one-sentence summary of what this session did> — touched <plan file(s)>
   ```
   Append only — never edit or remove a prior entry.

## Rules

- Do not create a separate `project-memory.md` or any other new state file — the two writes
  above are the entire scope of this prompt.
- Do not write to `plans/remediation-plan.md` or `plans/full-parity-plan.md` from this
  prompt — those are amended in place by `prompt2-plan-hardening.md`, `prompt3-controlled-execution.md`,
  and `prompt4-close-task.md` directly, following their own append/amend convention. This
  prompt only records that a session happened, not what it found.
- This memory is advisory continuity only. `plans/*.md` and real command output are the
  authoritative record of gate states and test results — never cite the Session Handoff Log
  as evidence for a taskcard's status.
