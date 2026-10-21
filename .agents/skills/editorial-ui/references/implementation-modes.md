# Implementation modes and tooling

## Existing app

Select `visual_policy: preserve` for a normal integration or scoped fix; select `redesign` only when the user authorizes replacement presentation. Preserve the existing stack and business contracts in either case. Resolve visual decisions using [design authority](design-authority.md).

Read repo instructions and lockfiles; identify framework, theme, primitives, rendering and testing tools. Reuse existing dependencies and versions. Do not silently update a dependency to match an upstream example. Do not introduce React into a vanilla app or vice versa without a task-level reason.

Map semantic values into the app, keep styles scoped, retain data flow and existing keyboard semantics. If an accessible primitive is already available, adapt its styling instead of building a focus trap from scratch. Verify affected routes, overlays, mobile states and existing tests.

## Standalone file

The delivered `index.html` has inline CSS, classic JavaScript and inline data. No network fetch, dynamic import, runtime font dependency, or required sibling file. Use inline SVG only for simple UI icons/diagrams; provide labels and equivalent text for content diagrams. Do not bundle font binaries. User-activated links to sources are permissible but are not offline-readable content; distinguish links from automatic dependency loads.

Use source code sources only at authoring time. `build_starters.py` resolves JSON/CSS/JS into HTML; opening a built HTML never reads those files. Never use `fetch('./data.json')` with file URLs. Blob-backed CSV export is generated locally and temporary URLs are revoked.

Use feature detection for optional animations. The baseline expects modern browsers with native dialog, CSS Grid and standard DOM APIs. The bundled browser suite targets Chromium only; record the browser and version actually exercised, and mark other browser coverage as unverified. Essential no-JavaScript explanatory text can use `<noscript>`, but the interactive experience requires JavaScript.

## Review mode

Do not change files. Use the evidence basis and check status defined in [quality gates](quality-gates.md#evidence-levels). Give severity by user consequence: data/action correctness and focus loss outrank minor style mismatch. Include a minimal reproduction and exact file/selector where known.
