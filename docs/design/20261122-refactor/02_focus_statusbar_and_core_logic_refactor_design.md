# 设计文档 02：状态栏全链路语义治理、核心逻辑修复与电量式进度（修订版）

> **所属序列**：Focus 重构体系 · 文档 02（分两批交付：Batch A 状态栏与运行时止血先行；Batch C 在完成语义 ADR 修订后落地电量式进度）
> **基线版本**：`focus-d4fb6a5a36af50e01611fe26ff949749226c0300`
> **前置约束**：遵守文档 00 的三条运行时所有权红线；电量式进度实施前须先通过第 4 节的完成语义 ADR 修订。

---

## 1. 拆分交付策略

本文档包含两类风险与依赖截然不同的改动，实施时拆分为两批：

- **Batch A（低风险、高收益、立即可做）**：状态栏去已完成态、单一 SSE 订阅与按作用域清错、`ReadingScroll` 60fps 空转止血、全屏 `Esc` 仲裁与键盘焦点闭环。不修改持久化阅读完成语义。
- **Batch C（先定 ADR、再动持久化投影）**：废除人工“完成本篇”按钮与双轨完成态，统一为知识库自动派生 `BatteryProgress` 电量式进度框。

---

## 2. Batch A · 状态栏全链路语义治理

### 2.1 现有 15 处过时/已完成滞留位点

| 分类 | 精确文件与行号 | 现状问题 |
| :--- | :--- | :--- |
| 已完成态滞留 | `TaskProgress.tsx:5, 21-33` & `host/service.py:383, 2049-2053` | 问答完成后落盘并持续下发 `status: "completed"` 的 `run`，前端渲染“已完成 + 耗时”。 |
| 已完成态滞留 | `WorkspaceApp.tsx:105, 225-233, 291-301, 622-668` | `readyNotice` 横幅、`preparationNotice` 就绪框（无关闭钮）与任务抽屉 `<summary>已完成任务</summary>` 长期霸占界面。 |
| 已完成态滞留 | `host/service.py:353, 2159` & `FocusReader.tsx:717` | `noteFeedback: { status: "saved" }` 持久化落盘，刷新后仍一直显示过时的“已记下”。 |
| 过时错误滞留 | `WorkspaceApp.tsx:193-197, 213-215` & `ConversationReader.tsx:36, 41` | SSE 重连或轮询恢复时未清连接错误，断线红条永驻。 |
| 跨文章串台 | `host/service.py:686-715, 2045-2046` & `ConversationReader.tsx:109` | 问答失败 `run` 与 `expired` 审批不清理，且前端未校验 `agent.run.sourceId === sourceId`，文章 A 报错串台到文章 B。 |
| 错用错误条 | `FocusReader.tsx:954, 999-1003, 1032` | 切精读未就绪时把“正在准备逐段精读”塞进 `setError()` 当红条展示，准备完成后不消失。 |
| 治标清理机制 | `host/status_notifications.py:5-9, 41-67` | 把 `completed/ready` 与 `failed/error` 混在 `TERMINAL_STATUSES`，只打 `dismissed` 标不剔除，“全部清空”误伤真实错误，且 `requests` 列表无限增长。 |

### 2.2 统一活跃状态契约与后端生命周期重构

1. **后端活跃状态投影（`reader-contracts/src/index.ts` & `host/service.py`）**：
   ```ts
   export interface ActiveStatusItem {
     id: string;                 // `${kind}:${targetId}:${attemptId}`
     kind: "chat" | "preparation" | "blog" | "ingestion" | "batch" | "progress" | "opening";
     targetId: string;
     sourceId?: string | null;   // 前端按当前文章隔离
     phase: "running" | "approval" | "error"; // 严格禁止 completed / ready / saved
     label: string;
     stage?: string;
     percent?: number;
     error?: string | null;
     attemptId: string;
     retryable?: boolean;
     cancellable?: boolean;
   }
   ```
2. **后端终态静默退出规则（`host/service.py`）**：
   - `_project_snapshot()`（L383）：对 `status === "completed"` 的 `run` 返回 `agent.run = null`（历史仍归档于 `execution:<runId>`）。
   - `_run()`（L2045-2046）：任务结束直接清空 `approvals`（审批超时转为 `run.status = "failed"`）。
   - `batch_list()` / `inbox_items()`：任务态投影直接过滤 `completed / deleted`，只吐出进行中与未忽略错误。
   - `noteFeedback`（L2159）：不再持久化 `status: "saved"`，仅保留失败态；`opening_errors` / `blog_errors` 在重新生成成功或来源删除时自动 `pop`。
