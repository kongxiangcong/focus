---
status: accepted
---

# Adopt the current-session diffusion prototype as the formal Reader UI direction

Visual revision, 2026-08-31: the user selected the retained Lightfield **雾光 / Mist** prototype as the formal default. Its floating reading card, vertical dashed progress rail, and desktop companion panel replace the initial layout and collapsed-marginalia choice below. All five prototypes remain retained for later skin integration. This updates presentation only; the authority and acceptance boundaries in this ADR and ADR 0004 remain in force. See the [current UI specification](../design/focus-reader-ui-spec.md).

The Focus Reader skeleton now has a selected visual direction. The accepted evidence is the current-session prototype captured in commit `5dae3de`, not an older Variant D implementation. The repository contains no A/B/C implementation, prototype switcher, or variant URL that must survive formalization.

The Reader Module will use one continuous Reading Chunk stream, a Reading Cursor-anchored diffusion field, distance-derived historical depth, a short settling/entering Continue Reading handoff, and current-chunk marginalia. Phrase-level emphasis is rejected. Exact visual tokens and motion values remain revisable under the formal UI specification.

ADR 0004 remains in force. `FocusReader({ host })` is the public Interface; host Adapters remain outside `reader-ui`; Focus Core remains authoritative for the Reading Cursor. Temporary transition state is presentation state between host-returned `ReadingWindow` projections and is neither persisted nor accepted as a second Cursor authority.

The Fixture Adapter remains a development and test Adapter. Formal UI completion does not imply Live-host verification, Workspace integration, deployed-environment acceptance, or production completion.
