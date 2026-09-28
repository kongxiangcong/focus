---
name: article-parser
description: Parse a selected PDF with server-side local-first MinerU auto selection or a complete saved SingleFile HTML locally into the canonical FOCUS Source Library.
---

# Article Parser

This is the only public Parser skill. Use the repository Python environment, install `host/requirements.txt`, and run `pnpm install --frozen-lockfile` at the repository root for Mozilla Readability and jsdom. HTML extraction is local and does not execute page scripts or fetch resources. PDF selection happens on the backend server. It probes local MinerU 4.0.8 Standard V1 health, tier and ZIP capabilities before submission. When local is usable it requires no remote token or cloud upload. Only confirmed absence or incompatibility permits mineru.net precision v4 with `MINERU_API_TOKEN` in the process environment or ignored `.env`. Starting, busy or temporarily unreachable local service means wait and retry locally. Explicit `FOCUS_PDF_PARSER=local-mineru|cloud` overrides auto for diagnostics.

Resolve `scripts/article_parser.py` relative to this skill directory:

```powershell
python -B -X utf8 scripts/article_parser.py parse-file <source.pdf-or-article.html> --workspace <workspace> [--title "<exact title>"] [--short-name "<stable work name>"] [--topic "<topic title>" --topic-id <topic-id>]
```

For web articles, first obtain a complete user-saved SingleFile `.html` with embedded images. A URL alone returns `saved_html_required`; MinerU-HTML submission and HTML remote-task resume are retired. Do not bypass access controls or add publisher-specific capture adapters.

The local extractor uses Mozilla Readability to locate the article body, restores the corresponding original DOM container to retain figures, removes structural interface noise, and converts the article to Markdown. Only body images are decoded into sequential local files. Missing images, placeholders, ambiguous boundaries, unsupported embedded media or meaningful inline SVG stop publication with a typed error. No-image articles are legal. Inspect the output against the selected source before claiming content-quality acceptance.

Choose a stable short name from the central subject, leaving the publisher's exact title in Source Title. Saved original HTML bytes remain unchanged in `source.html`; `content.md` contains the cleaned article. A canonical origin URL reuses the same Source; URL-less HTML uses the original fingerprint. Extraction provenance is `parser=article-parser`, `model_version=local-html-v1`, without a fabricated remote task ID.

Remote PDF defaults remain MinerU `vlm`, language `en`, OCR disabled. Local requests use Standard tier with its own OCR mode and V1 contract. Retain the printed CLI task ID after timeout and resume without selecting another backend or resubmitting:

```powershell
python -B -X utf8 scripts/article_parser.py resume <task-id> --workspace <workspace>
```

Completion requires Core publication of `content.md`, exactly one original (`source.pdf` or `source.html`), referenced local images, `metadata.json`, and `validation.json` under `sources/<source-id>/parser-bundle/`. The public CLI uses Core Source Library registration; Inbox uses the same parser implementation through IngestionApplication and guarded IngestionCore publication. No Reading Plan, translation, blog or reading-position advance is created by parsing. Respect the active Workspace owner's serialization; do not publish concurrently with a running Host.
