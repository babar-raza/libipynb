# Supervisor Prompt: Approval Gate Classifier
# libipynb — routes pending actions to plans/remediation-plan.md's Gate Contract (§7) and
# plans/full-parity-plan.md's extended gates (§4.1)
# Usage: fill in the facts below, then classify each pending action.

---

You are classifying which of this session's pending actions can proceed autonomously and
which require the maintainer (Babar Raza).

## Current State
Taskcard(s) in scope: [list]
Governing plan file: [plans/remediation-plan.md or plans/full-parity-plan.md]

## Pending Actions
```
[list the concrete actions this session wants to take next]
```

## Classification Rules

### autonomous-continue
Proceed without human intervention if:
- The action stays within the taskcard's own `Allowed actions`.
- It's a code/test/docs change in the Docs & Evidence, Validation Depth, Governance & Trust,
  or Conversion & CLI Surface lane (`remediation-plan.md` §6 — no authority gate required).
- It's running the validated command set, editing the governing `plans/*.md` file in place,
  or committing per the taskcard's own closeout rules.

### local-repair-loop
Run the Repair Loop (`prompt3-controlled-execution.md` Phase 2) and re-evaluate, no human
needed, if:
- The full validated command set fails and the fix is within this taskcard's own scope.
- Gate G2 independent review finds an issue that's fixable within scope.

### stop-gate-approval-required
Stop and report to Babar Raza if:
- A **Gate G3** action is pending (`git tag`, pushing a tag, publishing to PyPI/any
  registry) without a dated authorization already recorded in `remediation-plan.md` §13.
- A **Gate G6** action is pending (starting implementation on real kernel-protocol execution
  or parameter injection — `LIBIPYNB-P4a-1`/`P4a-2`/`P4b`/`P4c`/`P5a`/`P5b`/`P5c`) without a
  dated sign-off recorded in `full-parity-plan.md` §7.
- Any action in the Execution Security lane would widen (not narrow/gate) the execution
  adapter's default trust, per `remediation-plan.md` §6's Lane Ownership rule.

### stop-governance-conflict
Stop and report to the user if:
- The action would conflict with `remediation-plan.md`'s Gate Contract (§7) or Anti-Overclaim
  Rules (§11), or `full-parity-plan.md`'s extended gates/rules (§4.1/§4.3).
- A non-negotiable constraint from `SECURITY.md` cannot be satisfied.

### stop-push-approval-required
Stop and report to the user if: any git push, PR creation, merge, or other upstream operation
is required — this is a subset of Gate G3 concerns even outside a formal taskcard.

### stop-destructive-action
Stop and report to the user if:
- File deletion beyond files this session itself created as scratch output.
- Force-push, `git reset --hard`, `git clean -f`, branch deletion.
- Removal of tracked files not explicitly scoped by the taskcard.

### stop-credentials-missing
Stop and report to the user if a required credential (e.g. a PyPI token for Gate G3, once
authorized) is not available in this environment.

## Output Format

For each pending action, output:
```
ACTION: [description]
CLASSIFICATION: [autonomous-continue | local-repair-loop | stop-X]
REASON: [brief justification, citing the specific Gate/lane if applicable]
WHO_UNBLOCKS: [null | this session | User | Babar_Raza]
```

## Summary

At the end, provide:
```
AUTONOMOUS_CONTINUE_COUNT: N
LOCAL_REPAIR_COUNT: N
STOP_HUMAN_COUNT: N
NEXT_HUMAN_GATE: [description, or null]
```
