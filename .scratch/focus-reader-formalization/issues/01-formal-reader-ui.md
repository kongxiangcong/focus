# Rewrite the selected prototype as the formal Reader UI

Status: ready-for-human
Implementation: complete; awaiting human design review

## Requirements

- Promote only the current-session prototype captured in `5dae3de`.
- Keep `FocusReader({ host })` as the public Interface.
- Move pure Reading Chunk rendering and transition-frame derivation into internal modules.
- Remove prototype language and document the absence of A/B/C, switcher, and variant URLs.
- Namespace formal design tokens and use one Chinese synthetic Fixture Adapter path for development.
- Preserve complete host-projected history and current-chunk marginalia.
- Add a single-operation lock, AbortSignal propagation, stale-Cursor reload, and reduced-motion immediate commit.
- Update README and ADR status without claiming Live-host completion.

## Acceptance

- Contract, fixture, browser, and production-build evidence pass.
- The formal build contains no prototype switcher or variant path.
- Live-host verification is reported separately as incomplete.

## Comments

- The prototype evidence is preserved in commit `5dae3de` and `docs/design/focus-reader-current-session-prototype.md`.

## Answer

The current-session prototype was rewritten as the formal initial Reader UI. `FocusReader({ host })` remains the public Interface; Reading Chunk rendering and transition-frame derivation are internal modules; ReaderHost operations use a single-operation lock and AbortSignal; stale Cursor receipts reload the authoritative projection; complete history is a `ReadingWindow` Interface invariant; the synthetic development fixture is Chinese; and formal design tokens, documentation, ADR, tests, and browser evidence are in place.

Verified for human review: all Reader workspace typechecks, 11 Reader UI tests, 5 Standalone Adapter tests, production build, desktop browser, 390px browser, three historical depth levels, post-Continue focus landing, and zero browser console warnings/errors. Keyboard traversal automation, contrast resolution, long-history/Markdown performance, repeatable visual regression, and physical-device density remain in issue 02. A live ReaderHost remains issue 03.

The two-axis review found and corrected the non-canonical Issue status, duplicated host-load lifecycle, old-Chunk remount risk, synthesized transition history, scroll-time glow detachment, and incomplete sending/error control locks. The Issue now remains `ready-for-human` for design review rather than claiming final completion.
