# Validation

Baseline PR26 open at d76373232036a7845abb96eaf6f62760f17d0194; working tree initially clean.

- Standalone: `pnpm --filter @focus/standalone test --maxWorkers=1`: 13 files / 171 tests PASS (includes new bounds, keyboard, collapse and shrink tests).
- `pnpm reader:typecheck`: three TypeScript projects PASS.
- `pnpm reader:build`: PASS; existing >500 kB bundle warning remains.
- `tests/navigation_resize_browser.mjs`: Chromium 154.0.8037.57, actual WorkspaceApp with FixtureReaderHost. PASS: 3px threshold; actual mouse drag and min/max; pointer release/cancel/lost capture/Escape rollback; arrow/Home/End/Enter and focus; 800px container clamp and widening restoration; collapse 56px and reopening; light/dark; reduced motion; 390×844 top navigation without overflow; reading fullscreen; route retention and refresh default. Zero pageerrors. Wide viewport 1440×1000. Wide and narrow screenshots inspected internally.
- Browser command uses FOCUS_BROWSER_PORT=5174, FOCUS_PLAYWRIGHT_MODULE=/opt/codex/cua_node/lib/node_modules/playwright, FOCUS_CHROMIUM_EXECUTABLE=/usr/bin/chromium. Initial attempt used 5173 and timed out waiting for the handle: Vite had selected 5174 due port contention. Rerun against reported server port passed without relaxed assertions. A direct Vite launch attempt used the wrong package-local path and failed before serving; existing server was reused.
- `git diff --check`: PASS.

Scope: only left workspace navigation; reading drawers and annotation rails unchanged. Width remains component memory, not localStorage; existing collapse preference continues unchanged. Refresh returns 288px, adjusted to available bounds. Direct drag has no width animation; only handle disables touch scrolling, and selection is suppressed only while actively dragging.

Not run: physical touch/IME, screen reader, Safari/Firefox, embedded iframe interaction, full backend suite, separate reader-ui suite (no reader logic changed), 200% zoom/forced colors. No real user library or model calls; fixture data only. No merge/deploy.
