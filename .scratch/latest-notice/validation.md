# Validation and delivery

Baseline: PR26 open at 0fde3fdac4fd054a58412d80709e462cf7c77b33.

Implementation: one navigation notice, keyed dismissal in memory by workspace/source/session/discussion and frontier plan/chunk; progress change waits for settled view before another review. Reader event scope now also includes workspace and session. Shared scroll notifications publish follow-ref transitions even when notice booleans do not change. No backend writes, storage migration, visual redesign or motion changes.

Return semantics: active answer → existing latest/follow action; trailing old review → actual progress group; otherwise existing latest destination. Closing only hides the notice and restores keyboard focus. Replaced old UI text assertions while retaining draft/frontier/Host assertions.

Commands executed:
- `pnpm --filter @focus/reader-ui test`: 34 files, 205 tests PASS on final product code.
- `pnpm --filter @focus/standalone test --maxWorkers=1`: 12 files, 169 tests PASS.
- `pnpm reader:typecheck`: three projects PASS.
- `pnpm reader:build`: PASS; existing >500 kB chunk warning remains.
- Chromium 154.0.8037.57 via local Playwright/Vite, fixture only. Environment: `FOCUS_BROWSER_PORT=5173`, `FOCUS_PLAYWRIGHT_MODULE=/opt/codex/cua_node/lib/node_modules/playwright`, `FOCUS_CHROMIUM_EXECUTABLE=/usr/bin/chromium`.
- `tests/latest_notice_browser.mjs`: single notice, return geometry including trailing old review, keyboard Enter/Space dismissal and persistent focus target, repeated review suppression, materials/session/source isolation, advancement through Continue then review, refresh memory reset, 1440×1000 and 390×844/CSS fullscreen.
- `tests/discussion_fold_browser.mjs`: PASS, independent groups/storage/stream-stop/scroll/keyboard/theme/density/reduced-motion/fullscreen.
- `tests/reading_annotations_browser.mjs`: A1–A10/A12–A14/A17 regression; final result recorded below.

Development failures were not hidden: old banner/back-label assertions failed until updated for the approved replacement; browser exposed focus fallback selecting an earlier textarea and advancement gating behavior (the fixture now advances through actual Continue rather than injecting a snapshot without that action). One annotation run hit duplicate createRoot console warning while Vite hot-reloaded the edited product; rerun uses unchanged final product files and keeps the zero-console-error assertion.

Limits: no real model or user-library mutation, Python backend suite, physical IME/touch, screen reader, Firefox/Safari, 200% zoom or forced-colors run. Existing annotation tests cover synthetic IME only. This is not a new durable preference: refresh/remount resets dismissal by design.

Final unchanged-code browser rerun: latest_notice_browser PASS (zero page errors); reading_annotations_browser PASS all 14 scenarios including zero console/page/HTTP errors. Final build PASS (see /tmp/latest-build-final2.log for actual command output).
