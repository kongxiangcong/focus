# Step 1: status vocabulary and tokens

Changed `source-status.ts` to own phase, tone, detail, progress ratio, filters, attention and blog summary. `primaryAction` is checked against the pre-refactor expression across reading states, preparation states, readiness flags and busy/active/capability locks. Invalid sources expose an inspection action for the upcoming inspector. Existing cards only adopt the unified summary/detail labels at this step; no layout or Host behavior changes.

Added only `--reader-inspector:400px` and `--reader-library-content:1080px` to the existing geometric tokens.

- `pnpm reader:typecheck`: PASS.
- `pnpm reader:build`: PASS (existing bundle-size warning).
- `pnpm reader:test`: FAIL in reader-ui: 83 passed, 3 existing 5-second timeouts. This is the same resource-sensitive baseline area, outside the changed code.
- `pnpm --filter @focus/standalone test --maxWorkers=1 --testTimeout=20000`: 103 passed / 1 failed (an existing async heading lookup exceeded its 1-second wait). Focused rerun of that preparation test: 1 passed / 56 skipped.
- `pnpm --filter @focus/standalone test --maxWorkers=1 src/library/source-status.test.ts`: 14 passed, including exhaustive primary-action parity. No assertions or checked behavior were weakened.
- Browser checks remain blocked as documented in step 0; screenshots waived.

The supplemental pre-change standalone baseline completed with 84 passed / 6 failed: five 5-second timeouts and the existing `old failure` hidden-dialog assertion in the terminal-status clearing test. Assertions are unchanged; a longer CLI-only runtime limit is used for supplemental runs to separate timeout pressure from behavioral failures. Default command outcomes are reported separately.

The Plan-without-preparation status/action mismatch remains intentionally unchanged, as described in the baseline. No real user data has been inspected.
