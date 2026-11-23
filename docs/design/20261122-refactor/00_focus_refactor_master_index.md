# Focus 重构总控索引与跨文档共享契约（修订版）

> **基线版本**：`focus-d4fb6a5a36af50e01611fe26ff949749226c0300`
> **文档定位**：三份递进设计文档的总控入口、前置架构决策、运行时所有权红线与分批实施节奏（供后续各专题独立生成 `spec.md` 与 `issues/` 实施清单）。

---

## 1. 文档拆分矩阵

| 编号与文件名 | 专题范围 | 核心修改层 | 实施批次 |
| :--- | :--- | :--- | :--- |
| **01** `01_FOCUS_Evidence_BackAnnotation_and_Unified_IR_Design.md` | 对话阅读证据反标（含原文 PDF 块级多框与页级定位）、精读粗粒度联动、PDF/HTML/Markdown 统一 `source-ir.json` | 后端 `.agents/core/`、`host/core_bridge.py`、`host/service.py`；前端 `PaperViews.tsx` / `source-evidence.ts` / `ReadingChunk.tsx` | **Batch B**（单 PDF 垂直切片）→ **Batch C**（HTML/MD 与精读胶囊） |
| **02** `02_FOCUS_StatusBar_and_Core_Logic_Refactor_Design.md` | 任务框展示进行中与需处理的工作、移除重复阅读提示、核心运行时修复、完成语义 ADR 修订与知识库电量进度框 | 后端 `host/service.py` / `host/status_notifications.py` / Core 末段规则；前端 `WorkspaceApp.tsx` / `TaskProgress.tsx` / `source-status.ts` / `reading-scroll.ts` | **Batch A**（状态栏、SSE、rAF、焦点/Esc 先行）→ **Batch C**（ADR 修订后落地电量框） |
| **03** `03_FOCUS_Theme_and_UI_Consistency_Refactor_Design.md` | 去“AI 味”简洁主题（单炭灰深色 + 4 套浅色配色）、CSP 安全启动脚本、全量布局错位清零与 UI/动效一致性 | 前端 `index.html`、`public/theme-init.js`、`appearance.ts`、`focus-tokens.css`、`standalone.css`、`mist-reader.css`、`conversation-reader.css` | **Batch A**（CSP 脚本、Token 底座与独立布局修复）→ **Batch C**（5 套主题最终视觉验收） |

---

## 2. 必须前置锁定的 3 条运行时行为所有权红线

仅按文件名分工无法防止跨专题异步竞态（例如旧来源的异步响应覆盖新来源，或证据跳转意外推进精读游标）。在生成任何 Spec 之前，三份文档共同遵守以下 3 条运行时行为契约：

1. **当前来源与单一 SSE 快照所有权**：
   - `WorkspaceApp` 唯一持有当前活跃 `sourceId` 与全局唯一 SSE 订阅快照，并维护单调递增的切换代际号（`selectionGeneration`）。
   - 任何跨来源异步回调（`openSource`、文档/PDF 加载、导读/概览拉取、证据定位）落地前必须比对当前 `sourceId` 与 `selectionGeneration`，过期响应一律丢弃，严禁覆盖新来源状态。
2. **跨 Tab 证据定位的一次性消费语义**：
   - 从精读或其他入口触发跨 Tab 定位时，传递一次性 `PendingEvidenceJump { sourceId, messageId, evidenceId, preferredView, nonce }`。
   - 精读证据列表中的每条证据先定位到对话中的回答及其证据编号。读者点击回答中的编号后，再进入对应的来源位置。
   - PDF 来源提供原文 PDF 和中文译文两个视图。在原文 PDF 中点击证据时，定位到可靠证据块或已知页面。PDF 无法定位或版面版本失配时，直接切换到中文译文并定位对应证据块。在中文译文中点击时始终留在译文，按已验证的关联定位译文段落；缺少关联时保留当前位置并展示原文引文。
   - 同一来源连续定位以最后一次点击为准。回调在滚动、显示失败提示或清空意图前，须同时核对当前来源、切换代际和待消费意图的 nonce。意图已清空时，迟到的回调直接结束。
   - 等待定位期间，读者用滚轮、触屏、滚动条或键盘主动浏览时，立即清空待处理意图。定位自身触发的程序滚动可继续完成。验收时让目标页在手动滚动后才加载，阅读位置应停在读者选择处。
   - 目标视图完成渲染并滚动命中对应回答的证据编号或来源块（或判定目标不存在并降级提示）后，**立即消费并清空该定位意图**；定位状态绝不作为持久状态驻留，也不阻断用户后续滚动或退全屏。
3. **Cursor 移动的唯一合法权限**：
   - 精读推进、经 ADR 修订确认的末段完成，以及读者明确确认的重新阅读，可以修改精读 `Cursor` 与进度。证据跳转、两视图切换、跨 Tab 切换、全屏进出和 SSE 重连刷新均保持原进度。

---

## 3. 推荐分批实施节奏（风险前置、收益前置）

