# 设计文档 02：状态栏全链路语义治理、核心逻辑修复与电量式进度（修订版）

> **所属序列**：Focus 重构体系 · 文档 02（分两批交付：Batch A 状态栏与运行时止血先行；Batch C 在完成语义 ADR 修订后落地电量式进度）
> **基线版本**：`focus-d4fb6a5a36af50e01611fe26ff949749226c0300`
> **前置约束**：遵守文档 00 的三条运行时所有权红线。Batch C 的业务契约见 [ADR 0035](../../adr/0035-close-reading-completion-and-reset.md)。

---

## 1. 拆分交付策略

本文档包含两类风险与依赖截然不同的改动，实施时拆分为两批：

- **Batch A（低风险、高收益、立即可做）**：状态栏去已完成态、单一 SSE 订阅与按作用域清错、`ReadingScroll` 60fps 空转止血、全屏 `Esc` 仲裁与键盘焦点闭环。不修改持久化阅读完成语义。
- **Batch C（先定 ADR、再改阅读数据契约）**：完成状态统一依据精读，知识库电量按精读覆盖率派生，合并「新会话」和「重新阅读」。本专题前置工作就绪后即可独立实现并验收这些功能，无需等待专题 01 的 Batch B 真实 PDF 验收。

---

## 2. Batch A · 状态栏全链路语义治理

### 2.1 现有状态提示问题

| 分类 | 精确文件与行号 | 现状问题 |
| :--- | :--- | :--- |
| 已完成态滞留 | `TaskProgress.tsx:5, 21-33` & `host/service.py:383, 2049-2053` | 问答完成后落盘并持续下发 `status: "completed"` 的 `run`，前端渲染“已完成 + 耗时”。 |
| 已完成态滞留 | `WorkspaceApp.tsx:105, 225-233, 291-301, 622-668` | `readyNotice` 横幅、`preparationNotice` 就绪框（无关闭钮）与任务抽屉 `<summary>已完成任务</summary>` 长期霸占界面。 |
| 已完成态滞留 | `host/service.py:353, 2159` & `FocusReader.tsx:717` | `noteFeedback: { status: "saved" }` 持久化落盘，刷新后仍一直显示过时的“已记下”。 |
| 过时错误滞留 | `WorkspaceApp.tsx:193-197, 213-215` & `ConversationReader.tsx:36, 41` | SSE 重连或轮询恢复时未清连接错误，断线红条永驻。 |
| 跨文章串台 | `host/service.py:686-715, 2045-2046` & `ConversationReader.tsx:109` | 问答失败 `run` 与 `expired` 审批不清理，且前端未校验 `agent.run.sourceId === sourceId`，文章 A 报错串台到文章 B。 |
| 错用错误条 | `FocusReader.tsx:954, 999-1003, 1032` | 切精读未就绪时把“正在准备逐段精读”塞进 `setError()` 当红条展示，准备完成后不消失。 |
| 批量清理 | `host/status_notifications.py` | 成功任务目前仍依赖清空操作退出，批量清空的请求记录持续增长。 |

### 2.2 统一活跃状态契约与后端生命周期重构

1. **后端活跃状态投影（`reader-contracts/src/index.ts` & `host/service.py`）**：
   ```ts
   export interface ActiveStatusItem {
     id: string;                 // `${kind}:${targetId}:${attemptId}`
     kind: "chat" | "preparation" | "blog" | "ingestion" | "batch" | "progress" | "opening";
     targetId: string;
     sourceId?: string | null;   // 前端按当前文章隔离
     phase: "running" | "approval" | "needs_action" | "error";
     label: string;
     stage?: string;
     percent?: number;
     error?: string | null;
     attemptId: string;
     retryable?: boolean;
     cancellable?: boolean;
   }
   ```
