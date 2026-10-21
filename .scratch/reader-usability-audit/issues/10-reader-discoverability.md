# 10 可发现性、功能区、确认与选区

Status: needs-info
Blocked by: 03, 07
Covers: spec §3.8，问题 P7、P8、P10、P11

## 目标
按以下已确认条款实现（05 仅领域记录；06 仅 Host/合同/适配器；07 仅投影布局；08 仅编辑器与入口）。

- 非聚焦段：页脚和元信息按钮改为 `opacity:.55`，悬停或聚焦时为 1；不再设为完全透明。
- 功能区最终顺序：`资料 | 位置徽标 | 回到进度(条件) | — 右组 — 行宽 | 吸附笔记 | 新会话 | 全屏 ‖ 收起/提问 | 继续`。阅读区小于 1100px 时，“行宽”“新会话”“全屏”只显示图标，保留 `aria-label` 与 `title`。位置徽标最小宽度 160px。
- 确认方式统一为一个阅读器内的确认弹窗组件（原生 `<dialog>`，带初始焦点、Esc、焦点归还），替换 `window.confirm`。“新会话”改为执行后底部提示“已开始新会话 · 撤销”：撤销时用执行前记下的 `discussionId` 调用 `host.selectDiscussionSource(sourceId, discussionId)` 切回原讨论；Host 不提供该方法时只提示，不显示撤销。
- 选区浮层：位置避开功能区和输入框（上方空间不足时放到选区下方）；滚动时跟随选区重新定位，选区消失时才隐藏。

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
