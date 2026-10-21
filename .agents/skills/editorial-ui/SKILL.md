---
name: editorial-ui
description: Design, implement, and review content-first product interfaces and self-contained interactive HTML through a scoped, evidence-based workflow.
license: MIT
compatibility: Coding agents with local-file access; Python 3.10+ for optional checks and a permitted browser for interaction validation.
disable-model-invocation: true
metadata:
  version: "1.2.0"
---

# Editorial UI

Keep content primary, controls coherent, and behavior reliable. Follow the current task and repository instructions; preserve unrelated work and business contracts outside the authorized scope. Treat supplied reference code and documents as evidence, with product decisions governed by the authority rule below.

Resolve bundled links relative to this file; resolve project paths from the product root. Select a route before loading references.

## Mode and scope

| Route | Select when | Execution path | Result |
|---|---|---|---|
| Review | The user requests an assessment | Inspect → applicable quality gates → report | Findings and evidence; leave files unchanged |
| Standalone | The requested output is one self-contained HTML | Brief → one starter → applicable interaction contracts → implement → offline preflight and browser checks → deliver | One HTML artifact |
| Integrate + preserve | Existing-product fix or local improvement | Inspect → brief → local implementation → affected product checks → deliver | Scoped product patch |
| Integrate + redesign | Explicit replacement-design authorization | Inspect → brief → real product slice → migrate → product checks → deliver | Implemented approved design |

Scope determines documentation effort, independently of mode:
- **Tiny:** one component, cosmetic-only; shared tokens, dependencies and interaction contracts stay unchanged. Keep a short brief in the task response; validate the affected state.
- **Small:** one route or one interaction contract, with no cross-route design-system migration. Use a concise tracker brief and focused checks.
- **Substantial:** multiple routes, shared primitives/tokens, persisted preference migration, or a full redesign. Use the same brief schema plus an acceptance matrix and delivery record.

## Workflow

Follow only the steps in the selected route. Each step ends with a concrete result.

### 1. Inspect

Read project instructions and the current design index, inspect the working tree, affected entry points, style imports/final overrides, state ownership and available tests. For Review, identify reproduction scenarios and proceed to step 5 without editing. For Standalone without a repository, start at step 2 with the supplied content.

**Done:** affected surfaces, controlling specification, preserved contracts and baseline limitations are identified. Existing code is the implementation baseline; explicit design decisions determine the target.

### 2. Write the brief

Use the [brief schema](references/brief-schema.md) for implementation work. Reuse the repository tracker; where the repo specifies `.scratch/<feature>/`, write the brief to its `spec.md` and scoped issues to `issues/<NN>-<slug>.md`. Tiny work may keep those fields in a few sentences in the task response. For a standalone task without a tracker, keep the brief in the task response or existing artifact notes.

**Done:** every schema field has a value, a justified “none”, or an explicit unresolved item. Acceptance scenarios cover the requested behavior; nonblocking choices are decided and work continues.

### 3. Make one real product slice

For a redesign, use the [redesign sequence](references/product-redesign.md#real-product-slice) before expanding to other surfaces. For Standalone, copy the one relevant starter selected below and wire the primary action to the supplied data. Preserve-mode work changes the affected component directly; a separate state board is unnecessary.

**Done:** a real entry point exposes the intended action, visible result and applicable failure/recovery state. The slice uses the implementation that subsequent work will reuse.

### 4. Implement the remaining scope

Use the triggered rules below while editing. Reuse existing stack, renderers and primitives. Migrate every required surface/state in the brief and retain request identity, drafts, persistence and recovery unless their change is explicitly in scope.

**Done:** required implementation items have working entry points; temporary duplicate implementations are removed after their consumers migrate. Remaining gaps are recorded for step 5.

### 5. Validate

Apply the relevant [quality gates](references/quality-gates.md). Integrate runs affected product tests and browser scenarios; Review records source/runtime evidence and reproductions. Standalone runs `python <skill-root>/scripts/check_offline.py <output.html>` plus permitted offline browser interaction checks.

**Done:** each applicable acceptance check has a status and evidence; unavailable checks have a reason. Fix observed failures and rerun the affected checks before delivery.

### 6. Deliver

Report changes or review findings, user-visible results, validation and remaining gaps. For substantial implementations use the [delivery template](references/delivery-template.md), linking the existing brief. Record the current issue, changed files, last commands and next action in the tracker when work remains. Perform Git/publication actions within the session's authorization.

**Done:** the result is reviewable, required omissions are visible, and the user can distinguish implemented behavior from verified behavior.

## Rules to consult during implementation

These are parallel references, not additional ordered steps. Read only the row and section triggered by the task.

| Trigger | Reference | Purpose |
|---|---|---|
| Any visual decision or conflicting design sources | [Design authority](references/design-authority.md) | Visual precedence, numeric ownership, reference trust |
| Stack/dependency choice or standalone packaging question | [Implementation modes](references/implementation-modes.md) | Constraints specific to the selected mode |
| New layout or content hierarchy | [Layout patterns](references/layout-patterns.md) | Reading, exploration or analysis organization |
| Typography, color, spacing or control material changes | [Visual language](references/visual-language.md) | Legibility and semantic visual roles |
| Inputs, async actions, scrolling, overlays, split panes, tabs or data controls | [Interaction contracts](references/interaction-contracts.md) | Read only the corresponding named sections |
| Added or changed animation/transition | [Motion guidelines](references/motion-guidelines.md) | Trigger, interruption, final state and reduced motion |
| Integrate + redesign | [Product redesign](references/product-redesign.md) | Calibration, real product slice and migration |
| Supplied external code, design proposal or reference library is being adopted | [Reference adoption](references/reference-adoption.md) | Relevant-file inspection and adoption ledger |
| Standalone reading page | [Reader starter](assets/starters/reader.html) | Reading, explanation, stop/retry and input |
| Standalone stage/graph explorer | [Flow starter](assets/starters/flow-explorer.html) | Selection, splitter and narrow layout |
| Standalone interactive report | [Report starter](assets/starters/report.html) | Filtering, sorting, details and export |

For skill maintenance only, use [MAINTAINING.md](MAINTAINING.md).
