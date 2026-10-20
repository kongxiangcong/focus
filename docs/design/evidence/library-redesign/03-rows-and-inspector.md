# Step 3: source rows, cards, inspector and menu

The default Source Library view is now a compact list; a saved `focus.libraryView` preference still wins. Source rows and optional cards share the step-1 state vocabulary and primary-action guards. Titles open one LibraryPage-local inspector; double-click invokes the existing primary action, and invalid sources only open their problem details. Arrow keys move among visible rows, with the inspector following an open selection. Escape closes a menu before the inspector and restores the corresponding trigger/title focus. Focus lookup supports Source IDs containing spaces, Unicode and quotes.

`SourceInspector` retains preparation notices, candidate activation, dismissed-failure retry, Topic navigation and the existing source-management dialog, all Blog Output controls, source metadata/resources and confirmed reset/delete actions. Opening missing blog state uses the existing `refreshBlog`; list rendering adds no request or polling. Root `expandedSources`/`toggleDetails` were removed. Existing Host calls, confirmations, request IDs and locks are unchanged.

`standalone.css` uses the existing tokens for the new static layout, with a 1040px content-container breakpoint reserving inspector width on the right. Smaller containers overlay the inspector and move focus into it. Closed inspectors are unmounted. Full mobile modal behavior, motion and other step-6 refinements remain out of this step. Existing global progress and Inbox-link styles are preserved, so these changes do not restyle task/reader surfaces.

## Checks

All logs below are under `/tmp/focus-library-redesign/logs/`.

- `pnpm reader:typecheck`: PASS (`3-typecheck-final.log`).
- `pnpm reader:build`: PASS, existing bundle-size warning (`3-build.log`).
- `pnpm reader:test`: 85 reader-ui tests passed, 1 existing 5000ms timeout failed in `MistReader.test.tsx` (unread navigation/advance/review). Recursive execution stops before standalone, as in the baseline (`3-test.log`).
- Migrated standalone suite, before adding new interaction cases: 104/104 PASS in 6 files with `--maxWorkers=1 --testTimeout=20000` (`3-standalone.log`).
- Four added interaction cases: 4 PASS / 57 skipped (`3-interactions-retry.log`). Initial failures in two new tests were setup refresh races; awaiting initial source load before replacing mocks fixed the setup, without weakening assertions.
- Final standalone suite including all new cases: 107 PASS / 1 FAIL, 108 total in 6 files (`3-standalone-final.log`). The failure is the unchanged terminal-status `old failure` hidden-dialog assertion already recorded in the step-1 baseline. All four new interaction cases passed in this full run.
- Focused unchanged terminal-status rerun: 1 PASS / 60 skipped (`3-terminal-retry.log`). No assertion or production task logic was changed.
- Production dist contains no `library-directions` content; `git diff --check` passes.
- Both migrated browser scripts pass `node --check`. The fixture retry (`FOCUS_BROWSER_PORT=18765 PYTHONUTF8=1 python tests/confirmed_ux_browser.py`) remains blocked by missing `.agents/skills/focus-read/scripts/focus_read.py` (`3-browser-fixture.log`), so confirmed/preparation browser execution and geometry are not claimed as passed.
- Screenshots were explicitly waived; no screenshot comparison is claimed. Original design screenshot assets remain unavailable as documented at baseline.

The test changes migrate detail actions into the inspector, preserve original behavioral assertions, scope duplicated actions, and add focus restoration, visible-row navigation, menu-priority/outside handling, quoted-ID focus, lazy blog fetch and invalid-source inspection coverage. Prototypes, specs, contracts, Host/Core/Python and other pages are unchanged.
