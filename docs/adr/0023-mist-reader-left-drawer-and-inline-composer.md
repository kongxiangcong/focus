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