2. **任务可见性（`host/service.py`）**：
   - `_project_snapshot()`（L383）：对 `status === "completed"` 的 `run` 返回 `agent.run = null`（历史仍归档于 `execution:<runId>`）。
   - 任务框展示进行中、等待审批、需要读者操作和仍待处理的失败。待确认、暂停可继续、远端结果待核对均保留原有状态和对应操作。审批入口随审批失效而退出，问答结果沿用运行时记录的实际结果。
   - 批次只展示仍有工作或仍需处理的子项。一个子项成功后随首个反映成功的快照退出，其他子项仍可处理。已完成或删除的条目退出任务投影；批次和 Inbox 的业务记录继续用于查询与恢复。
   - `noteFeedback`（L2159）：不再持久化 `status: "saved"`，仅保留失败态；`opening_errors` / `blog_errors` 在重新生成成功或来源删除时自动 `pop`。
3. **保留「全部清空」**：一键隐藏当前已结束的失败提示。运行中、待确认、暂停可继续和远端结果待核对的任务保留在任务框。清空只影响提示可见性，业务记录和恢复入口继续保留。关闭在刷新后继续生效，迟到或重放的请求只影响当时对应的尝试，新尝试仍正常出现。

### 2.3 单一 SSE 订阅与三层作用域错误隔离（严禁笼统 `result.ok → 清 error`）

- **单一 SSE 连接**：统一阅读入口已由 `WorkspaceApp.tsx` 调用 `host.subscribe()`，精读和对话共用快照。验收以每个工作台页面的一条连接为单位，覆盖跨页、切篇和切 Tab。
- **跨来源可见性**：全局任务框可见其他来源的后台失败，条目标明来源。阅读内容区和输入区只显示当前来源的错误。切换来源只改变阅读区的可见范围，全局任务仍按自身状态更新。
- **三层独立错误作用域（核心修正）**：禁止在收到任意健康快照 `result.ok` 时笼统清空所有错误，改为严格按作用域独立管理：

| 错误作用域 | 归属状态 | 合法清理触发器 | 绝不被什么清除 |
| :--- | :--- | :--- | :--- |
| **连接层（`connectionError`）** | `WorkspaceApp` | SSE 重连或轮询恢复健康快照（`result.ok`） | — |
| **来源/文档层（`sourceError`）** | `ConversationReader` / `FocusReader` | 切换 `sourceId`（代际变更）或当前来源文档重新加载成功 | 无关的 SSE 心跳快照 |
| **操作尝试层（`operationError`，含笔记版本冲突）** | 对应操作组件（绑定 `attemptId` / `operation`） | 用户显式重试成功、手动点击关闭 `×` 或切换来源 | **SSE 重连恢复或其他无关健康快照** |

- **前端清理清单**：
  - `TaskProgress.tsx:5, 21`：移除 `terminal.completed`，遇 `completed` 返回 `null`。
  - `WorkspaceApp.tsx`：删除 `readyNotice`、`preparationNotice` 的 `ready` 分支和「已完成任务」折叠区。打开文章、切换来源、切换阅读方式或恢复已有位置时，移除「正在阅读 xxx」「已打开」「已就绪」这类仅复述当前操作或结果的弹框、浮层和横幅。用当前来源标题、选中的阅读方式和内容本身反馈位置。准备进度和可处理错误继续在对应界面位置显示。阅读页的同一审批只提供一处操作入口。
  - `FocusReader.tsx`：移除持久化 `noteFeedback === "saved"` 展示与 `expired` 审批；切精读“准备中”改为派生自 `view.preparations[sourceId]`，不再塞进 `setError()`。
  - `ConversationReader.tsx`：`ConversationComposer` 校验 `agent.run.sourceId === sourceId`；`.source-reader-error` 增加关闭钮；`positionNotice` 3s 自动消隐并在手动滚动时立即清空。

---

## 3. Batch A · 核心性能与交互逻辑修复

