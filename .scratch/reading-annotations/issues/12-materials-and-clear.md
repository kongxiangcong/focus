# 12 资料栏笔记页与清除/重置

Status: resolved
Type: task
Blocked by: 04, 05
Covers: spec §5.5（失效显示）、§11、A11（界面部分）、A15

## 目标

资料栏“笔记”页能看到句子备注与失效标注；小段/整篇笔记分组清楚；清除与重置后界面同步为空。

## 现状

- 资料栏笔记页：`FocusReader.tsx:666–686`，`details.focus-source-notes`，标题“笔记 · N”，空态“明确说“记下来”后，笔记会保存在这篇材料下。”，列表含编辑/删除/撤销。
- 资料栏分类按钮计数：654 行 `笔记 <small>{未删除笔记数}</small>`。
- 吸附栏卡片“编辑”会 `setSideMode("notes")` 并滚动到 `[data-source-note-id]`（旧 `onOpenNote`，760 行），新吸附栏不再使用。

## 设计

1. 笔记页分三组（各自 `details`，默认展开）：
   - **小段笔记**：无 `sentence`、且投影到某段（`anchor ?? placement` 有效）的 Reading Note，每条前加“第 N 段”（N 为该 Chunk index；未加载的段用 `sourceLines` 显示“第 a–b 行”）。
   - **整篇笔记**：无 `sentence` 的其余 Reading Note。
   - **句子备注**：带 `sentence` 的 Reading Note，按“句子 + 备注”显示：第一行「原句」（`sentence.quote.exact`，2 行截断，左侧 2px 红色虚线），第二行备注（`content`）；纯文本场景（复制、title 属性）用 `sentenceNoteText`。失效的（工单 06 `lost` 或 `sourceUpdated`）加标签“原文位置已失效”。点击条目：若该段已加载，关闭资料栏并 `jump` 到标注、加 `is-pulse`；否则无操作并给出提示“该段未加载”。
   - Reading Highlight **不**列出（U4）；与句子备注合成的标注只列句子备注这一条。
2. 编辑/删除/撤销：小段/整篇沿用现有逻辑；句子备注的“编辑”关闭资料栏并打开工单 08 的编辑框（段未加载时禁用），“删除”只删这条句子备注（`changeSourceNote delete`）+ 撤销；同区间的重点保留。
3. 计数：654 行仍为 `Reading Note 未删除数`（句子备注本身就是 Reading Note，已包含在内；重点不计）。
4. 空态文案改为：`在正文中选中句子可以标重点或写备注；对讨论说“记下来”可保存小段笔记。`
5. 清除/重置：Host 已在工单 02/04 保证；前端确认快照中 `sourceHighlights` 为空、`sourceNotes` 无未删除项后，本地乐观状态、草稿（`focus.annotationDrafts`、`focus.chunkNoteDrafts` 中属于该 Source 的键）一并清理——挂到现有 `focus.draftResetVersions` 机制（`FocusReader.tsx:237–250`）。

## 实施步骤

1. `Status: resolved`。
2. 失败测试（`FocusReader.test.tsx` 或新 `SourceNotesPanel.test.tsx`；如 666–686 行抽成组件更好测，可以抽出 `SourceNotesPanel.tsx`）：
   - 三组分类正确（带 `sentence` 的只进句子备注组，不进小段笔记组）；重点不列出；句子备注显示「原句」+ 备注；失效标签；
   - 点击句子备注跳转（mock jump）；
   - 计数；
   - resetVersion 变化后草稿键被清理。
3. 实现。

## 验收标准

- 测试通过；`confirmed_ux_browser.mjs` 的资料栏编辑/删除/撤销场景更新选择器后通过。

## 测试

```bash
pnpm --filter @focus/reader-ui test -- SourceNotesPanel FocusReader
```

## Comments

## Answer

Extracted SourceNotesPanel with default-open small-paragraph/whole-source/sentence groups, live-note counts, quote-plus-remark text, lost-position tags, scoped edit/delete/undo callbacks, unloaded notices, and exact SentenceLocator Plan/Chunk navigation priority. Sentence deletion changes only that Reading Note; highlights remain independent. A loaded lost remark can still edit its content without relocating its sentence; its quote-view action does not jump to an unrelated location.

Added optional ReadingWindow.noteClearVersion from SourceNotes.generation (spec section4 supplement), because notes-only clears do not change resetVersion. Both explicit versions invalidate only the matching Source's persisted annotation/chunk-note drafts and existing local UI; empty collections alone preserve recoverable input. Fixture clear now mirrors annotation/request-recovery erasure and returns an idempotent clear generation.

Validation: SourceNotesPanel+FocusReader22 tests PASS; fixture-reader-host4 PASS; annotation Host HTTP7 PASS; contracts/UI/standalone TypeScript checks PASS; standalone production build PASS. Focused Chrome materials regression PASS: threegroups, existing note edit/delete/undo, sentence quote+remark, and unchanged Reading Cursor. Synthetic screenshot/results: tmp/test-runs/annotations/panel12.png and panel12-results.json. The old full confirmed-UX harness has pre-existing fixture-contract issues recorded in browser-notes.md; its matching note scenario was run through the corrected isolated temporary launcher. Full browser matrix remains ticket13.

Integration pointer for08: FocusReader.sentenceNoteController ref accepts openEditor(note), openNote(note), and optional lostSentenceNoteIds;08 binds its controller and06 mark registry here. SourceNotesPanel passes the owning loaded chunk to its direct callback; lost edits use chunk-level positioning without highlighting or rebinding the quote.08 must also clear optimistic/hook state when resetVersion or noteClearVersion changes. No global event bridge was added.
