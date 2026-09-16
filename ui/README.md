# Focus Reader UI

This directory contains the host-agnostic formal Focus Reader UI and its standalone development host.

## Module layout

```text
ui/
├── apps/standalone/             # Runnable Fixture or HTTP host
└── packages/
    ├── reader-contracts/        # ReaderHost Interface and browser projections
    └── reader-ui/               # Formal Reader Module
```

The dependency direction is fixed:

```text
Focus Core
  -> host Adapter
  -> ReaderHost Interface
  -> FocusReader
```

`FocusReader({ host })` is the only public Reader UI Interface. `reader-ui` may import `reader-contracts`, React, and its own internal implementation. It must not import the Standalone app, HTTP, filesystem code, Python scripts, Workspace paths, or DSH packages.

The formal default is **雾光 / Mist**: a wide floating reading card, complete host-projected history that progressively fades, a vertical dashed progress rail, and a desktop companion panel. Light intensity, optional particles, larger text, and focus mode affect presentation only. Continue advances one Chunk; questions preserve the Cursor. The companion becomes a toggleable panel on narrow screens.

The five Lightfield prototypes remain under `apps/standalone/src/prototypes/lightfield/` as future skin references. They are available at `/prototypes/lightfield/?v=1` in the development server, but are not imported into the production build. There is no production theme switcher. Appearance changes in the formal UI preserve the current host projection and unsent input; the comparison picker's reset behavior is not used.

## Host Adapters

- `FixtureReaderHost` supplies Chinese synthetic data for development and tests. It never reads private Workspace data.
- `HttpReaderHost` consumes a browser-safe projection exposed by a future local Focus HTTP host.

A future real Adapter must implement the same `ReaderHost` Interface outside `reader-ui`. Host events and transport types must not leak through the seam.

## Commands

```powershell
pnpm install
pnpm reader:dev
pnpm reader:typecheck
pnpm reader:test
pnpm reader:build
```

The default is the same-origin HTTP Adapter. Set `VITE_FOCUS_READER_BASE_URL=fixture` explicitly for the synthetic Fixture Adapter.

## Evidence status

- Contract verified: ReaderHost and Adapter contract tests.
- Fixture verified: synthetic state and interaction tests.
- Browser verified: desktop and 390px checks, pointer-driven motion, post-Continue focus landing, and console.
- Production build verified: build succeeds without switcher or variant paths.
- Live-host verified: not complete.
- Production accepted: not claimed.

See `docs/design/focus-reader-design-verdict.md`, `docs/design/focus-reader-ui-spec.md`, and `.scratch/focus-reader-formalization/` for the decision and staged acceptance work.

## Real Agent Host

The standalone default is now the same-origin Python Host. Build with `pnpm reader:build`,
then start `python -m host --workspace ./workspace`. Explicit fixture mode is
`VITE_FOCUS_READER_BASE_URL=fixture`. See [Host quickstart](../docs/FOCUS_Web_Agent_Quickstart.md).