1. **【P0】停止 `ReadingScroll` 60fps 常驻空转**（`ui/packages/reader-ui/src/reading-scroll.ts:48-61, 134-149`）：改为事件驱动，仅在 `ResizeObserver`、`MutationObserver`、滚动事件、`streaming === true` 或 `heldUntil` 期间按需调度 rAF，静止态 0 唤醒。
2. **【P0】修复 `UnifiedReader` 切篇不同步（带代际校验）**：精读模式下切篇时，有已选且就绪的 Reading Plan 则恢复该来源的持久阅读位置。候选新 Plan 由读者显式启用。尚未就绪时在精读区显示准备状态，提供准备或重试操作及切回对话的入口。异步结果须核对 `sourceId` 和 `selectionGeneration`。
3. **【P0】修复全屏 `Esc` 抢占与退全屏丢状态**（`WorkspaceApp.tsx:552-557`、`ConversationReader.tsx:371-386`、`FocusReader.tsx:1017`）：全局 `Escape` 优先让 `dialog[open]` / 抽屉 / 批注编辑器消费；移除 `exitedFullscreen` 清空 `activeEvidence / returnPosition / jumpOrigin` 的逻辑；全屏保留模式切换入口与桌面宽屏双栏能力。
4. **【P0】修复 `#reading-children` 退场动画被 `hidden` 杀死**（`WorkspaceApp.tsx:582-584`）：改用 `inert` + `aria-hidden`。
5. **【P1】键盘焦点闭环与替换原生阻塞弹窗**：为 `.source-notes-drawer` 补全打开聚焦、关闭回焦与 `Esc` 优先关闭；将 `FocusReader.tsx:740, 824` 的 `window.confirm()` 替换为统一 `<dialog>`；`WorkspaceSelection.tsx:77` 仅在独立入口页启用 `autoFocus`；清理未使用的 `onSaveAppearance` 死代码并统一设置页标题文案。

---

## 4. Batch C · 完成语义 ADR 修订与知识库电量式进度框

### 4.1 精读完成与重新阅读

当前 Core 要求在最后一段调用 `finish`，知识库 Host 同时认可独立 Source 完成记录。02 将精读进度作为唯一的完成依据，变更由 [ADR 0035](../../adr/0035-close-reading-completion-and-reset.md) 定义。

