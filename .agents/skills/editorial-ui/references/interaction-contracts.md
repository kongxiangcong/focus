# Interaction contracts

Each contract describes observable behavior. Passing the bundled examples does not imply an implementation elsewhere satisfies it.

## Inputs, async actions and CJK

Use a real form/label and native textarea unless rich text is necessary. Enter submits; Shift+Enter inserts a line break, unless the product specifies otherwise. During composition, Enter must not submit. Track composition events and `event.isComposing`; legacy keyCode 229 may be an extra compatibility fallback, never the only method.

Snapshot the pending payload without destroying the editable draft. Prevent duplicate submission while pending. Do not reset input on an error or cancelled operation. Clear only the successfully consumed draft; if the user changed it while pending, preserve the newer text. Give Stop, Retry and failure their own real behavior. Appends, rerenders and resizing must not move focus.

DOM-dispatched composition events test handler logic only. Physical Chinese/Japanese/Korean IME sequences, especially browser-specific composition-end ordering, require manual OS/browser checks before calling input behavior fully verified.

## Stream/log follow

Model `FOLLOWING` and `READING_HISTORY`. Near-bottom scrolling or an explicit “latest” action can enter FOLLOWING. User scrolling away enters READING_HISTORY. A time delay alone must never re-enable FOLLOWING. Schedule position updates at most once per frame and re-check state when the callback runs. Detect late content resize but respect the same state. Do not use a one-bit “ignore next scroll” flag that can swallow a later real gesture.

Listen to wheel, touch, scroll and keyboard movement in the scrollable region. A short cooldown can avoid fighting an in-flight gesture, but is only additional protection. An explicit jump may bypass the cooldown. Show that new content exists without flashing the entire transcript. A screen reader should get concise status updates, not each token through a live region.

## Document navigation and geometry restoration

A reader may need three policies: intentional section/event navigation, conversation follow, and geometry restoration. Do not replace all three with a chat bottom-pin hook. Continue/open may reveal an actual event without changing domain state locally; user scroll still takes priority. Images, font loading, density changes and resize are not new navigation events. When reflow changes line wrapping, preserve a stable visible event ID plus relative offset rather than blindly reusing scrollTop.

## Overlays, drawers and fullscreen

An overlay drawer and a resizable split pane are different layouts. Preserve the product's selected behavior, side and auto-open semantics unless separately changed; opening an overlay should not silently turn into a permanent column. Distinguish modal and nonmodal drawers: background focus is isolated only when modal. Preserve editor drafts and selected assets across tabs/close where contracted.

Determine whether fullscreen is a CSS layout state or browser Fullscreen API, then use the correct overlay host/top layer. Escape dismisses the topmost applicable overlay before exiting an underlying fullscreen view. Test nested image/dialog/drawer order. Keep close controls reachable in short and narrow windows and restore focus to a visible opener/fallback.

## Modal dialog

For standalone modern browsers prefer `<dialog>` + `showModal()` so modality/top-layer behavior comes from the browser [S1]. Supply `aria-labelledby` and an actual visible title. Choose an initial focus target; keep Tab inside; support Escape; restore focus to the opener if it still exists. Restore to a sensible fallback if it disappeared. Native Escape close and programmatic close must run the same cleanup.

Close-on-backdrop is optional, not required. For destructive actions default focus to the safe action, and do not close before an asynchronous operation is known to succeed. Abort/cancel policy must be explicit. Do not implement the modal by merely adding `aria-modal=true` to a visually centered div. Use one modal system in an existing app [S2].

## Split panes

Separate `PENDING_POINTER` from `DRAGGING`: a few pixels of movement are required before starting a drag. Snapshot the initial ratio and collapsed state. On start set pointer capture on the actual handle, not a nested event target. Clear state on up/cancel/lost capture; Escape rolls back. Use `touch-action:none` only on the handle. Do not block text selection everywhere outside active drag.

Read bounds from the actual container. Clamp against useful minimum widths. When those widths cannot coexist, switch to stacked layout instead of inventing a ratio. Ensure CSS Grid track minimums cannot override the chosen fraction: use `minmax(0, …)` or an equivalent bounded layout. Preserve the last useful ratio when changing layout.

During iframe-adjacent drag, an intercepting transparent shield needs pointer events, or the iframe itself needs pointer events disabled. A `pointer-events:none` overlay does not intercept hit testing. Pointer capture complements this; do not claim all embedded-content cases are solved without testing.

Keyboard: focusable separator, accessible name and orientation, coherent value range, arrows to adjust, Home/End to limits, and an explicitly labeled reset. Use correct `aria-controls`. Do not add undocumented shortcuts that conflict with browser behavior [S3]. An automatic collapsing splitter is optional and requires explicit restore and collapse-state rollback tests; the starter does not auto-collapse.

## Disclosures, selectors and tabs

Simple hide/show can use `details/summary` or a button with `aria-expanded` and `aria-controls`. Keep focus on the trigger. A set of actual tabs uses roving tabindex, associated panels, selection state and arrow navigation [S4]. Use ordinary buttons with `aria-pressed` for a graph/list selection when it is not tab navigation. Do not apply `role=tab` just for a pill appearance.

## Data interactions

Give each filter a label. Filter, sorting, visible count, summary and export use the same current data view. Distinguish no records from no filter matches. Reset restores filters and stable initial ordering. Detail views retain units and provenance. CSV export escapes delimiters, quotes and spreadsheet-formula prefixes in user-supplied strings. A browser may mediate downloads; do not promise a filesystem save location.

Use text nodes for untrusted content. If HTML/Markdown rendering is truly required, use the project's maintained sanitizer and a documented trust model. Never execute supplied HTML scripts merely to preview them. An iframe sandbox requires a separate origin/capability design, not a blanket “safe” label. Do not put secrets into an offline artifact.

## Sources

[S1] https://developer.mozilla.org/en-US/docs/Web/HTML/Reference/Elements/dialog
[S2] https://www.w3.org/WAI/ARIA/apg/patterns/dialog-modal/
[S3] https://www.w3.org/WAI/ARIA/apg/patterns/windowsplitter/ (the APG pattern itself notes incomplete review)
[S4] https://www.w3.org/WAI/ARIA/apg/patterns/tabs/
