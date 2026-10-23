# 06 可标注文本、rehype 插件、投影与重新定位

Status: resolved
Type: task
Blocked by: 05
Covers: spec §5、D3、D6、D7、A10、A11

## 目标

给出“选区 ↔ 字符区间 ↔ 渲染标记”的统一实现，使标注在首次渲染就出现在正确位置，并在 Plan 重建、译文切换后正确重新定位。

## 现状

- `ui/packages/reader-ui/src/ReadingChunk.tsx:14–23`：`text = translated ? chunk.translation! : chunk.sourceMarkdown`，交给 `<MarkdownContent text sourceId figures onFigure />`；原文/译文切换是组件内部状态 `original`（20 行按钮，`onLanguage?.(chunk, !original)` 回调）。
- `ui/packages/reader-ui/src/MarkdownContent.tsx`：react-markdown；`remarkPlugins = [remarkGfm, remarkMath]`；`rehypePlugins = [rehypeRaw, [rehypeSanitize, schema], rehypeInlineFormatting, rehypeKatex]`（约 20–58 行），每次渲染再追加 `markFigures`（约 79–80 行）。`==x==` 在 `rehypeInlineFormatting` 中变成 `<mark>`。
- `ui/packages/reader-ui/src/note-projection.ts`：笔记投影规则（bundle 相同、行重叠最大、平局取小 index、重复出现取最后一次）。
- `FocusReader.tsx:542–563` 的 `highlight()` 用 TreeWalker 拼文本节点 + `indexOf`，是同一类思路但没有排除规则，**不要复用**。

## 设计

### 1. `annotatable-text.ts`

```ts
export const EXCLUDE_SELECTOR = ".katex, figure, [data-anno-ui], script, style";
const TABLE_PARENTS = new Set(["TABLE", "THEAD", "TBODY", "TFOOT", "TR"]);

export function domAnnotatableText(root: Element): { text: string; nodes: { node: Text; start: number }[] }
// TreeWalker(SHOW_TEXT)，acceptNode：祖先(到 root 为止)匹配 EXCLUDE_SELECTOR → REJECT；
// 父元素在 TABLE_PARENTS 且 data 全为空白 → REJECT。

export function domOffset(root: Element, container: Node, offset: number, edge: "start" | "end"): number | null
// 1. container 在排除子树内：取该子树根 el；edge=start → 返回 el 之前的累计长度；edge=end → el 之后。
// 2. container 是 Text：nodes 中找到它 → start + offset。
// 3. container 是 Element：offset 指子节点下标；取 childNodes[offset] 之前的所有可计文本长度。
// 4. container 不在 root 内 → null。

export function hastAnnotatableText(tree: HastNode): string    // 同规则，判断 className 含 "katex"、tagName figure/script/style、properties.dataAnnoUi
export function blockOf(root: Element, node: Node): Element | null  // 最近的 p, li, h1–h6, td, th, blockquote（不越过 root）
```

### 2. `rehype-annotations.ts`

```ts
export interface RenderMark {        // spec §5.4：一个 mark = 区间相同的一条重点和/或一条句子备注
  key: string;                       // "n:<noteId>" | "h:<highlightId>" | "p:<requestId>"
  start: number; end: number;
  highlightId?: string; noteId?: string;
  pending?: boolean; fresh?: ("hl" | "note")[]; ariaLabel: string;
}
export function rehypeAnnotations(options: { items: readonly RenderMark[] }): (tree) => void
```