| 阶段 | 核心交付内容 | 为什么这样排 |
| :--- | :--- | :--- |
| **前置决策** | 1. 01 已确定独立版面版本、逐字引文签发与块级展示规则。<br>2. 02 的精读完成与重新阅读规则见 [ADR 0035](../../adr/0035-close-reading-completion-and-reset.md)。 | 为各批次实施提供共享契约。 |
| **Batch A**<br>高收益止血 + 主题底座 | 1. **02 运行时止血**：单一 SSE 订阅 + 按作用域清错、状态栏彻底去已完成态、`ReadingScroll` 静止态 0 rAF、全屏 `Esc` 仲裁与焦点闭环。<br>2. **03 底座先行**：CSP 安全的同源外部启动脚本（`/theme-init.js`）、5 套主题 Token 体系（浅色 4 套 + 深色 1 套）与独立布局错位修复。 | 零磁盘 Schema 迁移风险，最快改善日常使用体感，同时提前扫清生产 CSP 阻断。 |
| **Batch B**<br>01 单 PDF 垂直切片 | 选取 1 份含跨栏与旋转页的真实 PDF，端到端跑通：`入库 → host/core_bridge.py 白名单扩展 read_range → cite → 点击证据 → 核对原文引文与 PDF 块或已知页面`，同步验证“同文重排 PDF 不误标”与“未知坐标系安全降级为页级”。 | 在改变 `content.md` 正向生成方式之前，用真实论文检验最核心的坐标与引用假设。 |
| **Batch C**<br>全格式扩展与终验 | 1. **01 扩展**：切入 HTML / Markdown 统一 IR、旧 Bundle 只读回归、精读粗粒度证据胶囊。<br>2. **02 精读完成与重新阅读**：统一精读完成依据、合并重读和新会话入口、上线知识库电量式进度框。<br>3. **03 终验**：在全部新 DOM 定型后完成 5 套主题组件级对比度、全量页面截图与 `system` 切换回归。 | 所有新组件一次性纳入最终视觉验收，零重复返工。 |

---

## 4. 跨文档共享契约（文件边界、Token 预占位与兼容红线）

### 4.1 共享组件修改边界

| 共享文件 | 01（证据反标与 IR） | 02（状态栏与逻辑修复） | 03（主题与 UI 一致性） |
| :--- | :--- | :--- | :--- |
| `ConversationReader.tsx` | 接入 `blocks[]` / `pdfRegions[]`、两视图按 `block_id` 同步、一次性跨 Tab 定位消费 | 消费壳层单一 SSE、按作用域清错、`sourceId` 错误隔离、退全屏保状态、`positionNotice` 自动消隐 | 抽屉挂载动效、滚动采样节流、证据卡与划词浮条栈布局 |
| `FocusReader.tsx` | `ReadingChunk` 粗粒度对话证据胶囊、`ReaderConversation` 解析 `[[e:ID]]` | 删除 `finish()` 按钮（按 ADR 修订）、修复 `UnifiedReader` 切篇同步（带代际校验）、移除持久化 `saved` 与 `expired` 审批、替换 `window.confirm` | `AnnotationRail` 真实宽度测量、统一双模式 Composer/气泡/工具条样式 |
| `WorkspaceApp.tsx` | 仅透传一次性 `PendingEvidenceJump` | 唯一持有 `sourceId` 与单一 SSE 订阅、删除 `readyNotice` 与已完成抽屉、按作用域清错、全屏 `Esc` 仲裁、移除阅读页双处 `AgentControls` | 主题与浅色配色选择器 UI、弹窗操作区类名、右下角通知栈、侧栏折叠行 Flex 化 |

### 4.2 CSS 语义 Token 预占位表

| 语义用途 | 约定 CSS 变量名 | 使用方 |
| :--- | :--- | :--- |
| 证据高亮底色 / 强调边框 | `--reader-mark` / `--reader-mark-strong` | 01（PDF 多框与译文段落高亮） |
| 电量式进度框四档填充色 | `--reader-battery-low` / `--reader-battery-mid` / `--reader-battery-high` / `--reader-battery-full` | 02（知识库 `BatteryProgress`） |
| 错误 / 进行中状态边框与底色 | `--reader-danger` / `--reader-error-bg` / `--reader-error-border` / `--reader-accent` | 02（状态栏与错误条） |

### 4.3 存储与向后兼容红线

1. **旧 Bundle 只读兼容（01）**：历史无 `source-ir.json` 的 Bundle 不强制重解析，统一只读降级到原有 `content.md` + `pdf_layout.py`。读者可以继续提问，Host 根据规范 Markdown 行范围及逐字引文签发新证据，对话和证据写入讨论记录。不同版面版本绝不跨版本绘制 PDF 框。
2. **状态归档不丢失（02）**：`agent.run` 完成后退出状态栏投影，`execution:<runId>` 归档继续保留。知识库完成状态与电量统一依据精读进度，历史独立完成记录退出当前状态投影。
3. **偏好存储无损迁移（03）**：沿用 `localStorage` 的 `focus.theme` 键名，新增 `focus.accent`（缺省回退 `"blue"`，深色模式保留不应用，切回浅色自动恢复）。
