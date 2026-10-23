# 阅读批注与小段笔记：实施规格

状态：方案已获用户批准（2026-10-22），待开发。本文件和 `issues/` 下的工单是唯一实施依据；开发在另一台服务器上进行。

范围：Integrate + redesign（多路由、共享 token、新领域实体），按 editorial-ui “Substantial” 级别执行：本规格 + 验收矩阵 + 交付记录。

## 0. 怎么读这份规格

| 文件 | 用途 |
|---|---|
| `spec.md`（本文） | 决定、术语、数据与接口、算法、视觉与动效数值、验收矩阵 |
| `prototype.html` | 交互与视觉的**参照实现**，单文件离线，浏览器直接打开。规格与原型冲突时以规格为准（差异见 §2） |
| `evidence/*.png` | 原型截图：吸附开/关、提交备注时卡片移入右栏的中间帧 |
| `issues/NN-*.md` | 逐个工单：目标、现状（文件:行号）、设计、步骤、验收、测试 |

`.scratch/` 在 `.gitignore` 里。把本目录带到开发服务器需要 `git add -f .scratch/reading-annotations`。

代码行号基于提交 `03f127e`（main，2026-10-22）。开工前先核对行号；有偏移时按符号名定位。

## 1. 用户目标

阅读一个 Reading Chunk（界面称“第 N 段”）时：

1. 选中句子，弹出气泡“重点 / 备注 / 引用提问”。“重点”是黄色高亮加粗；“备注”在句子下方弹出文本框，保存后句子下方出现红色虚线，句末右上角出现小灯泡；点灯泡查看备注。
2. 已标注的句子可以取消重点、编辑备注、删除标注（连同备注），删除可撤销。
3. 笔记分两类，位置不重叠：
   - **句子备注**：跟在画线句子旁边；
   - **小段笔记**：针对整个段，放在段结束处下方。
4. 打开“笔记吸附”：句内灯泡隐藏，高亮和虚线保留；句子备注以卡片出现在右栏、跟随句子；小段笔记在右栏卡片区下方。关闭吸附：卡片收回灯泡，小段笔记折叠在段末一行。切换、新增、删除都有短动画。
5. 讨论中对引用段说“记一下”保存的笔记，要出现在该段的小段笔记里（当前不显示，是缺陷）。

## 2. 已确定的决定

### 2.1 用户决定（2026-10-22）

| 编号 | 决定 |
|---|---|
| U1 | 方向按原型执行 |
| U2 | 段级笔记界面名称改为 **“小段笔记”**（原型里是“段全局笔记”，所有界面文案替换） |
| U3 | **高亮时文字加粗**（`font-weight:700`；原型没有加粗） |
| U4 | 吸附栏只列句子备注；只有“重点”的句子不出卡片 |
| U5 | 不论吸附开关，写备注都在句子下方弹框；吸附打开时，提交后弹框以动画移入右栏卡片位置 |
| U6 | 备注与小段笔记：Enter 保存，Shift+Enter 换行，输入法组字中不提交 |
| U7 | 吸附关闭时句子备注以灯泡显示；小段笔记折叠成段末“小段笔记 · N”，新保存的自动展开 |

**原型与规格的差异（只有这四处，其余以原型为准）：**
- 原型把重点和备注存在同一个对象 `{highlight, note}` 里；实现拆成两种记录：重点是独立的 Reading Highlight，备注是带 `sentence` 的 Reading Note（D1）。区间相同的二者在界面上合成一个标注，看到的效果与原型一致。
- 原型文案“段全局笔记 / 记段全局笔记 / 本段还没有段全局笔记 / 已删除段全局笔记 / 已存为第 3 段的段全局笔记”，实现时全部改为“小段笔记 / 记小段笔记 / 本段还没有小段笔记 / 已删除小段笔记 / 已存为第 N 段的小段笔记”。
- 原型高亮不加粗；实现加粗（U3）。
- 原型选区气泡只有“重点 / 备注”；产品保留现有“引用所选提问”能力，作为第三个按钮“引用提问”（§6.2）。

### 2.2 实施决定（本规格作出；如需推翻，先改本节和 ADR 0033）

| 编号 | 决定 | 理由 |
|---|---|---|
| D1 | **重点是新的独立数据**：新领域实体 **Reading Highlight（重点）**，只记录“哪句话被标为重点”，没有内容。**备注并入现有 Reading Note**，以“句子 + 备注”形式记录：一条带 `sentence`（句子定位与原句）的 Reading Note，`content` 就是备注文字（用户 2026-10-22 决定） | 重点没有内容，套不进 Reading Note（`content` 必须非空）；备注本身就是笔记，并入后编辑、删除、撤销、清除、资料栏列表全部复用现有机制 |
| D2 | Reading Highlight 存在同一个 `sources/<id>/notes/notes.sqlite3` 的新表 `highlights`，复用请求幂等、撤销槽和清除流程；句子备注在现有 `notes` 表新增 `sentence` 列 | 清除/重置与笔记同一事务；不新增文件 |
| D3 | **句子定位**（重点与句子备注共用同一形状）= Plan/Chunk + 显示层（原文/译文）+ 字符区间（UTF‑16）+ 原句引文（exact/prefix/suffix）；外加 Parser Bundle 版本与 Chunk 行范围（重点存在自身记录里，句子备注存在笔记的 `anchor` 里） | 字符区间用于快速定位；引文用于 Plan 重建或译文变化后重新定位；行范围用于跨 Plan 投影（与 ADR 0031 一致） |
| D10 | 同一句话可以既是重点又有备注：两条记录（一条 Reading Highlight、一条句子备注）的区间**完全相同**时，界面合成一个“标注”显示（黄底加粗 + 红虚线 + 灯泡）。同一 Chunk 同一层内，标注之间不允许部分重叠；同一区间最多一条重点、一条句子备注 | 用户看到的始终是“一处标注”，数据仍各归各位 |
| D11 | 句子备注不出现在“小段笔记”列表里（虽然它的 `anchor` 也指向该段），只以句内灯泡/右栏卡片显示；资料栏“笔记”页中以“「原句」+ 备注”形式列出 | 小段笔记针对整段，句子备注针对句子，两处不重复 |
| D4 | “记一下”修复：Reading Note 新增可选字段 **`placement`**（显示位置，不是证据锚点）。讨论绑定了段落引用、且模型没给 `anchor` 时，Host 用该段的行范围填 `placement`。投影用 `anchor ?? placement` | METHOD 禁止给类比/未解决问题加证据锚点（`methods/source-discussion/METHOD.md:14`），所以不能直接填 `anchor` |
| D5 | 小段笔记 = 投影到该段的 Reading Note（`anchor` 或 `placement`）。“记小段笔记”直接调用已有 `createSourceNote`（带 `chunk`），不经 AI | Host/适配器已就绪（ADR 0031），UI 尚未接线 |
| D6 | 字符区间以“可标注文本”计算：Chunk 渲染后 `.focus-markdown` 内的文本节点按文档顺序拼接，排除数学公式、图、标注界面元素（§5） | 选区与渲染必须使用同一套规则，DOM 与 hast 两侧有一致性测试 |
| D7 | 一次标注限制在同一块级元素内（同一 `p/li/h1–h6/td/th/blockquote` 段），同一 Chunk 同一层内标注不重叠 | 与原型一致；简化渲染和点击语义 |
| D8 | 写操作乐观显示：先按请求号显示待定状态，Host 成功后替换；失败时保留草稿并给出重试 | 交互契约：不因错误丢输入 |
| D9 | 吸附偏好沿用 `localStorage["focus.attachNotes"]`，不写 Host | ADR 0031 |

