---
name: article-blog
version: article-blog-v1
description: Turn a published Paper Source Parser Bundle into a Chinese Blog Output — a Reading Blog (always), a Value Analysis (only for hardware architecture, DSE, compiler, simulator or performance modeling work), and one self-contained merged index.html. Use for paper interpretation or paper value analysis, not for generic summaries or unsupported promotional copy.
---

# article-blog

生成一份 Reading Source 的 Blog Output：`blog.md`（Reading Blog，必有）、`value-analysis.md`（Value Analysis，条件产物）、`evidence/` 写作证据笔记，以及把两篇 Markdown 合并渲染出的单文件 `index.html`。

本资源包是 **唯一运行副本**。宿主不得复制本目录或其中任何文件；需要行为时只能调用本资源包内的脚本与方法文档。需求层权威文档是 `docs/requirements/reading-blog-guide.md`（带读博客）与 `docs/requirements/paper_architecture_value_guide.md`（论文价值分析）；方法内容与编辑入口在本资源包的 `reference/` 下。

## 输入前提

输入必须是已发布并通过校验的 `paper_pdf` Reading Source：其规范 `parser-bundle/` 含 `content.md`、`metadata.json`、`validation.json`，且 `validation.json.ok=true`、`metadata.json.source_kind=paper_pdf`、`metadata.json.parser=article-parser`。Article Source 不在本轮范围内。若用户只给 PDF，先完成入库（解析 + 发布 Bundle），不要在此处重新解析。

博客生成由共享 Application 编排：**Core 是唯一资产写入权威**，本资源包的脚本只写候选目录或读取产物，不直接发布 `sources/<source-id>/blog/`。

## 命令

脚本路径统一为 `scripts/article2blog.py`：

```powershell
python -B -X utf8 scripts/article2blog.py prepare --workspace <workspace> --source-id <source-id> --candidate <candidate-dir>
python -B -X utf8 scripts/article2blog.py render <blog-dir> [--no-embed-images]
python -B -X utf8 scripts/article2blog.py check <blog-dir> [--require-html]
```

- `prepare`：只读取 `sources/<source-id>/source.yaml` 与该 Source 的 `parser-bundle/`，在**候选目录**中生成 Blog Output 骨架（`evidence/evidence-map.md`、`evidence/implementation-notes.md`、`assets/`、`metadata.json`）。不复制 `source.pdf`，不读取 Workspace `state.json` 或 `sources/<id>/reading/` 下任何阅读资产。骨架提交由 Core 完成。
- `render`：把 `blog.md` 与（存在且适用时的）`value-analysis.md` 渲染为**单文件自包含** `index.html`：样式与脚本内联、引用图片默认 base64 内嵌（`--no-embed-images` 才退回链接）、公式由资源包内置的 KaTeX 渲染（`assets/katex/`，无外网请求）。渲染只写 `index.html`；渲染失败不改写任何 Markdown，也不破坏已发布的旧 HTML。
- `check`：对候选产物跑共用校验器，产出 `ok`、`errors`、`warnings` 与 `metrics`。`--require-html` 追加第④项：两页可渲染、默认打开带读博客、无外链资源、图片已内嵌、公式有渲染器、不适用页显示判定理由。校验只验形态合格；深度与证据缺口只报警告，不冒充质量通过。

失败返回稳定的 `error_id`，不回退到调用方自选输出目录。

## 流程

1. **先建共享写作证据笔记**：`evidence/evidence-map.md` 记录 3–5 项贡献及其原文锚点、方法模块（输入／输出／设计原因／自然替代／代价）、核心公式或算法、关键图表与实验证据、复现设置与缺失项、主张边界。
2. **写 Reading Blog**（`blog.md`）：按 `reference/reading-blog-method.md`。以问题组织材料，解释方法为什么成立，图表与实验只展开与结论有关的部分，区分作者结论、解释性推论与局限。
3. **判定并写 Value Analysis**（`value-analysis.md`，条件产物）：按 `reference/value-analysis-method.md`。论文涉及硬件架构／DSE／编译器／仿真器／性能建模任一方向时生成，固定五段主线：研究问题 → 输入输出 → 模块拆解 → 一个运行例子 → 贡献与边界；不适用则不生成，并在 `metadata.json` 记录 `not_applicable` 与判定理由，HTML 对应页面显示不适用说明。
4. **实现检索（条件执行）**：写 `evidence/implementation-notes.md`。有网时先查论文内代码／项目页／artifact 链接，再查作者或机构官方仓库，源码可访问时沿核心路径静态核查；无网时降级为"仅论文阅读"，记录检索范围与缺口。核查层级（仅论文阅读／静态核查／实际运行）写入该笔记并在 HTML 标注。检索不可用不判步骤失败，不以猜测升级为确定结论。
5. **合并渲染**：`index.html` 两个可切换页面——"带读博客"（默认）与"论文价值分析"。Value Analysis 不适用时，第二页显示不适用说明与 `metadata.json` 中的判定理由（不写成失败）；尚未生成时显示"本次未生成"。CSS／JS 内联、图片 base64 内嵌、公式由内置 KaTeX 渲染（TeX 原文保留为无脚本时的降级显示）；页脚展示 `metadata.json` 中的降级与证据缺口警告、实现核查层级，不出现质量通过字样。证据笔记只留磁盘，不进 HTML。

## 硬边界

- 不发明作者、机构、年份、URL、代码仓库、指标或结果；缺失文献信息标记为待核实。
- 不读取或修改用户私人阅读数据：`state.json`、Reading Plan、Plan Glossary、Reading Record、翻译与 Reading Notes 一律不触碰；写作证据笔记保存在 `blog/evidence/`，与用户 Reading Notes 分开。
- 不创建 Reading Plan 或全文翻译任务。
- 博客失败、取消或引用无效不删除、不要求重传 Parser Bundle。
- 一张图片只有文件名不足以采信；必须实际打开核对图片内容，并与图注、正文一起判断其支持的结论。
