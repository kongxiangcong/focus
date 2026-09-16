# Formal Focus Reader UI specification

Status: unified reading flow, 2026-09-16. Supersedes the Mist companion panel,
diffusion field, historical text fading and global Space action. ADR 0004 remains in force.

## Presentation

`FocusReader({ host })` is the only formal Reader. Desktop and narrow layouts share
one central scroll region for source excerpts, translations, questions and Codex
answers. A bottom composer aligns with that region. Source/translation toggling is
local presentation state, preserving draft and scroll. Historical text has normal
contrast. Settings contain the large-text option; atmosphere controls are removed.

Header: FOCUS, ellipsized source title (full title in Materials), Materials, loaded
paragraph directory, Settings and New Session. The directory describes only content
projected in this session; review does not change Core's Cursor. A review/reference
sets a cancellable paragraph citation next to the composer. Questions pass that
reference independently of the current Cursor; Continue still captures the actual
Cursor Receipt and remains a separate button. Space retains native scrolling.

Source text, translation and messages use react-markdown, remark-gfm, remark-math
and rehype-katex. Raw HTML is not executed. Tables, code and display math scroll
locally. Source-relative image URLs resolve via the existing authenticated asset
route; inline images are not automatically repeated as figures. No custom Markdown
parser or secondary document model is introduced.

## Session and chronology

The Host stores a session ID, thread ID, conversation and an ordered timeline of
message IDs and Core paragraph references. Paragraph text is always projected from
Core; the timeline is conversation presentation history, never a second Cursor or
Reading Record. Pre-migration sessions cannot reconstruct historical event timing:
their existing loaded paragraphs precede their existing messages once during migration.
New events are recorded in arrival order, including cross-source references.

New Session archives the old Host session and creates a blank one. Source Library,
Plans, Records, Notes and Cursor remain untouched. A fresh page offers Resume Last
Reading, which projects the saved paragraph without advancing. Refresh restores this
fresh session. The next send starts a new Codex thread. During active work, the action
reads Stop and New; Host interrupts and joins the old worker before switching. If it
cannot stop, reset fails visibly without switching state. Old responses are excluded
by monotonic snapshot revision and UI session epochs; uploads also carry an epoch.

## Input and recovery

The draft is always editable, including during generation, upload and errors. Send
and Continue are disabled only during conflicting operations. Successful send clears
only the submitted draft if it has not been edited meanwhile. Transport retries reuse
the captured request ID and input; reconnect only reloads state. A stale Cursor offers
Update Reading Position, not replay of an invalid Continue. Upload failures retain the
file for retry; removal works during upload. Approval failures restore submit controls,
with permission details folded by default. Completed tasks have no success banner.

Scrolling near the bottom follows new text. User scrolling away disables following
and reveals New Content / Back to Bottom. Settings, resize and source toggling do not
recenter the document. Stream content is not an aria-live log; concise task status is.
Native dialogs provide focus containment. Buttons have visible focus and touch-size
targets; mobile uses the same visible composer and safe-area padding.

## Verification

See `docs/FOCUS_Unified_Reader_Acceptance.md` for automated evidence and remaining
browser/runtime acceptance limits. Historical Mist screenshots describe the previous
implementation and are not evidence for this revision. Retained prototypes remain
isolated reference material.
