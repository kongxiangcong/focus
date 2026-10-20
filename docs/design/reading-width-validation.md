# Reader width and removable references

2026-10-20

The requested standard reading column and fixed composer/control area use a
1040px inner width (1088px including desktop padding). The width button shows
its destination: 宽幅 with outward arrows, 标准 with inward arrows. Its browser-local
preference never changes Host state. Standard aligns with the dock; wide uses
available reading space. Both modes share space between source and attached
discussion using a 3:2 grid with a 32px gap. Attachment still pauses below 1240px
or while materials are open. This supersedes the fixed 720px attachment geometry
in the earlier redesign acceptance record.

The × control explicitly removes the draft's paragraph reference. That state
survives typing and draft recovery; sending uses `receipt: null`, retaining the
Source discussion. Explicitly quoting another paragraph restores its reference.

Validation:
- `pnpm reader:typecheck` and `pnpm reader:build` pass.
- `pnpm reader:test`: 89 reader-ui and 150 standalone tests pass, including
  removing the reference before typing, sending null, and explicitly re-quoting.
- `tests/reading_width_browser.mjs` passes in headless Edge and exercises standard/wide, fixed dock geometry,
  attached column bounds, reference removal and the actual HTTP request, plus
  responsive widths 1600, 1440, 1280, 1024 and 390.
- Browser evidence uses an isolated synthetic Source and controlled Runtime,
  not a real-model quality or native IME qualification.

The existing attachment browser suite completed its layout, scroll-anchor,
sticky long-reply, materials pause/resume, resize, persistence and reduced-motion
assertions. Its final clean-console assertion failed on blocked data-URL fonts
(CSP default-src) and HTTP 404 resources; the complete suite is not marked passing.
The new focused browser suite checks page exceptions, not all console resources.

## Configurable standard width and non-overlapping materials

The follow-up request adds Settings → 标准阅读宽度 (720–1440px, 40px steps,
default 1040px), with the existing save/restore appearance behavior and browser-local
persistence. It controls the standard reading column and fixed dock together;
wide reading ignores the column limit.

Standard mode now reserves a separate grid column for materials, allowing text to
reflow when necessary. At viewport widths up to 720px, materials and reading occupy
separate rows. The dock retains its configured width when materials open or close.
This explicitly supersedes ADR 0026's overlay/unchanged-text-width rule for standard
mode per the user's follow-up; wide mode retains the previous behavior.

Typecheck, production build and 241 tests (89 reader-ui + 152 standalone) pass.
Settings tests cover preview, restore, save/reopen and invalid stored values.
The dedicated browser acceptance is `tests/reading_standard_settings_browser.mjs`.

Headless Edge verified saved width survives reload (1200px), closing materials
restores the requested width, the dock remains unchanged, and switching from wide
to standard while materials are open reserves space immediately. Six viewports
(1600, 1440, 1024, 800, 600, 390px) keep materials and reading in disjoint rectangles.
