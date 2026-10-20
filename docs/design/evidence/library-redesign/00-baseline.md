# Step 0 baseline

Date: 2026-10-20. Base: `fd1ace6fcdc28eb2c504feacfaf3fa83c8b80bfb`, branch `feat/library-redesign`.

The user authorized sequential implementation and one local commit per step, overriding the prompts' stop/commit restrictions. No push, merge or deployment is authorized. The user subsequently waived screenshots and authorized continuing without the missing `assets/library-redesign` directory. Prototype sources and design specifications are unchanged.

## Environment and checks

- No production FOCUS or Vite process was running before building. Dependencies installed from the frozen lockfile into a temporary pnpm store; no manifest or lockfile changes.
- `pnpm reader:typecheck`: PASS.
- `pnpm reader:build`: PASS, existing >500 kB chunk warning. No `library-directions` files in dist.
- `pnpm reader:test`: FAIL at reader-ui: 82 passed, 4 failed. Three tests hit the existing 5-second timeout (AgentReader attachment retry, Figures unread figures, MistReader cursor navigation); the following Figures test saw leaked sidebar state.
- `pnpm --filter @focus/reader-ui test --maxWorkers=1`: PASS, 86 tests / 11 files, without modifying assertions or timeouts. Parallel execution is resource-sensitive in this executor.
- `tests/confirmed_ux_browser.mjs` and `tests/preparation_dismiss_browser.mjs`: BLOCKED before browser startup. Their Python fixture imports `.agents/skills/focus-read/scripts/focus_read.py`, absent from this checkout and HEAD. No Host/Core/Python files were changed to work around this.
- `tests/upload_dialog_browser.mjs` and prototype browser smoke: BLOCKED by Chromium's local socket permission in the executor. The supported escalation route failed during sandbox setup, before command execution. Browser tests are not claimed passed.
- Screenshots: waived by the user. No visual verification claimed.

## Status/action audit

The existing status calculation treats a Plan with a non-null chunk and zero progress as `ready`, even without a preparation projection. The new vocabulary therefore says “可阅读” while the unchanged primary action says “准备阅读”. Also, a dismissed failed preparation falls back to the source's progress-derived phase, but the existing primary action retains preparation/retry semantics. A candidate with `selected_ready` preserves the selected Plan's reading action even while replacement preparation runs/fails. The implementation will preserve these original action conditions rather than infer readiness or alter Host operations.

Real user data is not available in this isolated checkout; this audit is source/fixture based.
