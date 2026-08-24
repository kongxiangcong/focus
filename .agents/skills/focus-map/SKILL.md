---
name: focus-map
description: Create or reuse a source-anchored Reading Plan for one registered Paper in the private FOCUS Reading Workspace. Use for explicit reading-plan mapping, not parsing, translation, navigation, or explanation.
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
