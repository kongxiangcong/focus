# 01 领域与决策文档

Status: resolved
Type: task
Blocked by: —
Covers: spec §2、§3、§11

## 目标

先把新概念和决定写进项目权威文档，后续工单引用它们。只改文档。

## 要改的文件

### 1. `CONTEXT.md`（术语表）

现有条目位置（约）：Parser Bundle 67–69、Reading Chunk 103–105、Reading Note 131–133、Attached Notes 135–137、Source Anchor 160–162。按现有格式新增/修改：

- **新增 Sentence Locator（句子定位）**：指向某 Parser Bundle 版本下某 Reading Chunk 的一个显示层（原文/译文）中的字符区间，并保存原句引文（exact/prefix/suffix），以便 Plan 重建或译文变化后重新定位。Reading Highlight 与句子备注共用。它不是 Source Anchor：不要求是 content.md 原文子串，不作为证据。
- **新增 Reading Highlight（重点）**：Source 所有的独立记录，只有一个 Sentence Locator，没有文字内容；可创建、删除、撤销，不可编辑。不是 Reading Note，不进入笔记列表，不推进 Reading Cursor。清除讨论与笔记、重置阅读时与 Reading Note 一起清除。界面：重点。
- **修改 Reading Note**：补充两点：(1) 可带 Placement（显示位置），仅决定笔记显示在哪个 Reading Chunk，不表示原文支持；(2) 可带 Sentence Locator（字段 `sentence`），这样的笔记叫**句子备注**，记录为“句子 + 备注”：`content` 是备注文字，原句在 `sentence.quote.exact`；只能由用户在正文直接创建，类型固定为“想法”。任何以纯文本显示笔记的地方都写成「原句」+ 备注。界面：备注（句子备注）/小段笔记（投影到段、无 `sentence`）/整篇笔记（无位置）。
- **新增 Placement**：Reading Note 的可选显示位置，形状同 Source Anchor 但无 quote；由 Host 在讨论绑定了段落引用且模型未给证据锚点时填写。Attached Notes 投影使用 `anchor ?? placement`。
- **修改 Attached Notes**：小段笔记投影依据改为 `anchor ?? placement`，并排除句子备注；句子备注以卡片形式跟随句子显示；Reading Highlight 不进吸附栏。

### 2. 新 ADR `docs/adr/0033-reading-annotations-and-chunk-notes.md`

格式参照 `docs/adr/0031-attached-notes-and-direct-note-entry.md`（frontmatter `status: accepted`）。内容要点（中文）：

1. 背景：用户 2026-10-22 批准原型；讨论“记一下”的笔记因无锚点不显示。
2. 决定：spec §2.1 U1–U7、§2.2 D1–D11 逐条写成段落（不要只贴表格编号）。重点写清“重点是独立实体、备注并入 Reading Note（句子 + 备注）”以及为什么备注不复用 `anchor.quote`（译文层与渲染文本不是 content.md 子串）。
3. 与 ADR 0031 的关系：取代其中“笔记栏为 sticky 列表”“关闭吸附不显示段落笔记”的展示部分；投影规则扩展为 `anchor ?? placement`；直接记笔记合同不变。
4. 与 ADR 0015/0018：Reading Highlight 与句子备注同属 Source；Reset/Clear 一起清除；Fresh Session 保留。
5. 后果：新表 `highlights`；`notes` 表新增 `placement`、`sentence` 两列；UI 新的标注层；`AttachedNotes.tsx` 被替换。
6. 验证：指向本目录工单 13，“本 ADR 不宣称功能已实现”。

### 3. `docs/adr/0031-attached-notes-and-direct-note-entry.md`

文首日期行后加一句：“2026-10-22：展示部分与投影来源由 ADR 0033 修订。”

### 4. `docs/design/README.md`

在“按修改范围选择规范”表“吸附笔记与直接记笔记”行改为：`[ADR 0031] + [ADR 0033]`，说明列补“句内标注（重点/备注）、小段笔记、吸附栏跟随卡片由 0033 定义；视觉数值见 .scratch/reading-annotations/spec.md §7，落地后迁入 focus-tokens.css”。更新日期。

## 验收标准

- 上述四个文件已改，术语在 CONTEXT 中可检索到：Reading Highlight、Sentence Locator、句子备注、Placement。
- ADR 0033 覆盖 U1–U7、D1–D11，每条都能在 spec 中找到对应。
- 不改任何代码。

## 测试

无代码测试。自查：`rg -n "Reading Highlight|Sentence Locator|句子备注|Placement" CONTEXT.md docs/adr/0033-*.md`。

## Comments

2026-10-23：ADR 0032 已用于 PDF parser 选择，本工单及规格引用统一改为 ADR 0033。

## Answer

已更新 CONTEXT 的 Reading Note、Attached Notes 与清除/重置/新会话定义，新增 Sentence Locator、Reading Highlight、Placement；新增 accepted ADR 0033，逐条记录 U1–U7 与 D1–D11，并说明与 ADR 0031/0015/0018 的关系。ADR 0031 与设计入口已链接新决定。只改文档。

验证：`git diff --check` 通过；术语检索完整；ADR 中 U1–U7、D1–D11 共 18 条段落与规格逐条对应；ADR 本地链接核对通过。无代码测试；本工单不宣称功能已实现，功能验收由工单 13 提供。
