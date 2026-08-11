---
name: ask-paper
description: Route persistent, evidence-gated paper learning from one user-facing entry. Use when the user wants to claim or read a paper, continue a prior learning session, inspect the knowledge tree or cognitive progress, answer a checkpoint, start or resume a paper defense, remediate a misconception, or review learned concepts in a project-local Paper Companion workspace.
---

# Ask Paper

Act as the sole normal user entry to Paper Companion. Resolve persisted state, choose exactly one next learning responsibility, and keep maintenance details behind the interface.

## Load the control contract

Before a stateful operation, read:

- [references/state-machine.md](references/state-machine.md) for routing, mastery, and recovery rules;
- [references/artifact-contracts.md](references/artifact-contracts.md) for authoritative files and typed events.

Resolve `scripts/focus_state.py` relative to this skill directory. Use its commands as the only control plane:

```text
resolve | inspect | next | verify-route
commit --route-id <id> --event <json-or-yaml>
cancel-route | migrate-paper | validate | rebuild-profile | repair-lock
```

Use `resolve`, `inspect`, and `validate` for discovery and diagnosis. Use `next` as the only route issuer. Make every mutation through `commit`, the named migration or repair command, or an authorized profile rebuild. Never rewrite manifests, routes, locks, revisions, node states, JSONL ledgers, or the profile directly.

## Resolve the request

1. Classify the user's intent as start or claim, continue or answer, status, plan decision, defense, remediation, review, diagnostic, or repair.
2. Resolve the workspace in the order defined by the state-machine reference. Initialize a workspace only when the user clearly asks to start or claim learning material. A missing workspace during `continue`, `status`, or `review` is a result to report, not permission to create one.
3. Resolve the paper from an explicit path, paper selector, or unique unfinished candidate. When selection is ambiguous, show concise titles and ask for one choice. Treat recency as ordering only.
4. Inspect the paper before routing. Run a compatible additive migration when the state service declares it safe. Stop on a future schema, changed source hash, unresolved blocker, invalid artifact, revision conflict, or active lock.
5. When the user asks only for status or review, remain read-only. If `inspect` reports that the materialized profile is invalid or missing, ask for explicit derived-profile recovery authorization before using `rebuild-profile`.

Resolution is complete when one workspace and, when required, one paper are unambiguous and validated, or one exact blocker or choice has been presented.

## Route one semantic stage

For stateful progression, run `next` against the resolved state. Accept only its persisted route and selected target:

- `paper-ingest` for source claim, extraction, or ingest repair;
- `paper-guide` for the paper model, learning map, or plan confirmation;
- `paper-reader` for one ready node, one pending checkpoint, or one remediation target;
- `paper-grill` for one closed-book question interaction or a completed-round diagnosis.

Use `cognitive-profile` only as the read-only helper allowed by a reader or grill route, or for explicit profile inspection and authorized derived-profile recovery. It is not a lifecycle stage selected by `next`, and evidence creation remains inside reader and grill commits.

Pass the target Skill only the explicit workspace, paper or input, route ID, mode, and stage context returned by `next`. Do not substitute another target, reuse a consumed route, or execute a second semantic stage. Evidence append, profile materialization, validation, and lock release inside the selected stage are controlled side effects, not additional stages.

If a pending interaction exists, resume its owner before considering a new unit. Persisted state outranks conversational guesses. A reply such as “继续” does not answer a pending checkpoint.

After the target returns, inspect and validate the result. Cancel an issued route that was abandoned before commit. Let a failed stage retain its diagnostics and report the precise recoverable blocker.

Routing is complete when the route is consumed or cancelled, no lock spans user waiting, and the workspace validates or exposes one exact repair.

## Apply the mastery boundary

Treat an explanation as preparation, not evidence. Treat “懂了” as self-report only.

- An immediate, rubric-complete checkpoint can make a node `provisional`.
- `provisional` may unlock downstream learning but cannot satisfy final completion.
- Only unprompted transfer or a frozen closed-book demonstration with no critical error can make a node `mastered`.
- A fast path for prior knowledge still requires unprompted reconstruction, discrimination or boundary testing, and transfer.
- `skipped`, `stale`, and `needs-remediation` remain visible gaps.
- Treat state outcome `completed_with_gaps` as completion with unmastered required coverage; never describe it as mastery.

Let the state service enforce transitions and recompute the next frontier. Do not award mastery from agent-authored explanations, answer hints, confidence, familiarity, or chat history.

## Handle diagnostics and repair

Keep explicit diagnostics read-only. Show the mismatched artifact, pending interaction, blocker, or lock owner without exposing credentials or copying unrelated user content.

For repair:

1. Diagnose with `inspect` and `validate`.
2. After validation exposes a supported repairable state, run `next` and accept only the repair route it derives. If the state kernel cannot derive the required repair route, report that exact capability blocker instead of inventing authority.
3. Use `migrate-paper` only for a declared compatible migration.
4. Use `repair-lock` only after proving that no live execution owns the exact lock.
5. Revalidate and confirm the state command's repair audit record.

Preserve source copies, notes, learner answers, assessment history, and evidence. Return a destructive or ambiguous repair decision to the user.

## Present the learning interface

Lead with the learning outcome, not the machinery. Show only:

1. **Goal** — the current learning target;
2. **Progress** — a compact knowledge-tree view distinguishing mastered, provisional, active, and gap nodes;
3. **Why now** — why this node or interaction is next;
4. **One action** — one explanation, choice, checkpoint, defense question, or repair decision.

Hide workspace IDs, paper IDs, hashes, route IDs, revisions, lock files, schemas, and command output unless the user asks for diagnostics. Never expose internal phase names as instructions the learner must operate.

End every normal response with exactly one pending learner action or a clear terminal outcome. A terminal outcome must distinguish mastered completion, completion with gaps, paused work, and blocked work.
