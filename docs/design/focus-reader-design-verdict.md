# Focus Reader Design Verdict

Status: accepted direction; formal details still provisional

## Promotion target

The design evidence being promoted is the current-session prototype captured in commit `5dae3de`. It is not an older Variant D implementation. No A/B/C implementation, prototype switcher, or `?variant=` path exists in the repository baseline.

## Confirmed decisions

- Use a low-saturation diffusion field whose brightest field follows the current Reading Chunk.
- Use one continuous single-column Reading Chunk stream.
- Keep the current Reading Chunk near the visual center while leaving recent context above it.
- Preserve every historical Reading Chunk supplied by `ReadingWindow.history` and derive visual depth from distance to the Reading Cursor.
- Use a short-distance, low-paint Continue Reading handoff with settling and entering Reading Chunks visible together.
- Keep the previous Reader conversation as subordinate marginalia attached to the current Reading Chunk.
- Do not add phrase-level emphasis.
- Preserve the existing `ReaderHost` Interface, `ReadingWindow` projection, and Focus Core authority over the Reading Cursor.
- Keep the Fixture Adapter as development and test data only.

## Not yet fixed

- Final color values and minimum contrast for historical depth levels.
- Final motion duration and diffusion intensity. The formal initial implementation uses 280ms as a reviewable starting point, not a permanent product constant.
- Final mobile density and sticky-action treatment on physical devices.
- Production Markdown rendering, images, glossary presentation, and long-source performance limits.
- The concrete live ReaderHost and deployed host environment.

## Evidence

- Prototype commit: `5dae3de`
- Prototype record: [focus-reader-current-session-prototype.md](./focus-reader-current-session-prototype.md)
- Desktop screenshot: [focus-reader-current-session-prototype.png](./assets/focus-reader-current-session-prototype.png)
- Evidence level at verdict time: Contract-checked, Fixture-verified, Browser-verified, and production-build-verified; not Live-host-verified.
