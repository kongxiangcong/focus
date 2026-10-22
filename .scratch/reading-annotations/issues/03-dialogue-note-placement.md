# 03 Core/Host：讨论笔记的 placement（修复“记一下”不显示）

Status: resolved
Type: task
Blocked by: 01
Covers: spec §4.3、D4、§6.7（Host 部分）、A8

## 问题与根因（已在当前服务器核实）

用户在讨论中引用某段并说“记一下”，笔记保存成功，但吸附栏看不到。

1. 讨论保存路径：`POST /reader/messages` → `HostService.start`（`host/service.py:1182` 起）。有段落引用时 `discussion['reference'] = self.core.reference(receipt)`（1210–1218），含该段 `sourceLines`、`bundleVersion`。
2. `DiscussionApplication.bind` 用正则 `_SAVE`（含“记一下”，`.agents/core/discussion_application.py:16–44`）设置 `saveIntent`。
3. 模型调用 `focus` 工具 `source_note` → `HostService._tool_call`（`host/service.py:1690–1707`）→ `DiscussionApplication.candidate(discussion, 'source_note', candidate)`（`discussion_application.py:68–77`）→ `SourceNotes.save(..., **arguments)`。
4. **Host 不会根据讨论引用自动生成锚点**；只有模型在参数里给出 `anchor` 才有。`methods/source-discussion/METHOD.md:14` 还要求类比、未解决问题不要加锚点。所以多数“记一下”的笔记 `anchor: null`。
5. 前端 `projectSourceNotes`（`ui/packages/reader-ui/src/note-projection.ts:7`）跳过 `!note.anchor`，因此不显示。笔记本身在资料栏“笔记”页能看到。

## 目标

给 Reading Note 增加“显示位置”`placement`，讨论有段落引用且模型未给 `anchor` 时由 Host 填写；前端投影用 `anchor ?? placement`（前端部分在工单 05/09）。

## 设计

### Core：`.agents/core/source_notes.py`

- `_connect`：`self._ensure_column(db, "placement")`（辅助函数定义见工单 02 §A；先合入的工单创建它）。`save` 的 `INSERT INTO notes` 必须改为带列名（工单 02 §A），本工单若先合入则由本工单改。
- 新方法 `_placement(source_id, version, placement)`：`None` 直接返回；否则键集合必须恰为 `{"sourceId","bundle","sourceLines"}`，`sourceId == source_id`、`bundle == version`，`sourceLines` 校验同 `_anchor`（整数、1 起、闭区间、在 Bundle 行数内）；不合格抛 `note_placement_invalid`。
- `save(...)` 增加关键字参数 `placement: dict | None = None`，写入列；**加入请求 digest**（否则同 requestId 不同 placement 会被误判为重放）。
- `_public` 增加 `"placement": json.loads(row["placement"]) if row["placement"] else None`；`sourceUpdated` 改为 `bool((anchor or placement) and row["bundle"] != current_bundle)`；`referenceStatus` 同理。
- `change` 的 edit/delete/undo 不改 placement。

### Core：`.agents/core/discussion_application.py` 的 `candidate` → `source_note`

在现有校验之后、调用 `save` 之前：

```python
placement = None
reference = scope.get("reference")
if "anchor" not in arguments and reference and reference.get("bundleVersion") == bundle == self.notes.bundle_version(source_id):
    placement = {"sourceId": source_id, "bundle": bundle, "sourceLines": list(reference["sourceLines"])}
return self.notes.save(..., placement=placement, **arguments)
```

- 只在模型没有给 `anchor` 时填；给了 anchor 的笔记已能投影。
- 引用的 Bundle 与当前不同（历史版本）→ 不填，笔记成为整篇笔记（现有 `note_bundle_changed` 规则不变）。
- 不改 METHOD.md；不让模型知道 placement。

### Host

`host/service.py` 在 `start` 中已把 `reference` 写进 `discussion`，只需确认 `candidate` 收到的 `scope` 就是这个 `discussion` 字典（`_tool_call` 传入 `self.active_discussion`）。如果持久化/恢复讨论时 `reference` 被丢弃（检查讨论恢复路径，例如 `resume` 相关代码），要一并保存 `reference.sourceLines` 与 `reference.bundleVersion`。

