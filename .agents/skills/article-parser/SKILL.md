---
name: article-parser
description: Parse a Chinese article URL or an explicitly selected saved single-file HTML through MinerU-HTML into the canonical FOCUS Source Library. Do not bypass access controls or add publisher-specific handling.
---

# Article Parser

Invoking this skill with a URL or selected `.html` file authorizes the required MinerU fetch or upload in that same turn. Do not ask for a second confirmation. Read `MINERU_API_TOKEN` from the environment or ignored `.env`; never print or persist credentials or signed URLs.

Resolve `scripts/article_parser.py` relative to this skill directory. Parse immediately, optionally attaching the registered Source to one Topic:

```powershell
python -B -X utf8 scripts/article_parser.py parse-url <url> `
  --workspace <workspace> [--title "<exact title>"] --short-name "<stable work name>" `
  [--topic "<topic title>" --topic-id <topic-id>] [--published-at YYYY-MM-DD]

python -B -X utf8 scripts/article_parser.py parse-file <article.html> `
  --workspace <workspace> [--title "<exact title>"] --short-name "<stable work name>" `
  [--topic "<topic title>" --topic-id <topic-id>] [--published-at YYYY-MM-DD]
```

Choose `short_name` in the same turn after considering the resolved title: remove marketing framing and retain the central object and claim. For the known AI Coding article, use `AI Coding 深水区编码让位人退到决策点`. The exact publisher title remains `title`; the stable Source ID is allocated only after MinerU completes.

If MinerU cannot read the URL because of access controls, login, rate limiting, network failure, or publisher behavior, return the direct typed error and tell the user to save one `.html` file manually. Do not inspect the publisher, automate login, scrape through another route, or add site-specific selectors. WeChat and Zhihu are both Article Sources.

On timeout, retain only the returned task reference and minimum registration inputs, then resume without resubmission:

```powershell
python -B -X utf8 scripts/article_parser.py resume <task-id-or-batch-id> --workspace <workspace>
```

Completion requires `content.md`, `source.html`, sequential referenced images, metadata, and validation to install atomically under `sources/<source-id>/parser-bundle/`. An identical canonical URL reuses the existing Source and may attach it to another Topic. Successful registration removes task staging; no receipts, polling history, alternate capture, Topic-owned copy, or compatibility artifact remains.
