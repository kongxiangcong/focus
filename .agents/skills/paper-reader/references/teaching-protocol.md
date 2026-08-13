# Teaching Protocol

Use this protocol for normal units, resumed checkpoints, and remediation targets. Make the learning process observable: an explanation prepares evidence; only the learner's persisted response can satisfy an exit criterion.

## Use node states

Use only these node states:

```text
planned | learning | provisional | verified-now | retained | needs-remediation | skipped | stale
```

Move a routed node from `planned` to `learning` when instruction begins. A sufficient immediate checkpoint earns `provisional`. Award `verified-now` only from unprompted transfer or a frozen closed-book assessment. Teaching never awards `retained`; that requires a different session at least seven days later.

## Establish the unit boundary

- Use the unit or remediation target selected by the route. Do not choose a later unit for convenience.
- Confirm that every dependency is `mastered`, `provisional`, or explicitly `skipped` where the plan permits it, and that the plan revision matches the paper state.
- Resolve every cited anchor through `ingest/source-map.yaml`. Distinguish author claims, reported evidence, and guide inference.
- Use the workspace explanation language. Keep quotations short and in the configured quote language.

## Teach an unstarted unit

1. Activate the prerequisite model with the unit's `entry_check` when it is useful.
2. Frame the question the unit answers.
3. Cite the minimum source anchors needed to ground the explanation.
4. Explain the mechanism as a causal trace, including the governing assumption and at least one tradeoff or boundary when the plan requires them.
5. Ask one checkpoint that directly tests the declared exit criteria.
6. Persist the waiting state before presenting the checkpoint, then stop for the learner's answer.

Create a unit artifact with this compact shape:

```markdown
# <unit id> — <title>

## Learning goal
<observable objective>

## Source anchors
- <stable anchor>

## Mental model
<causal model rather than paragraph-by-paragraph translation>

## Mechanism trace
1. <cause or transformation>
2. <effect or preserved information>

## Checkpoint
<one question>

## Exit criteria
- <observable criterion>
```

Keep generated teaching material separate from `notes/`. Have the canonical `answer-recorded` commit append learner responses to `reading/responses.jsonl`; never overwrite the unit artifact with later answers.

## Evaluate a pending checkpoint

Record the answer verbatim before judging it. Evaluate every required exit criterion and assign one verdict:

| Verdict | Observable meaning | State consequence |
|---|---|---|
| `no-evidence` | No relevant learner answer is present | Keep the node `learning` and the checkpoint pending |
| `misconception` | The answer contradicts a critical mechanism, assumption, or boundary | Mark the node `needs-remediation` |
| `partial` | Some required points are present and at least one is missing | Ask the smallest neutral follow-up |
| `sufficient` | Every required point is supported and no critical error remains | Mark the node `provisional` |
| `transfer` | The sufficient model is applied unprompted to a new situation | Mark the node `verified-now` and emit verification evidence |

An explanation given by the agent is not learner evidence. The profile rubric still determines the durable capability level represented by a node event.

## Interpret learner controls

| Learner intent | Action |
|---|---|
| Continue | Advance only when no answer is pending; otherwise restate the checkpoint |
| Why | Explain the current causal link and retain the current unit |
| Understood | Commit `self-reported` without changing the node state |
| Skip | Commit `node-skipped`; preserve the unmastered gap for diagnosis |
| Review | Summarize the current model and open questions without changing state |
| Status | Return control to `$ask-paper` for the authoritative progress view |

## Run remediation

- Work only on a routed node in `needs-remediation`; move it to `learning` while reteaching the smallest diagnosed gap.
- Teach the smallest diagnosed gap and trace it to the original answer and concept or claim.
- Ask a focused checkpoint that tests the missing mechanism or boundary without disclosing a future re-grill answer.
- Move the node to `provisional` after sufficient immediate evidence. Move it directly to `verified-now` only after genuine unprompted transfer; otherwise leave immediate closure to `paper-assess`.
- Preserve explicit skips as `skipped` and unmastered.
