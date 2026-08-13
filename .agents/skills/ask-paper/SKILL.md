---
name: ask-paper
description: Route persistent, evidence-gated paper learning from one user-facing entry. Use when the user wants to claim or read a paper, continue a prior learning session, inspect the knowledge tree or cognitive progress, answer a checkpoint, start or resume a paper defense, remediate a misconception, or review learned concepts in a project-local Paper Companion workspace.
---

# Ask Paper v0.2

Act as the sole user entry to FOCUS. Choose the cheapest reading mode that can satisfy the user's intent, restore persisted state, and delegate one semantic action while keeping control-plane details invisible.

## Choose the reading mode

Use one of three modes and persist it with the paper:

- `scout` — default for a newly discovered paper. Produce source identity, overview, key author claims, relevance to the current question, limitations, and a frontier decision. Do not create a knowledge DAG, cognitive profile evidence, checkpoints, or a defense.
- `study` — use when the user asks to learn, understand, compare, critique, or use the paper in research. Build only the key mechanism map, source anchors, a small number of integrative checkpoints, and a paper-level critique. Stop at `provisional` or `verified-now`; do not require every supporting node to pass a defense.
- `mastery` — use only when the user explicitly asks to master, defend, reproduce, teach, or retain a core paper. Enable the full dependency plan, frozen assessment, remediation, cognitive evidence, and delayed retrieval.

Upgrade modes without discarding earlier artifacts. Never downgrade or delete evidence automatically. If the intent is ambiguous, start in `scout`; do not ask the user to choose a mode before the paper has been screened.

## Load the control contract

Before a stateful operation, read:

- [references/state-machine.md](references/state-machine.md) for routing, mastery, and recovery rules;
- [references/artifact-contracts.md](references/artifact-contracts.md) for authoritative files and typed events.

Resolve `scripts/focus_state.py` relative to this skill directory. Treat it as one deep state interface. Use it to inspect, compute one next action, and commit the result; route files, helper authorization, locks, revisions, transactions, and recovery records are implementation details and must never be passed between semantic modules or shown to the learner.

```text
resolve | inspect | next | verify-route
commit --route-id <id> --event <json-or-yaml>
cancel-route | migrate-paper | validate | rebuild-profile | repair-lock
```

Use `resolve`, `inspect`, and `validate` for discovery and diagnosis. Use `next` to compute the action and `commit` for mutations. Never rewrite manifests, locks, revisions, node states, JSONL ledgers, or the profile directly. Existing route-oriented command fields are private compatibility data for the current kernel, not part of the v0.2 workflow interface.

## Resolve the request

1. Classify the user's intent as start or claim, continue or answer, status, plan decision, defense, remediation, review, diagnostic, or repair.
2. Resolve the workspace in the order defined by the state-machine reference. Initialize a workspace only when the user clearly asks to start or claim learning material. A missing workspace during `continue`, `status`, or `review` is a result to report, not permission to create one.
3. Resolve the paper from an explicit path, paper selector, or unique unfinished candidate. When selection is ambiguous, show concise titles and ask for one choice. Treat recency as ordering only.
4. Inspect the paper before routing. Run a compatible additive migration when the state service declares it safe. Stop on a future schema, changed source hash, unresolved blocker, invalid artifact, revision conflict, or active lock.
5. When the user asks only for status or review, remain read-only except for automatic recovery of a disposable projection. If `profile.yaml` is missing or invalid while the evidence ledger is valid, preserve the old file, rebuild automatically, and continue. If rebuilding fails, show evidence-derived status directly and report the projection warning; never block learning or ask the user to authorize projection recovery.

Resolution is complete when one workspace and, when required, one paper are unambiguous and validated, or one exact blocker or choice has been presented.

## Delegate one semantic action

For stateful progression, run `next` against the resolved state and translate the kernel's private target into one of three semantic modules:

- `paper-map` — source claim, extraction quality, Scout output, key claims, or a Study/Mastery map;
- `paper-study` — one Study/Mastery learning unit, integrative checkpoint, critique, or remediation;
- `paper-assess` — immediate closed-book verification, delayed retrieval, diagnosis, profile projection, or evidence inspection.

The semantic module may use the private target returned by the current kernel, but must not expose it as another Skill contract. Cognitive projection is part of `paper-assess`, not a fourth lifecycle module. Evidence creation remains in the commit that observed the learner.

Pass the module a bounded action packet: workspace, paper or input, reading mode, operation, expected state, and relevant artifact references. Do not pass helper capabilities or require the module to manage a route lifecycle. Evidence append, profile materialization, validation, and lock release are hidden commit effects, not additional stages.

If a pending interaction exists, resume its owner before considering a new unit. Persisted state outranks conversational guesses. A reply such as “继续” does not answer a pending checkpoint.

After the module returns, inspect and validate the result. Let a failed action retain its diagnostics and report the precise recoverable blocker.

Delegation is complete when the action is committed or abandoned, no lock spans user waiting, and the workspace validates or exposes one exact repair.

## Apply the evidence boundary

Treat an explanation as preparation, not evidence. Treat “懂了” as self-report only.

- An immediate, rubric-complete checkpoint can make a node `provisional`.
- `provisional` may unlock downstream learning but cannot satisfy final completion.
- Unprompted transfer or a frozen same-session closed-book demonstration with no critical error can make a node `verified-now`.
- Only an independent closed-book reconstruction in a later session, at least seven days after `verified-now`, can make a node `retained`.
- A fast path for prior knowledge still requires unprompted reconstruction, discrimination or boundary testing, and transfer.
- `skipped`, `stale`, and `needs-remediation` remain visible gaps.
- Treat the legacy state `mastered` as `verified-now` during migration; never silently promote it to `retained`.
- Treat state outcome `completed_with_gaps` as completion with unverified required coverage; never describe it as retained mastery.

Let the state service enforce transitions and recompute the next frontier. Do not award mastery from agent-authored explanations, answer hints, confidence, familiarity, or chat history.

## Handle diagnostics and repair

Keep explicit diagnostics read-only. Show the mismatched artifact, pending interaction, blocker, or lock owner without exposing credentials or copying unrelated user content.

For repair:

1. Diagnose with `inspect` and `validate`.
2. After validation exposes a supported repairable state, run `next` and accept only the repair action it derives. If the state kernel cannot derive it, report that exact capability blocker instead of inventing authority.
3. Use `migrate-paper` only for a declared compatible migration.
4. Use `repair-lock` only after proving that no live execution owns the exact lock.
5. Revalidate and confirm the state command's repair audit record.

Preserve source copies, notes, learner answers, assessment history, and evidence. Return a destructive or ambiguous repair decision to the user.

## Present the learning interface

Lead with the learning outcome, not the machinery. Show only:

1. **Goal** — the current learning target;
2. **Progress** — a compact knowledge-tree view distinguishing retained, verified-now, provisional, active, and gap nodes;
3. **Why now** — why this node or interaction is next;
4. **One action** — one explanation, choice, checkpoint, defense question, or repair decision.

Hide workspace IDs, paper IDs, hashes, route IDs, revisions, lock files, schemas, and command output unless the user asks for diagnostics. Never expose internal phase names as instructions the learner must operate.

End every normal response with exactly one pending learner action or a clear terminal outcome. A terminal outcome must distinguish verified-now completion, retained mastery, completion with gaps, paused work, and blocked work.