3. **重写 `host/status_notifications.py`**：
   - 将 `TERMINAL_STATUSES` 移除 `'completed'`, `'ready'`, `'deleted'`，改名 `DISMISSIBLE_ERROR_STATUSES`。
   - 废除 `dismissedPreparation:<source_id>` 多套隐藏机制与无限增长的 `requests` 列表，改为按 `kind:identity -> attempt_id` 覆盖写入的单条错误忽略 `POST /reader/status/dismiss`。

### 2.3 单一 SSE 订阅与三层作用域错误隔离（严禁笼统 `result.ok → 清 error`）

- **单一 SSE 连接**：由 `WorkspaceApp.tsx` 唯一调用 `host.subscribe()` 并将快照透传给 `FocusReader` / `ConversationReader`，消除三路独立 `EventSource`。
- **三层独立错误作用域（核心修正）**：禁止在收到任意健康快照 `result.ok` 时笼统清空所有错误，改为严格按作用域独立管理：

| 错误作用域 | 归属状态 | 合法清理触发器 | 绝不被什么清除 |
| :--- | :--- | :--- | :--- |
| **连接层（`connectionError`）** | `WorkspaceApp` | SSE 重连或轮询恢复健康快照（`result.ok`） | — |
| **来源/文档层（`sourceError`）** | `ConversationReader` / `FocusReader` | 切换 `sourceId`（代际变更）或当前来源文档重新加载成功 | 无关的 SSE 心跳快照 |
| **操作尝试层（`operationError`，含笔记版本冲突）** | 对应操作组件（绑定 `attemptId` / `operation`） | 用户显式重试成功、手动点击关闭 `×` 或切换来源 | **SSE 重连恢复或其他无关健康快照** |

- **前端清理清单**：
  - `TaskProgress.tsx:5, 21`：移除 `terminal.completed`，遇 `completed` 返回 `null`。
  - `WorkspaceApp.tsx`：删除 `readyNotice`、`preparationNotice` 的 `ready` 分支与 `<summary>已完成任务</summary>`；仅在 `route !== "/reading"` 时渲染顶栏 `AgentControls`（消除阅读页双处审批）；`navigate()` 清理 `notice`。
  - `FocusReader.tsx`：移除持久化 `noteFeedback === "saved"` 展示与 `expired` 审批；切精读“准备中”改为派生自 `view.preparations[sourceId]`，不再塞进 `setError()`。
  - `ConversationReader.tsx`：`ConversationComposer` 校验 `agent.run.sourceId === sourceId`；`.source-reader-error` 增加关闭钮；`positionNotice` 3s 自动消隐并在手动滚动时立即清空。

---

## 3. Batch A · 核心性能与交互逻辑修复

1. **【P0】停止 `ReadingScroll` 60fps 常驻空转**（`ui/packages/reader-ui/src/reading-scroll.ts:48-61, 134-149`）：改为事件驱动，仅在 `ResizeObserver`、`MutationObserver`、滚动事件、`streaming === true` 或 `heldUntil` 期间按需调度 rAF，静止态 0 唤醒。
2. **【P0】修复 `UnifiedReader` 切篇不同步（带代际校验）**（`FocusReader.tsx:964-1009`、`WorkspaceApp.tsx:302-306`）：偏好为 `chunks` 且切换 `sourceId` 时主动调用 `host.openSource(sourceId)` 并比对 `selectionGeneration` 防旧响应覆盖；失败空态提供明确准备操作与一键切回对话入口。
3. **【P0】修复全屏 `Esc` 抢占与退全屏丢状态**（`WorkspaceApp.tsx:552-557`、`ConversationReader.tsx:371-386`、`FocusReader.tsx:1017`）：全局 `Escape` 优先让 `dialog[open]` / 抽屉 / 批注编辑器消费；移除 `exitedFullscreen` 清空 `activeEvidence / returnPosition / jumpOrigin` 的逻辑；全屏保留模式切换入口与桌面宽屏双栏能力。
4. **【P0】修复 `#reading-children` 退场动画被 `hidden` 杀死**（`WorkspaceApp.tsx:582-584`）：改用 `inert` + `aria-hidden`。
5. **【P1】键盘焦点闭环与替换原生阻塞弹窗**：为 `.source-notes-drawer` 补全打开聚焦、关闭回焦与 `Esc` 优先关闭；将 `FocusReader.tsx:740, 824` 的 `window.confirm()` 替换为统一 `<dialog>`；`WorkspaceSelection.tsx:77` 仅在独立入口页启用 `autoFocus`；清理未使用的 `onSaveAppearance` 死代码并统一设置页标题文案。

