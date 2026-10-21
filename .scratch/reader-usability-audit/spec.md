# 阅读界面可用性修复：问题、方案与实施

Status: needs-info
Branch base: `feat/article-structure-guide`（审计时 HEAD `61095a8`）
范围：生产阅读页（`appearance="mist"`）及其所需的 Host 笔记接口。主要代码：`ui/packages/reader-ui/src/`、`ui/packages/reader-contracts/src/index.ts`、`ui/apps/standalone/src/adapters/`、`host/`。

---

## 2026-10-21 后续修订：段落笔记与功能区

本节依据用户当前明确要求，覆盖 §3.4 的同名入口、窄屏布局及删除段落讨论入口的旧条款；不扩展本次修改到其余未完成工单。

- 功能区“吸附笔记”简称“笔记”。普通窗口与全屏均能打开，以阅读区域实际可用宽度决定布局。
- 空间足够时保留原文行宽，笔记在右侧；空间不足时在阅读段内部按正文 3/4、笔记 1/4 分栏，替代原先段后折叠块。
- 展示该段对应的 Source Notes，按原文 Bundle 和行范围投影。讨论回复始终留在阅读流。
- 笔记栏保留“就这段讨论”，展开输入框并引用该段，不推进阅读进度。现有笔记的编辑／撤销可从旁注进入资料栏完成。
- “回到最新”“返回刚才位置”“回到进度”和回看提示进入功能区，不再覆盖正文。功能区移除“新会话”，将位置与提示归为一组、常用操作归为一组，小屏换行。
- 新增 `note-projection`、`AttachedNotes`，更新浏览器回归 `tests/reading_attachment_browser.mjs`。本次不宣称工单 08 的直接笔记编辑器或真实 Knowledge Base 验收完成。
- 验证：类型检查、Reader UI 113 项测试、Standalone 156 项测试和生产构建通过。Chromium 使用合成 Source Anchor 数据验证 1600×1000、1440×900、1280×800、1024×768、720×900、390×844 的布局与功能区，检查普通／全屏切换、3:1 比例、原文行宽与阅读位置保持、长笔记独立滚动、历史段落提问引用、开关持久化、减少动效、浅／深色及无页面错误。
- 浏览器复跑：先在仓库根目录运行 `pnpm reader:dev`，再设置 `FOCUS_PLAYWRIGHT_MODULE` 与 `FOCUS_CHROMIUM_EXECUTABLE` 执行 `node tests/reading_attachment_browser.mjs`。该脚本使用 Vite 测试页，不依赖私人 Knowledge Base 或 AI。

## 1. 已定的产品决定

| # | 决定 |
| --- | --- |
| D1 | Reading Note 仍然属于 Source。界面按 Source Anchor 的原文行范围，把笔记显示在对应 Reading Chunk 旁边；笔记不属于 Chunk 或 Plan。 |
| D2 | “吸附讨论”改为“吸附笔记”。讨论永远留在阅读流里，吸附位置只放笔记。 |
| D3 | 行宽改为 4 个按字数定义的离散挡位，“标准”约 42 个汉字一行（见 §3.3）。 |
| D4 | 正文里直接显示缩小的图，图旁边放“查看图 N”按钮。 |
| D5 | 同意扩展 Host 合同：新增不经过 AI 的“直接记笔记”接口；每个段落都有手动“记笔记”入口，用户可以直接在段落旁边写笔记。 |

---

## 2. 问题清单（审计证据）

证据来源：源码阅读，加上在 `knowledge-base/` 副本上起的隔离 Host（`127.0.0.1:8799`），用 Chromium 打开《Early Silicon of Raptor》实测，视口 1600×1000 与 1280×800。**[实测]** 表示浏览器复现；**[源码]** 表示只由代码推出。

