# HTML text and image extraction for a Focus Parser Bundle

Research date: 2026-09-26. This is a source review plus one small local Pandoc probe, not a real-article acceptance result. The target is an authorized article URL or saved HTML that yields `content.md`, local image files, and a canonical `source.html` for Focus's existing Parser Bundle format.

## 中文结论

**推荐先资格化“正文提取 + HTML 转 Markdown + 受控图片收集”这一条显式 HTML 解析路径。** [Readability](https://github.com/mozilla/readability) 可从 DOM 提取文章正文；[Turndown](https://github.com/mixmark-io/turndown) 可转 Markdown；Focus 需要负责把正文实际引用的 `data:`、本地相对路径和允许获取的远端图片落到 `images/image-001.*`，再改写 `content.md` 引用。另一种更省转换代码的试验是 [Pandoc `--extract-media`](https://pandoc.org/MANUAL.html#option--extract-media)，但仍需先选出正文、约束资源访问并规范化路径。本推荐是能力推断，还没有在 Focus 的真实文章样本上比较质量。

[MinerU 精准解析 API](https://mineru.net/apiManage/docs) 确实支持 HTML 并返回 `full.md` 与 `main.html`，但没有承诺把网页图片字节收进 ZIP；本次远端 HTML 批次尚未完成，不能声称现有 MinerU-HTML 路径已达到 PDF 的图片完整性。HTML 正文提取和图片文件收集是两种能力；图片语义理解还需另行验收。

当前 Focus 把 MinerU 的 `main.html` 复制为 `source.html`，而非逐字节保存用户选中的 HTML 原件；若要求与 PDF 原件的追溯性一致，需要先明确 `source.html` 保存原件还是规范化正文快照，再相应调整契约和验收。现有 [Bundle 校验](../.agents/core/reading_workspace.py)只验证本地图片链接，外链图片不会因此成为离线资产。

目标产物沿用现有目录契约（无图文章可没有 `images/`）：

```text
parser-bundle/
  source.html
  content.md
  images/image-001.png
  metadata.json
  validation.json
```

这里的“像 PDF 一样”指正文、实际引用的本地图片和 Core 可验的 Bundle；不意味着 HTML 的外链图片会被任何正文提取器自动下载，或图片内容自动获得视觉语义理解。

## Findings

| Method | Article text and Markdown | Image bytes | Main limit |
| --- | --- | --- | --- |
| [Remote MinerU-HTML](https://github.com/opendatalab/MinerU-HTML) | Its documented job is main-content extraction, with Markdown conversion via MinerU-Webkit. | The public project description does not promise that linked image bytes are downloaded into an archive. Treat `full.md`/`main.html` image references as unverified until a completed API result is inspected. | Remote HTML queue and image packaging remain unproved for Focus. |
| [Mozilla Readability](https://github.com/mozilla/readability) + [Turndown](https://github.com/mixmark-io/turndown) + a Focus-owned image collector | Readability returns a main-content HTML string and metadata; Turndown converts that HTML or DOM into Markdown. | Readability resolves relative image URLs when given the page URL, but neither its documented API nor Turndown performs image downloading. The collector must resolve, fetch, validate, store, and rewrite image references itself. | Gives Focus explicit control, but requires a bounded resource policy and article quality testing. |
| [Pandoc HTML reader](https://pandoc.org/MANUAL.html) with `--extract-media=DIR` | Converts HTML to Markdown. | Pandoc documents that `--extract-media` downloads or copies images/media referenced by the input and rewrites references. | It is a format converter, not a main-article extractor; feed it already isolated article HTML. Network fetch and filtering still need a policy. |
| [Chromium print to PDF](https://playwright.dev/docs/api/class-page#page-pdf) + existing MinerU PDF path | Renders the visible page as PDF and uses the already verified VLM PDF conversion. | Images loaded in the rendered page can appear in the PDF, and MinerU can then extract figures as for other PDFs. | Pagination/print CSS, lazy images, and missing network assets can change the article; the PDF is an intermediate, not the selected HTML original. Use only as an explicit qualified route, not a silent fallback. |
| [Docling](https://github.com/docling-project/docling/blob/main/docs/usage/supported_formats.md) | Accepts HTML and exports Markdown. | Image export modes exist, but HTML input image availability needs a direct version-specific probe; a [reported HTML case](https://github.com/docling-project/docling/issues/3497) yielded image placeholders even with embedded mode. | Do not assume PDF image behavior applies to HTML. |

## Recommended Focus pipeline to test

1. Capture an authorized page as HTML with an origin URL, or accept a saved single-file HTML. If the article is rendered by JavaScript, capture the rendered DOM only after the article and its images appear. Browser capture is an input acquisition step, not a guarantee that image bytes are saved. Playwright exposes [page content](https://playwright.dev/docs/api/class-page#page-content) and [network responses](https://playwright.dev/docs/network). Alternatively, Chromium's [MHTML capture](https://developer.chrome.com/docs/extensions/reference/api/pageCapture) is documented to encapsulate a page and its resources, including images; its archive still needs extraction and article selection.
2. Extract the article subtree with Readability, then convert it to Markdown with Turndown or Pandoc. Preserve the original HTML separately. If using saved HTML, retain its original origin URL so relative links can be resolved; Readability's Node example explicitly requires this.
3. Collect each image actually referenced by the extracted article, including `src`, `srcset`/`picture`, lazy image attributes, `data:` URIs, and local resources in a saved page. Prefer the image selected by the rendered DOM when available. Resolve relative URLs against the original page URL, fetch only allowed `http(s)` origins, enforce size/time/type/count limits, reject non-image responses, and write stable local names. Rewrite Markdown image targets to those local paths. This is a proposed Focus policy, not functionality claimed for Readability or Turndown.
4. Fail or explicitly mark incomplete when a required image cannot be acquired; never silently publish a Bundle that claims offline image completeness. Feed the candidate (`source.html`, `content.md`, local images, metadata) through Focus's existing Core validation/registration boundary. Compare article heading/order, tables, formulas, captions, and every Markdown image reference against the source before claiming quality acceptance.

For a small first probe, the **Readability + Turndown + bounded image collector** path offers the clearest article selection and resource provenance. Pandoc `--extract-media` is a useful alternate conversion/image-acquisition probe after article isolation; its documented ability to download linked media is attractive, but it must not bypass Focus's URL and size rules. Keep the PDF path unchanged and use the same final Bundle contract for both formats. The recommendation is an inference from the cited tool capabilities, not a measured ranking on Focus's article samples.

A local Windows Pandoc probe in `tmp/test-runs/html-media-probe-f63bf016` used `pandoc -f html -t gfm --resource-path <input-dir> --extract-media <dir>`. It extracted both a relative local PNG and a `data:` PNG. Without `--resource-path`, the relative image became a placeholder. GFM output retained a `<figure><img ...></figure>` block and absolute Windows media paths, so Focus would still need deterministic rewriting to local `images/image-001.*` paths and validation. This is a narrow synthetic probe, not article acceptance.

## Evidence and acceptance gaps

- [Readability's documented return value](https://github.com/mozilla/readability) includes processed article HTML and text; its Node example says to pass the page URL to resolve relative image and hyperlink URLs. It recommends sanitizing untrusted output. It is Apache-2.0 licensed.
- [Turndown's documentation](https://github.com/mixmark-io/turndown/blob/master/README.md) covers HTML/DOM to Markdown and custom rules. It does not describe resource downloading. Turndown is MIT licensed per its [repository](https://github.com/mixmark-io/turndown).
- [Pandoc's manual](https://pandoc.org/MANUAL.html#option--extract-media) explicitly says media can be downloaded, copied from disk, or extracted from a container and image references rewritten. Test URL, relative path, and embedded-image cases separately; the manual's broad promise is not evidence that every site permits retrieval.
- [MinerU-HTML's own README](https://github.com/opendatalab/MinerU-HTML) documents extraction and Markdown output, local VLLM/Transformers/OpenAI-compatible backends, and Apache-2.0 licensing. It does not establish an offline image directory in the hosted API ZIP.
- [Docling's format list](https://github.com/docling-project/docling/blob/main/docs/usage/supported_formats.md) confirms HTML input and Markdown output. Its [PDF figure export example](https://github.com/docling-project/docling/blob/main/docs/examples/export_figures.py) only demonstrates image capture for PDF; it cannot establish HTML image capture. A [2026 HTML issue](https://github.com/docling-project/docling/issues/3497) reports placeholders, so test before adoption.

Required live acceptance: run one accessible article URL with remote/lazy images and one saved single-file HTML with embedded `data:` images. Probe relative local assets separately with an HTML-plus-assets directory. Include tables or math where relevant. Verify exact local image references, image bytes, offline rendering, original HTML preservation, Core validation, and real downstream reading. Record failures as input-access, article-selection, media-acquisition, conversion, or Bundle-validation failures.
