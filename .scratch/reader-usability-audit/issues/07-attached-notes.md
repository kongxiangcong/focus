# 07 笔记投影和吸附笔记布局

Status: needs-info
Blocked by: 03, 06
Covers: spec §3.4，问题 P4

## 目标
按以下已确认条款实现（05 仅领域记录；06 仅 Host/合同/适配器；07 仅投影布局；08 仅编辑器与入口）。

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

## 现状（对照当前代码核实后的文件与行号）
基线 PR #24 `9f183cd`；相对审计 HEAD 的增量为技能文档清理，产品问题仍存在。FigureViewer 实际与 FigurePanel 同文件。
- `ui/packages/reader-ui/src/FocusReader.tsx:17`：`import { chunkFigures, figureChunk, extractFigures, figureNumber, imageIdentity, mergeFigures, type Figure } from "./figures";`
- `ui/packages/reader-ui/src/FocusReader.tsx:22`：`export interface FocusReaderProps { host: ReaderHost; appearance?: "mist" | "conversation"; standardWidth?: number; fontSize?: "small" | "standard" | `
- `ui/packages/reader-ui/src/FocusReader.tsx:32`：`export function groupReadingDiscussion<C extends { chunkId: string }>(`
- `ui/packages/reader-ui/src/FocusReader.tsx:52`：`export function FocusReader({ host, appearance = "conversation", standardWidth = 1040, fontSize = "standard", visible = true, fullscreen = false, onFu`
- `ui/packages/reader-ui/src/FocusReader.tsx:54`：`const [attachDiscussion, setAttachDiscussion] = useState(() => {`
- `ui/packages/reader-ui/src/FocusReader.tsx:55`：`try { return localStorage.getItem("focus.attachDiscussion") === "true"; } catch { return false; }`
- `ui/packages/reader-ui/src/mist-reader.css:182`：`.focus-source-notes { border:1px solid var(--reader-line); border-radius:var(--reader-card-radius); background:var(--reader-surface-1); }`
- `ui/packages/reader-ui/src/mist-reader.css:183`：`.focus-source-notes > summary { cursor:pointer; padding:8px 10px; font-size:12px; color:var(--reader-muted); }`
- `ui/packages/reader-ui/src/mist-reader.css:184`：`.focus-source-notes > ol, .focus-source-notes > p { margin:0; padding:4px 12px 12px; }`
- `ui/packages/reader-ui/src/mist-reader.css:185`：`.focus-source-notes > p { font-size:12px; color:var(--reader-muted); }`
- `ui/packages/reader-ui/src/mist-reader.css:186`：`.focus-source-notes li { margin:8px 0; font-size:13px; line-height:1.7; overflow-wrap:anywhere; }`
- `ui/packages/reader-ui/src/mist-reader.css:187`：`.focus-source-notes li button { min-height:var(--reader-control-h-sm); font-size:12px; padding:0 6px; }`

## 实施步骤
1. 先将状态改为 claimed；核对依赖。
2. 为本工单行为增加失败测试并记录红灯。05 为纯文档例外。
3. 按目标修改，数值统一由 focus-tokens.css / typography.ts 管理。
4. 运行验收命令、检查截图并追加证据；通过后 resolved，独立 commit，不 push。

## 验收标准
- 上述目标每条行为由对应单元/浏览器断言验证，未运行不得计为 PASS。
- spec §5 阅读锚点、草稿、输入法、Reading Cursor、鉴权与减少动效红线保持。
- 界面在 1600×1000、1280×800、1024×768、390×844 触屏的浅/深色截图中无溢出与不可达控件。
- 图片/笔记工单在真实 Knowledge Base 副本隔离 Host 中验证；图片 HTTP 200 且 naturalWidth > 0。

## 测试
- `pnpm reader:typecheck`
- `pnpm reader:test`
- 界面：`pnpm reader:build` 和受影响的 `tests/*.mjs`。
- Host：`.venv/bin/python -m unittest tests.test_web_host` 及相关测试。

## Comments
- 2026-10-21 SOURCE/PASS：已核对以上代码位置。待记录红/绿结果与截图。

- 2026-10-21：未开始实施，NOT_RUN。按本任务“所有依赖resolved才能选取”的门禁，06缺真实Knowledge Base验收，并经07/08传递阻塞。请先补齐真实Knowledge Base副本；解除依赖后继续按最小编号执行。未用已实现但未验收替代resolved。

- 最终复验补充：03因受影响吸附脚本控制台检查失败撤回resolved，记录于13；相关依赖继续阻塞。当前未实施项不计为通过，详见spec交付记录。

- 2026-10-21 用户后续任务：按 spec 顶部修订实现了“笔记”入口、Source Anchor 投影、宽屏旁注／窄屏 3:1 分栏、“就这段讨论”和功能区提示。旧 1240px 讨论吸附门槛已移除。直接笔记编辑器（08）及真实 Knowledge Base 副本验收仍未纳入本次范围。