1. **唯一完成条件**：当前精读 Plan 的全部 Chunk 已读完。对话模式不提供标记读完。历史独立 Source 完成记录退出当前阅读状态、电量和筛选的投影。无已完成精读的来源按当前精读事实展示。
2. **末段主动触底**：读者已进入精读正文，并在当前阅读前沿主动向下浏览、触达末段正文底部时，由 Core 提交一次完成。打开文章、程序滚动、证据定位、切 Tab、调整窗口和离开页面均不提交完成。仅当末段正文完整可见、无需滚动便能看到结尾时，在正文末尾提供可聚焦的行内「读完」动作。底栏保持现状。
3. **重新阅读**：将「新会话」「重新规划」和「重新阅读」合并为「重新阅读」。确认后先完整备份当前阅读版本，成功后再准备新一轮。整篇笔记带入新一轮，旧计划、进度、小段笔记、句子备注和重点可切回旧版本查看。开启空白讨论，旧讨论继续存档，旧消息和摘要退出模型上下文。立即重新生成计划和精读内容，就绪后从首段进入。生成失败时精读保持未开始，在当前来源提供重试入口。本轮阅读准备全部就绪后同时开放精读与对话，详见[设计文档 04 §1](04-conversation-reading-bilingual-view.md#1-上传翻译与重新阅读)。
   - 确认弹窗正文：「将先备份本轮阅读，可以在论文管理中切回。新一轮保留整篇笔记，重新准备精读并开启新对话。」取消后数据和会话保持原状。
4. **回看与导航**：电量展示当前阅读轮次的已读高水位。回看、证据跳转与切 Tab 保持进度和 Reading Cursor。

### 4.2 知识库 `BatteryProgress` 组件规范

在 `SourceRow.tsx` / `SourceCard.tsx` 用横向微缩电池框展示已读段数和覆盖率。悬停显示 `精读进度：read/total 段 (XX%)`，无障碍标注使用 `role="progressbar"` 与 `aria-valuenow`。「未开始 / 阅读中 / 已读完」按读者是否进入精读正文、当前阅读轮次是否已完成来判定。刚进入第一段时已读段数为 0，仍归入「阅读中」。

| 精读完成度 (`ratio`) | 视觉形态 | 预占位语义 Token（独立于主题 Accent） | 浅色默认色 | 深色默认色 |
| :--- | :--- | :--- | :--- | :--- |
| `0%`（未读完任何一段） | 空电量轮廓 | `--reader-line-strong` | 透明 + `#CBD5E1` 框 | 透明 + `#4B5563` 框 |
| `1% ~ 20%` | 低电量（红色） | `--reader-battery-low` | `#DC2626` | `#F87171` |
| `21% ~ 59%` | 中电量（琥珀黄） | `--reader-battery-mid` | `#D97706` | `#FBBF24` |
| `60% ~ 99%` | 高电量（浅绿色） | `--reader-battery-high` | `#4ADE80` | `#86EFAC` |
| `100%`（精读全部 Chunk 已读完） | 满电量（深绿色） | `--reader-battery-full` | `#15803D` | `#16A34A` |

---

## 5. 验收标准

1. **任务框与刷新**：成功任务随首个反映成功的快照退出，刷新后仍隐藏。混合批次中，暂停可继续和待核对的子项仍可见且可操作。每个工作台页面保持一条 SSE 连接。
2. **作用域清错双场景**：
   - 场景 A：断线后重连成功 → 顶栏断线提示自动消失；
   - 场景 B：断线前触发的笔记版本冲突在恢复后仍可处理。文章 A 的后台失败在文章 B 的阅读区不可见，在全局任务框中仍标明来源 A。
3. **性能与全屏**：精读静止态 0 rAF 唤醒；全屏下按 `Esc` 逐层关闭浮层后再退出全屏，退全屏后对话证据上下文不丢失。点击证据后延迟加载 PDF 目标页，在等待期间退出全屏，验证目标页加载后按当前布局命中证据。另测退出全屏后主动滚动再加载目标页，阅读位置应停在读者选择处。
4. **完成语义与电量（Batch C）**：单段文章进入正文为 `0/1`，归入「阅读中」。主动触达可滚动末段正文的底部，或点击无需滚动的末段正文内「读完」后为 `1/1`，归入「已读完」。证据跳转与切 Tab 不改变电量或 Cursor；对话和历史独立完成记录不产生满电。
5. **切篇与提示**：从 A 切到已有精读位置的 B 时恢复 B 的位置，A 的迟到响应无法覆盖 B。首次打开、切篇和切换阅读方式均不出现「正在阅读 xxx」类提示弹框或横幅；仍可在对应区域看到真实准备状态和可处理的错误。
6. **重新阅读（Batch C）**：取消确认后进度、旧 Plan、笔记和会话保持原状。在旧讨论的 PDF 目标页仍加载时确认重新阅读，验证旧跳转和返回位置立即清空；目标页随后加载完毕时，旧回调不滚动、不提示，也不恢复旧返回位置。取消重读时原跳转与返回位置保留。确认后开启新会话，从零准备新精读，旧计划、旧进度和逐段笔记不再进入新一轮，整篇笔记仍可查看。
   - 新一轮的首个提问只使用新讨论的上下文，旧聊天仍在存档中。生成失败时仍可对话，重试从重新准备新计划继续。
7. **全部清空（Batch A）**：混合批次中已结束的失败提示清空后跨刷新保持隐藏；运行中、待确认、暂停可继续和待核对的条目保留。再次尝试失败时显示新的提示。