## 3. 术语与文案

| 领域术语（代码/文档） | 界面文案 | 说明 |
|---|---|---|
| Reading Highlight | 重点 | 独立实体；黄色高亮 + 加粗 |
| 句子备注（带 `sentence` 的 Reading Note） | 备注 / 句子备注 | 红色虚线 + 灯泡；吸附时为右栏卡片；资料栏显示“「原句」+ 备注” |
| 标注（仅界面概念，不存储） | 标注 | 某个区间上的重点和/或句子备注合成的显示单元，“删除标注”同时删除二者 |
| Reading Note 投影到 Chunk 且无 `sentence` | 小段笔记 | 段末区域 |
| Reading Note 无锚点无 placement | 整篇笔记 | 只在资料栏“笔记”页 |
| Attached Notes 开关 | 笔记吸附（功能区按钮仍显示“笔记”） | `title`：打开时“关闭笔记吸附”，关闭时“打开笔记吸附” |

完整文案表：

| 位置 | 文案 |
|---|---|
| 选区气泡 | `重点` `备注` `引用提问` |
| 选区跨块级元素 | 只显示 `引用提问` |
| 选区与已有标注部分重叠 | `与已有标注重叠，请缩小选区`（+ `引用提问`） |
| 标注气泡 | `重点`/`取消重点`（aria-pressed）、`备注`/`编辑备注`、分隔线、`删除标注` |
| 备注编辑框 | placeholder `写下你的备注…`；提示 `Enter 保存 · Shift+Enter 换行 · Esc 取消`；按钮 `取消` `保存` |
| 备注查看框 | 引文（2 行截断）、备注全文、`编辑` `删除标注` |
| 资料栏句子备注条目 | 第一行 `「原句」`（2 行截断，衬线字体），下面是备注全文；失效时加标签 `原文位置已失效` |
| 灯泡 | aria-label/title `查看备注` |
| 卡片操作 | 图标按钮 aria-label `编辑备注`、`删除标注` |
| 右栏小段笔记 | 标题 `小段笔记` + 数量；空 `本段还没有小段笔记`；按钮 `+ 记小段笔记`、`就这段讨论` |
| 段末折叠行（吸附关） | `› 小段笔记 · N`（N=0 时不显示此按钮）、`+ 记小段笔记` |
| 小段笔记条目 | 类型标签 `想法/结论/问题/例子/概念`；来自讨论加标签 `来自讨论`；悬停 `编辑` `删除` |
| 小段笔记编辑框 | 类型单选 `想法 结论 问题`；placeholder `写下这一段的笔记…` |
| Toast | `已删除标注 · 撤销`、`已删除小段笔记 · 撤销`、`已放弃这条备注 · 撤销`、`已放弃修改 · 撤销`、`已存为第 N 段的小段笔记 · 查看`、`已存为整篇笔记，可在资料栏查看`、`重点未保存 · 重试`、`备注未保存 · 重试`、`这段原文已更新，标注未保存` |

## 4. 数据与接口

### 4.1 句子定位 `SentenceLocator`（重点与句子备注共用）

```ts
interface SentenceLocator {
  planId: string;
  chunkId: string;
  layer: "source" | "translation";
  range: { start: number; end: number };                     // 可标注文本内 UTF-16 偏移，[start, end)
  quote: { exact: string; prefix: string; suffix: string };  // exact = 原句；prefix/suffix 各 ≤ 32 个 UTF-16 单元；截断时避开代理对边界
}
```

校验（Core，两种实体相同）：键集合恰为上述五个；`layer ∈ {source, translation}`，`translation` 时该 Chunk 必须已有译文；`range` 为整数且 `0 ≤ start < end`、`end - start ≤ 2000`；`quote` 键集合恰为 `{exact, prefix, suffix}`，`1 ≤ len(exact) ≤ 2000`，`len(prefix), len(suffix) ≤ 64`（Python 按码点放宽，前端按 UTF-16 截 32）。Python 侧**不**校验 `end - start == len(exact)`（UTF-16 与码点长度不同）。`planId/chunkId` 必须存在于该 Source 的 Plan 中，且 Plan Bundle == 当前 Bundle。

### 4.2 Reading Highlight（重点，新独立实体）

公开形状：

```ts
interface ReadingHighlight extends SentenceLocator {
  highlightId: string;           // uuid4 hex
  sourceId: string;
  revision: number;              // 1 起；delete/undo 各 +1
  bundle: string;                // 保存时 Parser Bundle 指纹
  sourceLines: readonly [number, number];   // 该 Chunk 行范围（Host 从 Plan 读取，客户端不传）
  deleted: boolean;
  canUndo: boolean;
  sourceUpdated: boolean;        // bundle ≠ 当前 Bundle
}
```

操作只有 **create / delete / undo**（重点没有可编辑内容）。撤销语义：create 的撤销 = 软删除；delete 的撤销 = 恢复。

表（同一 `notes.sqlite3`）：

```sql
CREATE TABLE IF NOT EXISTS highlights (
  id TEXT PRIMARY KEY, revision INTEGER NOT NULL,
  bundle TEXT NOT NULL, plan_id TEXT NOT NULL, chunk_id TEXT NOT NULL,
  source_start INTEGER NOT NULL, source_end INTEGER NOT NULL,
  layer TEXT NOT NULL, range_start INTEGER NOT NULL, range_end INTEGER NOT NULL,
  quote TEXT NOT NULL,            -- JSON {exact,prefix,suffix}
  deleted INTEGER NOT NULL, undo TEXT)
```

请求幂等沿用现有 `requests` 表（digest 带 `"entity":"highlight"` 与操作名）。列表按 `rowid`。

### 4.3 Reading Note 的两个新字段

#### `placement`（D4，修复“记一下”）

- 表 `notes` 新增列 `placement TEXT`（`_connect` 中用 `PRAGMA table_info` 检测缺列后 `ALTER TABLE notes ADD COLUMN placement TEXT`；旧行为 NULL）。
- 形状：`{ "sourceId", "bundle", "sourceLines": [a, b] }`，校验同 `anchor` 但不允许 `quote`。
- 公开记录新增 `placement: {...} | null`；`sourceUpdated` 改为 `(anchor ?? placement)` 存在且 `bundle ≠ current`。