| ID | 优先级 | 问题 | 证据 |
| --- | --- | --- | --- |
| P1 | P0 | 段落缩略图、从缩略图打开的放大图全部损坏。根因：Host 要求每个业务请求带 `instance`（`X-FOCUS-Instance` 头或 `?instance=`），缺失时 `workbench.require_instance()` 返回 400。前端用 Markdown 相对路径拼图片地址时（`figures.ts` 的 `imageUrl()`、`MarkdownContent.tsx` 的 `urlTransform`）没带这个参数；`chunkFigures()` → `mergeFigures()` 又让 Markdown 扫描结果优先，丢掉了 Host 投影的带参地址。资料抽屉因为把 `view.figures` 放在最前，所以显示正常。AI 回答中的相对路径图片也受影响。 | [实测] `400 /reader/assets/…/images/image-001.jpg`；同图带 `?instance=` 时 200 |
| P2 | P1 | 正文里的图被替换成“查看插图 image-001.jpg”文字按钮，段落底部缩略图条又重复列一遍；没有图号时用文件名当标签；缩略图 92×58 且 `object-fit:cover`，会裁掉宽幅图表；抽屉网格同样裁切。 | [实测] 2 张图出现 4 个入口 |
| P3 | P1 | 行宽：标准 1040px ≈ 58 字一行；滑块 640–1440、步长 20、轨道 246px，每档约 6px；拖 10px 从 1040 跳到 1320；每个 `input` 事件都调 `preserveReading()` 并整列重排；“窄”“宽”不可点；上限与可用宽度无关；`data-reading-width` 写死为 `"standard"`。 | [实测] |
| P4 | P1 | 吸附讨论：阅读区小于 1240px 时开着也不生效，只在 `title` 里说明（1280 视口即如此）；生效时原文从 1040px 压到 721px；只吸附带引用的消息；sticky 长回答超出视口。 | [实测] |
| P5 | P1 | 记笔记只能通过 AI：Host 没有创建接口；“存为笔记”实际是发消息“请把下面的回答记下来…”，要等一轮 AI，还会进入讨论历史，运行中不可用。不能选中原文记笔记，也不能手写。笔记面板默认折叠在 `<details>` 里；列表不显示段落、引文、类型，不能跳回原文；界面完全没用 `SourceNote.anchor`。 | [源码] + [实测] |
| P6 | P1 | 打开资料抽屉时正文从 1040px 缩到 814px（1280 视口下 597px），违反 ADR 0026“平移而不改宽度”。原因是写死的 `standard` 命中“为抽屉让出一列”的规则，`--reader-shift` 被 `transform:none` 关掉。 | [实测] |
| P7 | P1 | 非聚焦段落的“查看原文/译文”“引用提问”在 `opacity:0` 下不可见，但仍可点击、可 Tab 到；触屏上几乎无法发现。 | [源码] |
| P8 | P1 | 功能区控件过多，位置徽标在 1024 级宽度下被截断；宽幅、吸附这类低频设置与“继续”同级常驻。 | [实测] |
| P9 | P2 | 讨论列表显示 `讨论 1 · <sourceId>`；进度列表显示 `chunk-002`。 | [源码] |
| P10 | P2 | 破坏性操作确认方式三种并存：`window.confirm`（重新阅读、删除阅读记录）、无确认（新会话）、可撤销（删除笔记）。 | [源码] |
| P11 | P2 | 选区按钮“引用所选提问”可能压在底部功能区上；滚动即消失。 | [源码] |

---

## 3. 方案

### 3.1 图片地址（P1）

图片 URL 的实例参数只在一处补齐：

- `figures.ts` 新增 `withAssetInstance(url, instanceId)`：只对 `/reader/assets/` 与 `/reader/historical-assets/` 开头且没有 `instance` 参数的地址追加 `?instance=`（已有查询串时用 `&`）。`imageUrl(src, sourceId, instanceId?)` 末尾调用它。
- `imageIdentity()` 已经忽略同源地址的查询串，所以身份比较保持不变；需要补测试锁住这一点。
- `FocusReader` 从 `view.workspace?.instanceId` 取实例号，经 React Context（新文件 `asset-context.ts`，导出 `AssetInstanceContext`）传给 `MarkdownContent`、`ReadingChunk`、`FigurePanel`、`FigureViewer`。`MarkdownContent` 的 `urlTransform` 改为调用 `imageUrl()`，不再自己拼地址。
- `mergeFigures` 对同一身份的图，如果已有地址没有 `instance` 而新地址有，就换成新地址（在 Context 缺失的测试环境里依然正确）。

