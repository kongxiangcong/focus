# 04 Host：重点接口、句子备注创建、窗口快照

Status: resolved
Type: task
Blocked by: 02, 03
Covers: spec §4.3、§4.4、A15、A16、A17（Host 部分）

## 目标

1. 暴露 Reading Highlight 的 HTTP 接口，`GET /reader/window` 返回 `sourceHighlights` 与 `highlightOperation`。
2. 现有直接记笔记接口 `POST /library/sources/<id>/notes` 接受可选 `sentence`，用于创建句子备注。

## 现状（行号基于提交 `03f127e`）

- 路由：`host/server.py:311–323` 有笔记五条路由（POST 创建 201、GET requests、POST edit/delete/undo）。错误映射：`note_bundle_changed` → 409（`host/server.py:124–125`）。
- `HostService.source_note_create`（`host/service.py:520–546`）：校验 `chunk` 形状、`self.core.plan_bundle(source_id, planId)` 比对 Bundle、`self.core.reference({...})` 读出 `sourceLines`，生成 `anchor`，调用 `SourceNotes.save`。
- `HostService.source_notes = DiscussionApplication(...).notes`（`host/service.py:73–74`）。
- 快照：`snapshot()`（`host/service.py:198–271`）中 `window['sourceNotes'] = self.source_notes.list(note_source, include_deleted=True)`；`noteOperation` 的清空 key 列表在 1171、1243 行附近。

## 设计

### A. 句子备注（改 `source_note_create`）

在现有 `chunk` 分支内，生成 `anchor` 后：

```python
sentence = payload.get('sentence')
if sentence is not None:
    if chunk is None:
        raise WorkspaceError('note_sentence_invalid', '句子备注需要段落引用')
    sentence = check_sentence(sentence, plan_id=chunk['planId'], chunk_id=chunk['chunkId'],
                              has_translation=bool(reference.get('translation')),
                              code='note_sentence_invalid')
```

- `sentence` 与 `quote` 不能同时给（同时给 → `ValueError('笔记段落引用不正确。')`）。
- 有 `sentence` 时 `kind` 必须是 `thought`、`origin` 必须是 `user`，否则 `ValueError('笔记类型或来源不正确。')`。
- 把 `sentence=sentence` 传给 `self.source_notes.save(...)`。
- `CoreBridge.reference`（`host/core_bridge.py:233–260`）返回投影后的 ReaderChunk，`translation` 为译文字符串或空；`has_translation` 统一用 `bool(reference.get('translation'))`。

### B. 重点服务方法（`host/service.py`）

```python
self.source_highlights = self.discussion_app.highlights   # 紧挨 source_notes 赋值

def source_highlight_create(self, source_id, payload): ...
def source_highlight_change(self, source_id, highlight_id, operation, payload): ...
def source_highlight_request(self, source_id, request_id): ...
```

`source_highlight_create`：
1. 与 `source_note_create` 同样先 `self.source_clear.recover()`，校验 `source_id` 是当前讨论 Source。
2. payload 键集合恰为 `{'requestId','chunk','layer','range','quote'}`，`chunk` 键集合 `{'planId','chunkId'}`；否则 `ValueError('标注参数不正确。')`。
3. `plan_bundle = self.core.plan_bundle(...)`；`reference = self.core.reference({'sourceId': source_id, **chunk})`。
4. `locator = check_sentence({'layer':..., 'range':..., 'quote':...}, plan_id=..., chunk_id=..., has_translation=..., code='highlight_invalid')`。
5. `self.source_highlights.save(source_id, request_id=..., plan_bundle=plan_bundle, chunk_lines=reference['sourceLines'], locator=locator, expected_generation=当前 generation)`。
6. `self.state['highlightOperation'] = {'sourceId': source_id, **result}`，`self.changed()`，返回 `self.snapshot()`。

`source_highlight_change`：payload 键集合 `{'requestId','expectedRevision'}`；调用 `change`；同样写 `highlightOperation`。

`source_highlight_request`：返回 `self.source_highlights.result(source_id, request_id)`。

### C. 快照

在设置 `sourceNotes` 的同一位置：

