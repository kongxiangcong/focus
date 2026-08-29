---
name: focus-map
description: Create, reuse, or explicitly reinitialize a source-anchored Reading Plan for one registered Reading Source in the private FOCUS Reading Workspace.
---

# Focus Map

Map one explicitly selected registered Reading Source into stable, ordered Reading Chunks. Do not invoke a Parser, translate or present source text, move an existing Reading Cursor, or start a reading conversation. Depend only on the common Parser Bundle; do not branch on parser, model, publisher, or Source kind.

Resolve scripts/focus_map.py relative to this skill directory.

## Reuse before drafting

First request the selected Reading Source without a draft:

~~~powershell
python -B -X utf8 scripts/focus_map.py map --workspace <workspace> --source-id <source-id>
~~~

If the result has reused=true, return the existing plan_id and chunk_id. Do not inspect the Reading Source or generate a new draft. Normal reuse preserves the current Cursor.

If the result reports `reading_plan_input_missing`, read the canonical `parser-bundle/content.md` and its referenced images. Build one private UTF-8 JSON draft in memory:

~~~json
{
  "chunks": [
    {
      "section_path": ["Method", "Address Mapping"],
      "source_lines": [420, 447],
      "images": ["images/image-012.png"]
    }
  ],
  "glossary": [["alias address", "别名地址"]]
}
~~~

Then pipe that private draft to the same command over stdin. Do not create a caller-visible draft file:

~~~powershell
python -B -X utf8 scripts/focus_map.py map `
  --workspace <workspace> --source-id <source-id> --scope <scope>
~~~

## Plan rules

- Chunks follow selected source order and cover the selected range continuously.
- Keep formulas, tables, fenced code, images, and adjacent captions intact.
- section_path must be evidenced by source headings.
- source_lines use one-based inclusive line numbers.
- images exactly match local image references inside the range.
- glossary terms are Source terminology needed for stable translation; a Chinese Article may use an empty glossary.
- chunks.jsonl stores only fixed identity, order, source anchor, and images.
- records/<chunk_id>.json starts with translation=null and notes=[].

Do not add summaries, learning objectives, questions, translations, Notes, state flags, hashes, or model evaluation to the draft.

## Explicit reinitialization

Only an explicit reset/rebuild request may run:

~~~powershell
python -B -X utf8 scripts/focus_map.py map `
  --workspace <workspace> --source-id <source-id> --reinitialize --scope <scope>
~~~

A successful reinitialization creates the next plan-NNN directory, fully installs its Chunks, Glossary, and empty Records, then selects its chunk-001 in state.json. Existing Plan directories and Reading Records remain unchanged. A failure leaves the prior Plan and Cursor selected.

Phase 1 intentionally has no compatibility conversion, locks, revisions, event log, or multi-writer recovery.

The JSON is transport only. Never persist it under `tmp/`, emit its path as a receipt, or retain internal staging after success or failure.