### 3.2 正文图片（P2，D4）

- 被识别为“图”的图片，在正文原位置渲染为 `figure.reader-inline-figure`，内部依次是：
  - 缩小图：`max-height: var(--reader-inline-figure-h)`（新 token，默认 280px），`max-width:100%`，`object-fit:contain`，左对齐；整张图是一个按钮，点击打开 `FigureViewer`，可访问名称为“放大图 N”。
  - 图旁动作行，放在图下方右侧：一个“查看图 N”按钮，行为与现在的 `showFigure` 相同，即在资料抽屉中固定并选中这张图。
- 删除 `ReadingChunk` 底部的 `.reader-thumbnail-strip`，同一张图在一段里只出现一次。
- 标签：有图号时用“图 N”；没有图号时用“第 {chunk.index} 段插图 {k}”，k 从 1 开始，按该段内出现的顺序编号。修改 `mergeFigures` 的 label 生成方式，让它接收可选的段落序号。
- 资料抽屉网格缩略图改为 `object-fit:contain`，背景用 `--reader-surface-1`。
- 表格、公式、代码中的受保护图片保持现有逻辑（`protectedIds`），不进入这条路径。

### 3.3 行宽挡位（P3，D3）

- 挡位以“每行汉字数 × 正文字号”定义，字号设置改变时行宽自动跟随：

  | id | 名称 | 每行字数 | 18px 正文时 |
  | --- | --- | --- | --- |
  | `narrow` | 窄 | 36 | 648px |
  | `standard` | 标准（默认） | 42 | 756px |
  | `wide` | 宽 | 50 | 900px |
  | `full` | 超宽 | 62 | 1116px |

  `--reader-column = calc(<字数> * var(--reader-reading-size))`；字数表放在 `typography.ts`，作为唯一来源。
- 偏好键 `focus.readingMeasure` 保存挡位 id。迁移：若只有旧键 `focus.readingWidth` 或 `focus.standardWidth`，按当前字号换算到最近挡位，写入新键后删除旧键。
- 可用性：某挡位所需宽度（列宽 + 48px 内边距；开启吸附笔记旁注时再加旁注宽度，见 §3.4）大于阅读区宽度时，该挡位禁用，提示“窗口宽度不足”。保存的挡位放不下时，**显示**为能放下的最大挡位，但不改写偏好；窗口变宽后自动恢复。
- 控件：功能区“宽幅”改名“行宽”，弹层内是 4 段的分段按钮（`role="radiogroup"`，每段 `role="radio"`），左右方向键切换并立即生效，Esc 关闭并把焦点还给“行宽”按钮。每次切换只调用一次 `preserveReading()`。删除滑块与 `standardWidth` 属性。
- 删除 `data-reading-width` 写死值与相关死代码，抽屉按 §3.5 处理。

### 3.4 吸附笔记（P4、P5，D1、D2、D5）

**投影规则**（纯函数，新文件 `note-projection.ts`）：

- 输入：`sourceNotes` 与当前已加载的 Chunks（每个 Chunk 需要新增 `bundleVersion`，见 §3.6）。
- 一条笔记投影到 Chunk 的条件是：`note.anchor` 不为 null，`note.anchor.bundle === chunk.bundleVersion`，并且两者 `sourceLines` 有重叠。同时满足的有多个 Chunk 时，取重叠行数最多的一个；仍然并列时取序号最小的。每条笔记最多显示在一个段落旁。
- 其余笔记（无锚点、原文已更新、所在段未加载）只出现在资料抽屉“笔记”页（§3.7）。
- 已删除但 `canUndo` 的笔记原位显示“已删除 · 撤销”。

