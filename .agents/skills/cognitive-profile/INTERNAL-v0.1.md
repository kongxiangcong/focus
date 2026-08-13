---
name: cognitive-profile
description: Inspect append-only paper-learning evidence and deterministically rebuild the workspace-local cognitive profile. Use only when $ask-paper requests profile inspection or recovery, or when a routed paper-reader or paper-grill stage uses it as a read-only evidence-schema helper; evidence is appended only by canonical parent commits.
---

# Cognitive Profile

Treat `cognitive-profile/evidence.jsonl` as authority and `profile.yaml` as its disposable deterministic projection. Keep semantic evidence creation inside the routed learning transaction that observed the learner.

## Gate the invocation

1. Resolve `../ask-paper/scripts/focus_state.py` relative to this skill directory.
2. For a reader or grill helper call, run `inspect` and `verify-route --helper` before the parent commit. Require the same workspace, paper, and expected revision, and require `cognitive-profile` in `allowed_helpers`.
3. As a helper, validate the proposed evidence metadata read-only. Let the parent `answer-recorded` or `grill-diagnosed` commit append the response-linked evidence, advance paper state, rebuild the profile, consume the route, and release the lock atomically.
4. For an explicit profile inspection, require an existing workspace and remain read-only.
5. Run `rebuild-profile` only when `$ask-paper` explicitly requests recovery of the derived profile after `validate` succeeds. A rebuild changes no evidence, node state, phase, or route.
6. Reject every cross-workspace, stale-route, unreferenced-answer, or unauthorized request.

Never discover, initialize, or merge workspaces. Never infer capability from chat history or create a second mutation after a parent route is consumed.

## Use the shared CLI

- Use `inspect`, `verify-route --helper`, and `validate` for routed evidence review.
- Use `rebuild-profile` only to fold the existing valid ledger into `profile.yaml`.
- Let `$ask-paper` own `resolve`, `next`, `migrate-paper`, `repair-lock`, and profile-recovery authorization.
- Never call `commit` or `cancel-route` as a profile helper. Never append or supersede evidence independently.

## Review evidence metadata

1. Read [references/level-rubric.md](references/level-rubric.md) completely.
2. Accept a candidate only inside `answer-recorded` or `grill-diagnosed`, after its verbatim learner response is available for the same atomic transaction.
3. Require `evidence_type`, `level_candidate`, `dimensions`, `confidence`, and `rubric`. If a candidate supplies `event_id`, `concept_id`, `verdict`, or `supersedes`, require it to match the routed observation. Let the state engine bind paper and node identity, `node_state_after`, response reference, contract hash, map revision, schema, and recorded time.
4. Treat `self-reported` and `node-skipped` as paper-reader-owned canonical events. Treat contradictions as new observed answer or grill evidence. Let `guide-installed` invalidate changed node contracts.
5. Allow `supersedes` only as metadata on a future observed canonical parent event that the state engine accepts. Standalone evidence correction or supersession is outside v0.1; report it as deferred instead of inventing an event type.

Review is complete when the candidate is either safe for the parent transaction or rejected with one exact contract error. It creates no artifact by itself.

## Inspect or rebuild the profile

Report the derived profile status, level, confidence, evidence references, paper references, and last observation. Use only these profile-status terms:

```text
verified | contested | stale | skipped | self-reported | unverified
```

When the user asks about a specific paper, also inspect `paper.yaml.reading.node_states` and report its separate node state. Do not confuse profile status `verified` with node state `mastered`.

For recovery, validate every evidence row and source reference, run `rebuild-profile`, then validate again. Preserve the ledger byte-for-byte and keep the previous valid profile when folding fails. The same valid ledger must produce the same profile regardless of chat context or wall-clock time.
