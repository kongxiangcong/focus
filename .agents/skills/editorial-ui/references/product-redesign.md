# Authorized product redesign

Use for Integrate + redesign. The [design authority](design-authority.md) rule selects the target; the [brief schema](brief-schema.md) records it. Keep prior ADRs as history and name the exact clauses replaced by the approved task.

## Real product slice

This is the authoritative calibration and migration sequence:

1. Inspect current effective styles and a before-state. Build a compact state board only for the controls/content affected by the redesign, using public or synthetic data and recording viewport, DPR, fonts, theme and density.
2. Build only the primitives needed for one high-value **real product slice**: actual route, data, primary action and recovery. Make the board consume those same primitives. Move to the real route before completing optional components/effects.
3. Exercise that route, then migrate other required surfaces using the same implementation. Extend shared components only for actual consumers.
4. Complete required-final enhancements and preferences. Validate preview/cancel/save and existing saved values. Generated documents and embedded content follow the explicit scope in the brief.
5. Consolidate consumers, remove superseded presentation rules and temporary comparison switches, and validate production as well as development entry points.

**Exit:** each required route/state is implemented and its acceptance row has evidence or an explicit remaining gap under [quality gates](quality-gates.md). A calibrated board is an intermediate output; acceptance exercises the real routes.

## Preserve state while changing presentation

Extract presentation around existing controllers, adapters, subscriptions and request identities. A comparison view shares those controllers. Keep unsent drafts, saved preferences, trusted asset/rendering boundaries and recovery semantics through migration. Use the relevant [interaction contracts](interaction-contracts.md) when changing navigation, streaming, overlays or geometry.

Record progress in the existing brief/issues: working route, modified files, checks, blockers and next action. Required-final work remains required when postponed. Choose reversible implementation details and continue through nonblocking phases under the existing authorization.
