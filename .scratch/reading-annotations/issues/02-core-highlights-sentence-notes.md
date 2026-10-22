# 02 Core：重点存储 SourceHighlights + 笔记 `sentence` 字段

Status: resolved
Type: task
Blocked by: 01
Covers: spec §4.1、§4.2、§4.3（`sentence`）、D1、D2、D3、A15、A17（Core 部分）

## 目标

1. 新独立实体 **Reading Highlight**（重点）的持久化：创建、删除、撤销、幂等请求、清除。
2. **Reading Note** 增加 `sentence` 字段：句子备注 = 句子定位 + 备注文字（`content`），与其他 Reading Note 同表、同规则、同清除。

两者共用同一个 `notes.sqlite3`，共用 `requests` 幂等表与 `clears` 计数。

## 现状（行号基于提交 `03f127e`）

- `.agents/core/source_notes.py`
  - `class SourceNotes`（33 行起）；`_connect`（约 52–65）建表 `notes`、`requests`、`clears`，库在 `{workspace}/sources/{sourceId}/notes/notes.sqlite3`，WAL。
  - `_LOCK = threading.RLock()`、`_REQUEST = re.compile(r"[A-Za-z0-9-]{8,80}\Z")`（21–22 行）。
  - `_anchor(...)`（约 88–102）校验 anchor 并编码。
  - `_public(row, source_id, current_bundle)`（104–115）生成公开记录。
  - `save(...)`（145–181）：digest 幂等、`note_request_conflict`、`note_cancelled`、`note_bundle_changed`、`expected_generation`→`discussion_cleared`；**插入用位置参数** `INSERT INTO notes VALUES(?, 1, ?, ?, ?, ?, ?, ?, 0, ?)`。
  - `change(...)`（183–240）：edit/delete/undo，修订号冲突返回 `{"status":"conflict","current":...}`。
  - `clear(source_id, request_id)`（71 行）；`list(...)`（117 行）；`result(...)`（123 行）；`bundle_version(source_id)`。
- `.agents/core/discussion_application.py:23–26`：`self.notes = SourceNotes(Path(workspace), writer_id=writer_id)`。
- `.agents/core/source_clear.py:34–46`：`SourceClear.recover()` 调用 `self.notes.clear(...)`。

## 设计

### A. 迁移（`SourceNotes._connect`）

新增辅助函数，供本工单与工单 03 共用（先合入者创建）：

```python
@staticmethod
def _ensure_column(db, name: str) -> None:
    if name not in {row[1] for row in db.execute("PRAGMA table_info(notes)")}:
        db.execute(f"ALTER TABLE notes ADD COLUMN {name} TEXT")
```

`_connect` 中：
- `self._ensure_column(db, "sentence")`；
- `CREATE TABLE IF NOT EXISTS highlights (...)`，建表语句见 spec §4.2。

**必须**把 `save` 中的 `INSERT INTO notes VALUES(...)` 改为带列名：`INSERT INTO notes(id, revision, content, kind, origin, bundle, anchor, evidence_role, deleted, undo, sentence) VALUES(...)`。否则加列后位置参数个数不匹配。

### B. 共用的句子定位校验

在 `source_notes.py` 中新增模块级函数（`source_highlights.py` 也导入它）：

```python
def check_sentence(value, *, plan_id: str, chunk_id: str, has_translation: bool, code: str) -> dict:
    """Validate {layer, range, quote}; return the full SentenceLocator dict."""
```

规则见 spec §4.1。失败抛 `WorkspaceError(code, ...)`，句子备注传 `note_sentence_invalid`，重点传 `highlight_invalid`。返回值 `{"planId","chunkId","layer","range":{"start","end"},"quote":{"exact","prefix","suffix"}}`，键顺序固定（便于 digest 稳定，配合 `sort_keys=True` 编码）。

### C. 笔记 `sentence`

- `save(...)` 增加关键字参数 `sentence: dict | None = None`（已由 Host 用 `check_sentence` 校验并补全 `planId/chunkId` 的完整定位）。
  - `sentence` 非空时要求 `anchor` 非空（否则 `note_sentence_invalid`）。
  - `sentence` 放进 digest 的 `payload`（同一 requestId 换句子 → `note_request_conflict`）。
  - 存 `json.dumps(sentence, ensure_ascii=False, sort_keys=True)`。
- `_public` 增加 `"sentence": json.loads(row["sentence"]) if row["sentence"] else None`。
- `change(... "edit" ...)` 只改 `content`；`sentence` 不变。不需要其他改动。

### D. 新文件 `.agents/core/source_highlights.py`

```python
class SourceHighlights:
    """Reading Highlights stored beside Source notes (same database)."""
    def __init__(self, notes: SourceNotes): ...
    def save(self, source_id, *, request_id, plan_bundle, chunk_lines, locator,
             expected_generation=None) -> dict
    def change(self, source_id, *, highlight_id, request_id, expected_revision, operation) -> dict
    def list(self, source_id, *, include_deleted=False) -> list[dict]
    def result(self, source_id, request_id) -> dict | None
```