**布局**：开关“吸附笔记”（`aria-pressed`，偏好键 `focus.attachNotes`，默认开启，旧键 `focus.attachDiscussion` 直接删除不迁移）。

- **旁注形态**：阅读区宽度 ≥ 当前行宽 + 32px 间距 + 280px 旁注 + 48px 内边距时启用。每个阅读组改为两列网格：左列是原文，宽度等于当前行宽、**不压缩**；右列是 280–320px 的旁注栏。整组居中，打开旁注时原文向左平移让出空间，不改变换行。旁注栏在本组内 `position:sticky; top:14px`，最大高度为视口高度减去功能区和输入框，超出部分在栏内滚动。
- **内联形态**：空间不足时，笔记块放在原文之后、讨论之前，标题“本段笔记 · N”，可折叠。功能区开关的 `title` 不再承担解释职责。
- **关闭时**：段落旁不显示笔记；“记笔记”仍然可用，编辑器临时以内联形态出现，保存后提示“已记下，可在 资料 › 笔记 查看”。
- 讨论消息永远留在阅读流，删除 `groupReadingDiscussion` 中的 `attached` 分支、`reading-group-ask` 按钮及 `data-discussion-attached` 相关 CSS。
- 非聚焦段的旁注跟随透镜颜色（`--reader-ink-3` / `--reader-ink-2`），聚焦段为正常颜色。

**笔记卡片**：Markdown 小字号正文；元信息依次为类型（想法 / 结论 / 问题 / 例子 / 概念）、“来自讨论”（`origin === "dialogue"` 时）、“原文已更新”（`sourceUpdated` 时）；编辑、删除按钮在卡片悬停或聚焦时显示，触屏上常显。编辑和删除复用现有 `changeNote()` 及冲突处理。

**记笔记的入口**（全部打开同一个 `NoteEditor` 组件，位置在该段的笔记区，旁注或内联）：

1. 段落页脚：“引用提问”旁新增“记笔记”。
2. 旁注栏：聚焦段的笔记列表末尾显示“＋ 记一笔”；没有笔记时只在聚焦段显示这一个轻量入口，其他段的旁注栏留空。
3. 选区浮层：由一个按钮改为两个，“引用提问”与“记为笔记”。选中文字作为引文显示在编辑器顶部。
4. AI 回答页脚的“存为笔记”：不再发消息给 AI，而是在该回答引用的段落旁打开编辑器，预填回答全文，`origin: "dialogue"`，用户可以先删改再保存。回答没有引用段落时，挂到当前透镜段；仍然没有时存为无锚点笔记。

**NoteEditor 行为**：

- 自增高 textarea，placeholder“记下你确认的理解…”；类型选择为 3 个小选项：想法（默认）、结论、问题，对应 `thought` / `conclusion` / `question`。
- Ctrl/Cmd+Enter 保存，Enter 换行；输入法组字时不触发快捷键。Esc 关闭编辑器：内容为空直接关闭；非空时保留草稿，段落“记笔记”按钮显示草稿圆点，再次打开时恢复。
- 草稿保存在现有 `drafts` 机制中（按 `sourceId:discussionId` 及 Chunk 键），刷新后可恢复。
- 保存时按钮显示“保存中…”且禁用；每份草稿使用稳定的 `requestId`（复用 `mutationId()`），重试不会产生重复笔记。失败时在编辑器内显示错误和“重试”，内容不丢。段落原文已更新（Host 返回 `note_bundle_changed`）时，提供“改存为整篇笔记”。
- 成功后关闭编辑器，新卡片短暂高亮（`--reader-duration-move` 淡出；减少动效模式下不高亮），焦点移到新卡片。
- 引文：选中文字是 `chunk.sourceMarkdown` 的原样子串时，作为 `quote` 发送；否则（例如选中的是译文）以 `> 引文` 前缀放进笔记正文。

### 3.5 资料抽屉不改正文宽度（P6）