```python
window['sourceHighlights'] = self.source_highlights.list(note_source, include_deleted=True) if note_source else []
window['highlightOperation'] = (self.state.get('highlightOperation')
    if note_source and (self.state.get('highlightOperation') or {}).get('sourceId') == note_source else None)
```

`highlightOperation` 的清空时机与 `noteOperation` 相同（把 `'highlightOperation'` 加进 1171、1243 行附近的 key 列表）。

### D. 路由（`host/server.py`，放在笔记路由后）

| 方法 | 路径正则 | 处理 | 成功码 |
|---|---|---|---|
| POST | `^/library/sources/([^/]+)/highlights$` | `source_highlight_create` | 201 |
| GET | `^/library/sources/([^/]+)/highlights/requests/([^/]+)$` | `source_highlight_request` | 200 |
| POST | `^/library/sources/([^/]+)/highlights/([0-9a-f]{32})/(delete\|undo)$` | `source_highlight_change` | 200 |

鉴权、`X-FOCUS-Instance` 校验、JSON 解析、`validate_source_id` 与笔记路由完全一致——复用同一分发逻辑。

错误映射：`highlight_bundle_changed`、`highlight_request_conflict` → 409；`highlight_invalid`、`note_sentence_invalid` → 400；`highlight_not_found` → 404。

## 实施步骤

1. `Status: resolved`。
2. 失败测试 `tests/test_reading_highlights_host.py`（夹具参照 `tests/test_direct_source_notes.py`）：
   - 重点：HTTP 创建 201，快照含 `sourceHighlights[0]`，`sourceLines` 等于 Chunk 行范围；非法 payload 400；Plan Bundle 过期 409 `highlight_bundle_changed`；delete/undo 各一次，`highlightOperation` 正确；过期修订号 conflict；重放两次返回同一 highlightId 且库里一条；`GET requests/<id>`；
   - 句子备注：`POST .../notes` 带 `chunk + sentence` → 201，`sourceNotes` 末条 `sentence.planId/chunkId` 与 chunk 相同、`anchor.sourceLines` 为 Chunk 行范围、`anchor` 无 `quote`；不带 `chunk` → 400 `note_sentence_invalid`；`kind:"conclusion"` → 400；`sentence` 与 `quote` 同给 → 400；`layer:"translation"` 而 Chunk 无译文 → 400；
   - 清除讨论与笔记后 `sourceHighlights == []` 且句子备注消失；重置阅读同样；新建会话（Fresh Session）都保留；
   - 缺少或错误 instance 头 → 与笔记接口同样被拒。
3. 实现，红转绿。

## 验收标准

- 测试通过；`test_direct_source_notes`、`test_web_host` 无回归。

## 测试

```bash
PYTHONPATH=tests:.agents:. .venv/bin/python -m unittest -q test_reading_highlights_host test_direct_source_notes test_source_highlights
PYTHONPATH=tests:.agents:. .venv/bin/python -m unittest -q test_web_host
```

## Comments

## Answer

Implemented authenticated, instance-bound highlight create/delete/undo/request HTTP routes, sourceHighlights and highlightOperation snapshots, direct sentence-note creation and validation, stable annotation error codes, and shared clear/reset operation scrubbing.

Validation: required ticket04 suites passed43 tests (test_reading_highlights_host, test_direct_source_notes, test_source_highlights, test_web_host). Final note/discussion/annotation regression passed39 tests after a legacy receipt compatibility repair; the explicit pre-upgrade receipt fixture also passed after final fixture refinement. TDD red/green slices covered missing routes, delete/undo, missing sentence persistence, generic error codes, stale Plan with unavailable archive, clear leaking saved operation, and pre-upgrade request digest conflict.

Seven annotation HTTP tests cover creation/replay/receipt lookup, chunk scope, delete/undo/stale revisions, strict payloads, source/translation validation, bundle changes409, missing404, note semantics, authorization/instance rejection, Fresh Session preservation, clear/reset erasure and request cancellation. These are isolated synthetic Host/Core tests; no real model was invoked.

Compatibility repair: absent sentence/placement fields retain the pre-annotation note request digest; supplied fields still participate in identity. Highlight creation rejects stale Plan Bundle before attempting historical reference lookup, preserving highlight_bundle_changed409 even when the archive is unavailable.