#### `sentence`（D1，句子备注 = 句子 + 备注）

- 表 `notes` 新增列 `sentence TEXT`（迁移方式同上），存 `SentenceLocator` 的 JSON。
- **只能通过直接记笔记接口创建**（`POST .../notes` 带 `chunk` 与 `sentence`）；讨论保存（模型调用 `source_note`）不接受 `sentence`。
- 规则：有 `sentence` 时必须有 `chunk`，且 `sentence.planId/chunkId` 与 `chunk` 相同；Host 照旧用 Chunk 行范围生成 `anchor = {sourceId, bundle, sourceLines}`，**不**把原句放进 `anchor.quote`（`anchor.quote` 要求是 content.md 原文子串，译文层和渲染后文本都不满足）。
- 句子备注的 `kind = "thought"`，`origin = "user"`，`evidenceRole` 由 Host 按现有规则给 `explanation`；`content` = 备注文字（非空、≤ 8000，沿用笔记规则；界面上限 2000）。
- 编辑只改 `content`（现有 `change edit`）；`sentence` 不可编辑（要换句子就删除后重建）。
- 公开记录新增 `sentence: SentenceLocator | null`。
- **任何以纯文本消费 Reading Note 的地方**（资料栏、将来的导出或给 AI 的笔记列表）都必须渲染成 `「原句」\n备注`，不能只显示 `content`。当前 Host/Core 中没有这样的文本消费者（AI 工具 `topic_notes` 读取的是阅读记录里的旧笔记，不读 `SourceNotes`，见 `.agents/core/reading_workspace.py:1613`），资料栏由工单 12 处理。

### 4.4 HTTP 接口

全部挂在 `host/server.py` 现有 `/library/sources/<sourceId>/notes` 路由旁，鉴权和 `X-FOCUS-Instance` 校验与笔记接口相同。

**新增（重点）：**

| 方法 | 路径 | 请求体 | 成功 |
|---|---|---|---|
| POST | `/library/sources/<sourceId>/highlights` | `{requestId, chunk:{planId,chunkId}, layer, range:{start,end}, quote:{exact,prefix,suffix}}` | 201 + 窗口快照（含 `highlightOperation`） |
| POST | `.../highlights/<highlightId>/delete` | `{requestId, expectedRevision}` | 200 + 快照 |
| POST | `.../highlights/<highlightId>/undo` | `{requestId, expectedRevision}` | 200 + 快照 |
| GET | `.../highlights/requests/<requestId>` | — | 该请求结果或 null |

**修改（句子备注）：** 现有 `POST /library/sources/<sourceId>/notes` 请求体增加可选 `sentence: {layer, range, quote}`（`planId/chunkId` 取自同一请求的 `chunk`，客户端不重复传）。编辑/删除/撤销沿用现有 `/notes/<noteId>/edit|delete|undo`。

错误码（`WorkspaceError` → HTTP）：`highlight_invalid` / `note_sentence_invalid` 400；`highlight_bundle_changed` 409（Plan Bundle ≠ 当前；句子备注沿用现有 `note_bundle_changed` 409）；`highlight_request_conflict` 409；`highlight_not_found` 404；修订号过期返回 `{"status":"conflict","current":...}`（与笔记 change 一致）。

`highlightOperation`：`{ sourceId, status: "saved"|"changed"|"conflict", operation?: "delete"|"undo", highlight?, current? }`。

窗口快照（`HostService.snapshot()`，`host/service.py:198–271`）新增 `window['sourceHighlights'] = highlights.list(note_source, include_deleted=True)`，范围规则与 `sourceNotes` 相同；`sourceNotes` 中的记录自然带上 `placement`、`sentence`。

实施补充（2026-10-23）：窗口另返回可选 `noteClearVersion`，值为当前 Source 的 `SourceNotes.generation`。仅清除讨论与笔记不会增加既有 `resetVersion`，因此前端同时比较这两个明确版本信号，清除属于该 Source 的批注和小段笔记草稿及乐观状态；普通空笔记集合不表示用户清除了草稿。Fresh Session 不增加任一版本。

### 4.5 前端合同（`ui/packages/reader-contracts/src/index.ts`）

- 新增 `SentenceLocator`、`AnnotationLayer`、`ReadingHighlight`、`CreateHighlightInput`、`HighlightOperation`、`NotePlacement`。
- `SourceNote` 增加可选 `placement?: NotePlacement | null`、`sentence?: SentenceLocator | null`。
- `CreateSourceNoteInput` 增加可选 `sentence?: { layer; range; quote }`。
- `ReadingWindow` 增加 `sourceHighlights?: readonly ReadingHighlight[]`、`highlightOperation?: HighlightOperation | null`、`noteClearVersion?: number`。
- `ReaderHost` 增加可选方法 `createHighlight?(input)`、`changeHighlight?(sourceId, highlightId, operation: "delete"|"undo", expectedRevision, requestId)`、`highlightRequestResult?(sourceId, requestId)`。
- 纯函数 `sentenceNoteText(note)`：有 `sentence` 时返回 `「原句」\n备注`，否则返回 `content`。所有以纯文本显示笔记的地方都用它。
- 能力判断：有 `createHighlight` 才显示“重点”；有 `createSourceNote` 才显示“备注”；都没有时选区气泡只剩“引用提问”。

## 5. 可标注文本与字符区间（D6）

### 5.1 定义

对一个 Chunk 当前显示层的 `MarkdownContent` 根元素（`.focus-markdown`）：

**可标注文本** = 按文档顺序拼接所有文本节点的 `data`，跳过以下元素子树内的文本：
1. `.katex`（KaTeX 输出，含 MathML 与 HTML 两份）；
2. `figure`（含 `figcaption`、图片）；
3. 任何带 `data-anno-ui` 属性的元素（灯泡等标注界面）；
4. `script`、`style`。

另外，父元素为 `table/thead/tbody/tfoot/tr` 的纯空白文本节点不计入（react-markdown 渲染时会丢弃它们，hast 侧必须同样跳过，否则两侧不一致）。

### 5.2 两侧实现

- 新文件 `ui/packages/reader-ui/src/annotatable-text.ts`：
  - `domAnnotatableText(root: Element): { text: string; nodes: { node: Text; start: number }[] }`
  - `domOffset(root, container: Node, offset: number, edge: "start"|"end"): number | null`：边界落在排除子树内时吸附到该子树之前（start）或之后（end）。
  - `hastAnnotatableText(tree: HastRoot): string`（同规则，供测试与插件使用）。
