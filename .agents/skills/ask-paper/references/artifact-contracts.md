# Paper Companion artifact contracts

Use this reference when creating, validating, migrating, or committing Paper Companion artifacts. Paths are relative to the selected `knowledge-base/` unless stated otherwise. Generated control files are state-service owned; learner notes and immutable source inputs are user-owned.

## Contents

- [Runtime layout](#runtime-layout)
- [Workspace and registry](#workspace-and-registry)
- [Paper manifest](#paper-manifest)
- [Ingest artifacts](#ingest-artifacts)
- [Guide artifacts](#guide-artifacts)
- [Reading artifacts](#reading-artifacts)
- [Assessment artifacts](#assessment-artifacts)
- [Cognitive evidence and profile](#cognitive-evidence-and-profile)
- [Route contract](#route-contract)
- [Typed event contract](#typed-event-contract)
- [Validation and ownership](#validation-and-ownership)

## Runtime layout

```text
knowledge-base/
├── workspace.yaml
├── reading-registry.yaml
├── .paper-companion/
│   ├── locks/
│   ├── routes/
│   ├── runs/
│   └── migrations/
├── cognitive-profile/
│   ├── profile.yaml
│   ├── evidence.jsonl
│   └── history/
└── research-corpus/
    └── <paper-directory>/
        ├── source.pdf
        ├── paper.md
        ├── images/
        ├── metadata.json
        ├── paper.yaml
        ├── ingest/
        │   ├── extraction-report.md
        │   ├── source-map.yaml
        │   └── validation.json
        ├── guide/
        │   ├── overview.md
        │   ├── knowledge-map.yaml
        │   ├── reading-plan.yaml
        │   └── claim-map.yaml
        ├── reading/
        │   ├── events.jsonl
        │   ├── responses.jsonl
        │   ├── units/
        │   └── sessions/
        ├── assessment/
        │   ├── questions.yaml
        │   ├── interview.jsonl
        │   ├── diagnosis.md
        │   └── remediation.yaml
        └── notes/
```

Treat optional page, table, equation, and SVG outputs as parser capabilities, not required artifacts. Keep generated teaching material out of `notes/`.

## Workspace and registry

Use this minimum `workspace.yaml` shape:

```yaml
schema_version: 1
workspace_id: kb-<stable-id>
created_at: <RFC-3339 timestamp>
defaults:
  explanation_language: zh-CN
  quote_language: original
paths:
  registry: reading-registry.yaml
  corpus: research-corpus
  profile: cognitive-profile
  control: .paper-companion
```

Keep internal paths relative. Do not persist the workspace's absolute path. Use `reading-registry.yaml` only as an index:

```yaml
schema_version: 1
last_used_paper: <paper-id-or-null>
papers:
  <paper-id>:
    directory: <relative-paper-directory>
    title: <title>
    aliases: []
```

Do not duplicate phase, status, revision, or node progress in the registry.

## Paper manifest

Use `paper.yaml` as the single mutable routing snapshot:

```yaml
schema_version: 2
paper_id: <stable-slug-and-hash-prefix>
title: <title>
aliases: []
learning_goal: deep-understanding
identifiers: {}
provenance:
  original_path: <informational-path-or-null>
  source_sha256: <sha256>
related_versions: []
artifacts:
  source_pdf: source.pdf
  parsed_markdown: paper.md
  parser_metadata: metadata.json
  images: images
  ingest_report: ingest/extraction-report.md
  source_map: ingest/source-map.yaml
  overview: guide/overview.md
  knowledge_map: guide/knowledge-map.yaml
  reading_plan: guide/reading-plan.yaml
  claim_map: guide/claim-map.yaml
  notes: notes
ingest:
  status: pending
  parser: null
  parser_version: null
  source_sha256: <sha256>
  validated_at: null
  warnings: []
reading:
  phase: ingest
  status: ready
  revision: 0
  plan_revision: 0
  map_revision: 0
  confirmed_plan_revision: null
  current_node: null
  node_states: {}
  pending_interaction: null
  assessment_round: 0
  remediation_targets: []
  outcome: null
  blocked_reason: null
  updated_at: <RFC-3339 timestamp>
```

Store mutable node state only in `reading.node_states`, keyed by stable plan node ID:

```yaml
reading:
  node_states:
    U001:
      status: planned
      contract_hash: <sha256>
      evidence_refs: []
      attempts: 0
      updated_at: <RFC-3339 timestamp>
```

The guide maps own objectives and dependencies; they do not own mutable learner state. `reading.pending_interaction` must contain enough information to resume without chat history:

```yaml
owner: paper-reader
kind: unit-checkpoint
prompt_id: prompt-<stable-id>
unit_id: U001
node_id: U001
artifact_ref: reading/units/U001.md
plan_revision: 1
assessment_revision: null
```

Use `outcome: complete` or `outcome: completed_with_gaps` only with `phase/status: complete/complete`.

## Ingest artifacts

Keep `source.pdf` byte-identical to the claimed input. Bind every generated ingest artifact to its SHA-256.

Require `metadata.json` to parse and `paper.md` to contain usable text. Use `ingest/source-map.yaml` for observable source anchors:

```yaml
schema_version: 1
source_sha256: <sha256>
anchors:
  - id: sec-3-2
    kind: section
    heading: <observed-heading>
    markdown_heading: <exact-heading-or-null>
    occurrence: 1
    page: null
    asset: null
```

Anchor IDs must be unique. Include `occurrence` when headings repeat. Use only observed locations; represent unavailable pages, captions, and assets as `null`.

Use `ingest/validation.json` with at least:

```json
{
  "schema_version": 1,
  "source_sha256": "<sha256>",
  "blocking_errors": [],
  "warnings": [],
  "checked_artifacts": []
}
```

An ingest succeeds only when the source hash matches, required files parse, local references resolve, anchor IDs are unique, and `blocking_errors` is empty. On failure, retain staged diagnostics and cancel the stage route; `inspect` and `next` own the resulting blocked projection.

## Guide artifacts

Use `guide/claim-map.yaml` to separate source attribution:

```yaml
schema_version: 1
source_sha256: <sha256>
claims:
  - id: C001
    kind: author-claim
    statement: <concise-statement>
    source_anchors: [sec-1]
    supported_by: [E001]
    assumptions: []
    limitations: []
```

Allow only `author-claim`, `reported-evidence`, `guide-inference`, and `open-question`. Require every referenced claim, evidence, assumption, limitation, and source anchor to exist.

Use `guide/knowledge-map.yaml` as the learner-independent knowledge graph:

```yaml
schema_version: 1
nodes:
  - id: N001
    concept_id: paper-local.execution-graph
    title: <concept-title>
    type: mechanism
    tree_parent: null
    order: 10
    objective: <observable-capability>
    source_anchors: [sec-1]
    requires:
      hard: []
      soft: []
    mastery_contract:
      must_show: [<observable-point>]
      probes: [reconstruct, discriminate, transfer]
      critical_errors: [<material-error>]
```

Require stable node and paper-local concept IDs, resolvable hard and soft prerequisites, an acyclic hard-prerequisite graph, valid tree parents, source anchors, observable objectives, and non-empty `must_show` and `probes`. Compute `contract_hash` from the normalized node type, objective, dependencies, anchors, and mastery contract.

Use `guide/reading-plan.yaml` to schedule every knowledge node exactly once:

```yaml
schema_version: 1
paper_id: <paper-id>
plan_revision: 1
learning_goal: deep-understanding
units:
  - id: U001
    title: <capability-oriented-title>
    required: true
    depends_on: []
    node_ids: [N001]
    objective: <observable-unit-capability>
    source_anchors: [sec-1]
    entry_check: <optional-unprompted-probe>
    exit_criteria: [<observable-point>]
    assessment_dimensions: [mechanism]
```

Require stable unique unit IDs, an acyclic unit dependency graph, valid source anchors, and exit criteria for every required unit. Every knowledge node must occur in exactly one unit. The state service initializes `paper.yaml.reading.node_states`; neither guide map contains a mutable `state` field.

Installing a substantive replacement plan uses `guide-installed`, increments `plan_revision`, and marks only nodes whose normalized contract changed as `stale`. Confirmation binds `confirmed_plan_revision` to the exact installed revision.

## Reading artifacts

Use `reading/units/<unit-id>.md` for generated teaching material. Keep learner responses append-only in `reading/responses.jsonl`. Each response record must contain a unique response ID, paper and unit IDs, prompt ID, plan revision, answer text, and recorded time.

Record state transitions in `reading/events.jsonl`. Every evidence-producing `answer-recorded` event must reference the persisted response rather than copying or reconstructing the learner's answer.

Before waiting, `unit-presented` persists `reading.pending_interaction`, consumes the current route, and releases its lock. Clear the interaction only when the matching prompt response has been committed.

## Assessment artifacts

Freeze `assessment/questions.yaml` before the first answer of a round. Bind it to the source hash, plan revision, assessment revision, covered node IDs, ordered questions, expected points, critical errors, follow-up limits, and pass rules.

Append verbatim answers to `assessment/interview.jsonl`. Do not revise a frozen question set after an answer; create a new assessment revision.

Write `assessment/diagnosis.md` only after all required questions in the frozen round are answered. Keep machine-routable targets in `assessment/remediation.yaml`:

```yaml
schema_version: 1
assessment_revision: 1
targets:
  - id: R001
    node_id: U002
    claim_refs: [C001]
    diagnosis_evidence_refs: [assessment/interview.jsonl#A003]
    state: needs-remediation
```

Preserve earlier rounds and targeted re-grill revisions. A `grill-diagnosed` event applies the whole frozen round at once, creates remediation targets, and computes either the next remediation route or a valid completion outcome.

## Cognitive evidence and profile

Treat `cognitive-profile/evidence.jsonl` as append-only authority. Each event must include:

- schema and unique event IDs;
- workspace-local paper and concept or node IDs, plus the state-owned `node_state_after`;
- evidence type, verdict, and conservative level candidate;
- map revision and normalized mastery-contract hash;
- stable response or interview artifact reference;
- concise rubric result, confidence, and recorded time;
- an optional superseded event ID.

Do not copy full answers into profile evidence. `answer-recorded`, `self-reported`, `node-skipped`, and `grill-diagnosed` append referenced evidence and rebuild `profile.yaml` inside their authorized transaction. Rebuild the profile deterministically from valid, non-superseded ledger events. The same ledger must produce the same profile. Keep the previous valid profile when validation fails.

Do not create a standalone evidence or supersession commit. A later observed canonical answer or diagnosis may carry a state-engine-validated `supersedes` reference; a separate correction workflow is deferred beyond v0.1.

Do not automatically merge concept identities across workspaces or papers. Cross-paper identity requires an explicit alias or future merge contract.

## Route contract

Store routes under `.paper-companion/routes/<route-id>.yaml`:

```yaml
schema_version: 1
route_id: route-<stable-id>
workspace_id: <workspace-id>
target_skill: paper-reader
allowed_helpers: [cognitive-profile]
mode: normal
paper_id: <paper-id-or-null>
input_path: null
input_sha256: null
expected_revision: 7
status: issued
issued_at: <RFC-3339 timestamp>
context:
  reason: <router-reason>
  operation: <optional-stage-operation>
```

Use only these route modes: `normal`, `confirmation`, `resume`, `remediation`, `targeted`, `diagnostic`, and `repair`. Keep finer routing details, including an optional operation, in `context`. A new-ingest route omits `paper_id` and binds the external input path and hash; a same-source repair route binds the existing `paper_id` and canonical `source.pdf` hash.

Only `next` issues a route. Only `commit` consumes a successful route; `cancel-route` cancels an abandoned one. A helper listed in `allowed_helpers` participates in the parent transaction and cannot consume the parent route or change phase independently.

## Typed event contract

Pass `commit` one JSON or YAML object containing a unique `event_id`, one canonical `type`, and its type-specific fields. The route supplies workspace, paper or input, target, mode, expected revision, and stage context. The state engine adds schema, paper identity, and recorded time to persisted ledger rows; do not invent a second envelope at a call site.

The implemented canonical event types are exactly:

| Event type | Owner | Semantic effect |
|---|---|---|
| `ingest-completed` | `paper-ingest` | Register validated generated ingest artifacts for a new claim or same-source repair |
| `guide-installed` | `paper-guide` | Install one guide/plan revision, initialize or stale node projections, and await confirmation |
| `plan-confirmed` | `paper-guide` | Bind confirmation to the installed plan revision and advance to read |
| `unit-presented` | `paper-reader` | Persist one teaching/checkpoint interaction before waiting |
| `answer-recorded` | `paper-reader` | Append the verbatim response and rubric result, then apply its allowed node consequence |
| `self-reported` | `paper-reader` | Record confidence or familiarity without changing node state |
| `node-skipped` | `paper-reader` | Record an explicit learner choice and preserve an unmastered gap |
| `grill-started` | `paper-grill` | Freeze a question set with `mode: full` or `mode: targeted` and persist its first interaction |
| `grill-answer-recorded` | `paper-grill` | Append one verbatim answer and persist the next frozen interaction when present |
| `grill-diagnosed` | `paper-grill` | Apply whole-round verdicts, evidence, remediation, and computed completion |
| `remediation-presented` | `paper-reader` | Persist one bounded reteaching interaction for a diagnosed node |

### Canonical event inputs

Store the event JSON or YAML inside the issued route's run directory. Resolve every staged artifact field relative to that same directory. Every object requires `event_id` and `type`; use the additional fields below exactly:

| Event | Allowed route modes | Required input fields | Conditional or optional fields |
|---|---|---|---|
| `ingest-completed` | `normal`, `repair` | `title`, `parsed_markdown`, `metadata`, `parser` | `aliases`, `identifiers`, `images`, `validation`, `source_map`; repair is same-source only, cannot change paper identity or `source.pdf`, and preserves downstream state only while all installed anchors remain valid |
| `guide-installed` | `normal`, `repair`, `confirmation` | `overview`, `claim_map`, `knowledge_map`, `reading_plan`, `prompt_id` | `learning_goal`; a confirmation-mode revision consumes that route and installs exactly the next plan revision |
| `plan-confirmed` | `confirmation` | `plan_revision` | The revision must equal both the installed and pending-confirmation revision |
| `unit-presented` | `normal` | `node_id`, `unit_id`, `unit_artifact`, `prompt_id` | Node and unit must equal the route context |
| `answer-recorded` | `resume`, `remediation` | `prompt_id`, `response_id`, `answer`, `verdict`, `rubric_results` | `evidence`; required and non-empty for `sufficient` or `transfer` |
| `self-reported` | `resume`, `remediation` | `prompt_id`, `response_id`, `statement` | Records confidence only and leaves node state unchanged |
| `node-skipped` | `normal`, `resume` | `node_id`, `response_id`, `reason` | The node must equal the routed or persisted pending node |
| `grill-started` | `normal`, `targeted` | `mode`, `questions`, `prompt_id` | Event `mode` is `full` for a normal route and `targeted` for a targeted route |
| `grill-answer-recorded` | `resume`, `targeted` | `prompt_id`, `answer_id`, `answer` | `next_prompt_id` is required when another frozen question remains |
| `grill-diagnosed` | `normal`, `targeted` with `context.operation: diagnose` | `diagnosis`, `verdicts` | Each verdict needs `node_id`, `verdict`, and `answer_id`; positive verdicts need `evidence`; full-round failures need matching `remediation_targets` |
| `remediation-presented` | `remediation` | `target_id`, `unit_artifact`, `prompt_id` | Target must equal route context and be `pending` or `teaching` |

An evidence candidate requires `evidence_type`, integer `level_candidate` from 0 through 4, string-list `dimensions`, `confidence` from `low|medium|high`, and non-empty `rubric`. It may supply a matching `event_id`, `concept_id`, `verdict`, or earlier same-concept `supersedes`. The state service owns all other persisted evidence fields.

Use another `guide-installed` event for an authorized plan revision. Use `answer-recorded` to evaluate either a normal checkpoint or a remediation checkpoint; its persisted pending interaction disambiguates the branch. Profile evidence and deterministic profile rebuild are atomic side effects of evidence-producing canonical commits.

Source drift, blockers, unlocks, and terminal eligibility are router-owned projections from validated state and artifacts, not additional stage event types. Reject an event whose type, paper, artifacts, or requested transition exceed its route.

For `answer-recorded`, require the matching prompt, verbatim response, verdict, itemized rubric result, and evidence candidates for every positive verdict. For `grill-diagnosed`, require per-node verdicts, frozen-round answer references, positive evidence candidates, and a remediation target for every failed required node. Keep demonstrated points, missing points, and critical errors in the rubric or diagnosis artifact. Let the state service derive source references, contract hashes, and `node_state_after`, then reject impossible transitions, missing references, duplicate event IDs, or mastery without the required gate.

Commit one semantic transaction per event file. Replaying the same event ID must not duplicate ledger entries or revisions.

## Validation and ownership

Require `validate` to check:

- compatible schemas and relative paths within the workspace;
- source-hash agreement and immutable source identity;
- artifact existence, parseability, and reference integrity;
- unique IDs, valid source anchors, and an acyclic learning DAG;
- plan, contract, assessment, and paper revision agreement;
- legal node, phase, route, and outcome states;
- evidence references, supersession links, and profile reproducibility;
- no active route or lock spanning an awaiting-user state.

State-service-owned files include workspace control metadata, registry fields, `paper.yaml`, routes, locks, event ledgers, and `profile.yaml`. Stage Skills may generate staged content artifacts, but promote or register them only through `commit`. Preserve learner-owned `notes/`, source inputs, verbatim answers, and historical assessment/evidence records.
