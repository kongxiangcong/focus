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

The formal presentation is **CDS 2.0, FOCUS adaptation**: a solid neutral canvas, one continuous reading column, a single collapsible sidebar, a left overlay materials drawer and a CDS composer (Editor + Notices + Chin). Light/dark/system themes and compact/comfortable density come from one product-owned token file, `focus-tokens.css`. Reading size, serif family, brightness and library view preferences keep their existing storage keys. Continue advances one Chunk; questions preserve the Cursor. The materials drawer never reflows the text column. See [the CDS design record](../docs/design/focus-cds-ui.md) and [ADR 0025](../docs/adr/0025-cds-focus-presentation.md).

The five Lightfield prototypes remain under `apps/standalone/src/prototypes/lightfield/` as future skin references. They are available at `/prototypes/lightfield/?v=1` in the development server, but are not imported into the production build. Production theming is limited to light/dark/system and compact/comfortable; there is no picker between prototype skins. Appearance changes in the formal UI preserve the current host projection and unsent input; the comparison picker's reset behavior is not used.

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
- Live-host verified: Stage 1 Inbox、刷新、Topic 与 Source 资源出口已在隔离真实 Workspace 验证。
- Production accepted: Stage 1 单篇入库已验收；整个 v0.2 产品仍不作生产完成声明。

See `docs/design/focus-reader-design-verdict.md`, `docs/design/focus-reader-ui-spec.md`, and `.scratch/focus-reader-formalization/` for the decision and staged acceptance work.

## Real Agent Host

The standalone default is now the same-origin Python Host. Build with `pnpm reader:build`,
then start `python -m host --workspace ./workspace`. Explicit fixture mode is
`VITE_FOCUS_READER_BASE_URL=fixture`. See the [web setup](../README.md).