- 一致性测试：用 react-markdown 在 jsdom 中渲染一组夹具（普通段落、列表、表格、行内/块公式、行内代码、链接、`**粗体**`、`==高亮==`、图片/图注、中英混排），断言 `domAnnotatableText(root).text === hastAnnotatableText(tree)`。这条测试不过，不能开始做选区。

### 5.3 选区 → 标注

`readSelection()`（`FocusReader.tsx:569`）扩展：
1. 选区在某 Chunk 的 `.focus-reading .focus-markdown` 内（沿用现有判断）。
2. 计算 `start = domOffset(root, startContainer, startOffset, "start")`、`end = domOffset(..., "end")`；去掉两端空白（`/\s/`）；`end ≤ start` 时不显示气泡。
3. 起止所在最近块级元素（`p, li, h1–h6, td, th, blockquote`）不同 → 气泡只显示“引用提问”。
4. 与已有标注（§5.4 的 mark）的关系：完全落在某个标注内 → 打开该标注的“标注气泡”；部分重叠 → 显示重叠提示；否则正常气泡。
5. 记录 `{chunk, layer, start, end, exact, prefix: text.slice(max(0,start-32), start), suffix: text.slice(end, end+32)}`。

### 5.4 渲染：rehype 插件

新文件 `ui/packages/reader-ui/src/rehype-annotations.ts`，导出 `rehypeAnnotations(options: { items: RenderMark[] })`。

**标注（mark）** 是渲染单位：同一 Chunk 同一层中，区间完全相同的一条重点和/或一条句子备注合成一个 mark（D10）。

```ts
interface RenderMark {
  key: string;                    // 有句子备注时为 "n:<noteId>"，否则 "h:<highlightId>"；新建中的为 "p:<requestId>"
  start: number; end: number;
  highlightId?: string;           // 有重点时
  noteId?: string;                // 有句子备注时
  pending?: boolean;              // 编辑框打开中的新备注（灰色虚线 + 淡底）
  fresh?: ("hl" | "note")[];      // 本次渲染要播放入场动画
  ariaLabel: string;              // 有备注：`备注：<前 60 字>`；否则 `重点`
}
```

- 插件放在 `MarkdownContent.tsx` 插件链**最后**（在 `rehypeKatex` 与 `markFigures` 之后），这样注入的元素不经过 sanitize，且遍历规则与 §5.1 一致。
- 按 §5.1 规则遍历文本节点，在区间边界拆分文本节点，把覆盖部分包进：
  `span.reader-anno[data-anno-key=key][class: reader-anno--hl(有 highlightId)? reader-anno--note(有 noteId)? reader-anno--pending? is-new-hl? is-new-note?]`
- 第一个片段加 `tabIndex=0`、`role="button"`、`aria-label`。
- 最后一个片段的**最后一个字符**单独拆出，和灯泡一起包进不换行容器，防止灯泡被挤到下一行：
  `span.reader-anno-nb > ( span.reader-anno.reader-anno--tail[data-anno-key] , span.reader-anno-bulb-anchor[data-anno-ui] > button.reader-anno-bulb[data-anno-ui][data-anno-bulb=key][type=button][aria-label=查看备注] > svg )`
  只有有 `noteId` 才生成灯泡。
- `MarkdownContent` 新增 prop `marks?: RenderMark[]`；插件数组按 `marks` 记忆化，避免无关重渲染。

### 5.5 重新定位、投影与合并

新文件 `ui/packages/reader-ui/src/annotation-projection.ts`：

```ts
type Located = { kind: "highlight"; item: ReadingHighlight } | { kind: "note"; item: SourceNote };   // note 必有 sentence
groupLocated(highlights, notes, groups): Map<groupId, Located[]>
resolveRange(text: string, loc: Pick<SentenceLocator, "range" | "quote">): { start: number; end: number } | null
buildMarks(text: string, located: Located[], layer: AnnotationLayer): { marks: RenderMark[]; lost: Located[] }
```

1. 输入：`sourceHighlights` 全部；`sourceNotes` 中 `sentence != null` 的。跳过 `deleted`（可撤销的只在 toast 期间由本地状态保留，不渲染）、`sourceUpdated`、`sentence.layer`/`layer` ≠ 当前显示层。
2. 归属 Chunk：先找 `planId + chunkId` 完全相同的 group；否则按 `bundle` 相同 + 行范围（重点用自身 `sourceLines`，句子备注用 `anchor.sourceLines`）重叠行数最大（平局取 `chunk.index` 小的）——与 `note-projection.ts` 相同规则；同一 Chunk 重复出现时归属最后一次出现。
3. `resolveRange`：`text.slice(start,end) === exact` → 原区间；否则在 `text` 中找 `exact` 的所有出现位置，按“prefix 末尾匹配长度 + suffix 开头匹配长度”最大、再按离原 `start` 最近选一个；找不到 → `null`（失效：不在正文渲染；句子备注在资料栏标“原文位置已失效”；失效的重点只是不显示）。
4. 合并：解析后区间完全相同的一条重点与一条句子备注合成一个 mark。剩余冲突（部分重叠，或同区间出现第二条同类记录）按记录顺序（重点与笔记各自的列表顺序，先比较 `start` 再比较类型：笔记优先）保留先出现的，其余进入 `lost`。
5. 可标注文本需要渲染结果，因此投影分两步：`FocusReader` 先按第 2 步把记录分组传给 `ReadingChunk`；`ReadingChunk` 在 `MarkdownContent` 内用 hast 文本（`hastAnnotatableText`）完成第 3–4 步。这样第一次渲染就带标注，不需要先渲染再测量。
6. 小段笔记投影（`note-projection.ts`）必须**排除** `sentence != null` 的笔记（D11）。

## 6. 交互规格

### 6.1 状态与入口总表

| 场景 | 吸附关 | 吸附开 |
|---|---|---|
| 选中段内文字 | 选区气泡（选区上方居中） | 同左 |
| 点“重点” | 新建 Reading Highlight，播放高亮扫入 | 同左（不出卡片，U4） |
| 点“备注” | 显示待定标注（灰色虚线，仅本地），句子下方弹出编辑框；保存时新建句子备注（Reading Note） | 同左（U5） |
| 编辑框保存 | 红虚线画入，灯泡弹出，焦点到灯泡 | 编辑框移入右栏卡片位置（§7 M8），焦点到卡片 |
| 点已标注文字 | 标注气泡（文字上方） | 同左，同时右栏对应卡片进入联动态 |
| 点灯泡 | 备注查看框（灯泡下方） | 灯泡不可见 |
| 卡片悬停/聚焦 | — | 卡片阴影加强 + 对应句子淡蓝底；卡片右上角出现操作 |
| 点卡片空白处 | — | 对应句子闪一下（M10），不滚动 |
| 删除标注 | 高亮/虚线反向扫出，灯泡缩小消失，toast 撤销 | 同左 + 卡片淡出右移 |
| 小段笔记 | 段末折叠行 | 右栏卡片区下方 |

