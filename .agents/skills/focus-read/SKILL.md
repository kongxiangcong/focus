---
name: focus-read
description: Read the current FOCUS Reading Chunk, translate when applicable, answer connected questions, search the Reading Source, save compact Reading Notes, or advance the Reading Cursor.
---

# Focus Read

Use one natural conversation for reading and explanation. There is no Guide or Explain mode and no FOCUS chat archive. The host conversation carries the dialogue; the Workspace stores only the fixed Reading Plan, Cursor State, cached translation, glossary, and compact per-Chunk Reading Notes.

Resolve `scripts/focus_read.py` relative to this skill directory. At the start of a new conversation, after an explicit restore, or after switching Reading Source, read the small persisted receipt once:

```powershell
python -B -X utf8 scripts/focus_read.py state --workspace <workspace>
```

Use the latest returned `source_id`, `plan_id`, and `chunk_id` as the conversation's hot Cursor receipt. Do not repeatedly reload state during an uninterrupted exchange.

## Read the current Chunk

```powershell
python -B -X utf8 scripts/focus_read.py current --workspace <workspace>
```

Present the source location and bound images with their original captions. If `status=translation_required`, the Plan is not fully prepared: use focus-map preparation operations to fill missing translations without moving the Cursor, then display the saved translation. Ordinary reading uses cached translations. If `status=source_ready`, display Chinese `source_text` directly (paper or article); do not call `retranslate`, and keep `translation=null`. Do not add an unsolicited summary, key-point list, diagram, image-mechanism explanation, or importance judgment.

The current Chunk is the default evidence. For a question, first identify the actual distinction the reader needs, then answer directly at their level. Use the smallest concrete example that preserves the mechanism. Add a diagram only when three or more relationships would otherwise be hard to follow. Distinguish current source evidence, documented intent, inference, and missing evidence; do not blend them. If reliable support is missing, say so instead of guessing.

Follow-up questions, alternative explanations, examples, Reading Source search, external first-party research, and side tasks never move the Cursor. Prefer inference from the conversation over asking the reader to restate context. End long explanations with direct answers to the reader's explicit questions; stop once those answers are usable.

## Search without flooding context

Locate evidence with snippets, then read only the selected range:

```powershell
python -B -X utf8 scripts/focus_read.py search --workspace <workspace> --query <query> --limit 5
python -B -X utf8 scripts/focus_read.py read-range --workspace <workspace> --start <line> --end <line>
```

Do not treat a search hit as proof. Check the selected source range and relevant figure or caption before making a Source-specific claim. External research stays in the host conversation and is not persisted by FOCUS.

## Save only distilled reading value

Reading Notes are short summaries or keywords that remain useful without the dialogue. Do not copy the user/model exchange. Save at most the semantic result of a thread:

- `thought`: a reader idea, connection, or judgment;
- `emphasis`: content the reader explicitly marked important;
- `question`: a worthwhile unresolved question;
- `clarification`: a stable explanation reached through discussion.

Use `origin=user` for a reader-authored formulation and `origin=dialogue` for a distilled joint conclusion. Never record acknowledgements, repeated explanations, side tasks, chatter, model-selected importance, or claims about understanding or mastery.

```powershell
python -B -X utf8 scripts/focus_read.py append-note --workspace <workspace> --expected-plan-id <plan-id> --expected-chunk-id <chunk-id> --kind <kind> --origin <origin> --content-file <note.txt> [--anchor <anchor.json>]
```

Notes are not returned by ordinary state or Chunk reads. Load them only for an explicit review, comparison, or note-generation request:

```powershell
python -B -X utf8 scripts/focus_read.py list-notes --workspace <workspace> --plan-id <plan-id> --chunk-id <chunk-id> [--kinds <kind> ...] [--limit <n>]
```

## Advance only on explicit reading intent

Only an explicit request such as “下一段”, “继续阅读”, or “回到文章继续” may call `continue`. A bare “继续” after an explanation continues the explanation. If its target is genuinely ambiguous, ask rather than advance.

Before advancing, distill any unsaved high-value result into a small JSON list of Notes; otherwise pass no file:

```powershell
python -B -X utf8 scripts/focus_read.py continue --workspace <workspace> --expected-plan-id <plan-id> --expected-chunk-id <chunk-id> [--pending-notes <notes.json>]
```

The command advances exactly one Chunk and does not translate the next Chunk. Repeating an old receipt returns current state without advancing again. After success, use the new receipt and call `current` only when the user wants the next Chunk shown.

Use `update-glossary`, `retranslate`, and `switch` only on explicit requests. A Cursor mismatch means the hot receipt is stale: use the returned current state and do not retry the old write blindly. Phase 1 intentionally provides no migration layer, locks, revisions, event log, or multi-writer protocol.

## Read an ordered Topic

On an explicit Topic Reading request, select the Topic once:

```powershell
python -B -X utf8 scripts/focus_read.py topic <topic-id> --workspace <workspace>
```

This selects the first unfinished Source in `topic.yaml.sources` order and reuses that Source's own Plan, Records, Notes, translation, and Cursor. `continue` advances exactly one Chunk; completing the last Chunk of a Source selects the next unfinished Topic Source. A Source completed through any Topic is already complete everywhere. Only explicit Source reinitialization/rereading resets it. Keep the returned `topic_id`, `source_id`, `plan_id`, and `chunk_id` as the hot receipt; Workspace state persists only `current_topic_id` plus existing per-Source cursors.

## Search and synthesize a Topic

Only search Sources referenced by the selected Topic, with a bounded total result count:

```powershell
python -B -X utf8 scripts/focus_read.py topic-search <topic-id> --workspace <workspace> --query <query> --limit 5
python -B -X utf8 scripts/focus_read.py topic-range <topic-id> <source-id> --workspace <workspace> --start <line> --end <line>
python -B -X utf8 scripts/focus_read.py topic-notes <topic-id> --workspace <workspace>
```

Create a Topic Synthesis only on explicit request. Build a small private JSON draft from source-anchored Topic Reading Notes and the ranges selected with `topic-range`, then send it on stdin:

```json
{
  "selected_ranges": [{"source_id": "DeepStack-paper", "source_lines": [120, 138]}],
  "claims": [
    {
      "text": "A concise cross-source claim.",
      "anchors": [{"source_id": "DeepStack-paper", "source_lines": [120, 138]}]
    }
  ]
}
```

```powershell
python -B -X utf8 scripts/focus_read.py synthesize-topic <topic-id> --workspace <workspace>
```

Every claim must carry at least one Source ID and Source Anchor that exactly matches an anchored Reading Note or selected range. The installed `topics/<topic-id>/synthesis/synthesis-NNN.json` contains only concise claims and anchors. It is explicit derived output: never copy Bundles, Records, dialogue, or source text, and never rewrite it automatically when reading or attaching Sources.

The explicit `current` command also marks the selected source as started in the existing Cursor State, without advancing it. Read-only state/window projections do not mark it. See [Library workflow](../../../docs/library-workflow.md).
