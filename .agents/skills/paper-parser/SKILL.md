---
name: paper-parser
description: Parse a selected PDF through MinerU hosted precision API and register one canonical Paper Source. Do not use a local MinerU or alternate parser.
---

# Paper Parser

Invoking this skill with a selected PDF authorizes its MinerU upload in the same turn. Do not ask for a second confirmation. Use only MinerU's token-authenticated precision API; never install local models or switch to Docling, PyMuPDF, or the token-free Agent API.

Read `MINERU_API_TOKEN` from the environment, falling back to ignored `.env` in the command working directory. Never request the token in chat, print it, pass it on the command line, or persist it. Signed upload and download URLs travel through system `curl` stdin.

Resolve `scripts/mineru_precision.py` relative to this skill directory:

```powershell
python -B -X utf8 scripts/mineru_precision.py parse <paper.pdf> `
  --workspace <workspace> [--title "<exact title>"] --short-name "<stable work name>" `
  [--topic "<topic title>" --topic-id <topic-id>] [--published-at YYYY-MM-DD]
```

Choose a recognized stable work name when evidenced by the paper, such as `DeepStack`, rather than mechanically compressing the complete title. Title resolution is explicit title, parsed H1, then local filename. Source ID allocation happens only after the Bundle validates and uses `<short-name>-paper`.

Defaults are `model_version=vlm`, formula and table recognition enabled, OCR disabled, and language `en`. Enable OCR only for scanned or broken text and `--language ch` only for predominantly Chinese material. The script enforces the 200 MB source limit; MinerU enforces its page limit.

On timeout, preserve the non-secret batch reference and task-local PDF, then resume without re-uploading:

```powershell
python -B -X utf8 scripts/mineru_precision.py resume <batch-id> --workspace <workspace>
```

Completion requires a byte-identical `source.pdf`, non-empty `content.md`, only referenced sequential images, minimal metadata, and passing `validation.json`. The Source Library atomically installs the Bundle, exact title, stable short name, final Source ID, optional ordered Topic reference, and empty per-Source Cursor entry. Identical PDF bytes reuse the existing Source; no Source or Topic asset is copied.

To attach an existing registered Paper to another Topic without parsing:

```powershell
python -B -X utf8 scripts/mineru_precision.py reuse `
  --workspace <workspace> --source-id <source-id> --topic "<topic title>"
```

Discard result ZIPs, extraction trees, successful task staging, request archives, polling history, receipts, and alternate representations. Parser operations never modify Reading Plans, Records, Notes, or Synthesis.