### 直接记笔记

`HostService.source_note_create`（`host/service.py:520–546`）现有行为是带 `chunk` 时生成 `anchor`，**保持不变**（它表示用户针对该段写的笔记，ADR 0031 已接受）。

## 实施步骤

1. `Status: claimed`。
2. 失败测试（新增到 `tests/test_source_discussion.py` 或新文件 `tests/test_dialogue_note_placement.py`）：
   - 讨论带段落引用、模型保存无 anchor → 快照 `sourceNotes[-1].placement.sourceLines == 该段 sourceLines`，`anchor is None`；
   - 模型给了 anchor → `placement is None`；
   - 讨论无引用 → `placement is None`；
   - 引用历史 Bundle → 不填 placement（或按现有规则拒绝保存，以现状为准并写明）；
   - 同 requestId 重放结果一致；
   - 旧库升级：先用旧 schema 建库插入一条笔记，再用新代码 `list` → 字段 `placement: None`；
   - Bundle 更新后带 placement 的笔记 `sourceUpdated=True`。
   参考 `tests/test_source_discussion.py:38–40` 的默认测试运行时（无 anchor 保存）和 `tests/test_stage4_reading.py:719–724`（带 receipt 与 anchor）。
3. 实现。
4. 回归：笔记相关全部测试。

## 验收标准

- 上述测试通过；无回归。
- 在开发服务器的真实 Knowledge Base 副本（复制到 /tmp，隔离 Host）中手动走一遍：引用段 → “记一下” → `GET /reader/window` 返回的新笔记带 `placement`。记录请求/响应摘要到 Comments。

## 测试

```bash
PYTHONPATH=tests:.agents:. .venv/bin/python -m unittest -q test_source_discussion test_source_notes test_direct_source_notes test_stage4_reading
```

## Comments

2026-10-23：TDD 首个 Host `start`/`snapshot` 用例先因 `placement` 缺失失败，再实现并通过。Host `start` 已将完整 `reference`（含 sourceLines/bundleVersion）与 discussion 一起保存进请求记录，运行时传递同一 scope；无需改恢复路径。历史 Bundle 依既有规则拒绝保存（绑定后变化报 `source_bundle_changed`，原有历史 scope 报 `note_bundle_changed`），不伪造显示位置。

真实 Knowledge Base 副本验收：从机器当前配置定位到库，仅只读复制源文件，SQLite 数据库用只读连接 backup；在仓库 tmp 的短路径副本启动隔离 Host。副本中清除目标来源旧讨论与笔记后，引用一段发送“记一下”：`POST /reader/messages → 200`；随后 `GET /reader/window → 200`，新笔记 `anchor:null`、`placement.sourceLines:[1,38]`、placement.bundle 等于笔记 bundle。外部 Runtime 用受控 CandidateRuntime，不调用真实模型；这是实际来源副本上的 Host/存储验收，不宣称外部模型效果。脱敏摘要：`tmp/annotation-placement-copy-evidence.json`（本地、不提交）。原库未写入。

## Answer

SourceNotes 兼容迁移 placement 列，以严格显示位置校验与请求 digest 保存；公开记录返回 placement，并据 `anchor ?? placement` 标记来源版本/历史可用性。编辑、删除和撤销保留位置。DiscussionApplication 仅在模型未给 anchor 且引用 Bundle 为当前版本时填 placement，继续拒绝模型传入 placement/sentence；证据锚点和直接手写笔记合同不变。

验证：新增 Host 与 Core 公开边界行为检查（有引用/无引用/证据锚点、重复请求与内容冲突、非法位置、旧 schema 迁移、修改/删除/撤销、Bundle 更新与历史可用性）；指定 `test_source_discussion test_source_notes test_direct_source_notes test_stage4_reading` 共 65 项通过，`git diff --check` 通过。嵌套 worktree 首轮触发 Windows 长路径、沙箱 socket/文件权限与既有时序失败；改用仓库短 fixture 根并提升执行后全部通过，未改断言或产品逻辑。
