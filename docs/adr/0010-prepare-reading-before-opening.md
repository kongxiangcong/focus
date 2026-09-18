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

Library upload/replan succeeds only once the whole Plan is ready. Open on an
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
