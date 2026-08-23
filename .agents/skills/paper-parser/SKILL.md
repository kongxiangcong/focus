---
name: paper-parser
description: Parse a PDF paper into source-faithful Markdown, images, metadata, and raw structured evidence with MinerU's hosted precision API. Use when a local or remote paper needs extraction before FOCUS mapping, study, or paper-to-blog work; do not use a local MinerU or Docling deployment.
---

# Paper Parser

Produce a reusable extraction bundle without interpreting the paper's scientific claims. This skill uses only MinerU's hosted **precision parsing API**; never install MinerU models or silently switch to Docling, PyMuPDF, the token-free Agent API, or another parser.

## Before uploading

Uploading a local paper sends it to MinerU. Proceed only when the user's request clearly authorizes cloud parsing of that paper. Otherwise identify the file and ask for upload consent. Reject secrets or private documents that the user has not authorized for this service.

Read the API token only from `MINERU_API_TOKEN`. Never request that the user paste it into chat, persist it in the repository, pass it on the command line, or print it. If it is absent, stop with the setup blocker and point the user to MinerU's API management page.

## Run the parser

Resolve `scripts/mineru_precision.py` relative to this skill directory:

```powershell
python -B -X utf8 scripts/mineru_precision.py parse <paper.pdf> --output <staging-directory>
```

Defaults are `model_version=vlm`, formula and table recognition enabled, OCR disabled, and language `en`. Enable OCR only for a scanned or broken-text PDF. Use `--language ch` only for predominantly Chinese material. The API accepts at most 200 MB and 200 pages; the script enforces the size limit and the service enforces page count.

The operation is asynchronous. Preserve the returned non-secret `batch_id` when a timeout or interruption occurs, then resume without re-uploading:

```powershell
python -B -X utf8 scripts/mineru_precision.py resume <batch-id> --source <paper.pdf> --output <staging-directory>
```

Do not treat upload or task creation as parse success. Completion requires a `done` result, a downloaded ZIP, and a validated local bundle.

## Stable bundle

Require these outputs:

- `source.pdf`: byte-identical input copy;
- `paper.md`: non-empty MinerU `full.md` projection;
- `images/`: extracted paper images, possibly empty;
- `metadata.json`: source hash plus parser/API provenance, without credentials or signed URLs;
- `raw/mineru/`: the untouched extracted API ZIP contents, including structured JSON when supplied;
- `validation.json`: machine-readable checks and warnings.

Keep raw output immutable. Never infer authors, venue, claims, or scientific correctness from file names. A structural pass is only permission for a semantic module to perform source spot checks; it is not proof that reading order, equations, tables, or figures are correct.

For FOCUS ingestion, stage the bundle inside the selected workspace and let `paper-map` perform page/section coverage, two-column order, inventory, and claim-to-span checks before promotion. Preserve a failed bundle for diagnosis and never overwrite notes, learner responses, assessments, or evidence.
