---
name: paper-map
description: Build or repair a source-faithful paper map for Scout, Study, or Mastery after ask-paper selects this semantic action. Internal FOCUS module; normal users enter through ask-paper.
---

# Paper Map

Own source fidelity and the smallest paper model required by the selected reading mode. Accept work only from `ask-paper`; treat the state kernel's route-shaped fields as private compatibility data.

For parser execution invoke `paper-parser`, which uses MinerU's hosted precision API and returns the stable extraction bundle. Read [references/paper-types.md](references/paper-types.md) when adapting the map to a paper type.

## Mode outputs

- `scout`: immutable source/hash, extraction report, overview, key author claims with anchors, limitations, research-question relevance, and `advance | park | reject`. Do not create a cognitive profile, knowledge DAG, reading plan, or assessment.
- `study`: all Scout outputs plus only the key mechanism/assumption/tradeoff nodes, a short dependency order, integrative checkpoints, and a critique target.
- `mastery`: the full evidence-anchored map and dependency plan needed for closed-book assessment and delayed retrieval.

## Source gate

Require more than structural parse success. Record page/section coverage, figure/table/equation inventory, two-column reading-order review where applicable, and sampled claim-to-span support checks. Missing core sections, unreadable central figures/formulas/tables, wrong reading order, or unsupported sampled anchors block promotion. Preserve exact source, raw parser output, and warnings. Cloud-upload authorization and credentials remain owned by `paper-parser`; never copy its token into FOCUS state.

Commit generated artifacts through the shared state script. Never edit source identity, paper state, ledgers, locks, or projections directly. Preserve user notes and all prior answers during repair.
