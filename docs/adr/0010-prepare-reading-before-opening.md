---
status: accepted
---

# Prepare all reading chunks before opening

The 2026-09-18 user request supersedes the planning-only and destructive reread
behavior in ADR 0008/0009 and the per-current-chunk translation path in ADR 0006.
All sources still receive a source-anchored Reading Plan. Preparation then fills
only missing translations. Chinese papers and articles use source text directly;
translation stays null. Optional Chunk language (zh/en/mixed) lets mixed sources
mark Chinese chunks independently. Old plans inherit Parser Bundle language.

Core exposes preparation status and explicit Source/Plan/Chunk reads and writes.
These operations never move Cursor or mark reading started. Readiness is derived
from chunks and records; Host task progress is temporary. Each completed translation
is saved separately. A retry resumes missing chunks, preserves Notes and rejects
writes to a no-longer-selected Plan. Existing translations are not overwritten.

Library replan succeeds only once the whole Plan is ready. Ingestion publishes
the Source without creating a Plan; a later Open action on an
unfinished plan resumes preparation, then starts reading after verification. Open
on a ready plan and explicit Continue run through Core, without an Agent. Continue
retains receipt checking, request deduplication and serialized writes. Topic
Continue checks its source plans before advancing across a source boundary.
Questions still invoke the Agent with the source/translation reference; reading
navigation is no longer a user/assistant exchange in the conversation.

The reader defaults to saved Chinese translations, with an optional original toggle.
Missing foreign translations show a preparation message, not a flash of source text.
Chinese source content is displayed directly. Formula/image/source anchors remain.

From-start reading resets only the selected chunk of the same Plan and preserves
translations and Notes. Replan detaches the old selection and creates a new Plan;
old Plans, translations and Notes remain. It does not clear notes or reparse.
New Plans are translated afresh; no unsafe reuse by chunk ordinal across plans.
Preparation is sequential through the existing single-owner task; parallel jobs
and automatic semantic translation-quality guarantees are out of scope.

On 2026-09-25, Stage 4 grill Q1–Q8 retained the full-Plan readiness gate:
the reader accepts initialization latency to avoid translation waits after reading
starts. Explicit entry authorizes planning and preparation without a separate Plan
confirmation. Only the selected Source is prepared, including in Topic Reading;
this qualifies the Topic-wide preparation behavior in the existing Host. Translation
uses whole-source context and a Plan Glossary, followed by cross-Chunk consistency
checks before opening. These are quality acceptance requirements, not a guarantee
of semantic correctness. The original-text toggle remains available on the reading
card; there is no original-only path that bypasses preparation. This supersedes
the v0.2 plan's proposed current-Chunk-only translation direction. This records a
target decision, not implementation evidence.

Stage 4 Q9–Q13 qualify the earlier fill-only and detach-before-replan rules.
Initialization may repair affected translations with bounded consistency checks;
delivered translations must not change silently. A replacement Plan is prepared
before switching the reading selection, preserving the old Plan and position on
failure or cancellation. Committed progress survives interruptions; closing the
browser does not cancel, while cancellation or Host restart requires explicit
resume and cancelled attempts cannot commit late results. Model or method changes
do not automatically invalidate ready artifacts; changed Bundles retain old assets
as history, and terminology changes require explicit preparation of affected text.
Repeated Continue requests from one position advance once, never queue multiple
jumps. These refinements protect both reader flow and already usable assets.

Stage 4 Q14–Q16 further separate readiness from navigation: preparation completion
only shows a bottom-right ready notification. Opening the prepared Source, including
a replacement Plan, requires a manual user action and never steals the current
selection. The last Chunk offers an explicit finish-this-Source action; the completion
page has reread and history/Notes access, but no start-next-Source button. Reopening
a completed Source preserves its completed state. Q17–Q18 make left-progress
navigation read-only: it changes the displayed Chunk, never the Reading Cursor or
completion state. Before completion only already-read Chunks are available; unread
Chunks cannot be previewed through this control. After completion all Chunks are
available. Questions may target the viewed Chunk, but reading cannot continue from
that historical position.
