# Reading dock polish: validation record

Date: 2026-10-20. Branch: `feat/reader-dock-polish`, based on
`feat/library-redesign` at `8a0ce09d6eee3005c47cfadfbf7a2fae1812235b`.

## Scope and user amendment

Implements local issues 01–05 under `.scratch/reader-dock-polish/` and ADR 0028.
The user subsequently stated: “不需要截图，移除截图需求”. Before/after screenshots
are therefore not deliverables. No screenshots were produced or represented as
reviewed. The amendment does **not** waive browser behavior, geometry, keyboard,
console or appearance-regression checks. Local ignored issue files retain the
status history and implementation comments; they are not force-added to Git.

No push, pull request, merge or deployment is part of this task.

## Implementation decisions and review

- Workspace control exclusions use `:where(:not(.focus-reader *))`, preserving
  specificity and leaving entry/login, workspace-primary and intentional reader
  palette branches unchanged. Static review found reader-owned labels, hover /
  focus feedback and explicit borders on metadata, group ask and image dialogs.
  Actual light/dark and density legibility is not verified by this environment.
- Dock tokens explicitly cover comfortable density, narrow layouts and coarse
  pointers. Specific send selectors override generic narrow/coarse minimum sizes;
  location badges clear their desktop max-width when occupying the ≤720px row.
  Focused ghost controls keep pill corners.
- The decorative draft dot is positioned within the disclosure's existing right
  inset instead of occupying flex width. This intentionally refines the issue's
  sample CSS so the dot does not move the right-aligned disclosure on collapse.
- The single disclosure retains its DOM identity. Existing `hold()`, collapsed
  focus on the disclosure and expanded focus on the textarea are untouched.
- Static CSS review confirms the intended 52/56px single-row calculation,
  36/40/44px send dimensions, grid-spanning reference and bottom-aligned actions.
  These calculations are not a substitute for browser measurements.
- A pre-existing collapse wrapper uses `overflow:hidden` for animation; its outer
  composer shadow/focus-within halo may be clipped at wrapper edges. The send
  focus outline fits inside its 6/7px inset. No unrelated animation/layout rewrite
  was introduced; browser visual verification remains outstanding.

## Checks

- `pnpm reader:typecheck`: passed.
- `pnpm reader:build`: passed; existing bundle-size advisory remains.
- `pnpm reader:test`: **failed** at reader-ui: 85/88 passed, three 5-second
  timeouts. The timed-out cases were ArticleStructure's structure-to-body test,
  Figures' unread-figure/drawer test, and MistReader's navigation/review test.
  No assertion failures were reported. Similar timeouts were observed before
  this dock implementation; the repository's timeout configuration was not changed.
- `pnpm reader:test --maxWorkers=1 --testTimeout=15000`: **passed**, reader-ui
  88/88 and standalone 150/150 (238 total). The exact default command above is
  still not a passing result; the serial/longer-budget run is recorded separately.
- `rg -n "发送 ↑" ui tests`: no matches.
- `git diff --check`: passed.
- `rg -n "Chin" docs/design/FOCUS_UI_CDS2_DESIGN_SPEC.md`: only explicit historical
  reference/source descriptions remain.

Targeted tests additionally cover decorative icon accessibility, fullscreen text,
inline composer/hint structure, IME/229/Shift+Enter protection, the persistent
disclosure node, draft retention, focus restoration, collapsed attributes, and
expanded/collapsed function-row text sequences. Conversation appearance is covered
by the existing FocusReader tests in the passing reader-ui run.

The following scripts parse successfully with `node --check`:
`reading_motion`, `reading_scroll`, `reading_discussion`, `reading_attachment`,
`reading_lens`, and `confirmed_ux` (all under `tests/*_browser.mjs`).

`reading_motion_browser.mjs` now asserts 52±1px composer height, 26px corner radius,
send/textarea center alignment and ordering, zero function-row ghost borders,
and unchanged disclosure left position through collapse/expand with a draft.
All six scripts capture JavaScript page errors and console errors. Existing
captures are optional with `FOCUS_BROWSER_CAPTURE=0`, matching the user's waiver.

## Browser execution blocker (not a pass)

Playwright is installed and resolves successfully; `/usr/bin/chromium` exists.
A normal headless `chromium.launch({ executablePath: '/usr/bin/chromium' })`
failed before page creation with SIGABRT and:

```
FATAL:chrome/browser/process_singleton_posix.cc:297
Check failed: . socket() failed: Operation not permitted (1)
```

The launch also emitted a crashpad database diagnostic. The decisive failure is
an environment socket restriction, not a missing npm package. No security setting
was changed and no restriction bypass was attempted. Because the shared browser
launch prerequisite fails, the six functional scripts and new geometry assertions
have **not executed successfully**. No claim of a clean browser console, live
keyboard traversal, density/theme visual review or passing browser acceptance is
made. Repeated launches under the same restriction are not a useful retry.

In a permitted browser environment, start the reader with its appropriate test
host/fixture, configure `FOCUS_PLAYWRIGHT_MODULE`, `FOCUS_CHROMIUM_EXECUTABLE`,
`FOCUS_BROWSER_PORT` and a writable `FOCUS_BROWSER_OUTPUT`, then run each of the
six scripts with `FOCUS_BROWSER_CAPTURE=0`. Browser acceptance remains open until
those runs, including the new geometry checks, pass.
