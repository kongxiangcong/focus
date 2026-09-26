---
status: accepted
---

# Separate explicit Source notes from passive reading progress

Stage 3 grill on 2026-09-25 separates two assets to keep intentional notes useful without interrupting reading: a Reading Note belongs to its Source and is saved only when the user explicitly requests it, while a Reading Progress Entry is recorded when advancing a Chunk or completing the Source. Progress entries retain brief reading and discussion facts and the user's explicitly stated understanding, never a model assessment; failure to generate an entry does not block advancement, and retrying it does not advance again.

Repeated requests to record a concept append notes rather than silently rewriting earlier notes. User edits take priority; each note supports a persistent last recoverable state for undo. Rereading keeps prior progress entries and records a new reading pass; rebuilding a Plan keeps old entries with that Plan while Source notes remain shared. Internal source anchors retain their Bundle version even though Stage 3 normally hides citation material to reduce reading burden.

This supersedes ADR-0001's placement of Reading Notes inside per-Chunk Records and narrowly qualifies ADR-0003's exclusion of history logs: bounded note recovery and compact reading progress are allowed, while host transcripts remain outside Core and Cursor State remains the sole authority for reading position. It rejects automatic note capture after every answer and retaining unaccepted corrections as notes. Old-data conversion remains Stage 5 work; these are accepted target decisions, not an implementation or acceptance claim.
