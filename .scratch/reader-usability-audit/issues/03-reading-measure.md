# 03 行宽四挡位替换滑块

Status: claimed
Blocked by: —
Covers: spec §3.3，问题 P3

## 目标
按以下已确认条款实现（05 仅领域记录；06 仅 Host/合同/适配器；07 仅投影布局；08 仅编辑器与入口）。

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
