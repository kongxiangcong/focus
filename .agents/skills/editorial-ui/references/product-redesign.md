# Authorized product redesign

This is an Integrate workflow with `visual_policy: redesign`, not a fourth mode or a mandatory new theme. A toolbar patch still uses preserve policy. Do not infer permission from merely receiving a reference URL; use the user's actual task.

## Brief before building

Write the following into the existing project plan, not an extra bureaucracy:

```text
mode: Integrate
visual_policy: redesign
product_root: actual local root
selected_spec: exact current file + section/revision
execution_addendum: exact overrides / scope decisions
reference_root: user-supplied local path, or none
reference_snapshot: own Git root + HEAD/status, or explicit directory snapshot
business_contracts: IDs, public APIs, persistence, request/retry/recovery, user intent
replaceable_presentation: tokens, layouts, materials, component internals, motion
numeric_source: one product-owned CSS/config/generator
scope: required-first / required-final / optional / separately-authorized
first_slice: high-value real route + interaction + recovery
acceptance: product commands + visual/interaction matrix + live/fixture distinction
```

The adopted design can replace earlier visual ADRs; record exactly which clauses are superseded and retain history. Do not use an old visual ADR to silently veto the redesign, and do not use redesign permission to override business semantics. A source document describing an earlier “analysis-only” session does not itself authorize new code; the current execution request provides that authority.

## Resolve contradictions rather than stack prompts

Use one execution entry with one selected design source. List deliberate changes to the proposal: e.g. implementation order, delivery scope and dependency/commit authorization. Do not ask an agent to “combine the best” of contradictory styles or scopes. Current approved task decisions outrank unselected earlier design preferences.

If the proposal includes themes, density or media enhancements, classify them explicitly. A feature moved after the first slice remains required-final unless scope has actually changed. Optional effects may be omitted with reasons; required feature omissions are incomplete work. Do not silently narrow an accepted product plan to make completion easier.

## Delivery sequence

1. **Baseline and bounded calibration.** Inspect current code and effective CSS, select/adapt the design spec, preserve a before-state, run available baseline checks, and build a small shared state board.
2. **Smallest shared foundation plus a real vertical slice.** Create only the primitives needed to exercise the riskiest/highest-value path. For a reader this may combine actual content, actions, composer, auxiliary overlay and recovery. Other products choose their own critical path.
3. **Migrate the remaining surfaces.** Reuse the now-tested foundation across navigation, resource views, jobs and settings. Grow a shared package only for actual consumers; do not build an entire abstract design system first.
4. **Complete approved enhancements and settings migration.** Test preview/cancel/save, stored preferences and theme/density interactions. Keep generated documents/iframe interiors separate unless their source templates are explicitly in scope.
5. **Consolidate and accept.** Migrate all consumers before deleting old rules; remove temporary appearance switches; verify production as well as dev entry. Compare fixed content/state/viewport and report uncovered scenarios.

A complete token sheet is not a complete redesign. Do not postpone the real slice until every primitive and optional animation is finished. A state board is a calibration aid, not an excuse to stop at a demo.

## Preserve the hard parts while changing the surface

Keep controllers/adapters and public contracts stable initially. Extract presentational components around the existing state, subscriptions, request IDs, monotonic versions and retry policies. Do not run two controllers or duplicate network listeners for before/after rendering. An internal comparison switch may select a view only; it must not create parallel sessions.

Navigation intent, stream-follow intent and layout restoration are distinct. An overlay, resize, theme change or late image is not a new document event. Retain stable content identity, focused action, unsent drafts and meaningful viewport position. Retain the actual top-layer/fullscreen relationship; a body portal is not automatically correct for every fullscreen implementation.

Protect saved preferences. Do not clear storage to hide migration bugs. Version new preferences only where useful, read existing values, define defaults and cancellation, and document any intentional change. Preserve authenticated asset and sanitization boundaries.

## Exit and resume discipline

For each phase record the actual modified files, working route, required scenarios, command outputs, remaining blockers and next action in the existing issue process. Continue through nonblocking gates under the existing authorization; do not invent a fresh manual approval checkpoint for each color/spacing decision.

Do not commit/push/deploy because a design proposal suggests independent commits. Stage-sized changes can remain uncommitted; actual Git writes obey the user's execution authorization. Protect dirty worktrees and do not silently stash/reset unrelated work.

Readiness requires required pages and states migrated, visual target demonstrated, critical behavior preserved, and evidence limits disclosed. Browser smoke, source review, native IME, assistive technology, fixture, real Host and paid-model tests are different evidence. Do not substitute any one for the others or promise future unattended continuation.
