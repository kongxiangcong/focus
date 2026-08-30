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

The formal initial UI promotes the current-session diffusion prototype captured in commit `5dae3de`. It uses one continuous Reading Chunk stream, complete host-projected history, a Reading Cursor-anchored diffusion field, a settling/entering Continue Reading handoff, and current-chunk marginalia. It contains no A/B/C variants, prototype switcher, or variant URL.

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

Set `VITE_FOCUS_READER_BASE_URL` to select the HTTP Adapter. Without it, Standalone uses the synthetic Fixture Adapter.

## Evidence status

- Contract verified: ReaderHost and Adapter contract tests.
- Fixture verified: synthetic state and interaction tests.
- Browser verified: desktop and 390px checks, pointer-driven motion, post-Continue focus landing, and console.
- Production build verified: build succeeds without switcher or variant paths.
- Live-host verified: not complete.
- Production accepted: not claimed.

See `docs/design/focus-reader-design-verdict.md`, `docs/design/focus-reader-ui-spec.md`, and `.scratch/focus-reader-formalization/` for the decision and staged acceptance work.