算法：
1. `items` 按 `start` 排序；空则直接返回。
2. 深度优先遍历，规则同 §1，维护累计偏移 `pos`。对每个可计文本节点 `[pos, pos+len)`，求与各 item 的交集，把文本节点替换为 `[纯文本, span, 纯文本, …]`。
3. 片段元素：`{type:"element", tagName:"span", properties:{className:["reader-anno", highlightId? "reader-anno--hl", noteId? "reader-anno--note", pending? "reader-anno--pending", fresh.includes("hl")? "is-new-hl", fresh.includes("note")? "is-new-note"], dataAnnoKey: key}, children:[text]}`。
4. 每个 item 的**第一个**片段加 `tabIndex: 0, role: "button", ariaLabel`。
5. 每个 item 的**最后一个**片段：把最后一个字符（注意代理对：用 `Array.from(text).at(-1)` 计算长度）拆出，生成
   ```
   span.reader-anno-nb
     span.reader-anno.reader-anno--tail(同类名, dataAnnoKey)  ← 最后一个字符
     (noteId) span.reader-anno-bulb-anchor[dataAnnoUi]
                 button.reader-anno-bulb[dataAnnoUi][dataAnnoBulb=key][type=button][ariaLabel=查看备注][title=查看备注]
                   svg(灯泡图标，见 prototype.html ICON.bulb，stroke-width 2.4, aria-hidden)
   ```
6. 插入的元素不再参与计数（遍历时跳过新节点：先收集再替换，或替换后跳过）。

### 3. `MarkdownContent.tsx`

- 新 prop `marks?: readonly RenderMark[]`。
- 插件链：`[...rehypePlugins, markFigures(...), [rehypeAnnotations, { items }]]`，`items` 为空时不加。用 `useMemo` 以 `marks` 的稳定键（key+start+end+flags 拼接）记忆化。

### 4. `annotation-projection.ts`

```ts
export type Located =
  | { kind: "highlight"; item: ReadingHighlight }
  | { kind: "note"; item: SourceNote & { sentence: SentenceLocator } };
export function groupLocated(highlights: readonly ReadingHighlight[], notes: readonly SourceNote[],
  groups: readonly { id: string; chunk: ReaderChunk | null }[]): Map<string, Located[]>
export function resolveRange(text: string, loc: Pick<SentenceLocator, "range" | "quote">): { start: number; end: number } | null
export function buildMarks(text: string, located: readonly Located[], layer: AnnotationLayer)
  : { marks: ResolvedMark[]; lost: Located[] }
// ResolvedMark = { key; start; end; highlight?: ReadingHighlight; note?: SourceNote }（转换成 RenderMark 时补 ariaLabel/fresh/pending）
export function quoteAt(text: string, start: number, end: number): SentenceQuote   // prefix/suffix 各取 32 个 UTF-16 单元
```

- `groupLocated`：只取 `sentence != null` 的笔记；跳过 `deleted`、`sourceUpdated`。定位字段：重点直接读自身，句子备注读 `note.sentence`；行范围：重点 `sourceLines`，句子备注 `anchor.sourceLines`。先按 `planId+chunkId` 精确匹配，再按 bundle + 行重叠最大（规则同 `note-projection.ts`），同一 Chunk 多次出现归最后一个 group。
- `resolveRange`：见 spec §5.5 第 3 条。打分：`commonSuffixLength(text.slice(0, i), prefix) + commonPrefixLength(text.slice(i+len), suffix)`，相同分数取 `|i - range.start|` 最小。
- `buildMarks`：过滤 `layer`，逐条 resolve；解析后区间**完全相同**的一条重点与一条句子备注合成一个 mark（key 用 `n:<noteId>`）；其余冲突（部分重叠、同区间第二条同类记录）按 spec §5.5 第 4 条进入 `lost`；解析失败也进入 `lost`。

### 5. `ReadingChunk.tsx`

- 新 props：`located?: readonly Located[]`（该 Chunk 的全部层）、`pending?: { start: number; end: number; layer: AnnotationLayer } | null`、`fresh?: Record<string, ("hl"|"note")[]>`、`onLayerChange?(chunk, layer)`。
- 在组件内用 `useMemo`：渲染前先用 unified 管线算出当前层的 `hastAnnotatableText`（为避免二次解析成本，可在 `MarkdownContent` 中通过一个“文本探针”插件拿到文本并回调；实现二选一，在 Comments 记录选择及性能测量：100 段长 Chunk 渲染时间增幅 < 20%）。
- 把 `buildMarks` 结果转换成 `RenderMark[]` 传给 `MarkdownContent`；同时通过回调 `onMarks?(chunkKey, marks, lost)` 上报，供选区判断（工单 08）、吸附栏（工单 09）与资料栏（工单 12）使用。
- 原文/译文切换时调用 `onLayerChange`，`FocusReader` 记录每个 chunkKey 的当前层（选区与吸附栏需要）。

