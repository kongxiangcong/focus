---
status: accepted
---

# Confirmed reading operations and work visibility

The confirmed 2026-09-30 UX specification supersedes ADR 0008, 0010 and 0015 where they describe historical Continue, from-start rereading, or the location of reader notes. The original confirmed spec is retained in `docs/requirements/FOCUS_User_Experience_Fix_Spec_Confirmed.md`.

- Continue from a historical Chunk browses the next already read Chunk without changing the Cursor or producing another progress entry. At the persistent frontier it advances exactly once. A completed Source remains completed during review and its final Continue is disabled.
- Fresh sessions persist a blank display while retaining old discussion events, notes, progress, and the persistent frontier. Temporary review never determines the next fresh-session Chunk.
- Reset Source Reading is explicitly confirmed and works on any Source without selecting it. It uses a durable forward-recovery journal, clears discussion/summary/note recovery and progress request copies, resets the selected Plan to its first Chunk with reading_started=false, and fences stale writes. Other assets and Sources remain intact. Existing internal clear-only calls remain distinct; the standalone Reset submits resetReading=true.
- Source/Plan/Bundle/reading-pass scope is required for progress enrichment. Missing provenance cannot be inferred from a repeated Chunk ordinal. Question drafts retain their original receipt.
- Every displayed reading occurrence has an event identity. Cached content is reused without simulated streaming. Messages follow their actual SSE deltas, and manual scrolling suspends automatic follow.
- Settings use explicit Save/Cancel. Connection Check never applies configuration. Appearance and backend failures are reported independently. Backend saves are blocked while a task is using the runtime.
- A shared work projection presents ingestion, preparation, blog, discussion/approval and progress tasks on all routes. Cancellation targets one business attempt. Terminal success is not active work, disconnected clients retain an unknown connection state, and recoverable failures remain available.
- Topic/material reading selectors are independent of library filtering. Notes, progress and discussion history occupy a hideable right sidebar, with a narrow-screen drawer. Metadata and membership are drafts committed by one recoverable operation.
- Upload grants freeze both optional Topic association and the generate-blog choice. Parse-only completes without a blog invocation. Default upload preserves the parse-plus-blog workflow.
