# 08 选区气泡、标注气泡、备注编辑/查看、乐观保存与撤销

Status: resolved
Type: task
Blocked by: 06, 07
Covers: spec §5.3、§6.1–§6.6、U5、U6、D7、D8、A1–A4、A16

## 目标

在正文里完成标注的全部交互（不含吸附栏布局与动效飞行），吸附开/关下行为一致。

## 现状

- 选区：`FocusReader.tsx:569–578` `readSelection()`，限定 `.focus-reading .focus-markdown`，产出 `{chunk, text, x, y}`；857 行渲染 `.reader-selection-quote` 按钮“引用所选提问”，点击 `referenceChunk(chunk, text)`。
- 滚动容器：`<main className="focus-stream" ref={stream}>`（713 行）。
- 读者关闭逻辑：`preserveReading(fn)` 保持阅读位置（用于开关类操作）。
- Host 写方法与快照：工单 05。投影与渲染：工单 06。样式：工单 07。

## 设计

### 文件

新目录 `ui/packages/reader-ui/src/annotations/`：

| 文件 | 职责 |
|---|---|
| `AnnotationLayer.tsx` | 挂在 `.focus-stream` 内的绝对定位层（`position:absolute; inset:0 auto auto 0; width:100%; pointer-events:none`，子浮层 `pointer-events:auto`），承载气泡/编辑框/查看框；坐标换算 `top = rect.top - streamRect.top + stream.scrollTop` |
| `AnnotationBubble.tsx` | 选区气泡与标注气泡（同一组件，`mode: "selection" \| "annotation"`） |
| `AnnotationEditor.tsx` | 备注编辑框（浮层） |
| `AnnotationNotePop.tsx` | 备注查看框 |
| `useAnnotationActions.ts` | 写操作、乐观状态、失败重试、撤销 |
| `useAnnotationDrafts.ts` | `sessionStorage["focus.annotationDrafts"]` 读写 |
| `AnnotationToast.tsx` | 单例 toast（有现成通知组件则复用），`aria-live="polite"`，6 秒 |
| `placement.ts` | `placeFloat(el, rect, side, align)`：spec §6.2/§6.4 的定位与翻转规则、`--arrow-x` |

`.focus-stream` 需要 `position: relative`（检查现有样式，如无则在 `reader-annotations.css` 中补）。

### 状态（放在 FocusReader 或一个 `useAnnotations` hook 中）

```ts
type Float =
  | { kind: "selection"; draft: SelectionDraft; rect: DOMRect; overlap: "none" | "partial"; crossBlock: boolean }
  | { kind: "annotation"; key: string; rect: DOMRect }        // key = RenderMark.key
  | { kind: "editor"; target: EditorTarget }
  | { kind: "note"; key: string };
interface SelectionDraft { chunk: ReaderChunk; layer: AnnotationLayer; start: number; end: number; quote: SentenceQuote; text: string }
type EditorTarget =
  | { isNew: true; draft: SelectionDraft }                 // 新句子备注；draft 来自选区，或来自已有重点的区间与原句
  | { isNew: false; noteId: string; revision: number };   // 编辑已有句子备注
```

`pending`（新建备注时的灰色虚线）由 `float.kind === "editor" && target.isNew` 推出，传给 `ReadingChunk`。

### 选区（替换 `readSelection` 与 857 行按钮）

按 spec §5.3：
1. 计算偏移用 `domOffset`；`layer` 取 FocusReader 记录的该 chunkKey 当前层。
2. `crossBlock = blockOf(start) !== blockOf(end)`。
3. 与工单 06 上报的该 Chunk 当前层 marks 比较得到 `overlap`；完全包含于某个 mark → 直接切到 `{kind:"annotation"}`。
4. 触发：`pointerup`（目标在 `.focus-stream` 内，`setTimeout 0`）和 `selectionchange`（去抖 220ms，指针按下期间忽略）。
5. 按钮能力：有 `createHighlight` 才显示“重点”，有 `createSourceNote` 才显示“备注”；都没有时只显示“引用提问”。

### 气泡按钮行为

