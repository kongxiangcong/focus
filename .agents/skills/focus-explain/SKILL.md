---
name: focus-explain
description: Research, answer, refuse, create, continue, select, or resume a private FOCUS Explanation Session independently from Guided Reading state.
---

# Focus Explain

Use the capability-limited `scripts/focus_explain.py` seam for every Explanation Session write. It exposes no Reading Cursor, Chunk Record, Note, glossary, translation, or Paper-switch operation.

## One explanation turn

First persist the reader's visible input. For an explicit new Explanation Request, create the next sequential session:

```powershell
python -B -X utf8 scripts/focus_explain.py new --workspace <workspace> --question-file <question.txt>
```

For a follow-up in the selected session, invoke `ask`; for explicit Continue Explanation, invoke `continue` with the reader's visible continuation instruction:

```powershell
python -B -X utf8 scripts/focus_explain.py ask --workspace <workspace> --question-file <question.txt>
python -B -X utf8 scripts/focus_explain.py continue --workspace <workspace> --content-file <continuation.txt>
```

Each command returns `response_required` with the saved role/content-only `history`. The user row is durable before research and answer generation begin. A failure after this point leaves it available through `resume` with `status=response_pending`.

Next read [the retrieval policy](../../../research/focus-explain-retrieval-policy.md), save a focused query in a private UTF-8 file, and search the complete parsed Paper:

```powershell
python -B -X utf8 scripts/focus_explain.py research --workspace <workspace> --query-file <query.txt>
```

Inspect every relevant returned section as a scientific unit, including its surrounding paragraphs, equations, tables, images, and original captions. Refine the query and search again when terminology or cross-references point elsewhere in the Paper. This search is Paper-wide and independent of the Reading Cursor.

When `status=external_research_required`, or when Paper evidence leaves a necessary concept unsupported, research external primary material such as the original paper, official specification, first-party documentation, or authoritative source code. Save the temporary research result as JSON with `sources`; each source has exactly `source_type`, `title`, `url`, and the relevant `content`. Use `research_paper`, `official_specification`, `first_party_documentation`, or `authoritative_source_code` as the source type, then validate the evidence:

```powershell
python -B -X utf8 scripts/focus_explain.py external-research --workspace <workspace> --evidence-file <external-evidence.json>
```

When primary research finds no support, use an empty `sources` array plus a factual `insufficient_reason`. Delete the temporary evidence file after the turn. Keep Paper matches and external research in the current reasoning context only: create no vector index, RAG store, persistent source ledger, event log, cross-Paper graph, or user-analysis record.

When evidence is sufficient, synthesize one direct visible answer. Normal answers need no source-by-source labels or mandatory citation list. When the reader explicitly requests sources, include the supporting sources in that visible answer content. Save only the answer in a private UTF-8 file and append it:

```powershell
python -B -X utf8 scripts/focus_explain.py answer --workspace <workspace> --answer-file <answer.txt>
```

When the available Paper and external primary material cannot support a reliable explanation, save a short factual reason in a private UTF-8 file and append a clear refusal:

```powershell
python -B -X utf8 scripts/focus_explain.py refuse --workspace <workspace> --reason-file <reason.txt>
```

The answer or refusal completes the turn as its visible assistant row. It contains no hidden source metadata, guess, fabricated mechanism, or reader evaluation. Each session alternates visible `user` and `assistant` rows; every persisted row contains exactly `role` and `content`.

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
