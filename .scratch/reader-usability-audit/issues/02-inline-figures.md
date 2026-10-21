# 02 正文缩小图、标签与比例

Status: needs-info
Blocked by: 01
Covers: spec §3.2，问题 P2

## 目标
按以下已确认条款实现（05 仅领域记录；06 仅 Host/合同/适配器；07 仅投影布局；08 仅编辑器与入口）。

- 被识别为“图”的图片，在正文原位置渲染为 `figure.reader-inline-figure`，内部依次是：
  - 缩小图：`max-height: var(--reader-inline-figure-h)`（新 token，默认 280px），`max-width:100%`，`object-fit:contain`，左对齐；整张图是一个按钮，点击打开 `FigureViewer`，可访问名称为“放大图 N”。
  - 图旁动作行，放在图下方右侧：一个“查看图 N”按钮，行为与现在的 `showFigure` 相同，即在资料抽屉中固定并选中这张图。
- 删除 `ReadingChunk` 底部的 `.reader-thumbnail-strip`，同一张图在一段里只出现一次。
- 标签：有图号时用“图 N”；没有图号时用“第 {chunk.index} 段插图 {k}”，k 从 1 开始，按该段内出现的顺序编号。修改 `mergeFigures` 的 label 生成方式，让它接收可选的段落序号。
- 资料抽屉网格缩略图改为 `object-fit:contain`，背景用 `--reader-surface-1`。
- 表格、公式、代码中的受保护图片保持现有逻辑（`protectedIds`），不进入这条路径。

## 现状（对照当前代码核实后的文件与行号）
基线 PR #24 `9f183cd`；相对审计 HEAD 的增量为技能文档清理，产品问题仍存在。FigureViewer 实际与 FigurePanel 同文件。
- `ui/packages/reader-ui/src/ReadingChunk.tsx:21`：`{!preparing && onFigure && <div className="reader-thumbnail-strip">{figures.map(f => <div className="reader-thumbnail" key={f.id}>`
- `ui/packages/reader-ui/src/ReadingChunk.tsx:67`：`return onFigure && figure ? <button className="reader-answer-thumbnail" aria-label={`放大${figure.label}`} key={figure.id} onClick={e => onZoom ? onZoom`
- `ui/packages/reader-ui/src/MarkdownContent.tsx:81`：`} }} urlTransform={(url, key) => {`
- `ui/packages/reader-ui/src/figures.ts:17`：`export function imageUrl(src: string, sourceId: string) {`
- `ui/packages/reader-ui/src/figures.ts:24`：`const resolved = imageUrl(src, sourceId);`
- `ui/packages/reader-ui/src/figures.ts:68`：`found.push({ src: imageUrl(src, sourceId), caption, bodyCaption: !!captionNode || ownCaption || !!adjacentCaption }); nodes.push({ node, id }); return`
- `ui/packages/reader-ui/src/figures.ts:88`：`export function mergeFigures(sourceId: string, ...lists: readonly (readonly ReaderImage[])[]): Figure[] {`
- `ui/packages/reader-ui/src/figures.ts:95`：`if (!old) map.set(id, { ...image, src: imageUrl(image.src, sourceId), id, sourceId, label: "" });`
- `ui/packages/reader-ui/src/figures.ts:104`：`return mergeFigures(chunk.sourceId, source.found.map(i => {`
- `ui/packages/reader-ui/src/reader-figures.css:64`：`.reader-thumbnail-strip { display:flex; flex-direction:column; gap:8px; margin-top:16px; }`
- `ui/packages/reader-ui/src/reader-figures.css:65`：`.reader-thumbnail { display:flex; gap:12px; min-width:0; align-items:center; }`
- `ui/packages/reader-ui/src/reader-figures.css:66`：`.reader-thumbnail > button { padding:0; border:0; flex:0 0 92px; }`
- `ui/packages/reader-ui/src/reader-figures.css:67`：`.reader-thumbnail img { display:block; width:92px; height:58px; object-fit:cover; border-radius:6px; }`
- `ui/packages/reader-ui/src/reader-figures.css:68`：`.reader-thumbnail > div { min-width:0; font:12px/1.5 var(--reader-ui); }`
- `ui/packages/reader-ui/src/reader-figures.css:69`：`.reader-thumbnail p { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; margin:2px 0; }`

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

- 2026-10-21：未开始实施，NOT_RUN。按本任务“所有依赖resolved才能选取”的门禁，01缺真实Knowledge Base验收。请先补齐真实Knowledge Base副本；解除依赖后继续按最小编号执行。未用已实现但未验收替代resolved。
