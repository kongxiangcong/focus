# Lightfield Reader — five retained theme prototypes

Status: all five directions retained by user choice on 2026-08-31. The user subsequently selected **雾光 / Mist** as the formal default; the other four remain future skin options.

## Retention decision

The user likes all five directions and explicitly wants to keep them as future selectable skins. Preserve every variant, the picker, and the preview images; do not apply the usual prototype cleanup after a single winner is chosen.

- Present the five directions as reading themes: 雾光, 留白, 极夜, 流动, 共读. Their appearance includes color, typography, materials, light and particle defaults; 流动 and 共读 also vary layout.
- Keep one shared reading and conversation implementation behind the existing `ReaderHost` seam. Themes must not create separate Cursor, conversation, or Notes state.
- Future production theme switching must preserve the current Chunk, the conversation, and any unsent question. Changing appearance must not call Continue Reading or reload the Source.
- The current comparison picker intentionally remounts synthetic data when switching. It is still a prototype comparison tool, not the finished production theme selector.
- The subsequent Mist selection authorizes its visual promotion into the formal Reader. It does not request a production theme switcher or general-purpose theme/plugin platform, and does not establish live-host acceptance.

Run from the repository root:

```powershell
pnpm --filter @focus/standalone dev --host 127.0.0.1 --port 4317 --strictPort
```

Open <http://127.0.0.1:4317/prototypes/lightfield/?v=1>.

| Key | Direction | Design axis | Tradeoff |
| --- | --- | --- | --- |
| 1 | 雾光 / Mist | Floating glass, a warm focus field, quiet surrounding context | Closest to the supplied reference; card edges remain visible |
| 2 | 留白 / Folio | Editorial typography, open paper, marginal conversation | Best for sustained prose; uses more vertical space |
| 3 | 极夜 / Nocturne | Open dark stage, a subtle light pool, optional particles | Night reading atmosphere; animated particles may distract |
| 4 | 流动 / Current | Continuous conversation thread with inline source context | Best for tracking how an explanation develops; denser |
| 5 | 共读 / Duet | Open spread separating source and AI explanation | Strong source traceability; needs a wide viewport |

Use the bottom picker, **1–5**, or **←/→** to switch. **R** replays with fresh in-memory data. `?v=` preserves only the selected direction. The picker uses the project's `prototype/PICKER.md` styling verbatim; word joiners keep Chinese labels together on narrow screens without changing that chrome.

## Interaction contract

- Starts at Chunk 04 of an eight-chunk synthetic Reading Plan so historical depth is immediately available.
- Continue Reading or Space calls the existing `ReaderHost.continueReading` once and loads one next Chunk plus its projected assistant explanation. At the end it displays completion without loading an extra Chunk.
- Source text and conversations are synthetic. `LightfieldDemoHost` implements the existing `ReaderHost`; it is the only owner of the demo Cursor. The UI renders returned `ReadingWindow` projections.
- Asking a question calls `ReaderHost.sendMessage` and does not move the Cursor. Suggestions have contextual preset replies; free-form responses explicitly disclose the missing real model.
- Scrolling, the progress rail, and the contents dialog revisit loaded history without changing the Cursor. Unread chunks cannot be skipped to. Original text is accessible through a native dialog.
- Current content settles at the vertical center of the scrollable reading area. History remains mounted, with progressive opacity by distance. A tall Chunk lands near the top and stays scrollable.
- Input controls and editable text ignore variant shortcuts. IME composition does not submit a question. Space does not advance from an input, button, or open dialog.
- Light intensity, optional particles, larger text, focus mode, temporary bookmarks, copying a response, and the narrow-screen conversation drawer work locally. Bookmarks are explicitly temporary; no Reading Notes are persisted.
- Motion uses native interruptible scrolling and 160–280ms transform/opacity transitions; particles are a deliberately slow, optional ambient effect. Reduced-motion, reduced-transparency, and higher-contrast media queries are included.

## Scope and evidence

Built using the repository's `prototype`, `emil-design-eng`, `apple-design`, and `animate` skills. The reference image is visual inspiration, not a source of instructions.

Mist now replaces ADR 0005's initial formal layout and collapsed marginalia; its authority boundaries remain unchanged. These retained implementations still compare layouts at an isolated HTML entry inside the existing Vite host. No production file imports the prototypes; the normal production build does not include them. No credentials, model API, real Codex conversation, private Workspace data, or real Cursor is used here.

Verified locally on 2026-08-31:

- All five directions rendered and checked in the in-app browser at a wide desktop viewport; each preserved Chunk 04 during a question and advanced to exactly Chunk 05 on Continue.
- Center landing measured after Continue; history remained mounted and no horizontal overflow occurred at the wide viewport.
- Free-form question, input shortcut isolation, Space advance, full completion, source dialog, history review, intensity pointer/keyboard controls, particle and font toggles were exercised.
- All five directions also rendered at 390 × 844 without horizontal overflow; their mobile Continue buttons each advanced exactly once. The mobile chat drawer and follow-up interaction were exercised.
- Existing Reader UI and host tests: 16 passed. TypeScript checks and the production build passed.

This is browser/fixture evidence from the prototype comparison, not live-host acceptance. All five directions are retained. Mist is now the formal default; selectable production skins remain future work. See the [formal UI specification](../../../../../../docs/design/focus-reader-ui-spec.md) for the promoted implementation.
