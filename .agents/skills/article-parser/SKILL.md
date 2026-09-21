---
name: article-parser
description: Parse a selected PDF, Chinese article URL, or saved single-file HTML through MinerU into the canonical FOCUS Source Library. Do not bypass access controls or add publisher-specific handling.
---

# Article Parser

This is the only public Parser skill. Invoking it directly with a URL or selected `.pdf`/`.html` file authorizes the required MinerU fetch or upload in that same turn. Do not ask for a second confirmation. Inbox staging is different: it requires the ingestion confirmation before this Parser is called. Read `MINERU_API_TOKEN` from the environment or ignored `.env`; never print or persist credentials or signed URLs.

Resolve `scripts/article_parser.py` relative to this skill directory. Parse immediately, optionally attaching the registered Source to one Topic:

```powershell
python -B -X utf8 scripts/article_parser.py parse-url <url> `
  --workspace <workspace> [--title "<exact title>"] --short-name "<stable work name>" `
  [--topic "<topic title>" --topic-id <topic-id>] [--published-at YYYY-MM-DD]

python -B -X utf8 scripts/article_parser.py parse-file <article.html> `
  --workspace <workspace> [--title "<exact title>"] --short-name "<stable work name>" `
  [--topic "<topic title>" --topic-id <topic-id>] [--published-at YYYY-MM-DD]

python -B -X utf8 scripts/article_parser.py parse-file <paper.pdf> `
  --workspace <workspace> [--title "<exact title>"] --short-name "<stable work name>" `
  [--topic "<topic title>" --topic-id <topic-id>] [--published-at YYYY-MM-DD] `
  [--model vlm|pipeline] [--language en|ch] [--ocr]
```

Choose `short_name` in the same turn after considering the resolved title: remove marketing framing and retain the central object and claim. For the known AI Coding article, use `AI Coding 深水区编码让位人退到决策点`. The exact publisher title remains `title`; the stable Source ID is allocated only after MinerU completes.

If MinerU cannot read the URL because of access controls, login, rate limiting, network failure, or publisher behavior, return the direct typed error and tell the user to save one `.html` file manually. Do not inspect the publisher, automate login, scrape through another route, or add site-specific selectors. WeChat and Zhihu are both Article Sources.

PDF defaults are MinerU `vlm`, formula/table recognition enabled, OCR disabled, and language `en`. Enable OCR only for scanned or broken text. On timeout, retain only the returned task reference, the selected local original when applicable, and minimum registration inputs, then resume without resubmission:

```powershell
python -B -X utf8 scripts/article_parser.py resume <task-id-or-batch-id> --workspace <workspace>
```

Completion requires `content.md`, exactly one byte-identical `source.pdf` or canonical `source.html`, sequential referenced images, metadata with `parser=article-parser`, and validation to install atomically under `sources/<source-id>/parser-bundle/`. An identical PDF original or canonical URL reuses the existing Source and may attach it to another Topic. Successful registration removes task staging; no receipts, polling history, alternate capture, Topic-owned copy, compatibility artifact, Reading Plan, translation, blog, or reading-state advance is created.

Parser candidates and resumable task references live under `parser-tasks/`; only Core installs a validated candidate into the Source Library. Application workflows must call this same implementation rather than asking a model to reproduce its script sequence. HTML retains MinerU-HTML model provenance; Markdown remains a local import outside this skill.