- 调用方（Host，工单 04）从 Plan 读出 `chunk_lines`、`plan_bundle`，并用 `check_sentence(..., code="highlight_invalid")` 生成 `locator`。Core 不依赖 Host 的 `CoreBridge`。
- `save`：
  - `request_id` 用 `SourceNotes._check_request`；
  - `expected_generation` 语义同笔记 → `discussion_cleared`；
  - digest = `_payload_identity({"entity":"highlight","op":"create","sourceId":..., "bundle": plan_bundle, "locator": locator})`；重放返回原结果；同 id 不同 digest → `highlight_request_conflict`；已取消 → `note_cancelled`（沿用）；
  - `plan_bundle != self.notes.bundle_version(source_id)` → `highlight_bundle_changed`；
  - 插入：`id = uuid.uuid4().hex`，`revision=1`，`undo='{"operation":"create"}'`；结果 `{"status":"saved","highlight": public}`。
- `change`：
  - `operation ∈ {"delete","undo"}`，否则 `highlight_invalid`；
  - id 不存在 → `highlight_not_found`；
  - 修订号不等 → `{"status":"conflict","current": public}`（结果也写入 requests）；
  - `delete`：`deleted=1`，`undo='{"operation":"delete"}'`；
  - `undo`：无撤销槽 → conflict；`create` 的撤销 = `deleted=1`；`delete` 的撤销 = `deleted=0`；撤销后 `undo=NULL`；
  - 成功 `revision += 1`，返回 `{"status":"changed","operation":op,"highlight": public}`。
- 公开记录：spec §4.2 字段，`quote`/`range` 从列还原，`sourceUpdated = bundle != current`，`canUndo = undo is not None`。
- 顺序 `ORDER BY rowid`。写库全程持 `_LOCK`，在 `with closing(self.notes._connect(source_id)) as db, db:` 中 `BEGIN IMMEDIATE`；若 `SourceNotes` 写前做 workspace lease 检查，这里同样调用。

### E. 清除与接线

- `SourceNotes.clear` 在同一事务中追加 `DELETE FROM highlights`。句子备注就在 `notes` 表里，无需额外处理。
- `DiscussionApplication.__init__`：`self.highlights = SourceHighlights(self.notes)`。
- `SourceClear` 不改。

## 实施步骤

1. `Status: resolved`。
2. 先写失败测试：
   - `tests/test_source_highlights.py`（夹具参照 `tests/test_source_notes.py`：临时 workspace、注册 Source、生成 Parser Bundle）：
     - 创建字段完整；重放返回同一 highlightId；同 id 不同 locator → conflict；
     - `check_sentence` 每个校验分支各一例（键集合、layer、无译文的 translation、range 边界、quote 键与长度）；
     - delete → undo 恢复；create → undo 软删除；无撤销槽再 undo → conflict；过期修订号 → conflict 带 current；未知 id → `highlight_not_found`；
     - Bundle 变化后 `sourceUpdated=True`，新建 → `highlight_bundle_changed`；
     - `SourceNotes.clear` 后重点为空；旧库（无 highlights 表）打开后自动建表。
   - 在 `tests/test_source_notes.py` 增加：
     - 带 `sentence` 的保存，公开记录含 `sentence`；不带时为 `None`；
     - `sentence` 无 `anchor` → `note_sentence_invalid`；同 requestId 换 `sentence` → `note_request_conflict`；
     - edit 后 `sentence` 不变；
     - 旧库（无 `sentence` 列）迁移后旧行 `sentence is None`，且新保存成功（证明插入改为带列名）。
3. 实现，红转绿。
4. 跑全部笔记相关测试确认无回归。

## 验收标准

- 新测试通过；`test_source_notes`、`test_direct_source_notes`、`test_source_discussion`、`test_stage6b_clear_retention` 无回归。
- 重点写入与请求回执在同一事务（异常注入测试一次：中途抛错不留半条记录）。

## 测试

```bash
PYTHONPATH=tests:.agents:. .venv/bin/python -m unittest -q test_source_highlights test_source_notes test_direct_source_notes test_source_discussion test_stage6b_clear_retention
```

## Comments

## Answer

Implemented SourceHighlights in the shared SourceNotes database, sentence locator validation, sentence-note persistence, shared clear fencing, and DiscussionApplication wiring. Existing note rows migrate on open; note INSERT uses explicit columns.

Validation: 45 tests passed across test_source_highlights, test_source_notes, test_direct_source_notes, test_source_discussion, and test_stage6b_clear_retention. TDD red cases covered missing highlight API, missing change API, unsupported sentence field, and clear retaining highlights before their corresponding implementation. SQLite receipt-write fault injection confirmed no highlight or request survives rollback. These are synthetic Core/Host tests, not real Runtime acceptance.

Windows execution used repository-local TEMP/TMP and a short fixture ROOT to avoid nested worktree path-length limits; HTTP/rename suites required escalated execution.
