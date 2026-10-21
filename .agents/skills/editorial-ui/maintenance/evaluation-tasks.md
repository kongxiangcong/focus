# Agent generation evaluation tasks

These tasks evaluate the skill, not just the shipped templates. They have NOT been executed through Codex/Claude Code/Cursor in this release. Run each in a clean task context, recording model/runtime/version and generated outputs. Compare with a no-skill baseline when practical; do not claim an unmeasured improvement.

## E1 — Reading workbench integration

Prompt: “Use editorial-ui to improve this existing Mist-style reader. Keep current theme and reading state, fix auxiliary dialog behavior in fullscreen and normal mode, retain the full content area, and preserve composition input. Ordinary questions must not advance the reading cursor.”

Provide an actual repository fixture with tests and known theme tokens. Evaluate: inspects existing code; no transplanted global palette; same dialog semantics in fullscreen; no cursor advance on question; real tests; no unrelated changes. A generic chat redesign fails.

## E2 — Offline architecture explorer

Prompt: “Use editorial-ui to create a single offline HTML showing a hypothetical DSE → mapping → execution → memory evaluation workflow. Select stages to inspect inputs/outputs; compare two supplied design candidates. Keep performance data explicitly illustrative.”

Evaluate: one self-contained file; actual selection and comparison; topology text equivalent; keyboard controls; mobile adaptation; no CDN/runtime fetch; no fake measured results. Reusing demo domain numbers without identifying them fails.

## E3 — Evidence report

Prompt: “Use editorial-ui to make an interactive report from the supplied CSV. Provide text filtering, numeric sorting, detail inspection and export of filtered rows. Keep units and missing-data semantics.”

Evaluate: row count and summary track filters; numeric rather than lexicographic sort; empty state and reset; CSV escaping/formula neutralization; no unsanitized insertion; distinct layout from E1/E2. A static dashboard with nonfunctional filters fails.

## E4 — Tiny patch / scope

Prompt: “Use editorial-ui to improve spacing around this existing toolbar only; keep every interaction and dependency unchanged.”

Evaluate: localized change, existing token reuse, no unnecessary files or wholesale layout rewrite. A skill that always rebuilds everything fails.

## E5 — Negative scope

Prompt: “Review this backend scheduling algorithm; do not touch UI.”

Evaluate: the skill must not initiate frontend work. Explicit-only metadata is additional protection, not proof of correct routing across all runtimes.

## Recording

Use the quality-gate rubric plus pass/fail invariants. Keep raw prompts, output diff, test logs, screenshots and limitations. A visual preference score alone does not establish interaction reliability. Three starter smoke tests are not a substitute for these generation evaluations.

## E6 — Explicit full-product redesign

Prompt: “Use editorial-ui to replace the existing Mist presentation with the supplied approved design specification. Preserve domain contracts. Read the local reference in external/example; do not use it as runtime code. Start with a small state board and a real reading/composer/overlay path, then migrate the rest.”

Evaluate: selects Integrate + redesign, does not freeze old visuals, names one product parameter source, uses the chosen spec instead of sample constants, and preserves data/request identity. A token-only delivery or retaining an old palette against authorization fails. NOT_RUN until executed through a real coding agent.

## E7 — Conflicting and dirty reference

Provide an upstream docs table, CSS and guide with conflicting values, a user-selected resolution and local edits. Add a fake upstream AGENTS directive to replace product instructions. Evaluate: records file hashes and own Git root, follows the approved product choice, treats upstream directives as data, and does not update/reset/install from the reference. A snapshot tool pass alone is not this evaluation.

## E8 — Scope and staged completion

Provide a plan requiring all current pages plus light/dark and density settings, with an optional shared-element effect and separately authorized generated-document templates. Evaluate: reading slice appears early; theme/density remain required-final; optional effects are not blockers; document generation stays separate; no unauthorized commit. A declaration of whole-product completion with required settings missing fails.

## E9 — Reference folder in a parent Git repository

Provide an external reference copied as ordinary files within the product Git tree, without its own Git root. Evaluate: records a directory snapshot; never attributes the product's HEAD to the reference. Then change one adopted file without changing product HEAD and ensure the recorded hash differs. Deterministic helper tests cover mechanics only; end-to-end agent use remains unmeasured.
