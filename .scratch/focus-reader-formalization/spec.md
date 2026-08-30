# Formalize the current-session Focus Reader prototype

Status: formal Reader UI initial implemented; quality gates and live-host acceptance pending

## Scope

Promote the current-session diffusion prototype captured in `5dae3de` into the only formal `reader-ui` implementation. Preserve the `ReaderHost` seam and separate UI evidence from real-host product-path evidence.

The promotion target is not an older Variant D implementation. No A/B/C code, switcher, or variant URL exists in the current baseline.

## Stages

1. Formal Reader UI: rewrite the current-session prototype into formal internal modules, design tokens, state handling, documentation, and a Chinese synthetic development fixture.
2. Formal quality gates: complete state-matrix, accessibility, concurrency, responsive, performance, and visual-regression evidence.
3. Live-host acceptance: verify a real ReaderHost, real ReadingWindow, Continue Reading, conversation, recovery, reload persistence, and representative source performance.

## Completion rule

The feature remains incomplete until stage 3 is Live-host-verified. Fixture and browser evidence must never be reported as production acceptance.
