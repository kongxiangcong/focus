---
status: accepted
---

# Use ghost reading controls and an inline pill composer

2026-10-20: The reader approved the reading-dock polish specification, replacing
only the Mist dock presentation. This does not redesign reading behavior.

## Decision

- Function-row actions use decorative inline line icons and borderless ghost
  controls with pill hover surfaces. Continue is the only solid primary action
  in that row. The current location is a borderless light-gray pill with a
  medium-weight path. Existing action order and accessible names are preserved,
  except Send changes from the old arrow-suffixed label to `发送`.
- The composer is Editor (including inline send/stop) + Notices. A single-line
  editor is a 52px / 56px pill, with 26px / 28px corners in compact / comfortable
  density. Send/stop is an inline circular icon button. Multiline text grows
  naturally with CSS field sizing, up to 170px, with send aligned to the bottom.
  Browsers without field sizing retain a single-line scrollable editor.
- The former Chin and visible keyboard hint are removed. Enter/Shift+Enter
  instructions remain available through an accessible textarea description.
- Collapse/Ask is one permanently mounted disclosure in the function row, after
  fullscreen and before stop/continue, with a CSS separator and decorative arrow.
  It supersedes ADR 0023's **2026-10-12 compact reading controls** placement rule:
  no separate collapse control sits to the right of the editor and no second
  expand node replaces it. Collapsed drafts use a non-text decorative dot.
- Workspace global control selectors exclude the `.focus-reader` subtree using
  zero-specificity `:where(...)`; reader-owned CSS defines its control baseline.
- Geometry lives in `focus-tokens.css`; no icon dependency or alternate palette
  is introduced. Touch action/send targets are 44px. Reduced motion disables
  disclosure-arrow transitions.

## Preserved semantics

Drafts and Source/Chunk references, reading-position hold, Enter/Shift+Enter and
IME protection, operation identity, running-task stop, and visible notices while
collapsed are unchanged. Collapsing focuses the persistent disclosure; expanding
focuses the textarea, preserving the existing `toggleComposer()` contract.
Conversation appearance continues to render the shared DOM without a redesign.
Drawer/dialog/media layouts and business state are outside this decision.

## Validation

See [the implementation validation record](../design/reading-dock-polish-validation.md).
The user explicitly removed screenshot requirements on 2026-10-20. Functional,
geometry, accessibility and regression checks remain required; environment-blocked
browser checks must be reported as unverified, not as passing.
