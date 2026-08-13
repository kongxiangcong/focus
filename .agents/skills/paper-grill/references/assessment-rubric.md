# Assessment Rubric

Use a frozen rubric to separate measurement from teaching. Generate questions from the confirmed plan, claim map, and source map; never add a question merely to fill a template category.

## Enforce the mastery gate

Use only these node states:

```text
planned | learning | provisional | verified-now | retained | needs-remediation | skipped | stale
```

In Mastery mode, assess every required `provisional` node before immediate verification. A passing frozen response moves it to `verified-now`. Only a later-session assessment at least seven days afterward may move it to `retained`.

## Freeze the round

Before asking the first question, persist an assessment revision containing:

- round ID, mode, plan revision, and source hash;
- covered concept and claim IDs;
- ordered questions and permitted branches;
- source anchors for each question;
- expected points and critical misconception indicators;
- required versus optional status;
- follow-up limits, pass rules, and remediation rules.

Treat the frozen revision as immutable after the first answer. Record any later correction as a new revision or audit event rather than rewriting history.

## Select coverage

Cover the dimensions supported by the paper:

1. Motivation
2. Problem formulation and exclusions
3. Core mechanism
4. Figure or dataflow reconstruction
5. Formula or model assumptions and boundaries
6. Evidence-to-claim support
7. Tradeoffs, constraints, and degradation cases
8. Criticism, comparison, or transfer

Include formula questions only when the source and claim maps identify a material formula or model. Preserve skipped required units as visible unverified coverage.

## Conduct the interview

Follow this loop:

```text
question -> verbatim answer -> optional neutral clarification or recorded follow-up -> next question
```

- Ask one question at a time.
- Clarify wording without revealing an expected point or solution path.
- Record every answer before interpreting it.
- Keep later answers separate from earlier answers; never backfill demonstrated knowledge.
- Release the route and lock before waiting for each answer.
- Reveal corrections only after every required question in the round is complete.

## Judge evidence

Judge each question against its frozen expected points:

| Verdict | Meaning | Node consequence in a frozen round |
|---|---|---|
| `no-evidence` | The answer does not address the required concept | `needs-remediation` |
| `misconception` | A critical mechanism, assumption, or boundary is wrong | `needs-remediation` |
| `partial` | Some expected points are demonstrated and others are absent | `needs-remediation` |
| `sufficient` | Required points are demonstrated closed-book with no critical error | `verified-now` |
| `transfer` | A sufficient model is applied correctly beyond the rehearsed case | `verified-now` |

Apply the frozen pass rule per concept and claim, not only as a total score. A core-mechanism misconception prevents paper completion regardless of aggregate performance.

## Diagnose the completed round

For every assessed concept or claim, record:

- verdict;
- stable answer evidence references;
- demonstrated and missing expected points;
- misconception, if present;
- affected claim, unit, or downstream inference;
- remediation target, when needed.

Identify each remediation target by its stable node ID, concept or claim reference, and diagnosis evidence. Move it to `needs-remediation`. Keep explicit learner skips visible as `skipped` and unmastered.

## Run targeted re-grill

- Include only nodes selected by the route after remediation; require current `provisional` evidence or an explicitly authorized reassessment.
- Test the diagnosed gap directly, preferably with a fresh example or boundary case.
- Freeze and preserve the targeted question set exactly like a full round.
- Mark a node `verified-now` only on `sufficient` closed-book or `transfer` evidence. Mark `retained` only when the delayed gate also passes.
- Return a failed node to `needs-remediation`; route it back to `$paper-reader` for another remediation cycle.
- Report immediate Mastery completion only when every required node is `verified-now` or `retained`. Report retained mastery only when every required node is `retained`.