| 按钮 | 行为 |
|---|---|
| 重点（选区） | `createHighlight({sourceId, requestId, chunk:{planId,chunkId}, layer, range, quote})`，乐观渲染带 `fresh:["hl"]`；清除选区；关闭气泡 |
| 备注（选区） | 清除选区；`float = editor({isNew:true, draft})` |
| 引用提问 | 现有 `referenceChunk(chunk, text)`；清除选区 |
| 重点（标注，只有备注） | `createHighlight`，locator 用该 mark 当前解析区间 + `note.sentence.quote`（prefix/suffix 用 `quoteAt` 重新计算）；`fresh:["hl"]` |
| 取消重点（标注，有重点和备注） | `changeHighlight(h, "delete")`；先播 M5 再提交渲染（M5 可在工单 11 补，先直接切换） |
| 取消重点（标注，只有重点） | 等同“删除标注” |
| 备注（标注，只有重点） | `float = editor({isNew:true, draft: 由重点的区间与原句构造})` |
| 编辑备注（标注，有备注） | `float = editor({isNew:false, noteId, revision})` |
| 删除标注 | 对存在的重点、句子备注并行发 delete；一个 toast `已删除标注 · 撤销` |

编辑框保存：新建 → `createSourceNote({sourceId, requestId, content, kind:"thought", origin:"user", chunk:{planId,chunkId}, sentence:{layer, range, quote}})`；编辑 → `changeSourceNote(sourceId, noteId, "edit", revision, requestId, content)`。新建成功后从 `noteOperation.note.noteId` 得到 id，用于焦点转移到灯泡/卡片。

按钮 `onPointerDown={e => e.preventDefault()}`。标注气泡打开时焦点到第一个按钮。

### 点击与键盘委托（在 `.focus-stream` 上）

- `click` 命中 `[data-anno-bulb]` → `float = note(key)`（吸附开时灯泡不可点，见工单 07 CSS）。
- `click` 命中 `.reader-anno[data-anno-key]` 且当前选区为空 → `float = annotation(key, rect)`；若它是正在编辑的待定标注则忽略。
- `keydown` Enter/Space 于 `.reader-anno[tabindex]` → 同上。
- `pointerover/pointerout` 于 `.reader-anno` → 同 key 的所有片段与吸附栏卡片加/去 `is-linked`（卡片部分在工单 09 消费，同一个 `linkedKey` 状态）。

### 编辑框

spec §6.4 全部规则。实现要点：
- 受控 `textarea`；`onCompositionStart/End` 记录组字；`onKeyDown`：`if (e.nativeEvent.isComposing || composing || e.keyCode === 229) return;` → Enter 且非 Shift 提交，Escape 取消。
- 提交时快照 payload；请求进行中禁用“保存”防重复；成功后只在草稿未被再次修改时清空（交互契约）。
- 外部 `pointerdown`：草稿空 → 取消；非空 → 保持。
- 打开时记录 `editorRect` 供工单 11 的 M8 使用（通过 ref 暴露 `getBoundingClientRect`）。

### 乐观与失败

spec §6.6。`useAnnotationActions` 维护 `optimistic: Map<requestId, {entity:"highlight"|"note", op:"create"|"edit"|"delete", record}>`，渲染用 `merge(view.sourceHighlights, view.sourceNotes, optimistic)`（乐观新建的重点用临时 `highlightId = "p-" + requestId`，句子备注同理）；收到快照后按 requestId（`highlightOperation` / `noteOperation`）或记录 id 清理。网络失败时保留并提示重试（`重点未保存 · 重试` / `备注未保存 · 重试`），重试复用 requestId。挂载时对 sessionStorage 中记录的未决 requestId 按实体调用 `highlightRequestResult` / `sourceNoteRequestResult`。

### 撤销

toast 中保存被删记录列表 `[{entity, id, revision}]`（revision 取 delete 返回值）；点击撤销对每条调用对应的 undo（`changeHighlight(..., "undo")` / `changeSourceNote(..., "undo")`）。两条删除只成功一条时 toast 改为 `标注只删除了一部分 · 重试`，重试只发失败的那条。同时只保留最近一条 toast。

## 实施步骤

