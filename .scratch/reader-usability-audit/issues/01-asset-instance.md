# 01 图片地址补齐 instance

Status: needs-info
Blocked by: —
Covers: spec §3.1，问题 P1

## 目标
按以下已确认条款实现（05 仅领域记录；06 仅 Host/合同/适配器；07 仅投影布局；08 仅编辑器与入口）。

图片 URL 的实例参数只在一处补齐：

- `figures.ts` 新增 `withAssetInstance(url, instanceId)`：只对 `/reader/assets/` 与 `/reader/historical-assets/` 开头且没有 `instance` 参数的地址追加 `?instance=`（已有查询串时用 `&`）。`imageUrl(src, sourceId, instanceId?)` 末尾调用它。
- `imageIdentity()` 已经忽略同源地址的查询串，所以身份比较保持不变；需要补测试锁住这一点。
- `FocusReader` 从 `view.workspace?.instanceId` 取实例号，经 React Context（新文件 `asset-context.ts`，导出 `AssetInstanceContext`）传给 `MarkdownContent`、`ReadingChunk`、`FigurePanel`、`FigureViewer`。`MarkdownContent` 的 `urlTransform` 改为调用 `imageUrl()`，不再自己拼地址。
- `mergeFigures` 对同一身份的图，如果已有地址没有 `instance` 而新地址有，就换成新地址（在 Context 缺失的测试环境里依然正确）。

## 现状（对照当前代码核实后的文件与行号）
基线 PR #24 `9f183cd`；相对审计 HEAD 的增量为技能文档清理，产品问题仍存在。FigureViewer 实际与 FigurePanel 同文件。
- `ui/packages/reader-ui/src/figures.ts:17`：`export function imageUrl(src: string, sourceId: string) {`
- `ui/packages/reader-ui/src/figures.ts:24`：`const resolved = imageUrl(src, sourceId);`
- `ui/packages/reader-ui/src/figures.ts:68`：`found.push({ src: imageUrl(src, sourceId), caption, bodyCaption: !!captionNode || ownCaption || !!adjacentCaption }); nodes.push({ node, id }); return`
- `ui/packages/reader-ui/src/figures.ts:88`：`export function mergeFigures(sourceId: string, ...lists: readonly (readonly ReaderImage[])[]): Figure[] {`
- `ui/packages/reader-ui/src/figures.ts:95`：`if (!old) map.set(id, { ...image, src: imageUrl(image.src, sourceId), id, sourceId, label: "" });`
- `ui/packages/reader-ui/src/figures.ts:104`：`return mergeFigures(chunk.sourceId, source.found.map(i => {`
- `ui/packages/reader-ui/src/MarkdownContent.tsx:81`：`} }} urlTransform={(url, key) => {`
- `ui/packages/reader-ui/src/FigurePanel.tsx:7`：`figures: readonly Figure[]; selected: string | null; selectionVersion: number;`
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

- 实现：figures.ts 统一 URL 实例补齐和去重优先级；asset-context.ts；FocusReader provider；MarkdownContent、ReadingChunk、FigurePanel/Viewer 使用实例上下文。
- 红灯：asset-instance.test.tsx 2 FAIL / 1 PASS；修复后新增 Context 场景，4 PASS。
- `pnpm reader:typecheck` PASS；`pnpm reader:test` PASS（103 reader-ui + 154 standalone）；`pnpm reader:build` PASS。
- Browser：Chromium 153.0.8010.0 已可运行；旧 fixture 入口需适配，原脚本执行 FAIL（等待缩略图超时），仍在补充证据。
- 阻塞：当前只提供 spec，环境中没有真实 Knowledge Base，spec §6 真实 Paper Source 图片 HTTP/自然宽度检查 NOT_RUN。不能将 synthetic fixture 计作真实数据通过。
- 需要提供可读取的 Knowledge Base 路径或脱敏副本；拿到后只复制到 /tmp 并启隔离 Host。02、11 依赖保持阻塞，继续无依赖工单03。

- 补充 RUNTIME/PASS：`tests/reader_asset_instance_browser.mjs` 在 Chromium 153.0.8010.0 的合成 Host 上通过八视口/主题组合；缩略图、放大图、抽屉图 HTTP 200、naturalWidth > 0；截图 `evidence/01/*.png`。真实 Knowledge Base 验收仍 NOT_RUN，状态不变。脚本适配了异步入口和移动端 lazy 图片滚入视口。
