# Step 7: regression, evidence and documentation

Date: 2026-10-20. Source implementation through Step 6 is `69b792f` on `feat/library-redesign`; this final step adds tests/docs and a narrow regression fix for Escape from the shared Library header. Each completed step has an authorized local commit. No push, merge, deployment, production-service restart or private-data inspection occurs.

## Changes

- `tests/library_browser.mjs`: an isolated HTTP-mock browser suite, independent of the missing Python fixture. It uses the real standalone HTTP adapter's request/response shapes and mutable synthetic Source/Topic lists. It verifies row/inspector keyboard focus, menu-first/header Escape, zero mutations for inspection, exactly one reorder per drop with local preview and rollback/retry, Alt moves, filter/search/card guards, five empty states and recovery, 1440/1024/390 × light/dark geometry/roles, mobile background inert and 40px width/height targets, both reduced-motion preferences during an actual reorder, progress transition removal, and panel reversal from a genuine intermediate opacity. It writes JSON measurements only after browser execution; no synthetic result file is claimed as a measured result.
- `LibraryPage.tsx` and `library-accessibility.test.tsx`: final review found the shared header was outside LibraryPage's bubbling subtree. A document-level Escape handler keeps menu-first/inspector-second priority, restores the correct trigger, and ignores composing/229 and native dialogs. Three new cases cover header search/Topic selector and exclusions; the targeted accessibility suite is 8/8 (`step7-header-escape.log`). This does not change Host operations or business state.
- ADR 0027 accepts direction A and explicitly supersedes CDS §5.2's inline disclosure. `focus-cds-ui.md` links the new Library implementation and evidence while identifying its old Library screenshot as historical. The acceptance matrix distinguishes unit/static evidence from blocked browser checks.

## Baseline and final commands

Logs are in `/tmp/focus-library-redesign/logs/`. The baseline checkout is `fd1ace6fcdc28eb2c504feacfaf3fa83c8b80bfb`. The pre-change standalone supplemental run is 84 PASS / 6 FAIL out of 90, as recorded in `01-status-model.md`; 104/104 belongs to Step 2 after 14 state tests were added, not the original baseline.

| Command | Baseline | Final Step 7 | Evidence |
| --- | --- | --- | --- |
| `pnpm reader:typecheck` | PASS | PASS | `step7-typecheck-final.log` |
| `pnpm reader:test` | reader-ui 82 PASS / 4 FAIL, stops before standalone | reader-ui 84 PASS / 2 FAIL, stops before standalone | `step7-test.log` |
| `pnpm --filter @focus/reader-ui test --maxWorkers=1` | 86/86 PASS | 86/86 PASS | `step7-reader-ui.log` |
| `pnpm --filter @focus/standalone test --maxWorkers=1 --testTimeout=20000` | pre-change supplemental 84 PASS / 6 FAIL, 90 total (original 5s budget); Step 2 104/104 with 20s budget | 150/150 PASS, 10 files; +60 cases against the original baseline | `step7-standalone.log` |
| `pnpm reader:build` | PASS; existing large-chunk warning | PASS; same large-chunk advisory | `step7-build.log` |
| `node --check tests/*_browser.mjs` (each file separately) | no new suite | 15/15 syntax PASS | Includes new library suite; syntax is not browser execution |
| Browser suites / fixture launchers | required Library suites already blocked | 15 JavaScript suites and 5 Python launchers BLOCKED, no browser assertions executed | `browser-inventory.json` |

Default-command failures are the unchanged Figures unread-figure/side-space and MistReader unread-navigation cases exceeding 5000ms. No reader-ui implementation or assertions changed. Serial execution passes all 86 without increasing its timeout. Standalone's CLI-only 20s runtime budget remains the same supplemental budget used during implementation; it is not presented as a successful default `pnpm reader:test`.

The first Step 7 sequential process was intentionally interrupted during serial reader-ui so the header Escape regression fix could land before the full standalone run. The settled sequence reran typecheck and serial reader-ui, then standalone and build. Interrupted runs are not counted as pass/fail test outcomes. Earlier step-specific test locator/mock synchronization corrections are documented in steps 4–6 and the acceptance record; original behavior assertions remain.

## Browser execution prerequisites and honest outcomes

The complete inventory is [browser-inventory.json](browser-inventory.json), with an entry for every `tests/*_browser.mjs` and every `tests/*_browser.py` launcher. All 15 JavaScript files pass `node --check`, then fail before opening a page because Chromium cannot create its process-singleton socket (`Operation not permitted`). This includes the new HTTP-mock suite and upload test, which do not require a Python Host.

`confirmed_ux_browser.py` and `reading_structure_browser.py` fail earlier while importing the absent `.agents/skills/focus-read/scripts/focus_read.py`. That file is also absent from the starting HEAD. `backend_setup_browser.py`, `status_clear_browser.py` and `workspace_binding_browser.py` can create their own isolated fixtures, but then encounter the same Chromium launch failure. No Host/Core/Python source was changed.

A first invocation selected Playwright's CommonJS entry for all scripts; dynamic-import scripts consequently had an undefined `chromium` export. The invocation was corrected to `index.mjs` for `await import` scripts and `index.js` for `createRequire` scripts. Python launchers received the same correct module environment. These setup errors were not treated as product regressions; the final recorded blocker for every JS suite is Chromium's socket restriction. No identical denied sandbox escalation was retried and no restricted filesystem path was accessed.

To execute the new suite in a permitted isolated environment: run a standalone Vite/preview server with synthetic HTTP responses only, set `FOCUS_TEST_URL` to that loopback URL, set `FOCUS_PLAYWRIGHT_MODULE` to its ESM module entry and `FOCUS_CHROMIUM_EXECUTABLE` if needed, then run `node tests/library_browser.mjs`. The default URL is `http://127.0.0.1:5281`; this is a suggested isolated endpoint, not a claim that a preview is currently running. Do not target or restart a production FOCUS instance. It reports measured results to `/tmp/focus-library-redesign/browser/library-results.json` only after a browser can launch. Existing real-Host suites must also satisfy their own fixture prerequisites.

## Scope and unverified work

Scope inspection against the starting baseline covers production standalone UI, the two geometric token additions, tests and documentation only. ReaderHost contracts, Host/Core/Python, dependencies/lockfile, design specifications and prototypes remain unchanged. `git diff --check` passes. The final production dist has no `library-directions` paths or matching prototype references. The token diff adds only `--reader-inspector:400px` and `--reader-library-content:1080px`.

Screenshots were waived. Browser geometry, real mid-frame reversals, real native drag-and-drop/file drop, touch, assistive technology, true IME, forced colors, non-Chromium engines and real private/runtime data remain unverified. Unit/mock results do not close those gaps. The known preserved status/action discrepancy for a Plan without a preparation projection remains unchanged rather than guessing readiness.