1. `Status: claimed`。
2. 失败测试（Vitest + Testing Library，`ui/packages/reader-ui/src/annotations/*.test.tsx`），宿主用工单 05 fixture 或内联 mock：
   - 选区在段内 → 三按钮；跨段落元素 → 只有“引用提问”；部分重叠 → 提示文字；完全包含 → 标注气泡；无 `createHighlight` → 不显示“重点”；无 `createHighlight` 且无 `createSourceNote` → 只有“引用提问”。
   - 重点：`createHighlight` 参数正确（range、quote.prefix/suffix 长度 ≤32、layer）；渲染出 `.reader-anno--hl`。
   - 备注保存：`createSourceNote` 参数含 `kind:"thought"`、`origin:"user"`、`chunk`、`sentence`；先重点后备注 → 同一组 span 同时有 `--hl` 与 `--note`。
   - 备注：编辑框出现；Enter 提交、Shift+Enter 换行、组字中 Enter 不提交（用 `compositionstart` + `keyDown {isComposing:true}`）、Esc 取消且非空草稿出现“已放弃这条备注 · 撤销”并能恢复；外部点击行为两种。
   - 草稿：输入后卸载重挂，草稿恢复。
   - 标注气泡：取消重点（有/无备注两种）、给重点加备注、编辑备注（调 `changeSourceNote edit`）、删除（两条记录都发 delete）→toast→撤销（两条都 undo）；fixture `failNext("note")` 时出现“只删除了一部分”。
   - 灯泡点击 → 查看框，Esc 关闭焦点回灯泡。
   - 失败：fixture `writeOutcome="failed"` → 不渲染、编辑框带草稿重开、toast 重试；重试成功且只产生一条记录；`bundle_changed` 提示“这段原文已更新，标注未保存”且不重试。
   - 选区引用提问行为与原先一致（迁移 `MistReader.test.tsx` 中相关断言）。
3. 实现。

## 验收标准

- 测试通过；`FocusReader.test.tsx`、`MistReader.test.tsx`、`AttachedNotes.test.tsx` 中与选区引用相关断言更新后通过。
- 物理中文输入法手测（Chrome + 系统拼音）：组字中按 Enter 只上屏不提交；记录到 Comments（不能用 DOM 事件代替）。

## 测试

```bash
pnpm --filter @focus/reader-ui test -- annotations MistReader FocusReader
pnpm reader:typecheck
```

## Comments

2026-10-23：通过 TDD 实现；首个编辑器用例先因缺组件失败，首个整合选区用例先因无“重点”气泡失败，再分别实现转绿。物理系统拼音输入法手测为 NOT_RUN：当前自动化只能生成 DOM 组字事件，不能将其视作物理 IME 证据；此项保留到工单 13 的人工验证缺口。

## Answer

已接入选区/标注气泡、句下备注编辑与查看框、灰色待定标注、灯泡委托点击/键盘、草稿持久化和放弃撤销。useAnnotations 隔离交互与逐出现位置的 marks/lost/layer/text registry；原文/译文层从实际 article 读取，重复 Chunk 不会串层。浮层按最终 Range 行框定位，并在滚动、缩放、布局变化及 transition/animation 结束后重新定位；非空编辑器在外点、新选区与吸附切换时保留。

独立 useAnnotationActions 实现乐观写、同 ID 重试、未决请求恢复、部分删除重试与双实体撤销、版本冲突保留草稿、清除/重置 epoch 围栏；临时记录禁止发删除请求。写快照通过 preserveReading 接收，资料栏句子编辑/查看直接接入 controller。重点与句子备注投影按规格合成，资料栏失效状态由当前层实际 lost 记录提供。

验证：61 项 UI 测试通过（21 项批注/编辑/动作行为检查及 40 项 FocusReader/MistReader/AttachedNotes 回归），reader-ui TypeScript 与 git diff --check 通过。受控 fixture 的真实 Chrome A1/A2/A3 预检通过：三按钮选区、重点 700 字重/渐变与刷新持久化、已有重点增加含 Shift+Enter 换行的备注、灯泡查看、编辑框位于最后选中片段下方 0..20px；日志 `tmp/test-runs/annotations/preflight-08.log`。浏览器证据不覆盖物理 IME，也不宣称真实模型质量。
