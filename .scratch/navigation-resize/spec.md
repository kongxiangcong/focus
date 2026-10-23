# Workspace navigation resize
Goal: drag the expanded left workspace navigation's right edge to resize it live.
Route: editorial-ui Integrate + preserve, small; only workspace navigation. Other sidebars unchanged.
Authority: user selection of sidebar 3; docs/design/README.md, CDS, reading-controls-update; numerical ownership focus-tokens.css.
Surface: WorkspaceApp desktop, collapsed, narrow top navigation, reading fullscreen; light/dark and keyboard.
Contracts: default 288px, collapsed 56px unchanged; desktop min 240px/max 420px and leave at least 480px for main content. Below existing 760px breakpoint keep top layout and hide handle. Container shrink clamps effective width, widening restores desired width. Width kept in component memory across routes/collapse; refresh returns default, no new storage.
Interaction: light 8px handle, col-resize, 3px drag threshold; pointer capture, up commits, cancel/lost capture/Escape rollback; keyboard arrows 16px, Home/End bounds, Enter/double click reset. No animation on direct drag, no selection blocking outside drag.
Reference: PR26 d763732, WorkspaceApp.tsx/standalone.css. No external assets.
Acceptance: unit lifecycle/bounds checks, typecheck/build, actual Chromium drag/keyboard/cancel/collapse/mobile/theme/fullscreen. No open decisions.
