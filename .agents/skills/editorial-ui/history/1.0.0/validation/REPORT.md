# Release validation · editorial-ui 1.0.0

Validation date: 2026-10-16. This report concerns the authored bundle, not the upstream React library.

## Results

| Check | Result | Evidence / scope |
|---|---|---|
| Deterministic build | PASS | Five generated files reproduce canonical sources |
| Bundle profile and references | PASS | Custom limited-profile validator; not official Agent Skills certification |
| Named opaque token contrast pairs | PASS | 22 pairs across light/dark; not every possible composite |
| Python unit regressions | PASS | 44 tests; `unit-tests.txt` |
| Chromium rendering and behavior assertions | PASS | 126 assertions, 0 failures; `browser-results.json` |
| External requests observed during exercised paths | PASS | Zero observed; offline contexts and HTTP(S) route blocking |
| Uncaught JavaScript page errors | PASS | Zero observed on exercised paths |
| Direct file URL opening | NOT_RUN | Navigation blocked by managed browser: `ERR_BLOCKED_BY_ADMINISTRATOR`; see `file-url-attempt.json` |
| Skill loading in Codex / Claude Code / Cursor | NOT_RUN | Metadata/install locations checked against docs; no runtime installation test |
| Agent generation-quality evaluations | NOT_RUN | Task prompts supplied in `references/evaluation-tasks.md` |
| Native OS IME / screen reader / real touch / iframe | NOT_RUN | Synthetic composition and pointer event checks are narrower |
| Safari / Firefox / 200% browser zoom | NOT_RUN | Not covered by this release |

## Environment and method

Browser: Chromium 144.0.7559.96. Python 3.13.5.
The managed browser refused local file navigation. No browser policy was changed or bypassed. The same standalone HTML bytes were loaded into fresh pages via Playwright `set_content` (`--transport inline`) with `offline=True` and HTTP(S) requests denied. This validates the HTML's rendering and tested interactions without network, but not a `file://` origin in this environment.

Static analysis found no automatic external or sibling-file dependencies in any of the three starter HTML files. They are authored as self-contained documents; direct-open behavior should still be verified in the user's local target browser.

Executed browser command:
```bash
python scripts/browser_smoke.py --transport inline --out <evidence-directory>
```
The script defaults to `--transport file` for a local browser that permits it. It installs no dependency and uploads no data.

## Covered behavior

The visual/layout matrix used 1440×1000, 1024×768, 390×844 and 320×740 for each starter. Each checked heading, main visibility, lack of accidental page-level horizontal overflow, and theme switching. Reduced-motion CSS and JavaScript were exercised separately for all three layouts.

Reader: dialog initial focus, repeated Tab containment, Escape and opener restoration; explanation preserving reading progress; explicit continuous-content append; synthetic composition guard and legacy keyCode 229 guard; Shift+Enter; empty validation; real text streaming; scroll-history retention and explicit follow; stop, error, retry; consumed draft clearing and newer draft preservation; cancellation on close.

Explorer: keyboard selection, matching selected state/details; arrow-key ratio updates with actual geometry checks; Home/End bounds; 4px dead-zone behavior; direct drag; Escape, pointercancel and lost-capture rollback; drag cleanup during responsive resize; safe reset focus, cancel and confirmed reset.

Report: actual text/status filtering and numeric sort; derived minimum from current view; empty state and reset; named details and focus restoration; export matches filtered rows; units/data caveat retained; CSV quoting and formula-prefix neutralization; query strings remain text rather than HTML.

## Visual inspection

Human-style visual inspection by the assistant used rendered screenshots, not OCR. Explicitly inspected: flow-explorer 1440px light and dark, reader 390px light, report 1440px light. No clipping, unreadable glyphs or broken primary hierarchy was observed in these inspected screenshots. Other captured screenshots remain available for review; do not interpret this as a full manual accessibility or cross-device review.

All screenshot files are in `screenshots/`. They are evidence images, not runtime dependencies or fonts.

## Regression found and repaired

The first browser run exposed a Tab-cycle escape from the native dialog's document focus to browser chrome/body. Native modal behavior was retained and a dynamic first/last-focusable Tab wrapper was added. Controls hidden or disabled at runtime are excluded. The final test run passed repeated dialog focus containment.

## Limitations

No performance benchmark, frame-rate guarantee, production-security certification, or empirical improvement in generated UI quality is claimed. The offline checker is heuristic, and the browser suite targets these example selectors only. The examples contain local simulated answers and hand-constructed architecture data, clearly marked in the UI. No fonts, proprietary brand assets or audio are packaged.
