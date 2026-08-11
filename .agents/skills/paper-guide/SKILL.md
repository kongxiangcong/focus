---
name: paper-guide
description: Build, repair, or confirm an evidence-anchored paper model and dependency-ordered reading plan. Use only when $ask-paper issues a route targeting paper-guide after validated ingest or while a guide plan awaits confirmation; otherwise remain read-only and return control to $ask-paper.
---

# Paper Guide

Act as a route-gated internal primitive. Complete exactly one guide or confirmation stage and return control to `$ask-paper`.

## Establish authority

1. Require an explicit workspace, paper, and route ID.
2. Resolve `../ask-paper/scripts/focus_state.py` relative to this skill directory. Use only its `verify-route`, `validate`, `commit --route-id --event <json-or-yaml>`, and `cancel-route` commands. Express every semantic change as a typed JSON or YAML event. Never rewrite `paper.yaml`, routes, locks, or revisions as free text.
3. Verify that the route is `issued`, targets `paper-guide`, and matches the workspace, paper, source hash, expected revision, and mode.
4. On a missing or invalid route, make no changes and direct the caller to `$ask-paper`.
5. Keep an explicitly requested diagnostic invocation read-only. For repair without a valid repair route, diagnose only and return the required repair to `$ask-paper`.

Stop when authority, validated ingest, or source fidelity cannot be proven.

## Build or repair the guide

1. Validate `paper.yaml`, `paper.md`, `ingest/source-map.yaml`, and `ingest/validation.json`. Reject stale or unresolved source anchors.
2. Read [references/paper-types.md](references/paper-types.md) when choosing a paper model, unit emphasis, or assessment dimensions.
3. Reconstruct the paper as problem, mechanism, evidence, assumptions, tradeoffs, and limits. Distinguish `author-claim`, `reported-evidence`, `guide-inference`, and `open-question` throughout.
4. Produce `guide/overview.md`, `guide/claim-map.yaml`, `guide/knowledge-map.yaml`, and `guide/reading-plan.yaml`. Keep the overview concise; use Mermaid when a relationship needs a diagram.
5. Put concept capabilities, tree projection, hard and soft prerequisites, source anchors, and mastery contracts in the knowledge map. Make the reading plan a unit DAG rather than a section list, and schedule every knowledge node exactly once through `node_ids`.
6. Generate the plan only. Leave full teaching, checkpoints, mastery decisions, and answer generation to `paper-reader` and `paper-grill`.

On a substantive repair, commit another `guide-installed` event. Let the state service increment map and plan revisions and mark changed node contracts stale rather than rewriting history.

## Handle plan confirmation

In generation mode, commit `guide-installed` to install all four staged guide artifacts, persist `guide/awaiting-user`, consume the route, and release the lock. Then present the paper's one-sentence problem, required and optional units, dependency order, emphasis, and available route adjustments.

In confirmation mode:

- On confirmation, commit a typed `plan-confirmed` event that advances atomically to `read/ready` and consumes the route.
- On requested changes, revise only the affected staged guide artifacts and commit another `guide-installed` event under the same revision-bound confirmation route. That commit consumes the route, increments guide revisions, preserves or stales evidence by contract hash, and remains `guide/awaiting-user`.
- On ambiguity, keep the installed plan awaiting confirmation, cancel the unused route with the exact reason, and ask one clarifying choice without assuming consent.

Consume a confirmation route through exactly one successful event: either `plan-confirmed` or revised `guide-installed`, never both.

Do not invoke `paper-reader`. Completion requires a consumed or cancelled route, a released lock, and state that agrees with the guide artifacts on disk.
