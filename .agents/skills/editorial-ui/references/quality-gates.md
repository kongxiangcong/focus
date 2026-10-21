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

Record two independent dimensions. **Basis** says where a finding comes from; **status** says whether a specific check ran and passed.

| Basis | Meaning |
|---|---|
| SOURCE | Inspected implementation or declaration; identify file/region/version |
| CLAIM | Upstream assertion or unverified hypothesis; identify origin and needed check |
| DECISION | Approved product target, adaptation or scope choice |
| RUNTIME | Scenario actually exercised; identify environment, inputs and observation |

| Status | Meaning |
|---|---|
| PASS | Named assertion was performed and passed, with evidence |
| FAIL | Check exposed a problem, with reproduction and consequence |
| NOT_RUN | Required check was unavailable or unexecuted; give reason |
| NOT_APPLICABLE | Check is outside this task's scope; give reason |

For example, a source check can be `SOURCE / PASS` while the corresponding browser scenario is `RUNTIME / NOT_RUN`. An unimplemented requirement remains incomplete; it cannot be marked NOT_APPLICABLE merely to close delivery.

### Evidence limits

Static checks establish only their named assertions. `check_offline.py` is heuristic, not a security boundary or proof of no network use; exercise the output in a fresh offline browser context. A denied dependency request remains a failed offline dependency check. If file URLs are blocked, use permitted inline testing and record direct-file opening as NOT_RUN.

Screenshots establish appearance in a fixed state, not keyboard operation. Synthetic IME events test handler logic, not native OS input. Fixtures are illustrative, not measured product data. Bundle/starter tests, historical release records and upstream marketing establish neither current product quality nor official affiliation. Report measured performance only with a recorded baseline and measurement. Respect tool/environment limits; unavailable or unauthorized live checks remain NOT_RUN.

## Acceptance rubric for a generated artifact

Information architecture and task fit (25%); state correctness and user control (30%); visual coherence and legibility (20%); responsive/accessibility behavior (15%); reproducibility and evidence (10%). This is an evaluation rubric, not a measured score for this release.

Any destructive-action correctness error, unusable keyboard modal, lost draft, broken primary action, misrepresented data or essential offline dependency blocks “ready to use”, regardless of score. Minor style deviations do not justify unrelated rewrites.

## Regression discipline

Keep a small named scenario for each regression. Fix the cause in the shared source, rebuild, and rerun tests. Never adjust an assertion only to hide a UI failure. Keep manual findings distinct from automated outputs.

## Reference-led product acceptance

For reference calibration, the real product slice and migration acceptance, follow [product redesign](product-redesign.md#real-product-slice).
