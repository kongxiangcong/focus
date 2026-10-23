# 09 吸附栏：跟随卡片、小段笔记区、记小段笔记、堆叠布局

Status: resolved
Type: task
Blocked by: 08
Covers: spec §6.1、§6.7、§6.8、§7.3、U4、U7（吸附开部分）、D5、A5、A9、A13

## 目标

用新的吸附栏替换 `AttachedNotes`：句子备注卡片跟随句子且互不重叠，小段笔记在卡片区下方（段结束处之下），能直接记小段笔记；窄时退为堆叠。

## 现状

- `FocusReader.tsx:293–296`：`notesOpen = mist && attachNotes && !showStructure`；`notesLayout = off | side | split`（按 `readingWidth >= columnWidth + padding + noteGap + noteWidth`）；`projectedNotes = projectSourceNotes(view?.sourceNotes ?? [], paragraphGroups)`。
- `FocusReader.tsx:743`：每个 group 渲染 `.reading-group-passage`（正文）与 `.reading-group-discussion`（讨论）。
- `FocusReader.tsx:754–766`：`<AttachedNotes chunk notes onDiscuss onOpenNote />`，`onDiscuss` → `preserveReading(() => referenceChunk(group.chunk))`。
- `AttachedNotes.tsx`：sticky 列表，`kinds` 中文映射在第 4 行。
- `mist-reader.css:271–300`：side/split 网格与 `.reading-group-notes` 样式；CSS 变量 `--reader-notes-width/gap/max-height` 在 `FocusReader.tsx:631` 设置；`typography.ts:15` `readingLayout = { padding: 48, noteGap: 32, noteWidth: 280 }`。
- `note-projection.ts:7`：跳过 `!note.anchor`。
- 浏览器回归 `tests/reading_attachment_browser.mjs` 依赖旧结构（`complementary` 名称“第 2 段笔记”、`.reading-group-notes`）。

## 设计

### 1. 投影修复

`note-projection.ts`：先跳过 `note.sentence != null` 的句子备注（D11，它们以卡片显示）；`const anchor = note.anchor ?? note.placement;`，后续全部用 `anchor`；跳过条件改为 `!anchor`。补测试：只有 placement 的笔记被投影；二者都有时用 anchor；带 `sentence` 的笔记不出现在小段笔记。

### 2. 组件

| 文件 | 职责 |
|---|---|
| `annotations/AnnotationRail.tsx` | `<aside class="reader-anno-rail" aria-label="第 N 段笔记">`，内含 `.reader-anno-rail__anchored`（卡片区，`position:relative`）与 `ChunkNotes` |
| `annotations/AnnotationCard.tsx` | 一张卡片 = 一条句子备注（按“句子 + 备注”显示）：引文 `sentence.quote.exact`（该 mark 同时有重点时引文加黄底+700）、备注正文 `content`（保留换行，纯文本）、右上角操作（编辑备注 → 工单 08 编辑框；删除标注 → 工单 08 删除流程，同时删同区间的重点） |
| `annotations/ChunkNotes.tsx` | 小段笔记区（吸附开）与折叠行（吸附关，工单 10 使用同一组件的 `variant="fold"`） |
| `annotations/rail-layout.ts` | 纯函数布局 + `useRailLayout` hook |

`AttachedNotes.tsx` 删除，`FocusReader` 中 754–766 行改为渲染 `AnnotationRail`。`aria-label` 保持“第 N 段笔记”，减少旧测试改动。

### 3. 卡片布局（`rail-layout.ts`）

```ts
export function layoutCards(items: { key: string; anchorTop: number; height: number }[], gap = 8)
  : { key: string; top: number; displaced: boolean }[]   // 按 anchorTop 升序；top = max(anchorTop, prevBottom + gap)；displaced = top > anchorTop + 6
export function railHeight(passageHeight: number, cards: { top: number; height: number }[]) // max(passageHeight, lastBottom + 4)
```

`useRailLayout(railRef, passageRef, keys)`（key = 有备注的 mark 的 `RenderMark.key`，即 `n:<noteId>`）：
- 测量：`anchorTop = 第一个 .reader-anno[data-anno-key=key] 的 getClientRects()[0].top − railAnchored.getBoundingClientRect().top − 6`；`height = card.offsetHeight`。
- 写入：`card.style.transform = translateY(top)`，`card.dataset.top = top`，`classList.toggle("is-displaced")`；`railAnchored.style.height = railHeight(...)`。
- 触发：`ResizeObserver`（stream、passage、每张卡片）、`document.fonts.ready`、标注列表变化、层切换、阅读宽度/字号变化；所有触发合并到一次 `requestAnimationFrame`。
- 首次布局与开关吸附时给 rail 加 `.no-anim`，下一帧移除（M13）。
- **只读写本 rail 内元素**；不要在布局中修改 scrollTop。

### 4. 网格

- `side`：`.reading-group-passage` 维持现有两列（正文 `var(--reader-column)`，栏 `minmax(0,1fr)`，`gap: var(--reader-notes-gap)`）；栏改为非 sticky、`align-self:start`；栏左 `padding-left:14px; border-left:1px solid var(--reader-line)`。
- `split`：保持 3fr/1fr。
- 堆叠：当 rail 实际宽度 < 200px 或 `data-reading-narrow=true` 时，`.focus-reader` 加 `data-anno-rail="stacked"`：passage 单列，rail 出现在正文下方（`margin-top:14px; border-left:0; padding-left:0`），卡片 `position:relative; transform:none; margin-bottom:8px`，不画连接短线，不计算跟随。

