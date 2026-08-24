# STAGE-SEQUENCING GUARDRAILS

---

## Mission

After running any of `prompt1-post-sprint-audit.md` / `prompt2-plan-hardening.md` /
`prompt3-controlled-execution.md`, determine the next required stage automatically —
don't ask the user which prompt to run next.

## Sequencing

Stage sequencing (which prompt runs next, given a stage's outcome) is defined once, in
`prompt-registry.yaml`'s `successor_rules` for each prompt — follow it directly rather than
re-deriving it here. This file only states what a final outcome may **never** be, regardless
of which stage produced it.

## Invalid Final States

These are never valid as a session's final outcome:

- A taskcard marked `completed_verified` without both a Gate G1 (regression, real command
  output) citation and a Gate G2 (independent review, a separate invocation) citation.
- A final summary that is prose-only, with no explicit per-taskcard status from the real
  vocabulary (`not_attempted` / `claimed_unproven` / `partially_done` /
  `completed_but_weakly_verified` / `completed_verified` / `blocker` / `follow_up`).
- A session ending with "let me know if you'd like me to continue" when nothing external is
  actually blocking further work — either continue or state the specific blocker.
- A `blocker` status on Gate G3 or G6 treated as satisfied because the session judged it
  unimportant, low-risk, or already effectively done — only a dated maintainer authorization
  recorded in the governing plan file satisfies these gates.
- A quality/coverage number cited alone as proof of correctness, with no Repair Loop or
  Verification Matrix history behind it (Anti-Overclaim Rule AO-7).
- `plans/*.md` left stale relative to the actual working tree at session end (the drift
  Gate G9 in `plans/full-parity-plan.md` §4.1 exists specifically to catch — the concrete
  precedent was `remediation-plan.md` itself briefly listing `V1` as `not_attempted` while
  it was fully implemented in the same working tree).

## Max Loop Iterations

Default: 3 Repair Loop cycles (`prompt3-controlled-execution.md` Phase 2, steps 2–5) per
taskcard. After 3 cycles without reaching a clean regression, stop and report exactly what
remains unresolved to the maintainer rather than continuing to loop silently.

## Output

A stated decision in this session's own chat response — which stage runs next, or why the
session is stopping — not a separate file.
