---
name: focus-guide
description: Present and navigate the current FOCUS Reading Chunk, record explicit Notes and brief discussions, correct Plan terminology, or replace its cached Chinese translation.
---

# Focus Guide

Present the Reading Chunk selected by the current Paper's Reading Cursor. A display-only invocation never moves the Reading Cursor, changes the current Paper or Plan, or selects an Explanation Session.

Resolve `scripts/focus_guide.py` relative to this skill directory and request the current presentation:

```powershell
python -B -X utf8 scripts/focus_guide.py present --workspace <workspace>
```

If the result has `status=presented`, show its cached Chinese `translation`, section/source location, and every bound image with its original `caption`. Do not regenerate or silently revise the translation.

If the result has `status=translation_required`, translate only `source_text` into faithful Chinese. Apply the returned Plan `glossary` exactly. Preserve headings, paragraphs, equations, tables, captions, references, and technical qualifications. Write only the translation to a private temporary UTF-8 text file, then cache and present it:

```powershell
python -B -X utf8 scripts/focus_guide.py present --workspace <workspace> --translation-file <translation.txt>
```

Normal presentation must not add an image-mechanism explanation, summary, key-point list, importance judgment, or reader evaluation. Display the original image and caption without proactive interpretation. A `reading_completed` result is final for this invocation; do not reset or select another Plan. Other failures contain a stable `error_id`; report the direct message and do not edit Workspace files manually.

## Current Chunk operations

For an explicit save-note request, preserve the reader's original remark in a private UTF-8 file and append it as a Reader Note:

```powershell
python -B -X utf8 scripts/focus_guide.py save-note --workspace <workspace> --content-file <note.txt>
```

For a brief Guided Reading question, answer directly from the presented Chunk. Save the original question and visible answer in separate private UTF-8 files, then append their neutral recap as a Discussion Note:

```powershell
python -B -X utf8 scripts/focus_guide.py record-discussion --workspace <workspace> --question-file <question.txt> --answer-file <answer.txt>
```

The answer and recap state what was asked and answered. They make no claim about reader understanding, misunderstanding, or mastery. A deeper request remains available for an explicit Focus Explain invocation.

Only the reader's explicit instruction that content is important may append an Emphasis Note. Preserve the selected content in a private UTF-8 file and invoke:

```powershell
python -B -X utf8 scripts/focus_guide.py emphasize --workspace <workspace> --content-file <emphasis.txt>
```

Ordinary presentation and model-selected importance never invoke `emphasize`.

For an explicit terminology correction, update the current Plan Glossary. The corrected term appears in future uncached translation requests; cached translations remain stable:

```powershell
python -B -X utf8 scripts/focus_guide.py correct-term --workspace <workspace> --source <source-term> --translation <chinese-term>
```

For an explicit retranslation, translate the current `source_text` faithfully with the returned Plan Glossary, save only the replacement Chinese text to a private UTF-8 file, and replace the current cache:

```powershell
python -B -X utf8 scripts/focus_guide.py retranslate --workspace <workspace> --translation-file <translation.txt>
```

Each operation above leaves the Reading Cursor unchanged. A structured failure leaves the previous Chunk Record and Plan Glossary intact; report it without editing Workspace files manually.

## Continue and restore

Only an explicit Continue Reading request may invoke:

```powershell
python -B -X utf8 scripts/focus_guide.py continue --workspace <workspace>
```

The core first resolves and validates the next Chunk. If it is uncached, the result is `continue_translation_required` and the Reading Cursor remains unchanged. Translate the returned `source_text` with its Plan `glossary`, save only that translation to a private UTF-8 file, then complete the same Continue Reading operation atomically:

```powershell
python -B -X utf8 scripts/focus_guide.py continue --workspace <workspace> --translation-file <translation.txt>
```

Only after the translation is cacheable does the core advance exactly one Chunk and present it. Any validation or write failure preserves the prior cursor and Chunk records. On the final Chunk, Continue Reading retains the Plan, clears the Chunk reference, and returns `reading_completed`. Never infer Continue Reading from a display, question, confirmation, translation, or other non-navigation request.

At the start of a new conversation, restore and present the persisted current Paper, Plan, and Chunk:

```powershell
python -B -X utf8 scripts/focus_guide.py restore --workspace <workspace>
```

Restoration is read-only except for the same explicit first-translation cache step described above. Repeated read-only sessions are harmless.

To explicitly switch the current Paper without changing any Paper-local Plan, Chunk, or Explanation reference:

```powershell
python -B -X utf8 scripts/focus_guide.py switch --workspace <workspace> --paper-id <paper-id>
```

Phase 1 supports one active writer per Paper. It intentionally has no locks, revisions, conflict recovery, or multi-writer guarantees. Do not run translation caching, Continue Reading, or other writes concurrently for the same Paper; multiple read-only presentation/restoration processes are allowed.
