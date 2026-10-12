---
status: accepted
---

# Open Mist reading materials from the left and keep composer controls inline

2026-10-10: The reader requested the shared image/notes entry to remain on the
left of the functional controls, but the materials pane must open from that same
left edge, not the far-right side. The conversation composer and its collapse
control also occupy a single horizontal row.

This supersedes ADR 0019's right-hand split *for standalone Mist appearance
only*. Mist uses one temporary left-side drawer for the full Source gallery,
Notes, Reading Progress and Discussion history. Opening the drawer overlays the
left of the reading flow, above the controls, without permanently narrowing
the reading column or moving the text and composer. Closing it restores the
whole reading canvas; the shared tabs, image selection, source binding, note
drafts and timeline remain unchanged. The drawer is available in normal and
fullscreen reading and on narrow viewports. Escape and an explicit close
control dismiss it.

The existing non-Mist conversation appearance retains ADR 0019's resizable
text/figure split. Mist does not show a now-irrelevant column resizer. The
composer collapse/expand button sits immediately beside the composer, keeps
any draft intact, and stays accessible when the composer is collapsed. The
new session/continue controls and the left image/notes entry remain in the
functional controls row.

Fullscreen hides the surrounding workspace chrome and replaces its two-row
grid with one full-height row. Its floating exit control stays below the
materials drawer so it cannot cover the drawer close button on narrow screens. It uses the same
single-column reader grid and first-row materials overlay as normal reading;
it must not reintroduce side-space columns or span the drawer across the action
and composer rows. The drawer leaves the reading stream's width and scroll
position intact in both modes.

## 2026-10-12 compact reading controls

The reader's latest request supersedes the collapsed composer placement above.
The expanded composer keeps its inline right-hand Collapse control. Collapsing
hides the entire composer row, including the draft-reference row, and moves
Expand Conversation into the functional controls after New Session. Draft text
and its Source/Chunk reference remain intact. Active task controls, errors and
draft recovery remain accessible independently of the collapsed composer.

Mist's Article Structure entry and current reading location now also live in
the functional controls, before Continue, rather than in a sticky row above
the body. The location shows the ordinal/total followed by the structure path
in a light gray bordered box with bold text. Narrow screens wrap controls and
the location without horizontal overflow. The structure introduction, review
semantics and non-Mist reader placement remain unchanged.
