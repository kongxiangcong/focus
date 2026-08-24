---
name: focus-explain
description: Create, continue, select, or resume a private FOCUS Explanation Session while keeping it independent from Guided Reading state.
---

# Focus Explain

Use the capability-limited `scripts/focus_explain.py` seam for every Explanation Session write. It exposes no Reading Cursor, Chunk Record, Note, glossary, translation, or Paper-switch operation.

## Start and answer

For an explicit new Explanation Request, preserve the reader's visible question in a private UTF-8 file and create the next sequential session:

```powershell
python -B -X utf8 scripts/focus_explain.py new --workspace <workspace> --question-file <question.txt>
```

The `response_required` result contains the saved role/content-only `history`. Generate the visible answer, save only that answer to a private UTF-8 file, then append it:

```powershell
python -B -X utf8 scripts/focus_explain.py answer --workspace <workspace> --answer-file <answer.txt>
```

The user row is durable before answer generation begins. If generation fails, stop before `answer`; a later `resume` returns `response_pending` with the original question available for retry.

## Continue

For a follow-up question in the selected session, persist the visible question first:

```powershell
python -B -X utf8 scripts/focus_explain.py ask --workspace <workspace> --question-file <question.txt>
```

For an explicit Continue Explanation request, preserve the reader's visible continuation instruction and invoke:

```powershell
python -B -X utf8 scripts/focus_explain.py continue --workspace <workspace> --content-file <continuation.txt>
```

Both return `response_required`. Use the returned saved history as the conversation context, generate the next visible answer, and complete the same two-stage flow with `answer`. Each session alternates visible `user` and `assistant` rows; each row contains exactly `role` and `content`.

## Select and resume

Select an older session only after an explicit reader request:

```powershell
python -B -X utf8 scripts/focus_explain.py select --workspace <workspace> --explanation-id <explanation-id>
```

At the start of a new conversation, resume the selected session:

```powershell
python -B -X utf8 scripts/focus_explain.py resume --workspace <workspace>
```

Resume from the returned saved history alone. The current Reading Chunk is never substituted as an older session's context. A missing session returns a structured error and leaves the prior selection unchanged.

Phase 1 supports one active writer per Paper. Multiple read-only resume operations are safe; serialize session creation, selection, questions, and answers for the same Paper.
