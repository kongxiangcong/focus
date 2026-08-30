# Focus Reader UI

This directory contains the host-agnostic Focus Reader skeleton. It deliberately does not contain a visual prototype yet.

## Module layout

```text
ui/
├── apps/standalone/             # Runnable browser host
└── packages/
    ├── reader-contracts/        # ReaderHost Interface and browser projections
    └── reader-ui/               # Host-agnostic Reader Module
```

The dependency direction is fixed:

```text
Focus Core
  -> host Adapter
  -> ReaderHost Interface
  -> FocusReader
```

`reader-ui` may import `reader-contracts`, React, and its own internal implementation. It must not import the Standalone app, HTTP, filesystem code, Python scripts, Workspace paths, or DSH packages.

The Standalone app currently has two Adapters:

- `FixtureReaderHost` is the default and keeps all demonstration state in memory.
- `HttpReaderHost` consumes a browser-safe projection exposed by a future local Focus HTTP host.

A future DSH Adapter must implement the same `ReaderHost` Interface. It belongs outside `reader-ui`; DSH session events and transport types must not leak through the Seam.

## Commands

```powershell
pnpm install
pnpm reader:dev
pnpm reader:typecheck
pnpm reader:test
pnpm reader:build
```

Set `VITE_FOCUS_READER_BASE_URL` when the Standalone app should use the HTTP Adapter. Without it, the app uses synthetic fixtures.

## Deferred to the visual prototype feature

- visual variants and the prototype switcher;
- the production Markdown pipeline;
- motion and particle implementations;
- final design tokens and responsive visual language.

Those concerns remain internal to `reader-ui`, so experimenting with them will not change `ReaderHost` or either host Adapter.
