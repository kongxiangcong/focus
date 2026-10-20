# Quality gates and honest evidence

## Required before claiming a working UI

1. Inspect a rendered wide and narrow screen; include realistic long text. Verify no accidental page-level horizontal overflow or clipped actions.
2. Exercise the main action and observe its real result. Test empty/error/cancel/retry when those states exist. Reject inactive placeholder buttons.
3. Navigate using keyboard; verify labels, focus visibility, dialog containment/restoration, and splitter/disclosure behavior.
4. Confirm composition Enter cannot submit. Distinguish synthetic event coverage from manual OS IME coverage.
5. During streaming scroll upward; verify appends do not move the reading viewport, and explicit return to latest restores following.
6. Test reduced motion in CSS and JS. Test each supported or newly required theme/density and functional contrast, not only decorative surfaces. Do not add themes solely for a checklist.
7. For offline output use static preflight plus a fresh file:// browser context with network denied. Exercise interaction paths, not just page load.
8. Record tested browser/version, viewport, real command outputs and checks not run.

## Suggested matrix

Wide desktop 1440×1000; compact desktop 1024×768; mobile 390×844 and 320×740. Also consider 1600×960/1280×800 for an existing reader. Check large text/200% zoom, pointer and keyboard, OS theme changes, and reduced motion. These are test cases, not CSS breakpoints.

Full-screen overlays must be tested inside the existing app's full-screen root. Embedded iframes, real touch gestures, screen readers and native IMEs require dedicated checks; this bundle does not claim those are covered by a Chromium headless smoke test.

## Evidence levels

`PASS`: performed assertion passed, with command or observation.
`FAIL`: observed a problem, with reproduction and scope.
`NOT_RUN`: needed but not executed, with reason.
`NOT_APPLICABLE`: explicitly out of scope, with explanation.

A successful syntax check is not a successful browser interaction. A screenshot is not proof of keyboard operation. A blocked request is still a network dependency attempt, not an offline pass. Generated fixture data does not become measured data because a chart looks polished.

## Acceptance rubric for a generated artifact

Information architecture and task fit (25%); state correctness and user control (30%); visual coherence and legibility (20%); responsive/accessibility behavior (15%); reproducibility and evidence (10%). This is an evaluation rubric, not a measured score for this release.

Any destructive-action correctness error, unusable keyboard modal, lost draft, broken primary action, misrepresented data or essential offline dependency blocks “ready to use”, regardless of score. Minor style deviations do not justify unrelated rewrites.

## Regression discipline

Keep a small named scenario for each regression. Fix the cause in the shared source, rebuild, and rerun tests. Never adjust an assertion only to hide a UI failure. Keep manual findings distinct from automated outputs.

## Reference-led product acceptance

Freeze the chosen design target with fixed synthetic/public content, viewport, DPR, fonts, theme and density. Compare actual product pages and component states against that target. Track reference resemblance separately from task fit and behavioral correctness. Do not invent a pixel-diff percentage, frame-rate guarantee or performance budget without a measured baseline.

Maintain an implementation/verification matrix per page and state. Required-final scope cannot silently become optional; unimplemented requirements are incomplete, not NOT_APPLICABLE. The board must use the product's primitives and cannot replace primary-route acceptance. Check dev and production-served assets, long timelines, rapid reversals and reduced-motion changes. Keep historical release logs labeled historical; passed bundle tests do not certify a product or generation quality.
