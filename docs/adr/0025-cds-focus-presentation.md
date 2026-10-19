---
status: accepted
---

# Adopt CDS 2.0 inspired FOCUS presentation

The explicit 2026-10-18 redesign authorization, together with the supplied
[FOCUS UI CDS 2.0 design specification](../design/FOCUS_UI_CDS2_DESIGN_SPEC.md), replaces the Mist
palette, translucency, closed reading cards, control geometry and navigation composition described
in ADR 0005/0008, the visual portions of ADR 0018, and the Mist appearance and 160ms drawer motion
named in ADR 0023. It does not supersede their business operations or ADR 0004 host boundary.
ADR 0023 left overlay, single-row composer collapse, action-row location and fullscreen behavior
remain binding; only their material and motion change.

## Decision

Use the local open-claude-ui reference as read-only evidence for surfaces, geometry and motion, and
implement the FOCUS adaptation described in the specification §4–§12. Do not adopt Claude business
concepts, model switching, attachments, subscriptions or multi-agent surfaces. FOCUS keeps its
brand, data, ReaderHost and recovery semantics.

One product-owned token file (`ui/packages/reader-ui/src/focus-tokens.css`) is the only numeric
authority for colour, geometry, type, elevation and motion. Light/dark/system and
compact/comfortable are required and are independent of backend configuration. Existing reading
font, size, brightness, library-view and draft storage keys stay readable; new preferences are
additive.

## Structure

The workbench uses one collapsible sidebar (288px expanded, 56px collapsed) that carries routes and
Topics. Reading renders a continuous document on the canvas with the function row above the
composer; the duplicate progress rail is removed and its paragraph list is reachable from the
location control. Materials remain a left overlay with four content types and never reflow the
text column. The composer keeps the Editor / Notices / Chin composition and its existing draft,
request-identity and recovery behavior.

No new package or dependency boundary is introduced; no reference code, font or asset is imported
at runtime. The appended `focus-workbench.css` override layer is removed and its intent lives in the
owning stylesheets.

See [the implementation and evidence record](../design/focus-cds-ui.md); tracker in
`.scratch/focus-ui-refactor/`.

## Partial supersession (2026-10-20)

[ADR 0026](0026-reading-lens-on-demand-figures.md) supersedes automatic figure opening/selection, defines making room as translation without changing text width (overlay when space is insufficient), and updates Reading Lens, local attachment preferences, colour and motion. The original decision above is retained for history; other business semantics remain binding.
