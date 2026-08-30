# Complete formal Reader UI quality gates

Status: ready-for-agent
Blocked by: 01

## Requirements

- Verify every loading, ready, continuing, sending, error, cursor-changed, and completed state.
- Add keyboard, focus, reduced-motion, responsive, and operation-race coverage.
- Establish a repeatable visual-regression baseline for desktop and mobile.
- Measure representative long-history and production Markdown performance.
- Resolve historical-text contrast and physical-device mobile density.

## Comments

- The initial implementation may satisfy part of this issue, but it stays open until the full matrix and performance evidence exist.
- Initial coverage now includes operation locking, stale-Cursor reload, initial error retry, completed history, reduced-motion immediate commit, desktop/390px screenshots, focus landing, and console checks.
- Remaining work includes automated keyboard traversal, a repeatable visual-regression harness, historical-text contrast resolution, production Markdown/long-history performance, and physical-device mobile review.
