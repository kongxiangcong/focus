# Paper Companion state machine

Use this reference when resolving a workspace, selecting a paper, issuing a route, evaluating a transition, recovering an interrupted interaction, or determining completion.

## Contents

- [Control principles](#control-principles)
- [Workspace and paper selection](#workspace-and-paper-selection)
- [State dimensions](#state-dimensions)
- [Mastery and evidence](#mastery-and-evidence)
- [Route priority](#route-priority)
- [Lifecycle transitions](#lifecycle-transitions)
- [Routes, locks, and revisions](#routes-locks-and-revisions)
- [Recovery and invalidation](#recovery-and-invalidation)
- [Completion](#completion)

## Control principles

- Treat persisted state as memory. Treat chat as the current interaction only.
- Keep `paper.yaml` as the sole mutable routing snapshot for a paper. Treat event, response, interview, and evidence ledgers as append-only history.
- Let `focus_state.py` validate and apply typed events. An internal Skill proposes semantic judgments; it does not write authoritative state.
- Execute one semantic stage per route. Stop before user input and resume with a new route.
- Prefer artifact reality to a stale phase label. Route a missing or stale required artifact to its owning repair stage.
- Preserve unknown, skipped, provisional, contested, and blocked states. Never manufacture completion.

## Workspace and paper selection

Resolve a workspace in this order:

1. an explicit workspace supplied by the user;
2. the current directory when it is a marked `knowledge-base/`;
3. the nearest ancestor's marked `knowledge-base/`;
4. a non-empty unmarked `knowledge-base/`, after one explicit adoption decision;
5. `$PWD/knowledge-base/`, only for a clear start or claim request.

Never silently adopt a non-empty unmarked directory. A future workspace schema blocks execution. A compatible additive migration must leave a migration record and preserve existing content.

Resolve a paper in this order:

1. an explicit PDF path, paper directory, stable selector, or unique alias;
2. the only unfinished paper;
3. a user choice among unfinished candidates.

Use `last_used_paper` only to order candidates. Identify a source by SHA-256. Reuse an equal hash; preserve equal-title/different-hash sources as separate related versions.

## State dimensions

Use lifecycle phase and execution status as orthogonal fields.

Lifecycle phase:

```text
ingest | guide | read | grill | remediate | complete
```

Execution status:

```text
ready | running | awaiting-user | blocked | complete
```

Use these learning-node states only:

```text
planned | learning | provisional | mastered | needs-remediation | skipped | stale
```

| Node state | Meaning | May unlock downstream learning | Satisfies clean completion |
|---|---|---:|---:|
| `planned` | Not yet taught or diagnosed | No | No |
| `learning` | Instruction or checkpoint is active | No | No |
| `provisional` | Immediate rubric passed without a critical error | Yes | No |
| `mastered` | Transfer or frozen closed-book gate passed | Yes | Yes |
| `needs-remediation` | A material gap or misconception is diagnosed | No | No |
| `skipped` | Learner explicitly declined verification | Only when the plan permits | No |
| `stale` | Its source, dependency, or mastery contract changed | No | No |

Keep self-report, presentation, diagnosis, and answer verdicts in events. They are not competing node states.

Track each remediation target by stable target ID, node ID, diagnosis evidence, and current target status. Project target status onto the node vocabulary: teaching uses `learning`, a sufficient remediation checkpoint uses `provisional`, a failed target uses `needs-remediation`, and a successful targeted grill uses `mastered`. An explicit learner waiver is represented as `skipped`, never mastered.

## Mastery and evidence

Freeze each node's objective, source anchors, required observable points, critical errors, and probe kind before accepting an answer. Bind evidence to the validated paper source, map revision, node ID, resulting node state, and mastery-contract hash.

Use answer verdicts consistently:

| Verdict | Reader consequence | Frozen grill consequence |
|---|---|---|
| `no-evidence` | Keep `learning` and the question pending | `needs-remediation` |
| `misconception` | `needs-remediation` | `needs-remediation` |
| `partial` | Ask the smallest neutral follow-up | `needs-remediation` after the round |
| `sufficient` | `provisional` | `mastered` when the frozen closed-book contract is complete |
| `transfer` | `mastered` | `mastered` |

Allow a prior-knowledge fast path only after at most three unprompted probes covering reconstruction, a nearby distinction or boundary, and transfer. Route a failed probe to the smallest diagnosed prerequisite or current-node gap.

Semantic judgment remains model-produced and auditable. Deterministic code validates the frozen contract, references, allowed transition, critical-error constraint, and aggregation; it does not prove that free text is scientifically correct.

## Route priority

After resolution, validation, and lock acquisition, choose the first applicable branch:

1. Resume a persisted pending interaction with its owner Skill and operation.
2. Stop on a blocker that has no authorized repair.
3. Route absent, stale, or invalid extraction to `paper-ingest`.
4. Route absent, stale, or invalid guide artifacts to `paper-guide`.
5. Route an unconfirmed plan to `paper-guide` confirmation.
6. Route a remediation node in `needs-remediation` or `learning` to `paper-reader` remediation.
7. Route a remediated `provisional` node selected for reassessment to `paper-grill` targeted mode.
8. Route the next ready required or selected optional node to `paper-reader`.
9. Route all taught-but-unmastered required coverage to `paper-grill` full mode.
10. For an explicit profile request, inspect the current deterministic projection; run authorized recovery only when validation reports that the projection is missing or invalid.
11. Return the completion outcome computed by the final grill diagnosis.

Select ready nodes whose hard dependencies are `provisional` or `mastered`, plus explicitly permitted skips. Order a ready frontier by the plan's `(order, id)`. A provisional dependency permits learning continuity but remains subject to the final grill.

## Lifecycle transitions

| Current state | Guard | Route or event | Result |
|---|---|---|---|
| No paper | Readable new input | `paper-ingest` | `guide/ready` after validated ingest |
| `ingest/ready` or invalid extraction | Input identity is valid | `paper-ingest` | `guide/ready` or `ingest/blocked` |
| `guide/ready` | Ingest gate passes | `paper-guide` generation | `guide/awaiting-user` |
| `guide/awaiting-user` | Plan decision persisted | `paper-guide` confirmation | `read/ready` or revised `guide/awaiting-user` |
| `read/ready` | A ready node exists | `paper-reader` | `read/awaiting-user` or `read/ready` |
| `read/awaiting-user` | Pending checkpoint exists | `paper-reader` resume | Node verdict and recomputed frontier |
| `read/ready` | All selected nodes are taught | `paper-grill` full | `grill/awaiting-user` |
| `grill/awaiting-user` | Frozen questions remain | `paper-grill` resume | Next question or whole-round diagnosis |
| Completed grill | Material gaps exist | `grill-diagnosed` | `remediate/ready` |
| `remediate/ready` | A node needs teaching | `paper-reader` remediation | `provisional` or still `needs-remediation` |
| `remediate/ready` | A remediated node is provisional | `paper-grill` targeted | `mastered` or `needs-remediation` |
| Eligible terminal state | Final diagnosis computes completion | `grill-diagnosed` | `complete/complete` |
| Any `blocked` | Exact repair is authorized | Owning Skill in repair mode | Revalidate before normal routing |

## Routes, locks, and revisions

Treat a route as a stale-work guard, not as a security credential. Require it to bind:

- one workspace and, when known, one paper or input hash;
- one target Skill and one route mode from `normal`, `confirmation`, `resume`, `remediation`, `targeted`, `diagnostic`, or `repair`;
- stage-specific context such as the selected node, target, question, reason, or operation;
- one expected paper revision;
- explicitly allowed helpers;
- `issued`, `consumed`, or `cancelled` status.

Do not expire a route by wall-clock time. Consume it once. Any relevant revision change invalidates an outstanding route. A route never spans a wait for user input: commit `awaiting-user`, consume the route, and release the lock before presenting the question.

Acquire a per-paper or pre-ingest input-hash lock only for inspection and mutation. Re-read state after acquisition. Check the expected revision on commit. Release on every exit. Clear a suspected stale lock only through explicit `repair-lock` after proving that no live operation owns it.

## Recovery and invalidation

Before asking for user input, persist the interaction owner, operation, prompt ID, current node or question, plan or assessment revision, and artifact reference. Build the next session from this bounded handoff rather than chat history.

Require event IDs to be unique and commits to be payload-idempotent. Commit learner responses, evidence, paper state, and the profile projection as one recoverable transaction, then validate every reference. On an interrupted commit, replay the same event ID with the identical payload or fail closed; never create a second semantic event to guess the outcome.

When a source hash changes, let the router block the paper and preserve the prior immutable source version. When a plan or mastery contract changes, increment its revision and mark affected evidence and nodes `stale`; preserve unaffected node evidence by stable ID and contract hash. Never rewrite historical answers or assessments.

## Completion

Use state outcome `complete` only when every required node is `mastered`, the frozen paper-level pass rule succeeds, no critical misconception remains, and all evidence references validate. Present it to the learner as mastered completion.

Use state outcome `completed_with_gaps` only after an explicit learner decision to stop with one or more required nodes `skipped`, `stale`, `provisional`, or otherwise unmastered. Present it as completion with gaps, list those gaps, and preserve them in the profile. A paused or blocked paper is not complete.