按 ADR 0026 实现：打开抽屉时阅读列整体平移（`--reader-shift`）而不改变宽度；空间不够时抽屉覆盖正文。删除 `[data-reading-width=standard][data-side-open=true]` 的让列规则；`readerShift` 的计算要考虑旁注形态的总宽度。720px 以下保持现有的上下堆叠布局。

### 3.6 Host 与合同（D5）

- **新接口** `POST /library/sources/<sourceId>/notes`，请求体：
  ```json
  { "requestId": "…", "content": "…", "kind": "thought", "origin": "user",
    "chunk": { "planId": "plan-001", "chunkId": "chunk-002" }, "quote": "可选" }
  ```
  处理放在 `host/service.py` 新方法 `source_note_create()`，路由在 `host/server.py` 现有 `notes` 分支：
  1. 与 `source_note_change` 一样，校验 `sourceId` 是当前讨论来源，并调用 `source_clear.recover()`。
  2. 有 `chunk` 时，读取该 Plan 的 Chunk 记录与 `provenance.json`。Plan 的 bundle 不等于当前 Parser Bundle 时，抛 `WorkspaceError('note_bundle_changed', '这段原文已更新，可改存为整篇笔记')`。否则 `anchor = {sourceId, bundle, sourceLines: chunk.source_lines, quote?}`。
  3. 调用 `SourceNotes.save(bundle=当前 bundle, request_id=requestId, intent_id=requestId, kind, origin, evidence_role, anchor)`。`evidence_role` 在 `kind === "question"` 时为 `unresolved_question`，否则为 `explanation`。
  4. 写 `state['noteOperation'] = {'sourceId', 'status': 'saved', 'note'}`，调用 `changed()`，返回 `snapshot()`。
  - `kind` 只接受 `thought` / `conclusion` / `question`；`origin` 只接受 `user` / `dialogue`。
- **Chunk 投影**：`core_bridge.project_chunk()` 输出 `bundleVersion`（取 Plan `provenance.json` 的 `bundle`，按 Plan 缓存，避免每段读文件）。合同 `ReaderChunk` 增加 `bundleVersion?: string`。
- **合同**：`ReaderHost` 增加 `createSourceNote?(input: CreateSourceNoteInput): Promise<ReaderHostResult<ReadingWindow>>`；`http-reader-host.ts` 与 `fixture-reader-host.ts` 都要实现，fixture 版要能模拟成功、失败、`note_bundle_changed` 三种结果。
- **领域记录**：`CONTEXT.md` 的 Reading Note 条目补充“可按 Source Anchor 显示在对应 Reading Chunk 旁（吸附笔记），但不属于 Chunk 或 Plan；可由用户直接手写，或从讨论回答中确认保存”，并新增术语 **Attached Notes（吸附笔记）**。新建 `docs/adr/0031-attached-notes-and-direct-note-entry.md`，取代 ADR 0026 中 Discussion attachment 的部分。在 ADR 0026 末尾加一行 superseded 指针，保留原文。

### 3.7 资料抽屉“笔记”页（P5、P9）

- 去掉 `<details>`，默认展开。按“第 N 段 · 章节名”分组，顺序与 outline 一致；末尾分组为“整篇 / 未定位”（无锚点或原文已更新的笔记）。
- 每组标题是按钮：段落已加载时跳到该段（`jumpReference`）；未加载时禁用，并提示“打开该段后可跳转”。
- 顶部按钮“记一条整篇笔记”，打开无锚点的 `NoteEditor`。
- 讨论页：标签改为“讨论 i”加可得的摘要。合同只有 `discussionId`、`sourceId` 时，至少去掉内部 sourceId，显示“讨论 i（当前）”标记当前讨论。如果要显示首问摘要，就在 Host `discussions` 投影中增加 `title`（首条用户消息前 40 字）。
- 进度页：`chunk_id` 映射为“第 N 段 · 章节名”。

### 3.8 可发现性与功能区（P7、P8、P10、P11）