### 6.2 选区气泡

- 由 `AnnotationBubble` 组件取代现有 `.reader-selection-quote` 按钮（`FocusReader.tsx:857`）。
- 按钮：`重点`（高亮笔图标，黄色 `#f7ce46`）、`备注`（钢笔图标，粉红 `#f0a3a6`）、竖分隔线、`引用提问`（沿用现有 `referenceChunk(selection.chunk, selection.text)`）。
- 按钮 `onPointerDown` 调 `preventDefault()`，保持选区可见。
- 定位：选区 `getBoundingClientRect()` 上方 10px、水平居中；上方空间 < 56px 时翻到下方；左右夹在 8px 内；箭头对准选区中心（`--arrow-x`，夹在 14px…宽度-14px）。
- 选区折叠、窗口尺寸变化、开始新选区时关闭。键盘选区（Shift+方向键）由 `selectionchange` 去抖 220ms 触发，指针按下期间不触发。

### 6.3 标注气泡

- 按钮：`重点`/`取消重点`（`aria-pressed`，按下态底色 `rgba(247,206,70,.18)`）、`备注`/`编辑备注`、分隔线、`删除标注`。打开时焦点到第一个按钮，Esc 关闭并把焦点还给标注文字。
按钮与数据操作对应（`h` = 该 mark 的重点记录，`n` = 句子备注记录）：

| 按钮 | 条件 | 操作 |
|---|---|---|
| `重点`（未按下） | 只有 `n` | `createHighlight`，locator 取 `n.sentence` 的当前解析区间与原句 |
| `取消重点` | 有 `h` 和 `n` | `changeHighlight(h, "delete")`，高亮反向扫出（M5），虚线与灯泡保留 |
| `取消重点` | 只有 `h` | 等同 `删除标注` |
| `备注` | 只有 `h` | 打开编辑框（新建），保存时 `createSourceNote` 的 `sentence` 用 `h` 的区间与原句，结果与 `h` 合成同一 mark |
| `编辑备注` | 有 `n` | 打开编辑框（编辑），保存 `changeSourceNote(n, "edit", content)` |
| `删除标注` | 任意 | 对存在的 `h`、`n` 各发一次 delete（并行），一个 toast `已删除标注 · 撤销`；撤销时对二者各发 undo |

### 6.4 备注编辑框

- 浮层宽 `min(320px, 100vw - 16px)`，放在标注最后一个行框下方 10px，左对齐行框左边 −10px；下方放不下且上方够时翻到上方。
- `textarea` 自适应高度（最小 64px，最大 240px），打开即聚焦、光标置尾。
- 键盘：Enter（非组字、非 Shift）提交；Shift+Enter 换行；Esc 取消；组字判断用 `event.isComposing`，`keyCode === 229` 作兼容兜底。
- 空内容时“保存”禁用。
- 点浮层外：草稿为空 → 取消（移除待定标注）；草稿非空 → 保持打开（不丢输入）。
- Esc 取消非空草稿 → toast `已放弃这条备注 · 撤销`（编辑已有备注时为 `已放弃修改`），撤销重新打开编辑框并恢复草稿。
- 草稿持久化：`sessionStorage["focus.annotationDrafts"]`，键：新建 `${sourceId}:${planId}:${chunkId}:${layer}:${start}-${end}`，编辑 `${sourceId}:note:${noteId}`；输入时写入，保存成功或取消后删除；重新打开同一键恢复。
- 保存：
  - 新建：`createSourceNote({sourceId, requestId, content, kind:"thought", origin:"user", chunk:{planId, chunkId}, sentence:{layer, range, quote}})`。
  - 编辑：`changeSourceNote(sourceId, noteId, "edit", revision, requestId, content)`。
- “重点 + 备注”：先点“重点”，再点该标注 → `备注`；两条记录区间相同，自动合成一个标注。

### 6.5 备注查看框

- 灯泡下方 10px，宽同编辑框；内容：引文（2 行截断，左侧 2px 红色虚线）、备注全文（保留换行）、`编辑` `删除标注`。
- `role="dialog"`、`aria-label="备注"`；Esc 关闭并聚焦灯泡；点外部关闭。

### 6.6 乐观更新、失败与撤销

- 每次写操作生成 `requestId`（`crypto.randomUUID()` 去掉横线，满足 `[A-Za-z0-9-]{8,80}`）。
- 本地乐观表 `optimistic: Map<requestId, {entity: "highlight"|"note", op: "create"|"edit"|"delete", record}>` 立即参与渲染；Host 返回快照后，以快照中的 `sourceHighlights` / `sourceNotes` 为准并移除该项。
- 失败：移除乐观渲染；备注失败时重新打开编辑框并恢复草稿；toast `重点未保存 · 重试` 或 `备注未保存 · 重试`（重试复用同一 requestId，依赖 Host 幂等）。`highlight_bundle_changed` / `note_bundle_changed` → toast `这段原文已更新，标注未保存`，不重试。
- 网络中断后恢复：用 `highlightRequestResult` / `sourceNoteRequestResult` 查询未决 requestId。
- 删除：调用 delete 后 toast `已删除标注 · 撤销` 6 秒；撤销对每条被删记录调用 undo（expectedRevision 取 delete 返回的 revision）。删除两条中只有一条成功时，toast 改为 `标注只删除了一部分 · 重试`，重试只针对失败的那条。

### 6.7 小段笔记

- 数据：`projectSourceNotes`（改为 `anchor ?? placement`，并排除 `sentence != null` 的句子备注）投影到该 group 的 Reading Note。
- 条目：类型标签（`kinds` 映射见 `AttachedNotes.tsx:4`）+ `来自讨论`（origin=dialogue）+ 内容（`MarkdownContent`，13px UI 字体）+ 悬停 `编辑` `删除`。
- `记小段笔记`：在区域内展开编辑框（类型单选 想法/结论/问题，默认 想法），Enter 保存 → `createSourceNote({sourceId, requestId, content, kind, origin:"user", chunk:{planId, chunkId}})`。`note_bundle_changed` 时提示 `这段原文已更新，可改存为整篇笔记`，提供按钮“存为整篇笔记”（去掉 `chunk` 重试）。
- `编辑`：区域内编辑框 → `changeSourceNote(..., "edit", revision, requestId, content)`；`删除` → delete + toast 撤销。
- 草稿：`sessionStorage["focus.drafts"]` 现有机制按 Source/Discussion 隔离，不够细；新增 `sessionStorage["focus.chunkNoteDrafts"]`，键 `${sourceId}:${planId}:${chunkId}` 或 `${sourceId}:note:${noteId}`。
- 讨论保存（“存为笔记”按钮或用户说“记一下”）成功后：笔记若投影到已加载段 → 该段小段笔记新条目入场动画（M11），吸附关时自动展开折叠行，toast `已存为第 N 段的小段笔记 · 查看`（“查看”平滑滚动到条目，减少动效时直接跳）；若是整篇笔记 → toast `已存为整篇笔记，可在资料栏查看`。判断依据：快照 `noteFeedback.status === "saved"` 时对比前后 `sourceNotes` 找到新 noteId。

