---
name: paper2blog
description: Turn a paper-parser evidence bundle into a source-faithful Chinese technical blog with an evidence map, causal method explanation, figure and experiment analysis, limitations, and traceable references. Use for paper interpretation or paper-to-blog writing, not for generic summaries or unsupported promotional copy.
---

# Paper to Blog

Create a publishable Chinese technical explanation from parsed paper evidence. Reorganize the paper around why its design works; do not translate section by section or inflate the abstract.

## Establish the evidence workspace

Input must be a registered Paper whose canonical `parser-bundle/` contains `paper.md`, `metadata.json`, `validation.json`, and `images/`. Require `validation.json.ok=true` and `metadata.json.parser=mineru-precision-api`. If the user supplies only a PDF, invoke `paper-parser` first and honor its MinerU upload-consent and token boundary.

Resolve `scripts/paper2blog.py` relative to this skill directory and prepare the Paper-local Blog Output:

```powershell
python -B -X utf8 scripts/paper2blog.py prepare --workspace <workspace> --paper-id <paper-id>
```

The command resolves only `papers/<paper-id>/paper.yaml` and that Paper's canonical `parser-bundle/`, then atomically creates `papers/<paper-id>/blog/`. It does not read Workspace pointers or anything under `reading/`. The Blog Output contains `paper.md`, `metadata.json`, `assets/`, and `evidence-map.md`; it does not copy or read `source.pdf`. Never invent author, venue, URL, code repository, metric, or result.

Read [references/writing-method.md](references/writing-method.md) before writing. Inspect the actual architecture, pipeline, and decisive experiment images; filenames and captions alone are insufficient.

## Build the evidence map first

Complete `evidence-map.md` before drafting prose. Require:

- 3–5 contributions, each tied to a section, figure, table, equation, or reported number;
- 2–6 method modules with inputs, outputs, design reason, natural alternative, and cost;
- 2–5 material formulas, or pseudocode/interface/complexity for a non-formula paper;
- at least one key figure and one key table or structured experimental result;
- reproduction settings and explicit missing details;
- claim boundaries: what each result supports and does not support.

If a required evidence class genuinely does not exist, say so and use the documented substitute. Do not fabricate it to satisfy a template.

## Write the blog

Write the article as `blog.md`. Organize each core design through:

```text
problem -> constraint -> why the natural alternative fails -> design choice
        -> module/formula mechanics -> figure/table evidence -> cost and boundary
```

Use a paper-specific Mermaid overview, not a generic problem-to-result flow. Explain variables before formulas. For each central figure, explain modules/arrows/axes and the claim it supports. For each key table, explain metric direction, strongest baseline, largest differences, likely causes, fairness, and confounders. Separate author claims, reported evidence, and your own inference.

End with concrete limitations, executable open questions, a copyable citation/BibTeX block when metadata supports it, and numbered clickable references. Mark missing bibliographic facts for verification instead of guessing. Then render the final static artifact:

```powershell
python -B -X utf8 scripts/paper2blog.py render <workspace>/papers/<paper-id>/blog
```

Rendering requires local Node.js and `marked`; the script discovers the Codex bundled runtime or accepts `MARKED_CLI`. The final required files are `evidence-map.md`, `blog.md`, and `blog.html`. External publishing remains a separate user-authorized task.

## Validate

Run:

```powershell
python -B -X utf8 scripts/paper2blog.py check <workspace>/papers/<paper-id>/blog
```

Treat failed parser-bundle links, placeholders, a missing evidence map, an empty final article, no causal method detail, no limitations, a missing/stale `blog.html`, or a copied `source.pdf` as blocking. Warnings about length or absent images require judgment based on the paper, not mechanical padding.

Preparation and validation failures return one JSON error with a stable `error_id`. Do not fall back to a caller-selected output directory for registered Papers. Blog generation has no Reading write capability: never read or modify `pointers.yaml`, Reading Plans, Chunk Records, Plan Glossaries, translations, Notes, or Explanation Sessions.