- 非聚焦段：页脚和元信息按钮改为 `opacity:.55`，悬停或聚焦时为 1；不再设为完全透明。
- 功能区最终顺序：`资料 | 位置徽标 | 回到进度(条件) | — 右组 — 行宽 | 吸附笔记 | 新会话 | 全屏 ‖ 收起/提问 | 继续`。阅读区小于 1100px 时，“行宽”“新会话”“全屏”只显示图标，保留 `aria-label` 与 `title`。位置徽标最小宽度 160px。
- 确认方式统一为一个阅读器内的确认弹窗组件（原生 `<dialog>`，带初始焦点、Esc、焦点归还），替换 `window.confirm`。“新会话”改为执行后底部提示“已开始新会话 · 撤销”：撤销时用执行前记下的 `discussionId` 调用 `host.selectDiscussionSource(sourceId, discussionId)` 切回原讨论；Host 不提供该方法时只提示，不显示撤销。
- 选区浮层：位置避开功能区和输入框（上方空间不足时放到选区下方）；滚动时跟随选区重新定位，选区消失时才隐藏。

---

## 4. 工单

工单文件在 `.scratch/reader-usability-audit/issues/`，由开发 Agent 按本节生成。每张工单需写明：目标、涉及文件、实施步骤、验收标准、测试。

| # | 工单 | 覆盖 | 依赖 |
| --- | --- | --- | --- |
| 01 | 图片地址补齐 instance | P1，§3.1 | — |
| 02 | 正文缩小图 + “查看图 N”；去掉缩略图条；标签与比例 | P2，§3.2 | 01 |
| 03 | 行宽 4 挡位替换滑块 | P3，§3.3 | — |
| 04 | 资料抽屉平移不改宽度 | P6，§3.5 | 03 |
| 05 | 领域记录：CONTEXT 与 ADR 0031 | D1、D2、D5，§3.6 | — |
| 06 | Host 创建笔记接口、Chunk `bundleVersion`、合同与两个 Host 适配器 | §3.6 | 05 |
| 07 | 笔记投影函数与吸附笔记布局（旁注/内联），移除吸附讨论 | P4，§3.4 | 03、06 |
| 08 | NoteEditor 与 4 个记笔记入口 | P5，§3.4 | 07 |
| 09 | 资料抽屉笔记/讨论/进度列表 | P5、P9，§3.7 | 06、08 |
| 10 | 非聚焦段可发现性、功能区精简、统一确认、选区浮层 | P7、P8、P10、P11，§3.8 | 03、07 |
| 11 | 验收证据：浏览器脚本、截图、文档更新 | 全部 | 01–10 |

---

## 5. 回归红线

- 阅读位置：所有布局变化（行宽、吸附笔记开关、抽屉开合、编辑器开合）都通过 `preserveReading()` 保持视口内的阅读锚点，一次操作只调用一次。
- 草稿：提问草稿、引用、笔记编辑草稿，在切换来源、收起输入框、刷新后都保持。
- Enter 发送、Shift+Enter 换行、输入法组字不发送（提问输入框）；笔记编辑器为 Ctrl/Cmd+Enter 保存。
- 笔记的编辑、删除、撤销、冲突处理语义不变；笔记仍然只属于 Source；“清除讨论与笔记”“重新阅读”照常清除笔记。
- Reading Cursor、Reading Progress Entry、Continue Reading 语义不变；记笔记不推进阅读位置。
- 现有 Host 鉴权与 `instance` 校验不放宽。
- 减少动效：所有新动效都有 `prefers-reduced-motion` 与 `:root[data-reduced-motion=true]` 回退。
- 非 Mist 外观只需不崩溃。

## 6. 验证

