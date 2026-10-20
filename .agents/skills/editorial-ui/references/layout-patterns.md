# Layout patterns

## Select a content model

**Reader:** reading is the main task. Maintain continuous document flow, line length, section position, and text selection. Controls belong beside the current content or in a compact toolbar. An explanation is an auxiliary layer, not an instruction to replace the article or advance its cursor. A modal/sheet may be used for the demo; an existing product can use a nonmodal companion region when it preserves reading space and focus semantics.

**Explorer:** selection links a spatial/process overview to a detail region. The graph may be vertical, horizontal, or a canvas according to complexity. Do not force arbitrary graphs into the bundled four-stage list. The demo's selectable ordered process is an accessible starting pattern, not an automatic DAG layout engine. Selected state, arrows and detail titles should agree. Provide text-equivalent topology if drawing edges on canvas/SVG.

**Report:** lead with a concise conclusion or question, then the evidence and controls. Filters must change rows and derived summary numbers. Keep units and status meaning stable. A detail dialog is appropriate for supplementary evidence; essential comparisons stay on the main page. Never use a data table solely for visual layout.

## Space adaptation

Let components react to their container, not only the global viewport. Reduce secondary text or group optional actions before dropping the main action. Maintain accessible names after visible labels are shortened. On narrow screens stack exploration and detail regions in reading order or open details on demand. Do not squeeze two panels below their minimum useful widths.

Avoid nested scroll regions unless there is a clear independent task (stream/log, table, source viewer). Mark and name keyboard-scrollable regions. Preserve selected item, draft, and progress when crossing breakpoints. Avoid replacing DOM in a way that destroys focus.

If a layout changes while an interaction is active, cancel or settle it deliberately. A splitter that becomes hidden must release pointer capture and clear overlays. Test `pointercancel`, lost capture, and resize during drag.

## Integration discipline

Inspect current screenshots, styles and component ownership before modifying an application. Do not transplant `.topbar`, `button`, or `body` global styles from a starter. Scope tokens and selectors, reuse theme providers, and do not fork the app's modal stack.

For FOCUS-like readers: preserve the existing theme rather than assuming it needs this bundle's warm palette. Ordinary questions do not advance reading state. Continuing reading is a separate explicit command. Fullscreen and non-fullscreen share the same auxiliary-panel behavior, and existing history/session handling stays authoritative.

## Layout invariants for validation

The primary content is visible without dismissing onboarding. Major actions remain reachable with keyboard and on a narrow screen. A open auxiliary layer does not silently delete or replace the main content. No unintentional page-level horizontal overflow. 200% zoom and large text remain usable; explicitly identify any intentionally scrolling graph/table. Do not fade historical reading text below useful contrast.
