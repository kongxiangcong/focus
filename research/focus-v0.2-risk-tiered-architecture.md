# FOCUS v0.2 Risk-Tiered Architecture

> Status: implemented at the workflow/interface layer on 2026-08-13. The deterministic kernel remains a private compatibility implementation; Atlas remains design-only.

## Decision

FOCUS keeps fail-closed boundaries for source identity, source/inference separation, raw learner answers, evidence, revision conflicts, path confinement, and append-only history. It becomes fail-soft for derived profiles, indexes, views, and ordinary reading progress.

Rigor is spent where error is frequent and consequential: extraction truth, claim support, semantic scoring, delayed retention, completion rate, and research reuse. Not every paper pays for a full knowledge DAG and defense.

## Reading modes

| Mode | Trigger | Required output | Completion |
|---|---|---|---|
| Scout | Default for a new paper | source/hash, extraction quality, overview, key claims, limitations, research relevance, `advance/park/reject` | mapping decision saved |
| Study | learn, understand, compare, critique, use in research | Scout output, key mechanism map, anchors, a few integrative checkpoints, critique, visible gaps | selected key nodes complete |
| Mastery | master, defend, reproduce, teach, retain a core paper | full dependency plan, frozen assessment, remediation, cognitive evidence, delayed retrieval | immediate verification and retention reported separately |

Mode upgrades are monotonic and reuse artifacts. A user is not forced to choose before screening. Scout never creates cognitive evidence.

## Semantic modules and state

`ask-paper` is the only user entry and delegates one action to:

- `paper-map`: ingest truth, Scout, and the smallest Study/Mastery map;
- `paper-study`: teaching, integrative checkpoints, critique, remediation;
- `paper-assess`: immediate assessment, delayed retrieval, diagnosis, evidence projection.

The state vocabulary is:

```text
planned → learning → provisional → verified-now → retained
                    ↘ needs-remediation
```

`verified-now` requires unprompted transfer or a frozen closed-book reconstruction. `retained` requires a different persisted session and at least seven full days. Legacy `mastered` migrates to `verified-now`. Profile level 0–4 is UI-only and never routes work.

The current kernel may still use persisted routes and physically separate response ledgers internally. These are not v0.2 interfaces. Revision/CAS, short locks, event idempotency, path confinement, atomic rename, and evidence preservation stay hidden behind the state script. A wholesale runtime rewrite is out of scope until maintenance evidence justifies it.

## Source and semantic quality gates

Ingest promotion records page/section coverage; figure/table/equation/algorithm inventory; two-column reading order where applicable; caption/asset binding; and sampled claim-to-span support with precise locators. Structural success alone is insufficient. A core-section omission, unreadable central object, wrong reading order, or unsupported sampled anchor blocks promotion.

The next evaluation budget goes to:

1. repeated scoring agreement for the same answer;
2. verdict sensitivity across model/prompt variants;
3. checkpoint discrimination between reconstruction and paraphrase;
4. guide coverage of core mechanisms and boundaries;
5. sampled source-anchor support precision;
6. seven-day delayed retrieval rate;
7. Scout→Study→Mastery conversion, completion, and abandonment rates;
8. downstream research reuse in a synthesis, critique, question, idea, or experiment.

Transaction-count coverage, migration breadth, and retry-state completeness are secondary unless a real failure appears.

## Atlas v0

Atlas remains unimplemented. Its canonical ontology is only `Concept | Synthesis | Question | Idea`.

Paper is a read-only FOCUS projection. Claim stays paper-local. Project/Experiment consumes Atlas IDs but owns its own records. Relations are only `supports`, `contradicts`, `requires`, and `tests`; `as_of` and `supersedes` are optional when version history actually exists.

Stable short IDs, shallow paths, redirects after a real rename/merge, source/inference separation, and rebuildable indexes remain hard constraints. Full stale propagation, migration framework, vector/rerank, broad doctor checks, and retrieval regression wait for actual scale and query logs. Exact/BM25 is introduced only when file search demonstrably fails.
