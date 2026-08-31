# Focus Reader Design Verdict

Status: Mist is the formal default, selected by the user on 2026-08-31; other themes retained

## Promotion target

The user selected **雾光 / Mist**, the first Lightfield prototype, as the default formal Reader UI. The earlier prototype captured in commit `5dae3de` established the continuous-history behavior; Mist now supplies the visual layout. The isolated five-way picker remains available for future skin work and is not imported by the formal UI.

## Confirmed decisions

- Use a low-saturation diffusion field whose brightest field follows the current Reading Chunk.
- Use a wide continuous Reading Chunk stream between a vertical dashed progress rail and a desktop companion panel.
- Keep the current Reading Chunk near the visual center while leaving recent context above it.
- Preserve every historical Reading Chunk supplied by `ReadingWindow.history` and derive visual depth from distance to the Reading Cursor.
- Use a short-distance, low-paint Continue Reading handoff with settling and entering Reading Chunks visible together.
- Present the current Reading Chunk on a warm translucent card. Read chunks become gray at progressively lower opacity and can be reviewed at full contrast without changing the Reading Cursor.
- Show host-projected current-chunk conversation in the companion panel; use a collapsible panel on narrow screens. This replaces the old collapsed marginalia layout.
- Default to Mist with 65% light intensity and particles off. Light, particle, large-text, and focus controls change presentation without resetting the ReadingWindow or unsent input.
- Do not add phrase-level emphasis.
- Preserve the existing `ReaderHost` Interface, `ReadingWindow` projection, and Focus Core authority over the Reading Cursor.
- Keep the Fixture Adapter as development and test data only.

## Not yet fixed

- Final color values and minimum contrast for historical depth levels.
- Final motion duration and diffusion intensity. The formal initial implementation uses 280ms as a reviewable starting point, not a permanent product constant.
- Final mobile density and sticky-action treatment on physical devices.
- Production Markdown rendering, images, glossary presentation, and long-source performance limits.
- The concrete live ReaderHost and deployed host environment.

## Retained theme exploration — 2026-08-31

The user chose to retain all five Lightfield prototypes (雾光, 留白, 极夜, 流动, 共读) for future selectable reading themes, rather than select and keep only one. Preserve their implementations, picker, and screenshots. See the [retained prototype decision](../../ui/apps/standalone/src/prototypes/lightfield/README.md).

The subsequent Mist selection authorizes replacing the formal presentation and revises the visual choices in ADR 0005. The other four themes remain future options, without a production theme switcher or plugin platform. Future production switching must preserve the current Reading Chunk, conversation, and unsent input. The prototype picker's reset-on-switch behavior is for comparison only and must not become production theme behavior.

## Evidence

- Mist implementation and verification: [formal UI specification](./focus-reader-ui-spec.md).
- Retained Lightfield implementations and previews: [prototype record](../../ui/apps/standalone/src/prototypes/lightfield/README.md).
- Historical foundation: commit `5dae3de`, [prototype record](./focus-reader-current-session-prototype.md), [desktop screenshot](./assets/focus-reader-current-session-prototype.png).
- Evidence levels remain distinct: contract, fixture, browser, and production build do not constitute Live-host verification or production acceptance.
