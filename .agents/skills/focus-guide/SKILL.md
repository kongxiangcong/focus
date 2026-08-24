---
name: focus-guide
description: Present the current FOCUS Reading Chunk as a stable cached Chinese translation with its bound source images and captions. Use for Guided Reading display; navigation, notes, and discussion operations are added by their own tickets.
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
