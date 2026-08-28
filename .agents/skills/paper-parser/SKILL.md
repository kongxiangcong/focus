---
name: paper-parser
description: Parse a PDF paper into one compact parser-bundle with source-faithful Markdown, sequentially named images, metadata, and validation through MinerU's hosted precision API. Use when a local or remote paper needs extraction before FOCUS registration, mapping, or paper-to-blog work; do not use a local MinerU or Docling deployment.
---

# Paper Parser

Produce a reusable extraction bundle without interpreting the paper's scientific claims. This skill uses only MinerU's hosted **precision parsing API**; never install MinerU models or silently switch to Docling, PyMuPDF, the token-free Agent API, or another parser.

The API control plane uses Python's standard library. Signed object-storage uploads and result downloads use the system `curl` executable because those hosts can reset Python `urllib` transfers on Windows; signed URLs are passed through standard input and are never persisted or placed in process arguments.

## Before uploading

Uploading a local paper sends it to MinerU. Proceed only when the user's request clearly authorizes cloud parsing of that paper. Otherwise identify the file and ask for upload consent. Reject secrets or private documents that the user has not authorized for this service.

Read the API token from the process environment variable `MINERU_API_TOKEN`; when it is empty or absent, fall back to `MINERU_API_TOKEN` in `.env` under the command's current working directory. Keep `.env` ignored by Git and never commit it. Never request that the user paste the token into chat, pass it on the command line, or print it. If both sources are empty, stop with the setup blocker and point the user to MinerU's API management page.

## Run the parser

Resolve `scripts/mineru_precision.py` relative to this skill directory:

```powershell
python -B -X utf8 scripts/mineru_precision.py parse <paper.pdf> `
  --workspace <workspace> --title "<paper title>" --topic "<topic title>" --authorize-upload
```

Defaults are `model_version=vlm`, formula and table recognition enabled, OCR disabled, and language `en`. Enable OCR only for a scanned or broken-text PDF. Use `--language ch` only for predominantly Chinese material. The API accepts at most 200 MB and 200 pages; the script enforces the size limit and the service enforces page count.

The operation is asynchronous. Preserve the returned non-secret `batch_id` when a timeout or interruption occurs, then resume without re-uploading:

```powershell
python -B -X utf8 scripts/mineru_precision.py resume <batch-id> `
  --workspace <workspace>
```

The deterministic core keeps a private task-local copy of the authorized PDF, so resume cannot accidentally pair the remote result with a different local file.

Do not treat upload or task creation as parse success. Completion requires a `done` result, a transient downloaded ZIP, and one validated `parser-bundle/`. Do not create `parser-bundle-verified`, retain `result.zip`, or render PDF pages as parser outputs.

## Stable bundle

Require these outputs:

- `source.pdf`: byte-identical input copy;
- `paper.md`: non-empty MinerU `full.md` projection whose local image links point into `images/`;
- `images/`: only images referenced by `paper.md`, renamed `image-001.*`, `image-002.*`, and so on by first-reference order;
- `metadata.json`: parser/API provenance and the non-secret batch reference, without credentials, signed URLs, or content hashes;
- `validation.json`: machine-readable checks and warnings.

The MinerU ZIP and extracted raw tree are transient and must be discarded after normalization. Never infer authors, venue, claims, or scientific correctness from file names. A structural pass is only permission for a semantic module to spot-check `source.pdf`; it is not proof that reading order, equations, tables, or figures are correct.

For FOCUS, install the single `parser-bundle/` directly inside a new Paper and register the Paper, Topic membership, and its empty entry in `state.json` only after structural validation succeeds. A repeated parse allocates the next readable Paper ID; reuse an existing Paper only with the explicit `reuse --paper-id ...` operation. Preserve the non-secret task reference for resume, but discard incomplete staging. Parser operations own only Parser Bundle and registration artifacts and leave Reading Plans, Glossaries, and Reading Records unchanged.

To add an already registered Paper to another Topic without uploading or parsing again:

```powershell
python -B -X utf8 scripts/mineru_precision.py reuse `
  --workspace <workspace> --paper-id <paper-id> --topic "<topic title>"
```
