# 10 吸附关闭：灯泡、段末小段笔记折叠行、讨论保存反馈

Status: resolved
Type: task
Blocked by: 08
Covers: spec §6.1、§6.7（讨论反馈）、U7、A7、A8

## 目标

吸附关闭时：句子备注以灯泡显示（工单 06/07 已渲染，本工单确认交互闭环）；每段末尾出现小段笔记折叠行；讨论保存笔记后给出定位反馈。

## 现状

- 吸附关闭时 `notesOpen=false`，旧实现**完全不显示**段落笔记（这是要改的）。
- 段落文章底部已有 `<footer><button>引用提问</button></footer>`（`ReadingChunk.tsx:30`），悬停才显示（`mist-reader.css:255–263`）。
- 讨论“存为笔记”按钮：`ReadingChunk.tsx:75` → `FocusReader.tsx:749` `send("请把下面的回答记下来：…", false, false, chunk)`。
- 资料栏笔记页反馈：`view.noteFeedback` → “已记下 / 未保存，可重试”（`FocusReader.tsx:667`）。

## 设计

### 1. 折叠行（`ChunkNotes variant="fold"`）

- 位置：每个 group 的 `.reading-group-passage` 内、正文之后（吸附关且非堆叠时）。
- 结构：
  ```
  div.reader-chunk-notes-fold[data-open]
    div.row
      (N>0) button.ghost[aria-expanded][aria-controls]  › 小段笔记 · N
      (有 createSourceNote) button.ghost  + 记小段笔记
    div.body (grid 0fr/1fr)  > div.inner[inert 当关闭] > div.panel  条目列表 + 编辑框
  ```
- 不重复“就这段讨论”——段落 footer 已有“引用提问”。
- 展开状态：组件内 `Set<chunkKey>`（不持久化）；正在编辑时强制展开；新条目（见下）自动展开。
- 条目、编辑、删除、记小段笔记逻辑与工单 09 `variant="rail"` 共用。

### 2. 灯泡闭环检查

- 吸附关时灯泡可见、可聚焦（Tab 顺序：标注文字 → 灯泡）、点击打开查看框（工单 08）。
- 吸附开时灯泡 `visibility:hidden`，不在 Tab 顺序中（`visibility:hidden` 自然移出；确认 jsdom 外的浏览器行为在工单 13 中断言）。

### 3. 讨论保存反馈

在 FocusReader 中对比前后快照：
- 条件：新快照 `noteFeedback?.status === "saved"`，且 `sourceNotes` 出现了之前没有的 noteId。
- 用 `projectSourceNotes` 判断新笔记归属 group：
  - 有 → 记录 `freshNoteId`（条目加 `is-new`，M11）；吸附关时展开该 group 折叠行；toast `已存为第 N 段的小段笔记 · 查看`，“查看”调用现有滚动控制器 `scrolling.controller.current?.jump(条目元素)`（减少动效时瞬移），然后重放 `is-new`。
  - 无 → toast `已存为整篇笔记，可在资料栏查看`。
- 不自动滚动（用户正在阅读；只有点“查看”才移动）。
- 资料栏原有“已记下”状态保留。

## 实施步骤

1. `Status: claimed`。
2. 失败测试（`ChunkNotes.test.tsx`、`FocusReader.test.tsx` 新用例）：
   - 吸附关：折叠行数量、展开收起 aria、`inert`；N=0 时只有“记小段笔记”。
   - 记小段笔记在折叠行内完成。
   - 讨论保存（mock host 在 `sendMessage` 后返回带 `noteFeedback` 和新笔记的快照）：带 placement → 对应段展开 + toast 文案含段号；无 placement → 整篇 toast；“查看”调用 jump。
   - 灯泡：吸附关可点击；吸附开 CSS 规则存在（类名断言）。
3. 实现。

## 验收标准

- 测试通过；工单 13 浏览器场景 A7、A8 通过。

## 测试

```bash
pnpm --filter @focus/reader-ui test -- ChunkNotes FocusReader MistReader
```

## Comments

2026-10-23：折叠行与反馈分别按 TDD 推进：先因缺少 fold 组件/保存反馈失败，再实现转绿；吸附关保存自动展开用例先红，复用 09 已验证的 ChunkNoteList 切片后转绿。真实 Chrome 发现无引用回答“存为笔记”误用当前段，新增公开 UI 用例证实 receipt 错误后修复为明确 null，保留“undefined 才沿用当前阅读上下文”的合同。

## Answer

新增 ChunkNotesFold/FoldedChunkNotes：关闭吸附后在每段末尾提供数量折叠行、aria-expanded/controls 与 inert 关闭面板；新建、编辑期间及新保存条目自动展开，零条时只显示创建入口。共用 09 的直接记笔记/编辑/删除/撤销和草稿实现，不经过 AI。讨论保存按新 noteId 与有效投影区分段笔记和整篇笔记，显示对应 toast；只有点“查看”才跳转并重播条目强调，接收新增笔记快照前 hold 阅读位置。

同时补齐两处交互边界：保存时继续输入的句子备注，成功后保留草稿并切换为编辑已确认笔记，后续保存不再创建重复备注；保存回调暴露 editorRect/noteId/token 供 11 的 M8 动效消费。新 toast 覆盖旧通知，6 秒关闭只影响显示。

验证：73 项批注、fold/list、反馈及 FocusReader/MistReader/旧 AttachedNotes UI 测试通过，reader-ui TypeScript 与 git diff --check 通过。真实 Chrome A7/A8/A9 通过：fold 展开/收起、带引用讨论保存到第 3 段并带“来自讨论”、无引用回答保存以 receipt:null 生成整篇 toast、直接创建带 chunk、不经 AI，以及 Bundle 变化转存整篇；并通过既有 A1/A2/A3/A4/A10/A17 预检。日志 `tmp/test-runs/annotations/detached-10.log` 与 `detached-metrics.json`（本地临时证据）。物理 IME 仍由 13 记录 NOT_RUN，不以 DOM 事件替代。
