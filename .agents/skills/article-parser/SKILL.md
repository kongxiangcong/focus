---
name: article-parser
description: Parse a Chinese article URL or an explicitly authorized saved single-file HTML through MinerU-HTML into the common FOCUS Parser Bundle. Do not bypass access controls or add publisher-specific handling.
---

# Article Parser

Use MinerU's token-authenticated precision API with `model_version=MinerU-HTML`. Do not inspect the publisher, automate a login, bypass anti-bot controls, or add site-specific selectors. Read `MINERU_API_TOKEN` from the environment or the existing ignored `.env`; never print or persist credentials or signed URLs.

Resolve `scripts/article_parser.py` relative to this skill directory.

For an accessible article URL, require explicit authorization for MinerU to fetch it:

```powershell
python -B -X utf8 scripts/article_parser.py parse-url <url> `
  --workspace <workspace> --title "<title>" --topic "<topic>" --authorize-cloud-fetch
```

If MinerU cannot read the URL because of access controls, login, or rate limiting, return the direct error and tell the user to save one `.html` file manually. Do not attempt another fetch path. Upload that file only after explicit authorization:

```powershell
python -B -X utf8 scripts/article_parser.py parse-file <article.html> `
  --workspace <workspace> --title "<title>" --topic "<topic>" --authorize-upload
```

On timeout, retain only the one returned `task_id` or `batch_id` plus the minimum task-local registration inputs, and resume without resubmission:

```powershell
python -B -X utf8 scripts/article_parser.py resume <task-id-or-batch-id> --workspace <workspace>
```

Completion requires MinerU's `full.md`, `main.html`, and referenced images to normalize as `content.md`, `source.html`, and sequential `images/image-NNN.*`, followed by common Bundle validation and Source registration. Discard the result ZIP, extraction tree, and task directory after success. Do not retain request/response archives, polling history, receipts, or alternate source captures.