- 每张工单：`pnpm reader:typecheck`、`pnpm reader:test`；涉及 Host 时运行相关 Python 测试，例如 `.venv/bin/python -m unittest tests.test_web_host`，按改动范围增加。
- 涉及界面的工单：`pnpm reader:build` 后运行对应的 `tests/*.mjs` 浏览器脚本（环境变量 `FOCUS_PLAYWRIGHT_MODULE`、`FOCUS_CHROMIUM_EXECUTABLE`、`FOCUS_BROWSER_PORT`，见 `docs/design/reading-width-validation.md`）。行为改变的旧脚本（`reading_width_browser.mjs`、`reading_attachment_browser.mjs`、`reading_standard_settings_browser.mjs`、`reader_figures_browser.mjs`）同步更新，不得删除断言了事。
- 视口矩阵：1600×1000、1280×800、1024×768、390×844（触屏模拟），浅色与深色。
- 真实数据回归：在知识库**副本**上起隔离 Host（`--workspace <副本> --bind 127.0.0.1 --port <空闲端口>`），打开带图的 Paper Source，确认缩略图、放大图、抽屉图片全部为 200，且 `naturalWidth > 0`。


## 交付记录

2026-10-21，**部分实施，尚未完成验收**。简报见 [brief.md](brief.md)。保持 Integrate / visual_policy: preserve；未改变 §1 决定或 §5 红线。基于拉取时最新 PR #24 的 `feat/article-structure-guide`，基线 `9f183cd`。所有提交仅在本地，没有 push。

### 工单与提交

| 工单 | 当前状态 | 实施 commit |
| --- | --- | --- |
| 01 | needs-info | 1440bf1 |
| 02 | needs-info | — |
| 03 | needs-info | 084e1f6 |
| 04 | resolved | 8958431 |
| 05 | resolved | b9b314b |
| 06 | needs-info | 98fbeab |
| 07 | needs-info | — |
| 08 | needs-info | — |
| 09 | needs-info | — |
| 10 | needs-info | — |
| 11 | needs-info | — |
| 12 | needs-triage | — |
| 13 | needs-triage | — |

01 图片地址、03 四挡行宽、04 抽屉平移、05 领域文档、06 直接创建 Reading Note 的 Host/合同/适配器已实施。01/06 缺真实 Knowledge Base 验收；03 专项通过，但最终吸附脚本控制台检查失败，因此撤回 resolved。04/05 自身范围验证通过；04 与未来 Attached Notes 的实际组合仍由07验证。02、07–11 未开发，按依赖必须等待前置工单 resolved。

12/13 为开发中新发现的验证基础设施/运行错误，needs-triage，未擅自修改范围外代码。12 已在基线复现；13 尚未证明是基线问题。

### §2 问题最终结论

PASS 只表示下列已列明范围；NOT_RUN 不等于通过。未实施的目标标记 FAIL，并注明没有运行目标验收。

| 问题 | 结论 | 证据与边界 |
| --- | --- | --- |
| P1 图片 instance | NOT_RUN | 单元与合成隔离 Host 的 thumbnail/viewer/gallery HTTP 200、naturalWidth > 0 均 PASS；真实带图 Paper Source 尚无数据可测，见01与 asset 日志。 |
| P2 正文图片 | FAIL | 02被01阻塞，正文图/缩略图去重与 contain 尚未实现；目标验收 NOT_RUN。 |
| P3 行宽 | FAIL | 四挡、迁移、禁用、偏好恢复、键盘及矩阵专项 PASS；受影响吸附脚本最终控制台检查 FAIL，见03/13。 |
| P4 Attached Notes | FAIL | 07未实施，仍是旧 Discussion attachment；目标验收 NOT_RUN。 |
| P5 Reading Note 输入 | FAIL | 06直接创建 API/合同/幂等/冲突测试 PASS，真实数据 NOT_RUN；08 NoteEditor、四个入口及09列表未实施。 |
| P6 抽屉不缩正文 | PASS | 04 单元及四视口×双主题浏览器验证，开合宽度不变；未来 Attached Notes 组合只有纯函数覆盖，需07补实测。 |
| P7 段落操作可发现性 | FAIL | 10未实施，目标验收 NOT_RUN。 |
| P8 功能区密度 | FAIL | 10未实施，目标验收 NOT_RUN。 |
| P9 列表命名/锚点 | FAIL | 09未实施，目标验收 NOT_RUN。 |
| P10 确认方式 | FAIL | 10未实施，目标验收 NOT_RUN。 |
| P11 选区工具 | FAIL | 10未实施，目标验收 NOT_RUN。 |