### 6.8 吸附开关

- 沿用 `.reader-attach-toggle`（`FocusReader.tsx:843`），`preserveReading` 包裹，`localStorage["focus.attachNotes"]`。
- 切换时：关闭所有浮层；正在编辑的备注若草稿为空则取消，非空则保持编辑框（编辑框不随吸附变化）。
- 窄屏：右栏宽度 < 200px 或 `data-reading-narrow=true` 时为**堆叠布局**：卡片按句子顺序静态排在该段正文下方、小段笔记之上，不做跟随定位，不做飞行动画（只淡入）。

## 7. 视觉与动效数值

### 7.1 新增 token（写入 `focus-tokens.css`，组件 CSS 只引用 token）

| token | 浅色 | 深色 |
|---|---|---|
| `--reader-anno-highlight` | `rgba(247,206,70,.50)` | `rgba(230,190,60,.30)` |
| `--reader-anno-highlight-strong` | `#d6a514` | `#d9a441` |
| `--reader-anno-line` | `rgba(163,43,49,.80)` | `rgba(255,157,157,.80)` |
| `--reader-anno-pending-line` | `var(--reader-faint)` | 同 |
| `--reader-anno-bulb-bg` | `#fffaf0` | `#2a2620` |
| `--reader-anno-bulb-bg-hover` | `#fff2d6` | `#353024` |
| `--reader-anno-bulb-border` | `rgba(194,138,30,.45)` | `rgba(217,164,65,.45)` |
| `--reader-anno-bulb-ink` | `var(--reader-mark-strong)` | 同 |
| `--reader-anno-bubble` | `#1d2125` | `#33383e` |
| `--reader-anno-on-bubble` | `#f8f7f4` | `#f8f7f4` |
| `--reader-anno-hl-icon` | `#f7ce46` | 同 |
| `--reader-anno-note-icon` | `#f0a3a6` | 同 |
| `--reader-anno-card-gap` | `8px` | — |
| `--reader-anno-card-offset` | `6px`（卡片顶与句子首行顶的上提量） | — |
| `--reader-anno-narrow-rail` | `200px` | — |

动效时长与曲线只用已有 token：`--reader-duration-quick 140ms`、`--reader-duration-move 240ms`、`--reader-duration-travel 380ms`、`--reader-duration-exit 170ms`、`--reader-ease-out cubic-bezier(.22,.8,.24,1)`、`--reader-ease-inout cubic-bezier(.45,0,.2,1)`、`--reader-ease-in cubic-bezier(.4,0,1,1)`。灯泡弹出用回弹曲线 `cubic-bezier(.34,1.5,.64,1)`，新增 token `--reader-ease-pop`。

### 7.2 组件样式（放在新文件 `ui/packages/reader-ui/src/reader-annotations.css`，由 reader-ui 入口与其他 CSS 一起引入）

```css
@property --anno-hl-w { syntax:'<percentage>'; inherits:false; initial-value:100%; }
@property --anno-ul-w { syntax:'<percentage>'; inherits:false; initial-value:100%; }

.reader-anno {
  --anno-hl-img: linear-gradient(transparent, transparent);
  --anno-ul-img: linear-gradient(transparent, transparent);
  background-image: var(--anno-hl-img), var(--anno-ul-img);
  background-repeat: no-repeat;
  background-position: 0 0, 0 100%;
  background-size: var(--anno-hl-w) 100%, var(--anno-ul-w) 1.5px;
  padding-bottom: 3px; border-radius: 2px; cursor: pointer;
  transition: background-color var(--reader-duration-quick) var(--reader-ease-out);
}
.reader-anno--hl { --anno-hl-img: linear-gradient(var(--reader-anno-highlight), var(--reader-anno-highlight)); font-weight: 700; }
.reader-anno--note { --anno-ul-img: repeating-linear-gradient(90deg, var(--reader-anno-line) 0 4px, transparent 4px 7px); }
.reader-anno--pending { --anno-ul-img: repeating-linear-gradient(90deg, var(--reader-anno-pending-line) 0 4px, transparent 4px 7px); background-color: var(--reader-hover); }
.reader-anno.is-linked, .reader-anno:focus-visible { background-color: var(--reader-accent-soft); outline: none; }
.reader-anno-nb { white-space: nowrap; }
.reader-anno-bulb-anchor { position: relative; display: inline-block; width: 0; height: 0; }
.reader-anno-bulb {
  position: absolute; left: 1px; bottom: .78em; width: 17px; height: 17px; padding: 0;
  display: grid; place-items: center;
  border: 1px solid var(--reader-anno-bulb-border); border-radius: 9px 9px 9px 3px;
  background: var(--reader-anno-bulb-bg); color: var(--reader-anno-bulb-ink);
  box-shadow: 0 1px 2px rgba(29,33,37,.10); cursor: pointer; transform-origin: 0 100%;
}
.reader-anno-bulb::after { content: ""; position: absolute; inset: -8px; }      /* 31px 命中区 */
@media (pointer: coarse) { .reader-anno-bulb::after { inset: -14px; } }        /* 43px 命中区 */
.reader-anno-bulb svg { width: 11px; height: 11px; }
.reader-anno-bulb:hover { background: var(--reader-anno-bulb-bg-hover); }
```

命中区实测修正（2026-10-23）：17px border-box 灯泡含两侧 1px 边框，伪元素的绝对定位包含块宽为 15px。为达到 31px / 43px 实际命中区，inset 分别取 -8px / -14px（原 -7px / -13px 仅为 29px / 41px）。

其余（卡片、气泡、浮层、小段笔记、折叠行、toast）按 `prototype.html` 中同名样式移植，映射如下，数值不变，颜色换成上表 token：