### 5. 小段笔记区（`ChunkNotes variant="rail"`）

spec §6.7 与 §3 文案。
- 条目内容用 `MarkdownContent`（与旧 AttachedNotes 一致）。
- `记小段笔记`：区域内编辑框（类型单选 想法/结论/问题），Enter 保存 → `host.createSourceNote({sourceId, requestId, content, kind, origin:"user", chunk:{planId, chunkId}})`。失败 `note_bundle_changed` → 行内提示 + “存为整篇笔记”按钮（去掉 chunk 重试，同一新 requestId）。
- `编辑`/`删除`：`host.changeSourceNote`；删除 toast 撤销（复用工单 08 的 toast）。
- `就这段讨论`：`preserveReading(() => referenceChunk(group.chunk))`（与旧实现相同）。
- 草稿：`sessionStorage["focus.chunkNoteDrafts"]`（spec §6.7）。
- host 无 `createSourceNote` 时隐藏“记小段笔记”。

### 6. 联动

工单 08 的 `linkedKey` 状态：卡片 `pointerenter/leave/focus/blur` 设置；卡片 `is-linked` 类；点卡片空白（不在按钮或表单内）→ 对应片段加 `is-pulse`（M10，移除再加以重启动画）。

## 实施步骤

1. `Status: resolved`。
2. 失败测试：
   - `rail-layout.test.ts`：不重叠、被挤开标记、高度计算。
   - `AnnotationRail.test.tsx`：卡片只来自句子备注，只有重点的标注不出卡片（U4）；“重点 + 备注”的卡片引文带黄底；小段笔记显示 anchor 与 placement 两类；空态文案；记小段笔记调用参数；bundle 变化后改存整篇；编辑/删除/撤销。
   - `note-projection.test.ts` 补 placement 用例。
   - 更新 `AttachedNotes.test.tsx` → 重命名为 `AnnotationRail.test.tsx`，保留仍成立的旧断言（开关持久化、就这段讨论、side/split 判定）。
3. 实现；完成后删除 `mist-reader.css` 中旧 `.reading-group-notes*` 等规则。
4. 更新 `tests/reading_attachment_browser.mjs` 的选择器到新结构（保持其几何断言含义：side 时正文宽度不变 756px、栏宽 280px）。

## 验收标准

- 单元测试通过；`reading_attachment_browser.mjs` 更新后通过。
- 演示数据下（1600×1000、1280×800、1024×768）：卡片互不重叠；未被挤开的卡片 top 与句子首行 top 差 ≤ 8px；小段笔记区 top ≥ 正文 bottom 且 ≥ 最后一张卡片 bottom（工单 13 自动化）。

## 测试

```bash
pnpm --filter @focus/reader-ui test -- rail-layout AnnotationRail note-projection FocusReader
pnpm reader:typecheck && pnpm reader:build
```

## Comments

## Answer

Replaced AttachedNotes with AnnotationRail sentence cards, anchored packing and rail-height measurement, followed by the shared ChunkNotes/ChunkNoteList paragraph section. Highlights without remarks never create cards. Card quote emphasis follows the merged highlight, action callbacks reuse08 edit/delete/undo, and linking/pulse stay within the owning passage. Layout signatures include range and highlight presence/revision so a bold-line reflow is measured even when note keys and total heights remain unchanged.

Rails below200px (or reading-narrow) stack below the source; wide mode preserves original text width and280px rail. Cards are nonsticky and paragraph notes begin below both the body and last card. ResizeObserver, font readiness and layout changes schedule one animation-frame measurement; no scrollTop writes. Existing note projection from06 excludes sentence notes and accepts placement.

Shared paragraph CRUD now supports direct save withoutAI, kind selection, composition-safe Enter/Shift+Enter, chunk Bundle conflict fallback to whole-source with a newrequestId, persistent source/chunk/note drafts, edit/delete/undo, revision conflicts, optimistic pending content/deletion and failure recovery. Retry identity survives component remount. Newer text typed during an earlier pending save is preserved.10fold/feedback integration was merged while retaining explicit null discussion-reference semantics; rail receives its freshNoteId.

Validation: targeted09tests33 PASS before10merge; combinedrail/fold/feedback38 PASS; finalsharedlist/fold8 PASS; annotations13 PASS after scoping the existing deletion test to its open popup (cards now also expose Delete Annotation). CompleteUI run had181 PASS and that one stale unscoped selector failure; its corrected focused suite passed. Contracts/UI/standalone typechecks and productionbuild PASS. Final full-suite aggregation belongs to13 after11.

Chrome reading_attachment_browser.mjs PASS:756px text/280px side rail; split or specified stacked fallback; reading-anchor preservation; discussion binding; cards and paragraph foot;390–1600px; preference; reducedmotion. The old bounded sticky-scroll assertion was replaced by foot-below-body/card assertions because sticky lists were intentionally removed. Root independently ran A5 at1600/1280/1024: all cards have actual anchors, non-displaced tops differ by≤8px, cards do not overlap, paragraph foot is below body/cards, bulbs hidden, and placement-origin label correct. Evidence: tmp/test-runs/annotations/rail-09.log, browser/rail-metrics.json, rail09-browser/metrics.json. Synthetic fixtures only.