---

## 4. Batch C · 完成语义 ADR 修订与知识库电量式进度框

### 4.1 现状冲突与 Owner 裁决（坚持单一事实源，拒绝双态并存）

现有代码存在两处硬约束：Core 禁止在末段继续 `advance` 而要求显式 `finish`，且知识库认可无精读 Plan 的独立 Source 完成记录。若退而求其次“同时保留电量覆盖率与独立完成记录”，会导致知识库出现“20% 红电却标已读完”的认知分裂。

**Owner 裁决**：坚持**废除“完成本篇”常驻按钮与人工确认完成态**，在实施前先提交一份短 **ADR 修订**，明文锁死以下 4 个边界：

1. **单段文章与末段自动达成**：打开文章本身**不等于** 100%；在末段（含仅 1 段的文章）无需常驻“完成本篇”按钮，当用户实际滚动触达末段正文底部（或停留在末段后正常离开且已触底）时，由 Core 自动提交末段完成，使 `readChunks === totalChunks`（100%）。
2. **历史无 Plan 的独立完成记录**：在知识库只读投影为 `100% 深绿满电`（兼容老用户“已读完”筛选结果），不丢失历史完成资产。
3. **重开与重新阅读**：电量展示已读高水位（回看前段不倒退）；仅当用户显式发起新一轮精读（Fresh Pass）时才重置电量。
4. **证据跳转与切 Tab**：严守 ADR 0034，**绝不触发末段自动完成或任何 Cursor 移动**。

### 4.2 知识库 `BatteryProgress` 组件规范

在 `SourceRow.tsx` / `SourceCard.tsx` 用横向微缩电池框替代冗长文字阶段徽章，hover 显示 `精读进度：read/total 段 (XX%)`，无障碍标注 `role="progressbar"` 与 `aria-valuenow`；筛选器（`未开始 / 阅读中 / 已读完`）基于电量百分比自动派生（`0%` / `1%–99%` / `100%`）。

| 精读完成度 (`ratio`) | 视觉形态 | 预占位语义 Token（独立于主题 Accent） | 浅色默认色 | 深色默认色 |
| :--- | :--- | :--- | :--- | :--- |
| `0%`（未开始或未规划） | 空电量轮廓 | `--reader-line-strong` | 透明 + `#CBD5E1` 框 | 透明 + `#4B5563` 框 |
| `1% ~ 20%` | 低电量（红色） | `--reader-battery-low` | `#DC2626` | `#F87171` |
| `21% ~ 59%` | 中电量（琥珀黄） | `--reader-battery-mid` | `#D97706` | `#FBBF24` |
| `60% ~ 99%` | 高电量（浅绿色） | `--reader-battery-high` | `#4ADE80` | `#86EFAC` |
| `100%`（自动达成或历史完成投影） | 满电量（深绿色） | `--reader-battery-full` | `#15803D` | `#16A34A` |

---

## 5. 验收标准

1. **状态栏终态与刷新**：任一任务在**收到终态的首个快照后**即从状态栏与任务抽屉移除，刷新页面后不再出现；全站仅 1 条活跃 SSE 连接。
2. **作用域清错双场景**：
   - 场景 A：断线后重连成功 → 顶栏断线提示自动消失；
   - 场景 B：断线前触发的笔记版本冲突错误，在 SSE 重连恢复后**依然保留并可由用户处理**，绝不被无关健康快照抹掉；文章 A 报错切至文章 B 不可见。
3. **性能与全屏**：精读静止态 0 rAF 唤醒；全屏下按 `Esc` 逐层关闭浮层后再退出全屏，退全屏后对话证据上下文不丢失。
4. **完成语义与电量（Batch C）**：单段文章仅打开不标 100%，触底后自动满电深绿；历史无 Plan 完成记录显示 100% 深绿且留在“已读完”筛选中；证据跳转与切 Tab 绝不改变电量或 Cursor。