## 实施步骤

1. `Status: resolved`。
2. 先写**一致性测试** `annotatable-text.test.tsx`：夹具覆盖普通段落、多段、有序/无序列表、GFM 表格、行内与块公式、行内代码、代码块、链接、`**粗体**`、`==高亮==`、图片与图注、中英混排、emoji（代理对）。对每个夹具：渲染 `<MarkdownContent>`，断言 `domAnnotatableText(root).text === hastAnnotatableText(tree)`（tree 用同一插件链在测试里跑 unified 得到）。
3. `domOffset` 测试：边界在文本中、在元素间、在公式内（吸附到边界）、在 root 外。
4. `rehype-annotations.test.tsx`：单段内、跨行内元素（一半粗体一半普通）、跨公式（公式不被包裹）、尾字符代理对、有/无灯泡、`pending`/`fresh` 类名；渲染后再用 `domAnnotatableText` 计算，**总文本不变**（灯泡被排除）。
5. `annotation-projection.test.ts`：精确命中、偏移失配后靠引文找回、多处出现靠 prefix/suffix 选对、找不到进入 lost、部分重叠进入 lost、**同区间重点 + 句子备注合成一个 mark**、同区间两条重点只留一条、层过滤、Plan 重建（chunkId 变了）靠行重叠归属、无 `sentence` 的笔记被忽略。
6. 接入 `MarkdownContent`/`ReadingChunk`；用演示数据（工单 05 `seedMarks`）渲染，断言 6 个标注都出现在正确文字上，其中“重点 + 备注”的标注只有一组 span（同时有 `--hl` 与 `--note`）。

## 验收标准

- 以上测试全部通过；`MarkdownContent.test.tsx`、`Figures.test.tsx` 无回归。
- 没有标注时 `MarkdownContent` 输出与改动前完全相同（快照或 DOM 比较）。

## 测试

```bash
pnpm --filter @focus/reader-ui test -- annotatable-text rehype-annotations annotation-projection MarkdownContent Figures
pnpm reader:typecheck
```

## Comments
## Answer

已实现 DOM/HAST 可标注文本与 UTF-16 边界、跨行内节点的标注插件、尾字符代理对与灯泡、位置重新解析/重叠冲突/同区间合并、层过滤和 Plan 重建投影；ReadingChunk 提供 located/pending/fresh 与稳定的 onMarks(key, marks, lost, layer, text)、onLayerChange 回调。FocusReader 状态接线由依赖此接口的工单 08 完成。

共享 markdown-pipeline 将原始 HTML 单元格的二次 React Markdown 数学解析前移至 HAST；所有文本探针都在数学、图处理后执行，生成的“查看图”控件用 data-anno-ui 排除。原作者 mark 保留。projectSourceNotes 采用 anchor ?? placement 并排除句子备注。按 05 已记录的依赖修正，此工单补齐 seedMarks，演示六处标注首帧直接渲染，其中重点+备注共用同一组。

### 实施选择与性能

选择同一 Markdown 解析中的文本探针与转换器，不做重复解析。临时 SSR 测量：每组 100 个长 Chunk（原型第 1 段重复 8 次），预热后交替测量 5 组；无标注中位 301.088ms，标注中位 324.7154ms，增幅 7.85%（低于 20%）。这是本机 SSR 实验，不代替工单 13 的浏览器交互验收。

Unicode 边界补充：quoteAt 的 prefix/suffix 截取最多 32 UTF-16 单元，但分别剔除截断造成的首个孤立低代理、末个孤立高代理，必要时取 31 单元；避免 JSON/SQLite UTF-8 持久化出错。已同步规格 §4.1 注释，并添加 emoji 边界回归。

验证：annotatable-text、rehype-annotations、annotation-projection、annotation-demo、MarkdownContent、Figures、note-projection 共 47 项通过；reader-ui 与 standalone TypeScript 检查通过；standalone 生产构建通过（400 modules）。
