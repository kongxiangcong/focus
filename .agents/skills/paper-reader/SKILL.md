---
name: paper-reader
description: "Teach, resume, or remediate exactly one source-anchored paper learning unit and judge its checkpoint evidence. Use only when ask-paper supplies a valid route authorizing paper-reader for an existing workspace and paper; permit explicit read-only diagnostics, and return every repair request to ask-paper for authorization."
---

# Paper Reader

Advance one observable learning action. Treat the routed workspace state, persisted source anchors, and the user's recorded answer as authority.

## Gate the invocation

1. Resolve `../ask-paper/scripts/focus_state.py` relative to this skill directory.
2. For a routed call, run its `inspect` command and then `verify-route`. Require the route to be issued, to target `paper-reader`, and to bind the requested workspace, paper, mode, stage context, and expected revision.
3. For a direct diagnostic request, require an explicitly named existing workspace and remain read-only. Report findings through `$ask-paper` when a write or repair is needed.
4. For any other missing, consumed, stale, mismatched, or unauthorized route, stop stateful work and direct the caller to `$ask-paper`.

Never discover or initialize a workspace, select a different paper, clear a lock, or advance another phase.

## Use the shared CLI

- Use `inspect` and `verify-route` before producing stateful output.
- Read `../ask-paper/references/artifact-contracts.md` before constructing an event; use its declared event type and fields.
- Submit every state, artifact, response, or evidence mutation with `commit --route-id <id> --event <json-or-yaml>`.
- Run `validate` after a successful commit. Use `cancel-route` when abandoning an issued route before commit.
- Let `$ask-paper` own `resolve`, `next`, `migrate-paper`, and `repair-lock`. Never repair a lock from this stage.
- Let an evidence-bearing parent commit append evidence and rebuild the profile in the same transaction. Use `cognitive-profile` only as a read-only evidence-schema helper before that commit.

## Run the routed action

1. Inspect `paper.yaml`, the confirmed reading plan, knowledge map, claim map, source map, and the persisted pending interaction. Stop on a source-hash, revision, artifact, dependency, or blocker mismatch.
2. Read [references/teaching-protocol.md](references/teaching-protocol.md) completely. Follow the branch authorized by the route:
   - Teach the routed ready unit in normal mode.
   - Evaluate the persisted checkpoint in resume mode.
   - Teach only the routed remediation target in remediation mode.
   - For a requested repair, remain read-only and return the exact required change to `$ask-paper`; reader events do not authorize repair mode.
3. Keep the interaction at one observable action: present one teaching step or evaluate one user response. Preserve the current unit when answering a causal question or giving a review.
4. Before asking the user to answer, use `unit-presented` in normal mode or `remediation-presented` in remediation mode. Commit the staged unit artifact, stable prompt ID, routed node or target, and waiting interaction before showing the checkpoint; `commit` consumes the route and releases the lock.
5. When evaluating an answer, use `answer-recorded`. Preserve the answer verbatim and include its rubric verdict, allowed node or target consequence, and evidence candidate. The same commit appends response-linked evidence and rebuilds the profile atomically.

Use `focus_state.py` for every mutation, evidence append, route decision, lock operation, and derived-profile fold. Do not edit `paper.yaml`, route files, locks, JSONL ledgers, or `profile.yaml` directly. If the shared script cannot perform a required mutation, fail closed and return the blocker to `$ask-paper`.

## Hand back control

State what was observed, what remains provisional or unmastered, and the single pending user action. Let `$ask-paper` run `next` and issue the next route; do not issue or reuse one here.
