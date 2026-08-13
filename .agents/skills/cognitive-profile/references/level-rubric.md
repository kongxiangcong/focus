# Cognitive Level Rubric

Use this rubric to review evidence metadata embedded in `answer-recorded` or `grill-diagnosed`. Let the shared deterministic state engine append that evidence inside the parent transaction and materialize the profile.

## Track mastery state

Use only these node states:

```text
planned | learning | provisional | verified-now | retained | needs-remediation | skipped | stale
```

Treat a sufficient immediate checkpoint as `provisional`. Move a node to `verified-now` only when a frozen closed-book response or an unprompted transfer demonstrates the precommitted rubric. Move it to `retained` only after an independent closed-book reconstruction in a different persisted session at least seven full days later. Self-report changes no node state. Legacy `mastered` evidence projects as `verified-now`.

## Evidence candidate contract

Each candidate embedded in the parent event must identify:

- evidence type, conservative level candidate, dimensions, confidence, and concise rubric statement;
- optional event ID, concept ID, and verdict only when they match the routed node and parent verdict;
- an optional earlier same-concept event in `supersedes`, only when this new observed parent event is an authorized correction.

The state engine supplies schema, paper and node identity, `node_state_after`, source-artifact reference, contract hash, map revision, and recorded time. Use the learner answer being persisted by the same parent transaction as the source. Keep the answer itself in its response or interview ledger rather than duplicating it in profile evidence. Do not create a standalone evidence or supersession event; that workflow is deferred.

## Verdicts and level candidates

| Level | Observable learner performance |
|---|---|
| 0 | No usable observed evidence, or a fundamental misconception |
| 1 | Recognizes the term and gives a sound basic definition |
| 2 | Explains its purpose and a coarse causal relationship |
| 3 | Explains the mechanism, key assumption, and at least one tradeoff |
| 4 | Transfers the model to a new situation, compares alternatives, or makes an evidence-based criticism |

Apply these gates:

- Treat self-report as evidence of confidence or intent, never as a level or node-state upgrade.
- Treat one answer as a `level_candidate`; durable node mastery remains a separate state-machine judgment.
- Require at least one verified mechanism answer before materializing Level 3 as a UI summary; do not call it durable capability.
- Require transfer or cross-context evidence with the mechanism dimension before proposing Level 4. The same response may demonstrate the Level 3 foundation; a separate earlier Level 3 event is not required.
- Use `misconception`, `partial`, `sufficient`, and `transfer` consistently with the persisted reader or grill rubric.
- Lower confidence or propose `contested` when newer observed evidence conflicts with the current materialized view.
- Mark long-unused capability `stale` only through explicit evidence or policy; retain its historical evidence.

## Rebuild invariants

- Read only the current workspace's `cognitive-profile/evidence.jsonl`.
- Validate event schema, unique IDs, source references, concept identity, and supersession links before replacing the profile.
- Preserve the ledger byte-for-byte during rebuild.
- Exclude superseded evidence from the active view while retaining its history.
- Derive output only from ledger contents; wall-clock time and chat context must not change the result.
- Produce the same profile for the same valid ledger.
- Keep the previous valid profile when validation or rebuild fails.

Materialize each concept with its level, profile status, confidence, evidence references, paper references, and last observed time. Level is a UI projection and must not drive routing. A profile backed only by self-report or skipped evidence remains unverified; consult evidence and node state separately for `provisional`, `verified-now`, and `retained`.