### 干净构建与最终命令

删除 standalone dist 后运行下表；其后仅调整浏览器脚本的旧行宽断言与记录文件，生产代码未再变化。日志在 `evidence/logs/`。浏览器启动命令的环境和隔离 fixture 说明见 [validation/environment.md](validation/environment.md)。所有浏览器使用新起合成 Host；未连接或修改任何真实服务与知识库。

| 检查 | 结果 | 日志 |
| --- | --- | --- |
| `pnpm reader:typecheck` | PASS | focus-final-typecheck.log |
| `pnpm reader:test` | PASS，107 + 156 = 263 项 | focus-final-test.log |
| `pnpm reader:build` | PASS，有构建 chunk 大小提示 | focus-final-build-current.log |
| `.venv/bin/python -m unittest tests.test_direct_source_notes tests.test_article_overview` | PASS，15项 | focus-final-python.log |
| `.venv/bin/python -m unittest tests.test_web_host` | FAIL，测试导入问题；补 PYTHONPATH 后还依赖已删 CLI | focus-final-web-host.log；12 |
| `tests/reading_width_browser.mjs`（调用 measure 矩阵并保留 Source Anchor 取消检查） | PASS | focus-final-reading_width_browser.log |
| `tests/reading_standard_settings_browser.mjs` | PASS | focus-final-reading_standard_settings_browser.log |
| `tests/reader_drawer_translation_browser.mjs` | PASS | focus-final-reader_drawer_translation_browser.log |
| `tests/reader_asset_instance_browser.mjs` | PASS，仅合成数据 | focus-final-reader_asset_instance_browser.log |
| `tests/reader_figures_browser.mjs` | PASS，现有图入口回归；不代表02完成 | focus-final-reader_figures_browser.log |
| `tests/reading_attachment_browser.mjs` | FAIL，几何/锚点/焦点/减少动效检查已过，最后字体 CSP/404 错误断言失败 | focus-final-reading_attachment_browser.log；13 |
| 真实 Knowledge Base 副本上的图片、Reading Note 回归 | NOT_RUN，无可复制的真实知识库 | 01/06 |
| 尚未实施功能的全量 §5/§6 验收 | NOT_RUN | 07–11 |

### 视口矩阵截图

以下三个目录各有 8 张截图；390×844 使用触屏模拟。截图为合成数据的可重复证据，不代表真实数据门禁通过。

- `evidence/final-reader_asset_instance_browser/`
- `evidence/final-reading_width_browser/`
- `evidence/final-reader_drawer_translation_browser/`

每个目录的文件名：`1600-1000-light.png`、`1600-1000-dark.png`、`1280-800-light.png`、`1280-800-dark.png`、`1024-768-light.png`、`1024-768-dark.png`、`390-844-light.png`、`390-844-dark.png`。附加旧场景截图见 `evidence/final-reader_figures_browser/`、`evidence/final-reading_attachment_browser/`；后者不是通过证据。已目视检查宽/窄屏与浅/深主题代表截图，几何和溢出边界由矩阵脚本断言。

### 未完成项与续做入口

1. 请提供可访问的真实 Knowledge Base 路径或副本，包含带图 Paper Source 与有效 Reading Plan/Chunk Bundle。然后按用户要求 `cp -a` 到 `/tmp/<目录>/kb`，用独立 hostdata、空闲端口和新 Host 打印的口令验证01/06。现有真实数据和运行服务保持不动。
2. 12的旧测试 fixture 与13的控制台错误需要分诊。没有通过屏蔽断言或放宽安全策略制造绿灯；03目前为 needs-info。
3. 前置验证通过后按最小可执行编号继续02、07、08、09、10、11，逐张先红后绿、独立提交；不允许把“代码已写”视为 resolved。
4. 目前不能宣称 spec 全部修复或 §6 全通过，也没有将未实现功能列作已交付。
