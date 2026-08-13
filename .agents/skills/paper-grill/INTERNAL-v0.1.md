---
name: paper-grill
description: "Run, resume, or target a closed-book paper defense with a frozen source-anchored rubric, verbatim answers, diagnosis, and remediation targets. Use only when ask-paper supplies a valid route authorizing paper-grill for an existing workspace and paper; permit explicit read-only diagnostics, and return every repair request to ask-paper for authorization."
---

# Paper Grill

Run a closed-book evidence round. Keep the rubric frozen, the answers verbatim, and correction separate from questioning.

## Gate the invocation

1. Resolve `../ask-paper/scripts/focus_state.py` relative to this skill directory.
2. Run its `inspect` command and then `verify-route`. Require an issued route that targets `paper-grill` and binds the requested workspace, paper, mode, stage context, and expected revision.
3. For a direct diagnostic request, require an explicitly named existing workspace and remain read-only. Send any required write or repair back through `$ask-paper`.
4. Reject every other missing, consumed, stale, mismatched, or unauthorized route before generating or recording assessment content.

Never discover or initialize a workspace, select a paper, clear a lock, or reopen a completed paper.

## Use the shared CLI

- Use `inspect` and `verify-route` before generating, resuming, or scoring a round.
- Read `../ask-paper/references/artifact-contracts.md` before constructing an event; use its declared event type and fields.
- Submit every question-set, answer, diagnosis, node-state, or evidence mutation with `commit --route-id <id> --event <json-or-yaml>`.
- Run `validate` after a successful commit. Use `cancel-route` when abandoning an issued route before commit.
- Let `$ask-paper` own `resolve`, `next`, `migrate-paper`, and `repair-lock`. Never repair a lock from this stage.
- Let `grill-diagnosed` append evidence and rebuild the profile in the same transaction. Use `cognitive-profile` only as a read-only evidence-schema helper before that commit.

## Run the routed round

1. Inspect the paper state, confirmed plan revision, claim map, source map, completed or skipped units, frozen questions, current question, and remediation targets. Stop on any source, revision, artifact, or blocker mismatch.
2. Read [references/assessment-rubric.md](references/assessment-rubric.md) completely and follow the authorized branch:
   - Freeze a new full-round rubric before asking the first normal question.
   - Record the pending answer and continue the same frozen round in resume mode.
   - Freeze a focused rubric for only the nodes selected by the route after remediation, normally nodes with current `provisional` evidence.
   - For a requested repair, remain read-only and return the exact required change to `$ask-paper`; grill events do not authorize repair mode.
3. Ask one question per user interaction. Use `grill-started` to freeze a full or targeted question set and persist the first prompt before displaying it; `commit` consumes the route and releases the lock.
4. On resume, use `grill-answer-recorded` to append the learner's verbatim answer and persist the next frozen prompt when one remains. Use only neutral clarification or a recorded follow-up. Hold corrections and expected points until the round is complete.
5. After every required question is answered, use `grill-diagnosed` to commit the whole-round diagnosis, per-node verdicts, evidence candidates, missing points, misconceptions, affected claims, remediation targets, and computed outcome. The same transaction appends evidence and rebuilds the profile.

Use `focus_state.py` for every mutation, route decision, lock operation, evidence append, and derived-profile fold. Do not edit assessment files, `paper.yaml`, route files, locks, JSONL ledgers, or `profile.yaml` directly. If the shared script cannot commit the operation, fail closed and report the blocker through `$ask-paper`.

## Hand back control

After the round, present the evidence-bound diagnosis and the next user action. Let `$ask-paper` run `next` to route remediation, targeted re-grill, completion, or review.
