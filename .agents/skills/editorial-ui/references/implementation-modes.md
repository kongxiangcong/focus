# Implementation modes and tooling

## Existing app

Select `visual_policy: preserve` for a normal integration or scoped fix; select `redesign` only when the user authorizes replacement presentation. Preserve the existing stack and business contracts in either case. An approved product spec, not the old palette or bundled defaults, controls redesign visuals. Use [product redesign](product-redesign.md) and [reference adoption](reference-adoption.md) when applicable.

Read repo instructions and lockfiles; identify framework, theme, primitives, rendering and testing tools. Reuse existing dependencies and versions. Do not silently update a dependency to match an upstream example. Do not introduce React into a vanilla app or vice versa without a task-level reason.

Map semantic values into the app, keep styles scoped, retain data flow and existing keyboard semantics. If an accessible primitive is already available, adapt its styling instead of building a focus trap from scratch. Verify affected routes, overlays, mobile states and existing tests. No commit, PR, push or deployment without explicit authorization.

## Standalone file

The delivered `index.html` has inline CSS, classic JavaScript and inline data. No network fetch, dynamic import, runtime font dependency, or required sibling file. Use inline SVG only for simple UI icons/diagrams; provide labels and equivalent text for content diagrams. Do not bundle font binaries. User-activated links to sources are permissible but are not offline-readable content; distinguish links from automatic dependency loads.

Use source code sources only at authoring time. `build_starters.py` resolves JSON/CSS/JS into HTML; opening a built HTML never reads those files. Never use `fetch('./data.json')` with file URLs. Blob-backed CSV export is generated locally and temporary URLs are revoked.

Use feature detection for optional animations. The baseline expects modern browsers with native dialog, CSS Grid and standard DOM APIs. The bundled browser suite targets Chromium only; consult the current release report for actual execution; do not promise Safari/Firefox/embedded-WebView behavior. Essential no-JavaScript explanatory text can use `<noscript>`, but the interactive experience requires JavaScript.

## Review mode

Do not change files. Separate source-confirmed findings, runtime-observed findings and hypotheses. Give severity by user consequence: data/action correctness and focus loss outrank minor style mismatch. Include a minimal reproduction and exact file/selector where known.

## Scripts

`audit_reference.py` is a read-only declared-file snapshot helper, not a visual/code audit. It distinguishes the reference Git root from an enclosing product root and never downloads or executes upstream code.

All bundle Python commands use 3.10+ standard library except `browser_smoke.py`, which needs Playwright. No script uploads files or downloads dependencies automatically. Scripts return nonzero on errors; do not ignore exit status.

`check_offline.py` statically inspects common auto-load attributes, CSS resources, module imports, network APIs and selected dynamic asset construction. It is conservative and heuristic: minified/obfuscated code and arbitrary runtime evaluation can evade it; strings/comments may create review findings. It never executes the artifact. `PASS` means no known issue detected, not proof or sandboxing.

`browser_smoke.py` opens the three bundled files with `file://`, blocks HTTP(S), records attempted network requests, exercises controls and writes evidence. A blank render can be offline while still broken, so behavior assertions are essential. When a managed browser blocks file URLs, `--transport inline` loads the same HTML bytes into a fresh offline page without bypassing that policy. This verifies rendering and interactions, but NOT the file-origin path. The report records the selected transport. The script's selectors are specific to the samples and are not a general audit of arbitrary generated HTML.

`validate_skill.py` checks this bundle's limited metadata profile and referenced files, token contrast pairs, no packaged fonts and built-asset consistency. It is not an official Agent Skills conformance validator. Runtime-specific `disable-model-invocation` is deliberately included alongside portable core fields.
