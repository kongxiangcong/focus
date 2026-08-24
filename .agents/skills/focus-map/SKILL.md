---
name: focus-map
description: Create, reuse, or explicitly reinitialize a source-anchored Reading Plan for one registered Paper in the private FOCUS Reading Workspace.
---

# Focus Map

Map one explicitly selected registered Paper into stable Reading Chunks. Do not invoke Paper Parser, translate source text, present a Chunk, move an existing Reading Cursor, or create an Explanation Session.

## Reuse before generating

Resolve `scripts/focus_map.py` relative to this skill directory. First invoke the map command without a draft:

```powershell
python -B -X utf8 scripts/focus_map.py map --workspace <workspace> --paper-id <paper-id>
```

If it returns an existing `plan_id` with `reused=true`, stop. Ordinary repetition must preserve the current Chunk exactly. If it returns `reading_plan_input_missing`, inspect the selected Paper's canonical `parser-bundle/paper.md` and local images, then prepare a semantic draft.

## Draft the first plan

Write a private JSON draft outside the public repository with this shape:

```json
{
  "chunks": [
    {
      "section_path": ["Method", "Architecture"],
      "source_lines": [20, 42],
      "images": ["images/image-001.png"]
    }
  ],
  "glossary": [["systolic array", "脉动阵列"]]
}
```

Chunks must be ordered, continuous across the selected range, and source-faithful. Keep complete Markdown tables, fenced equations or code, and an image with its adjacent original caption in one Chunk. Bind exactly the local image references inside each range. `section_path` uses source headings. The optional reading scope may omit material such as appendices or references, but never silently omit lines inside the selected range.

Do not put Plan IDs, Chunk IDs, translations, Notes, hashes, timestamps, states, or evaluations in the draft. The deterministic core owns those fields and installs `plan-001/chunks.jsonl`, `glossary.tsv`, and the first selected Reading Chunk only after all validation succeeds.

Install the draft:

```powershell
python -B -X utf8 scripts/focus_map.py map --workspace <workspace> --paper-id <paper-id> --scope "<optional scope>" --draft <draft.json>
```

Treat every nonzero result as blocking for this invocation. The command emits one direct JSON error with a stable `error_id`; do not repair Workspace pointers or Plan files manually.

## Explicit reinitialization

Only an explicit reader request to replace the active Reading Plan may reinitialize it. Inspect the immutable Parser Bundle again and prepare a complete fresh draft under the same source-unit rules. Build the new chunks and Plan Glossary from source; perform no content matching, hash comparison, cursor migration, source-change inference, or merge with the active Plan.

Install and select the next sequential Plan atomically:

```powershell
python -B -X utf8 scripts/focus_map.py map --workspace <workspace> --paper-id <paper-id> --reinitialize --scope "<optional scope>" --draft <draft.json>
```

A successful result has `reinitialized=true`, a new `plan_id`, and its fresh `chunk-001` selected. Existing Plan directories, cached translations, Notes, Explanation Sessions, the current Explanation Session reference, and other Paper pointers remain unchanged. A failure leaves the prior Plan and Reading Cursor selected; report the structured error without editing Workspace files manually.
