# Evidence-grounded paper-to-blog method

## Four layers

Keep these artifacts distinct:

1. MinerU raw output: layout, text, figures, tables, equations, and structured JSON.
2. Parser bundle: stable `paper.md`, `images/`, `metadata.json`, and source identity.
3. Evidence map: claims and writing decisions anchored to observable paper evidence.
4. Blog: a reader-oriented causal explanation. HTML or publishing is optional post-processing.

The parser preserves evidence; it does not decide what the paper means. The evidence map fixes the source basis before fluent prose can hide missing reading.

## Method explanation

For each material module:

1. State the local contradiction it solves.
2. Define inputs, outputs, state, and assumptions.
3. Explain the causal or dataflow trace.
4. Introduce the formula or algorithm and define every variable.
5. Explain why a natural alternative is insufficient.
6. Connect the choice to a figure, table, ablation, proof, or measurement.
7. State added complexity, resource cost, failure condition, or scope boundary.

Formula count is not depth. If the paper is empirical or non-mathematical, use a precise protocol, pseudocode, interface, measurement model, or complexity argument instead.

## Figures and experiments

For an architecture figure, explain modules, arrows, data/control flow, and where the contribution sits. For multi-panel figures, explain each panel's role. For curves, explain axes, baseline, trend, turning points, anomalies, and plausible causes.

For a key table, establish metric direction, comparison conditions, strongest baseline, largest differences, likely mechanism, and unresolved confounders. State the hypothesis each experiment tests before reporting numbers. Never use a result to support a broader claim than its setup permits.

## Anti-hallucination checks

- Repair line wraps and hyphenation, but do not silently repair ambiguous formulas or numbers.
- Confirm important numbers in a table, caption, or surrounding text.
- Confirm figure meaning from the image, caption, and body reference together.
- Label instructional synthesis and criticism as inference.
- Use external background only for prerequisites; it cannot replace the paper's evidence.
- Keep quotations brief and link/cite their source.

## Reader completion test

A successful reader can explain the addressed constraint, why this design was chosen, how state or data flows through it, what the key equation constrains, what the decisive evidence proves and does not prove, which component causes the improvement, and where reproduction is likely to fail.
