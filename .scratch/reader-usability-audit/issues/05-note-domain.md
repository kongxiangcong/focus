# 05 领域记录：CONTEXT 与 ADR 0031

Status: resolved
Blocked by: —
Covers: spec §3.6，问题 D1、D2、D5

## 目标
按以下已确认条款实现（05 仅领域记录；06 仅 Host/合同/适配器；07 仅投影布局；08 仅编辑器与入口）。

- **新接口** `POST /library/sources/<sourceId>/notes`，请求体：
  ```json
  { "requestId": "…", "content": "…", "kind": "thought", "origin": "user",
    "chunk": { "planId": "plan-001", "chunkId": "chunk-002" }, "quote": "可选" }
  ```
  处理放在 `host/service.py` 新方法 `source_note_create()`，路由在 `host/server.py` 现有 `notes` 分支：
  1. 与 `source_note_change` 一样，校验 `sourceId` 是当前讨论来源，并调用 `source_clear.recover()`。
  2. 有 `chunk` 时，读取该 Plan 的 Chunk 记录与 `provenance.json`。Plan 的 bundle 不等于当前 Parser Bundle 时，抛 `WorkspaceError('note_bundle_changed', '这段原文已更新，可改存为整篇笔记')`。否则 `anchor = {sourceId, bundle, sourceLines: chunk.source_lines, quote?}`。
  3. 调用 `SourceNotes.save(bundle=当前 bundle, request_id=requestId, intent_id=requestId, kind, origin, evidence_role, anchor)`。`evidence_role` 在 `kind === "question"` 时为 `unresolved_question`，否则为 `explanation`。
  4. 写 `state['noteOperation'] = {'sourceId', 'status': 'saved', 'note'}`，调用 `changed()`，返回 `snapshot()`。
  - `kind` 只接受 `thought` / `conclusion` / `question`；`origin` 只接受 `user` / `dialogue`。
- **Chunk 投影**：`core_bridge.project_chunk()` 输出 `bundleVersion`（取 Plan `provenance.json` 的 `bundle`，按 Plan 缓存，避免每段读文件）。合同 `ReaderChunk` 增加 `bundleVersion?: string`。
- **合同**：`ReaderHost` 增加 `createSourceNote?(input: CreateSourceNoteInput): Promise<ReaderHostResult<ReadingWindow>>`；`http-reader-host.ts` 与 `fixture-reader-host.ts` 都要实现，fixture 版要能模拟成功、失败、`note_bundle_changed` 三种结果。
- **领域记录**：`CONTEXT.md` 的 Reading Note 条目补充“可按 Source Anchor 显示在对应 Reading Chunk 旁（吸附笔记），但不属于 Chunk 或 Plan；可由用户直接手写，或从讨论回答中确认保存”，并新增术语 **Attached Notes（吸附笔记）**。新建 `docs/adr/0031-attached-notes-and-direct-note-entry.md`，取代 ADR 0026 中 Discussion attachment 的部分。在 ADR 0026 末尾加一行 superseded 指针，保留原文。

## 现状（对照当前代码核实后的文件与行号）
基线 PR #24 `9f183cd`；相对审计 HEAD 的增量为技能文档清理，产品问题仍存在。FigureViewer 实际与 FigurePanel 同文件。
- `CONTEXT.md:128`：`按 Chunk 隔离的阅读资产，包含可选的纯中文翻译与阅读进度记录；中文来源不保存重复翻译，主动 Reading Notes 独立属于 Source。`
- `CONTEXT.md:131`：`**Reading Note**:`
- `CONTEXT.md:136`：`属于 FOCUS Workspace、固定绑定一份 Reading Source 的持续讨论，独立于所选 Backend；切换 Backend 不拆分或重建讨论。讨论历史与显式 Reading Notes、Reading Cursor 分开，保留至用户明确清除。`
- `CONTEXT.md:137`：`_Avoid_: Backend-specific chat, native Runtime Session, Reading Note, reading checkpoint`
- `CONTEXT.md:140`：`用户确认后清除一份 Reading Source 的全部 FOCUS Discussions、派生讨论摘要和 Reading Notes，并使关联运行上下文失效。它保留 Reading Plan、Reading Cursor、Blog Output 和 Reading Progress Entrie`
- `CONTEXT.md:153`：`每个 Reading Chunk 推进或完成本篇时系统简短保存的阅读进度记录，记载读过的段落、实际讨论的话题及用户明确表达的理解；与主动 Reading Note 分开，不表示系统对能力的评价，也不决定阅读位置。`
- `docs/adr/0026-reading-lens-on-demand-figures.md:7`：`2026-10-20: Reading figures open only on explicit demand. Paragraph thumbnails open the native image viewer; “在资料栏固定” opens the Source gallery and sel`
- `docs/adr/0026-reading-lens-on-demand-figures.md:11`：`Reading Lens represents visual attention, never the persistent Reading Cursor. Discussion attachment is an explicit local presentation preference, pau`

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

- 文件：CONTEXT.md、ADR 0031、ADR 0026 superseded 指针、docs/design/README.md 索引。
- 纯文档工单按要求跳过红灯；术语、文件及指针断言 PASS；git diff --check PASS。
- `pnpm reader:typecheck` PASS；`pnpm reader:test` PASS（107+154）。无界面改动，截图/构建 NOT_APPLICABLE；06–11 功能不由本 ADR 验收通过。