| 原型类名 | 产品类名 | 要点 |
|---|---|---|
| `.card` | `.reader-anno-card` | 绝对定位 `left:0; right:0; top:0`，位置只用 `transform: translateY(top)`；内边距 `8px 11px 9px`；圆角 `--reader-card-radius`；阴影 `--reader-shadow`；字体 `13px/1.65 var(--reader-ui)`；`transform-origin:0 0` |
| `.card::before` | 同 | 连接短线：`top:13px; left:-15px; width:11px; border-top:1px solid var(--reader-line-strong)`；`.is-displaced` 时 `opacity:0` |
| `.card.is-linked` | 同 | `box-shadow: 0 0 0 1px var(--reader-accent-line), 0 12px 32px -18px rgba(29,33,37,.3)` |
| `.card__quote` | `.reader-anno-card__quote` | `12px/1.6 var(--reader-serif)`，`--reader-muted`，左 `2px dashed var(--reader-anno-line)`，`padding-left:8px`，单行截断；该标注也是重点时引文 `span` 加 `--reader-anno-highlight` 底色与 700 字重 |
| `.card__actions` | `.reader-anno-card__actions` | 右上角 `top:4px; right:4px` 绝对定位，悬停/聚焦/联动时 `opacity:1`；24px 图标按钮（14px 图标）；不改变卡片高度 |
| `.bubble` | `.reader-anno-bubble` | `padding:3px; gap:2px; border-radius:10px`；底色 `--reader-anno-bubble`；按钮高 30px、`padding:0 10px`、圆角 7px、13px 字、图标 15px；悬停 `rgba(255,255,255,.13)`；分隔线 `1px × (高-12px)`，`rgba(255,255,255,.18)` |
| `.float::before` | 同 | 10px 旋转方块箭头，背景继承浮层 |
| `.pop` | `.reader-anno-pop` | `width:min(320px,100vw-16px); padding:10px 12px; border-radius:12px`；`--reader-surface-2`；`--reader-shadow-popover` |
| `.editor textarea` | `.reader-anno-editor textarea` | `min-height:64px; max-height:240px; padding:8px 10px; border-radius:8px; 13px/1.65`；聚焦 `border-color: --reader-accent-line` + `0 0 0 3px --reader-accent-soft` |
| `.cnotes` | `.reader-chunk-notes` | 顶部 `1px dashed var(--reader-line-strong)`，`margin-top:14px; padding-top:10px`；`12.5px/1.65` |
| `.cfoot` | `.reader-chunk-notes-fold` | 折叠用 `grid-template-rows: 0fr → 1fr`；面板左侧 `2px solid var(--reader-line-strong)`，`padding:6px 12px` |
| `.toast` | 复用现有通知样式；没有时按原型 | 底部居中 28px，深色底，`aria-live="polite"` |

### 7.3 布局数值

| 项 | 值 |
|---|---|
| 右栏宽 | 侧栏布局 `readingLayout.noteWidth = 280px`；与正文间距 `noteGap = 32px`（`typography.ts:15`，不改） |
| 右栏左边线 | `padding-left:14px; border-left:1px solid var(--reader-line)` |
| 分栏布局 | 沿用现有 3fr : 1fr |
| 堆叠阈值 | 右栏实际宽度 < `--reader-anno-narrow-rail`（200px）或 `data-reading-narrow=true` |
| 卡片纵向 | `top_i = max(anchorTop_i, bottom_{i-1} + 8px)`；`anchorTop = 标注第一个片段首个行框 top − 右栏顶 − 6px` |
| 卡片区高度 | `max(正文高度, 最后一张卡片 bottom + 4px)`；小段笔记区紧随其后，所以总在“段结束处下方”且在所有卡片之下 |

### 7.4 动效表

所有效果在 `prefers-reduced-motion: reduce` 或 `:root[data-reduced-motion=true]` 下关闭，只保留最终状态；JS 动画在这两种条件下不创建。业务状态与焦点不等待 `animationend`。

| 编号 | 触发 | 元素/属性 | 数值 | 中断 |
|---|---|---|---|---|
| M1 | 选区气泡、标注气泡、浮层出现 | opacity 0→1，`scale(.94) translateY(2px)`→none；`transform-origin` 指向箭头 | 140ms ease-out | 关闭即移除 |
| M2 | 新增重点 | `--anno-hl-w` 0%→100%（行内背景按阅读顺序扫过多行） | 380ms ease-out；尾字符片段 `delay 300ms, 80ms` | 重渲染即结束 |
| M3 | 新增备注 | `--anno-ul-w` 0%→100%；与 M2 同时发生时延迟 80ms | 380ms ease-out | 同上 |
| M4 | 灯泡出现（新备注保存后） | opacity 0→1，scale .3→1，原点左下 | 380ms `--reader-ease-pop`，delay 320ms | — |
| M5 | 取消重点 / 删除标注 | WAAPI 把 `--anno-hl-w`、`--anno-ul-w` 100%→0%，完成后重渲染（400ms 兜底定时器） | 240ms ease-inout | 兜底保证最终状态 |
| M6 | 删除时灯泡、卡片 | 灯泡 scale→.3 + 淡出；卡片 `translate(10px, top) scale(.97)` + 淡出 | 170ms ease-in | — |
| M7 | 打开吸附 | ① 正文列 FLIP：`translateX(dx)`→none（dx=切换前后正文左边差），380ms ease-out；② 视口内每张卡片从其灯泡位置（加 dx 补偿）`translate(...) scale(.12)` + opacity 0 → 最终位置，380ms ease-out，依次延迟 35ms；③ 小段笔记区 `translateY(6px)`+淡入，240ms，delay 160ms；④ 灯泡淡出缩小 140ms ease-in | 再次切换：取消全部动画、清空飞行层 |
| M8 | 吸附开时提交备注 | 记录编辑框矩形；关闭浮层、渲染卡片后，卡片从编辑框位置 `translate(dx, top+dy) scale(编辑框宽/卡片宽)`、opacity .4 → 最终位置，380ms ease-out；结束后卡片加 `is-saved`（240ms 黄色描边淡出：`0 0 0 2px rgba(247,206,70,.7)`） | 堆叠布局只播 `is-saved` |
| M9 | 关闭吸附 | 切换**前**克隆视口内卡片到 `position:fixed` 飞行层（保持原矩形）；切换后每个克隆飞向对应灯泡左上角：`translate(...) scale(.1)` + 淡出，380ms ease-inout，依次 30ms；灯泡淡入放大 240ms ease-out，`transition-delay = 260ms + min(k,8)×30ms`，900ms 后清除延迟 | 飞行层元素 `finished` 或被取消都移除 |
| M10 | 点卡片 | 对应句子底色 `rgba(45,95,127,.22)` 保持 60% 后淡出 | 900ms | 再点重新开始 |
| M11 | 小段笔记新条目 | 条目 `translateY(6px)`+淡入 240ms；文字底色 `--reader-accent-soft` 1400ms 淡出 | — | — |
| M12 | 折叠行展开/收起 | `grid-template-rows` 0fr↔1fr，箭头旋转 90° | 240ms ease-out | 反向即可 |
| M13 | 卡片重新排布 | `transform` 过渡 240ms ease-out；首次布局和开关时加 `.no-anim` 禁用过渡 | — | — |

`will-change` 不常驻；飞行层 `pointer-events:none; z-index` 高于正文、低于浮层。

## 8. 代码落点总览

