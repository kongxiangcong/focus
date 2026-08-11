# Paper-type teaching strategies

Load this reference when selecting a paper model, deciding which learning units are required, or adapting assessment dimensions. Choose one primary strategy and optional secondary traits from the paper's observable structure. Record the classification as a guide inference with confidence, not as an author claim.

## Systems, architecture, compiler, and ML systems

Model the end-to-end path from problem pressure through interfaces, mechanism, resource constraints, and evaluation. Prefer units that require the learner to:

- trace one object or operation across subsystem boundaries;
- explain why each interface preserves necessary information;
- connect design choices to latency, throughput, capacity, energy, or programmability;
- interpret central architecture or dataflow figures;
- identify workload and baseline assumptions;
- test where the mechanism degrades.

## Algorithm and model papers

Model the problem definition, objective, representation, algorithm steps, assumptions, complexity, and empirical support. Prefer units that reconstruct the algorithm, explain each objective term, compare an ablation or alternative, and transfer the method to a changed input or constraint.

## Empirical and measurement papers

Model the research question, population, measurement pipeline, variables, controls, confounders, statistical claims, and external validity. Prefer units that separate observation from causal inference, inspect sampling and measurement choices, and identify plausible alternative explanations.

## Theory papers

Model definitions, assumptions, theorem dependencies, proof strategy, boundary cases, and counterexamples. Prefer units that restate definitions precisely, explain why each assumption is needed, trace lemma dependencies, and construct a case where weakening an assumption breaks the result. Do not invent experimental evidence.

## Survey, taxonomy, and position papers

Model scope, selection method, organizing axes, synthesis claims, omissions, and the argument connecting evidence to recommendations. Prefer units that classify a new example, compare taxonomy boundaries, and identify excluded or weakly supported regions. Do not treat cited work as independently verified merely because the paper mentions it.

## Claim-map rules

Use stable IDs and source anchors. Keep these kinds distinct:

- `author-claim`: a claim attributable to the paper;
- `reported-evidence`: a reported result, measurement, proof, or artifact supporting a claim;
- `guide-inference`: an instructional synthesis made by the guide;
- `open-question`: an unresolved issue or unsupported extension.

For each material claim, capture supporting evidence, assumptions, limitations, and confidence when present. Never promote a guide inference into an author claim.

## Knowledge-map rules

Build the knowledge map as the learner-independent capability graph. Give every node a stable `id`, paper-local `concept_id`, type, observable objective, source anchors, numeric order, optional `tree_parent`, hard and soft `requires`, and a frozen mastery contract with `must_show`, `probes`, and `critical_errors`.

Keep hard prerequisites acyclic. Use `tree_parent` only for the learner-facing tree projection; use `requires` for scheduling. Label external prerequisites explicitly and never attribute them to the paper without a source anchor.

## Reading-plan rules

Construct a DAG around conceptual dependency, not document order. Each unit must include:

```yaml
- id: U01
  title: <conceptual task>
  required: true
  depends_on: []
  node_ids: [N01]
  objective: <observable learner capability>
  source_anchors: [sec-1]
  entry_check: <optional unprompted diagnostic>
  exit_criteria:
    - <observable criterion>
  assessment_dimensions: [motivation, mechanism]
```

Use only dimensions supported by the paper: `motivation`, `problem-formulation`, `mechanism`, `figure-dataflow`, `formula-model`, `evidence`, `tradeoff`, and `criticism-transfer`. Do not force formula, figure, or experiment units when the source does not support them.

Make background units optional when an entry check can establish prior knowledge. Keep core mechanism, decisive evidence, and material limitations required. Schedule every knowledge node exactly once.

Keep mutable node state out of the plan. Let the state service initialize each installed node as `planned` in `paper.yaml.reading.node_states`. Reserve the full node-state vocabulary for that state projection: `planned`, `learning`, `provisional`, `mastered`, `needs-remediation`, `skipped`, and `stale`. A sufficient immediate checkpoint can produce only `provisional`; require transfer evidence or final closed-book proof for `mastered`. Guide generation never awards either state.
