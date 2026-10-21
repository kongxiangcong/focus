# 06 Host 创建笔记、bundleVersion 与适配器

Status: ready-for-agent
Blocked by: 05
Covers: spec §3.6，问题 P5

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
- `host/service.py:74`：`self.source_notes = self.discussion_app.notes`
- `host/service.py:75`：`self.source_clear = SourceClear(self.store, self.source_notes)`
- `host/service.py:140`：`selection = json.loads((self.workspace / 'state.json').read_text()).get('sources', {}).get(window['source']['sourceId'], {}) if (self.workspace / 'sta`
- `host/service.py:141`：`for c in ([*window['history'], *([window['current']] if window['current'] else [])] if selection.get('reading_started') else []):`
- `host/service.py:143`：`if selection.get('reading_started') and window['current']:`
- `host/service.py:271`：`window['sourceNotes'] = self.source_notes.list(note_source, include_deleted=True) if note_source else []`
- `host/server.py:311`：`if len(parts) >= 2 and parts[1] == 'notes':`
- `host/server.py:316`：`result = service.source_note_change(source_id, unquote(parts[2]), self._body(), parts[3])`
- `host/core_bridge.py:13`：`from core.source_notes import SourceNotes`
- `host/core_bridge.py:23`：`'topic_notes': ('topic_notes', {'topic_id': 'string'}),`
- `host/core_bridge.py:31`：`('search', 'read_range', 'topic_search', 'topic_range', 'topic_notes')}) +`
- `host/core_bridge.py:38`：`'action': {'type': 'string', 'enum': ['catalog', 'search', 'read_range', 'topic_search', 'topic_range', 'topic_notes', 'source_note']},`
- `host/core_bridge.py:119`：`# Missing selection/plan is a real empty state; corrupt assets remain errors.`
- `host/core_bridge.py:137`：`'current': self.project_chunk(result['current']) if result['current'] else None,`
- `ui/packages/reader-contracts/src/index.ts:180`：`sourceNotes?: readonly SourceNote[];`
- `ui/packages/reader-contracts/src/index.ts:324`：`assets: { bundle: boolean; blog: boolean; notes: boolean; plans: number; progress: boolean };`
- `ui/packages/reader-contracts/src/index.ts:342`：`selectionReason?: string;`
- `ui/packages/reader-contracts/src/index.ts:365`：`selectionReason?: string;`
- `ui/apps/standalone/src/adapters/http-reader-host.ts:149`：`...(typeof item.selection_reason === "string" ? { selectionReason: item.selection_reason } : {}),`
- `ui/apps/standalone/src/adapters/http-reader-host.ts:415`：`return this.request(`/library/sources/${encodeURIComponent(sourceId)}/notes/${encodeURIComponent(noteId)}/${operation}`,`
- `ui/apps/standalone/src/adapters/http-reader-host.ts:422`：`const response = await this.fetch(`${this.baseUrl}/library/sources/${encodeURIComponent(sourceId)}/notes/requests/${encodeURIComponent(requestId)}`);`

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
