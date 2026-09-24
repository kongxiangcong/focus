# 阶段 2：入库后生成博客

状态：已 grill 定稿（2026-09-23）。依据：总计划 §1、§3.3、P2；ADR-0011、ADR-0013。依赖：阶段 1。
术语以 CONTEXT.md 为准：Reading Blog（带读博客）、Value Analysis（论文价值分析）、article-blog（统一方法入口）。文档中历史名 paper2blog 一律视为 article-blog。

## 用户结果与范围

已发布 Bundle 进入独立博客步骤，由 article-blog 方法生成两类解释文章及其合并单文件 HTML，用户在 FOCUS 工作台内点击打开查看并核查来源。按阶段 0／1 明确的授权边界启动，不把一次确认解释成任意外发授权。

- **Reading Blog（必有）**：按 `docs/requirements/reading-blog-guide.md` 生成的中文技术细读长文（`blog.md`）。
- **Value Analysis（条件有）**：按 `docs/requirements/paper_architecture_value_guide.md` 生成的架构价值分析文（`value-analysis.md`）。论文不涉及硬件架构、DSE、编译器、仿真器、性能建模任一方向时跳过生成，HTML 对应页面显示"本文不适用架构价值分析"及判定理由。
- **合并 HTML（必有）**：`index.html` 单文件，两个可切换页面——"带读博客"（默认）与"论文价值分析"；全部资源（CSS／JS／图片 base64／公式渲染）内嵌。

写作证据笔记与用户 Reading Notes 分开；生成博客不依赖 Reading Plan、Cursor 或私人阅读记录。首轮只接受 Paper Source（`paper_pdf` Bundle），Article Source 的博客在 5A 补齐。不含外网发布、跨文献综合或 HTML 输入覆盖；阶段 2D 可选此处的一个最小受限 AI 步骤作为探针。

## 产物结构

```
sources/<source-id>/blog/
├── value-analysis.md      # Value Analysis（条件产物，不适用时不存在）
├── blog.md                # Reading Blog（权威中间产物）
├── evidence/
│   ├── evidence-map.md        # 共享写作证据笔记（机制、图表、实验、边界）
│   └── implementation-notes.md # 实现检索与源码核查记录（含核查层级与缺口）
├── assets/                # 引用图片（不复制 source.pdf）
├── metadata.json          # 绑定 Source/Bundle、方法版本、各产物状态与生成时间、警告
└── index.html             # 合并单文件 HTML（最终交付物）
```

两篇 Markdown 是权威中间产物，index.html 只是合并渲染；证据笔记只留磁盘供核查，不进 HTML。

## 方法资源与版本

统一入口 `methods/article-blog/`：`SKILL.md` + `reference/reading-blog-method.md` + `reference/value-analysis-method.md` + `scripts/`（prepare／render／check，由旧博客脚本演化）。资源包内副本为唯一运行副本，禁止宿主私有副本；`docs/requirements/` 下两份 guide 保持需求层权威文档。博客工作流纳入同一 Application，绑定 Source／Bundle 和方法版本。旧 `.agents/skills/paper2blog/` 随资源包建立迁移废弃。

## 触发与状态展示

- 入库时用户勾选"同时生成博客"→ Bundle 发布成功后自动接续；否则 Source 上显示「生成博客」入口手动触发。
- Source 详情处显示三个子状态：价值分析（生成中／已完成／失败／不适用）、带读博客（生成中／已完成／失败）、HTML（生成中／已完成／失败）。生成中不阻塞阅读。
- 重新生成按钮文案按失败粒度：文档失败为「重新生成价值分析」／「重新生成带读博客」，仅渲染失败为「重新生成 HTML」；全部成功后的主动重跑入口统一为「重新生成」。

## 实现检索（条件执行）

Value Analysis 手册要求的官方实现检索按宿主能力条件执行：有网时检索论文内链接与官方仓库并静态核查核心路径；无网时降级为"仅论文阅读"，在 implementation-notes.md 记录检索范围与缺口。核查层级（仅论文阅读／静态核查／实际运行）写入 implementation-notes.md 并在 HTML 该页标注。检索不可用不判步骤失败。

## 验收出口

- 同一有效 Bundle 能生成、展示 Reading Blog 及配套 index.html；适用时同时生成 Value Analysis，不适用时该页显示不适用说明与理由。
- index.html 在 FOCUS 工作台内嵌查看器中可点击打开，两个页面切换、正文、图片、公式、样式正常显示；本地 file:// 打开可用为附带收益，不作验收门槛。
- 重要主张、公式、图表和数值在正文中带可点击引用，可追溯到 Bundle 章节／图表或文末参考文献；区分原文结论、解释性推论和局限。
- 共用校验器检查候选产物：①两篇 md 各自符合指南骨架；②正文引用的每张图片实际解码成功（不凭文件名推断）且来自 Bundle；③文内引用可解析；④平台内嵌查看器可正常渲染两页；⑤深度与证据质量不可自动判定的部分以警告写入 metadata.json 并在 HTML 页脚可见，不冒充质量验收通过。不做人工核查。
- 重试粒度为单篇文档：一篇成功一篇失败时成功篇保留可访问，只重跑失败篇再重渲染 index.html；渲染失败不污染两篇 md。覆盖写，不保留历史版本；多次生成结果以 metadata.json 状态可见。
- 博客失败、取消、无效引用不删除或重传 Bundle；已有合法 HTML 在失败重生成时仍可访问。重复请求不重复发布。
- 没有 Plan 也能完成博客；不创建全文翻译任务、不写用户备注或游标。
