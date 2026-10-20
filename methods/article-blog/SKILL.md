---
name: article-blog
description: Generate a Chinese Reading Blog and self-contained HTML from a registered PDF or HTML Reading Source Parser Bundle. Use for source-based technical reading and explanation, not generic summaries or unsupported promotional copy.
metadata:
  version: article-blog-v2
---

# article-blog

从已发布的 Reading Source Parser Bundle 生成 `blog.md`、`evidence/evidence-map.md` 和单文件 `index.html`。本资源包是唯一运行副本，宿主通过共享 BlogApplication 调用；Core 是正式资产的唯一写入者。

## 输入与边界

输入为已通过校验的 `paper_pdf` 或 `article_html` Parser Bundle。需求依据为 `docs/requirements/reading-blog-guide.md`；运行方法见 `reference/reading-blog-method.md`。网页为二手解读时，区分文章作者转述与原研究结论。

只给原始文件时先完成入库。生成只使用来源与候选目录，不读取或修改 Reading Plan、Cursor、翻译、Reading Records 或用户 Reading Notes。共享写作证据单独保存在博客目录。

## 流程

1. 在候选目录准备 metadata 和来源图片，绑定 Source、Bundle 指纹与 `article-blog-v2`。
2. 按 `reference/reading-blog-method.md` 写带读博客，并生成 `evidence/evidence-map.md`，记录主张、原文锚点、机制、图表、实验证据与边界。使用 `reference/reading-format.md` 的语义排版。
3. 校验正文结构、引用及来源图片；图片须能实际解码并与来源对应。缺失证据标记为待核实，不编造作者、URL、指标或结论。自动校验只证明形态合格，深度与证据缺口以警告记录。
4. 将 `blog.md` 渲染为单页 `index.html`。CSS、脚本、引用图片和 KaTeX 内嵌，无外部资源依赖。内部证据和核查记录留在磁盘，不进入阅读正文。
5. Core 校验候选并原子发布。失败或取消保留 Parser Bundle 和已有合法产物；HTML 失败只重试渲染，正文失败只重试正文后渲染。

## 脚本接口

```powershell
python -B -X utf8 scripts/article2blog.py prepare --workspace <workspace> --source-id <source-id> --candidate <candidate-dir>
python -B -X utf8 scripts/article2blog.py render <candidate-dir>
python -B -X utf8 scripts/article2blog.py check <candidate-dir> --require-html
```

`prepare` 仅建立候选骨架，不复制原始 PDF／HTML。`render` 仅写候选 HTML，默认内嵌图片；`--no-embed-images` 仅用于显式请求链接资源的非发布用途。`check` 返回 `ok`、`errors`、`warnings` 与 `metrics`；正式发布须通过自包含单页校验。

旧版本的额外文件保持原样，当前流程不消费它们；只有明确重新生成或重新渲染才更新现有博客及方法版本。
