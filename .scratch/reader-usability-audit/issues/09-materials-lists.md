# 09 资料抽屉笔记、讨论与进度列表

Status: needs-info
Blocked by: 06, 08
Covers: spec §3.7，问题 P5、P9

## 目标
按以下已确认条款实现（05 仅领域记录；06 仅 Host/合同/适配器；07 仅投影布局；08 仅编辑器与入口）。

- 去掉 `<details>`，默认展开。按“第 N 段 · 章节名”分组，顺序与 outline 一致；末尾分组为“整篇 / 未定位”（无锚点或原文已更新的笔记）。
- 每组标题是按钮：段落已加载时跳到该段（`jumpReference`）；未加载时禁用，并提示“打开该段后可跳转”。
- 顶部按钮“记一条整篇笔记”，打开无锚点的 `NoteEditor`。
- 讨论页：标签改为“讨论 i”加可得的摘要。合同只有 `discussionId`、`sourceId` 时，至少去掉内部 sourceId，显示“讨论 i（当前）”标记当前讨论。如果要显示首问摘要，就在 Host `discussions` 投影中增加 `title`（首条用户消息前 40 字）。
- 进度页：`chunk_id` 映射为“第 N 段 · 章节名”。

## 现状（对照当前代码核实后的文件与行号）
基线 PR #24 `9f183cd`；相对审计 HEAD 的增量为技能文档清理，产品问题仍存在。FigureViewer 实际与 FigurePanel 同文件。
- `ui/packages/reader-ui/src/FocusReader.tsx:17`：`import { chunkFigures, figureChunk, extractFigures, figureNumber, imageIdentity, mergeFigures, type Figure } from "./figures";`
- `ui/packages/reader-ui/src/FocusReader.tsx:22`：`export interface FocusReaderProps { host: ReaderHost; appearance?: "mist" | "conversation"; standardWidth?: number; fontSize?: "small" | "standard" | `
- `ui/packages/reader-ui/src/FocusReader.tsx:32`：`export function groupReadingDiscussion<C extends { chunkId: string }>(`
- `ui/packages/reader-ui/src/FocusReader.tsx:52`：`export function FocusReader({ host, appearance = "conversation", standardWidth = 1040, fontSize = "standard", visible = true, fullscreen = false, onFu`
- `ui/packages/reader-ui/src/FocusReader.tsx:54`：`const [attachDiscussion, setAttachDiscussion] = useState(() => {`
- `ui/packages/reader-ui/src/FocusReader.tsx:55`：`try { return localStorage.getItem("focus.attachDiscussion") === "true"; } catch { return false; }`

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