| 层 | 文件 | 改动 |
|---|---|---|
| Core | `.agents/core/source_notes.py` | `highlights` 表；`notes` 表 `placement`、`sentence` 列迁移与校验；`save` 接受二者；`clear` 同时清重点；`_public` 加两个字段 |
| Core | `.agents/core/source_highlights.py`（新） | `SourceHighlights`：save/change(delete|undo)/list/result |
| Core | `.agents/core/discussion_application.py` | `self.highlights`；`source_note` 无 anchor 时按讨论引用填 `placement`；拒绝 `sentence` |
| Host | `host/service.py` | `source_highlight_create/change/request`；`source_note_create` 接受 `sentence`；snapshot 加 `sourceHighlights` |
| Host | `host/server.py` | 4 条重点路由与错误码映射 |
| 合同 | `ui/packages/reader-contracts/src/index.ts` | §4.5 |
| 适配器 | `ui/apps/standalone/src/adapters/http-reader-host.ts`、`fixture-reader-host.ts` | 新方法；fixture 内存实现与种子数据 |
| 渲染 | `ui/packages/reader-ui/src/annotatable-text.ts`、`rehype-annotations.ts`、`annotation-projection.ts`（新）；`MarkdownContent.tsx`、`ReadingChunk.tsx` | §5 |
| 交互 | `ui/packages/reader-ui/src/annotations/`（新目录）：`AnnotationBubble.tsx`、`AnnotationEditor.tsx`、`AnnotationNotePop.tsx`、`useAnnotationActions.ts`、`useAnnotationDrafts.ts`、`AnnotationToast.tsx` | §6 |
| 吸附 | `ui/packages/reader-ui/src/annotations/AnnotationRail.tsx`、`ChunkNotes.tsx`、`rail-layout.ts`、`useAnnotationMotion.ts`；替换 `AttachedNotes.tsx` | §6.7、§7.3、§7.4 |
| 样式 | `focus-tokens.css`、`reader-annotations.css`（新）、`mist-reader.css`（删除被替换的 `.reading-group-notes` 规则） | §7 |
| 文档 | `CONTEXT.md`、`docs/adr/0033-reading-annotations-and-chunk-notes.md`（新）、`docs/adr/0031-*.md`、`docs/design/README.md` | 工单 01 |

## 9. 工单与依赖

| 工单 | 内容 | 依赖 |
|---|---|---|
| 01 | 领域与决策文档 | — |
| 02 | Core：重点存储 `SourceHighlights` + 笔记 `sentence` 字段 | 01 |
| 03 | Core/Host：讨论笔记 `placement`（修复“记一下”不显示） | 01 |
| 04 | Host：重点接口、句子备注创建、快照 | 02、03 |
| 05 | 合同与适配器（含 fixture 种子数据） | 03、04 |
| 06 | 可标注文本、rehype 插件、投影与重新定位 | 05 |
| 07 | 视觉基础：token 与组件样式 | — |
| 08 | 选区气泡、标注气泡、备注编辑/查看、乐观保存与撤销 | 06、07 |
| 09 | 吸附栏：跟随卡片、小段笔记区、记小段笔记、堆叠布局 | 08 |
| 10 | 吸附关闭：灯泡与段末折叠行、讨论保存反馈 | 08 |
| 11 | 动效 M1–M13 | 09、10 |
| 12 | 资料栏笔记页与清除/重置 | 04、05 |
| 13 | 验收：浏览器测试与截图矩阵、交付记录 | 全部 |

可并行：02 与 03；07 与 02–06；09 与 10；12 与 08–11。02 与 03 都给 `notes` 表加列（`sentence`、`placement`），统一用 `SourceNotes._ensure_column(db, name)` 辅助函数，先合入的一方创建它；04 同时需要二者的结果。

## 10. 验收矩阵

| # | 场景 | 证据 |
|---|---|---|
| A1 | 选中段内句子 → 气泡三按钮；跨块级 → 只有“引用提问” | 单元 + 浏览器 |
| A2 | 重点：黄色底 + 700 字重 + 扫入；刷新后仍在 | 浏览器（计算样式 `font-weight` 700，`background-image` 含高亮渐变） |
| A3 | 备注：编辑框在句子下方；Enter 保存、Shift+Enter 换行、组字中 Enter 不提交；保存后红虚线 + 灯泡；灯泡查看全文 | 单元（组字事件）+ 浏览器；物理输入法手测记录 |
| A4 | 标注气泡：取消重点（有/无备注两种）、给重点加备注、编辑备注、删除（同时删除重点与句子备注）；撤销两者都恢复 | 浏览器 |
| A5 | 吸附开：灯泡 `visibility:hidden`，高亮/虚线保留；卡片互不重叠；卡片与句子首行 top 差 ≤ 8px（未被挤开时）；小段笔记区 top ≥ 正文 bottom 且 ≥ 最后一张卡片 bottom | 浏览器几何断言（1600×1000、1280×800、1024×768） |
| A6 | 吸附开写备注：编辑框在句子下方，提交后卡片出现在右栏，过程中存在 WAAPI 动画 | 浏览器 + 中间帧截图 |
| A7 | 吸附关：卡片飞回、灯泡可见；小段笔记折叠行数量正确，展开/收起 | 浏览器 |
| A8 | 讨论“记一下”（引用了段落）→ 笔记出现在该段小段笔记，带“来自讨论”；未引用段落 → 整篇笔记 toast | Host 单元 + 浏览器（fixture） |
| A9 | 记小段笔记：直接保存不经 AI；bundle 变化提示改存整篇 | Host 单元 + 浏览器 |
| A10 | 原文/译文切换：只显示当前层标注 | 单元 + 浏览器 |
| A11 | Plan 重建后标注通过引文重新定位；找不到时不渲染、资料栏句子备注标“原文位置已失效” | 单元 |
| A12 | 减少动效：所有操作直接到最终状态，`document.getAnimations()` 为空 | 浏览器（`reducedMotion: "reduce"`） |
| A13 | 窄屏 390×844：吸附开为堆叠布局、无溢出、控件可达；吸附关时灯泡命中区 ≥ 43px | 浏览器截图 + 命中断言 |
| A14 | 深色主题：高亮、虚线、灯泡、气泡对比度可读 | 截图 |
| A15 | 清除讨论与笔记 / 重置阅读：标注一并清除；新建会话保留 | Host 单元 |
| A16 | 写失败：草稿保留、可重试且幂等；删除只成功一半时可只重试失败的那条 | 单元（模拟失败） |
| A17 | 句子备注是 Reading Note：资料栏“笔记”页以“「原句」+ 备注”列出；不出现在小段笔记列表；清除笔记时一起清除 | 单元 + 浏览器 |

## 11. 保持不变的契约

Reading Note 属于 Source（ADR 0015/0031）；直接记笔记不经 AI、不进讨论历史、不推进 Reading Cursor、不生成 Reading Progress Entry；Reading Lens 与 Reading Cursor 分离；Host 鉴权与 instance 校验；清除/重置语义（ADR 0018）；讨论消息留在阅读流；`==高亮==` 作者标记保持原样式（与标注无关）。
