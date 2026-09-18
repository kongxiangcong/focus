---
name: focus-map
description: Create, reuse, prepare translations for, or explicitly reinitialize a source-anchored Reading Plan for one registered Reading Source in the private FOCUS Reading Workspace.
---

# Focus Map

Map one explicitly selected registered Reading Source into stable, ordered Reading Chunks. Do not invoke a Parser, present source text in chat, move an existing Reading Cursor, or start a reading conversation. After mapping, prepare all required translations through Core. Depend only on the common Parser Bundle; do not branch on parser, model, publisher, or Source kind.

Resolve scripts/focus_map.py relative to this skill directory.

## Reuse before drafting

First request the selected Reading Source without a draft:

~~~powershell
python -B -X utf8 scripts/focus_map.py map --workspace <workspace> --source-id <source-id>
~~~

If the result has reused=true, reuse the existing plan_id and chunk_id, then check preparation and fill only missing translations. Do not generate a new draft. Normal reuse preserves the current Cursor.

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
- Each Chunk is the smallest continuous source range that completes one primary comprehension task: include the definitions, mechanism, derivation, or direct evidence needed for that task, and split before a separate task begins.
- Keep formulas, tables, fenced code, images, and adjacent captions intact.
- Set optional `language` on each draft Chunk to `zh`, `en`, or `mixed`, based on its actual prose. Chinese prose with technical English terms is `zh`; substantial foreign prose needs translation (`en` or `mixed`). Existing Chunks without this field inherit bundle language. Chinese papers and articles both skip translation.
- section_path must be evidenced by source headings.
- source_lines use one-based inclusive line numbers.
- images exactly match local image references inside the range.
- glossary terms are Source terminology needed for stable translation; a Chinese Article may use an empty glossary.
- chunks.jsonl stores fixed identity, order, source anchor, images, and optional Chunk language.
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

Library upload and replan prepare the entire Plan but do not start reading. Do not call current/continue to translate chunks. The next explicit reading action starts it. See [Library workflow](../../../docs/library-workflow.md).

## Prepare reading without moving the Cursor

After mapping (including reused plans), call `focus` action `preparation` with `source_id`.
For each pending chunk, call `prepare_chunk` with `source_id`, `plan_id`, `chunk_id`.
Translate only its source_text using relevant_glossary. Preserve formulas, tables,
code, image links, captions and source meaning; add no explanation. For mixed prose,
retain Chinese passages and translate foreign passages. Save immediately using
`prepare_translation` with the same IDs and `translation`. Never replace an existing
translation during preparation. Chinese chunks remain translation=null.

Repeat only missing chunks; after interruption, query preparation again. Finish
only when ready=true. Report completed/total as preparation, not reading progress.
A missing translation is not permission to advance or mark a chunk as read.

For CLI hosts, equivalent operations are:

```text
python scripts/focus_map.py prepare --workspace <workspace> --source-id <source>
python scripts/focus_map.py prepare --workspace <workspace> --source-id <source> --plan-id <plan> --chunk-id <chunk>
# Pipe UTF-8 translation text to stdin:
python scripts/focus_map.py prepare --workspace <workspace> --source-id <source> --plan-id <plan> --chunk-id <chunk> --translation-stdin
```
