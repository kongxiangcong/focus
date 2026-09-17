---
status: accepted
---

# Source Library management and three application entries

The 2026-09-17 user request supersedes ADR 0005's 2026-09-16 single-page
presentation decision. Standalone opens /library, with /reading and /settings.
Reading remains one natural conversation anchored in source text, behind ReaderHost;
these routes are navigation, not new domain contexts or reading modes. Production
Mist uses a progress sidebar, a centered current output with fading history, and a
small collapsible composer. The five Lightfield prototypes remain unchanged.

## One directory authority

Existing ADR 0003 data is already canonical and is used in place, without copying:

```
workspace/
  state.json                         # sole Cursor State
  sources/<source-id>/
    source.yaml                      # identity, title, kind, short name
    parser-bundle/                   # original, content.md, images, metadata, validation
    reading/plans/plan-NNN/
      chunks.jsonl
      glossary.tsv
      records/<chunk-id>.json         # cached translation and Notes
  topics/<topic-id>/topic.yaml        # ordered Source IDs, no copied assets
```

Existing Plans, Records, Topics and Cursor State need no format migration. Missing
current_topic_id in earlier canonical Cursor State is normalized once on mutation.
No speculative conversion of pre-Source-Library layouts is allowed: unsupported
layouts fail visibly and must be migrated using evidence of their actual schema.
This is narrow in-place compatibility, superseding the no-compatibility non-goal
in ADR 0001 only for canonical data; no parallel state model is introduced.

## Library operations

GET /library/topics and /library/sources project files, including Cursor-derived
progress and a Notes count (all saved Notes; no invented time window). Upload accepts
a selected PDF and invokes the existing hosted precision paper-parser automatically
through the Host Agent workflow. Before source registration, the Host run is the
parsing status, not a placeholder Source tree. Every distinct original is registered
in its own sources/<source-id>; identical PDF bytes reuse their existing Source per
ADR 0003. A failed run remains visible and can be retried in the same conversation.
No alternate parser and no browser credentials are introduced.

DELETE removes the entire Source directory and its Cursor entry, and detaches its
ID from Topic manifests. Host reading references to deleted assets are removed;
raw dialogue remains Host-owned. No trash or retained bundle is created.

Reread explicitly clears Notes in every Plan and resets that Source's selected Plan
and Chunk. Fixed old Plan definitions and cached translations remain; the next map
creates a new Plan. The Host starts focus-map then focus-read in a fresh conversation.
This overrides focus-map's reinitialization rule that preserves old Notes. It does
not delete the Parser Bundle, other Sources, Topic membership, or host dialogue.
A planning failure leaves a visible unplanned Source; opening it retries planning.
Only this explicit reread operation resets progress; browsing and questions never do.

Mutations are serialized by the existing single-owner Host and rejected while an
Agent task is running. File operations belong to Core/SourceLibrary, not the UI.
Routes retain Host/Origin checks and authentication. Library interfaces extend
ReaderHost optionally, preserving fixture/DSH adapters. Settings persist appearance
locally and backend selection through the existing Host setting; backend switches
create a fresh conversation without touching reading assets. WorkBuddy remains
unavailable as specified by ADR 0007 until its integration is implemented.
