---
name: paper-assess
description: Run immediate or delayed closed-book paper assessment, diagnose gaps, and rebuild evidence-derived cognitive projections after ask-paper selects it. Internal FOCUS module; normal users enter through ask-paper.
---

# Paper Assess

Own frozen assessment, delayed retrieval, diagnosis, and the disposable cognitive projection. Accept work only from `ask-paper`.

Read [references/assessment-rubric.md](references/assessment-rubric.md) for frozen assessment and [references/cognitive-levels.md](references/cognitive-levels.md) for evidence projection.

## Immediate verification

Freeze questions and rubric before the learner answers. Ask one question per interaction, preserve each answer verbatim, and diagnose only against source-anchored observable points. Passing evidence yields `verified-now`; it does not prove long-term retention.

## Delayed retention

Award `retained` only when all are true:

- the node already has valid `verified-now` evidence;
- the new closed-book reconstruction occurs in a different persisted session;
- at least seven full days have elapsed since that evidence;
- the learner reconstructs the mechanism and boundary or transfer without a critical error.

Otherwise retain the strongest prior state and record why the retention gate did not pass.

## Projection recovery

Treat the append-only evidence ledger as authority and `profile.yaml` as disposable. If the profile is absent or invalid, preserve the old file, rebuild automatically, and continue. If rebuilding fails, show a read-only evidence summary and a projection warning. Never ask the user to authorize this recovery, never modify evidence during rebuild, and never use the profile's UI level for routing.
