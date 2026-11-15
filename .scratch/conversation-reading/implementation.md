# 统一阅读与对话：实施计划

Status: needs-triage
日期：2026-11-15
规格：[spec.md](spec.md)。用户已授权持续开发；正式入口、Host 证据工具及原文投影现已接入。验证记录见 production-acceptance.md。

## 1. 交付顺序

P0（本轮）：规格 → 实施计划与工单 → 同风格单方向原型 → 类型检查/浏览器手动验收 → 用户确认。用户已经选择左右分栏方向，不做无关三套视觉方案；原型比较的是不同证据状态而非风格分歧。

P1（获准开发后）：契约与迁移设计 → 完整原文/映射 → 联合开场与模型引用校验 → 统一布局 → 联动动效 → 恢复兼容 → 全面验收。

先交付一个真实垂直切片：打开现有来源 → 原文渲染 → 问题 → 一条真实验证的证据 → 左侧定位。通过后再扩展多证据、图表、重连与版本状态，不能先把模拟数据铺成正式界面。

## 2. 模块边界与拟改动文件

| 边界 | 现有入口 | 拟职责 |
| --- | --- | --- |
| 来源读取 | .agents/core/reading_workspace.py、source_library.py；host/core_bridge.py | 提供与 Plan 无关的 SourceDocument、bundleVersion、原文 blocks/object manifest |
| 原文显示映射 | reader-ui/src/markdown-pipeline.ts、annotatable-text.ts、MarkdownContent.tsx | 在已有安全 Markdown 管线构建稳定 block/range 映射；不得重复创建另一套 Markdown 语义 |
| 结构导读 | .agents/core/article_overview.py；host/reading_runtime.py；host/service.py | v2 Source/Bundle 开场；一次候选联合输出，原子发布，读取兼容 v1 |
| 讨论与引用 | .agents/core/discussions.py、discussion_application.py；host/discussions.py、core_bridge.py、service.py | 追加 evidence 模型、校验、结构化流及消息身份，不另建聊天系统 |
| Host 契约与适配 | reader-contracts/src/index.ts；host/server.py；http-reader-host.ts | 新增 source document、opening、answer evidence、bookmark、completion 契约；保持能力发现兼容旧 Host |
| 阅读组合 | reader-ui/src/FocusReader.tsx | 引入独立 UnifiedReadingWorkspace 组合；先开发开关隔离，获验收后替换旧主流程 |
| 原文与证据 UI | 拟新增 SourceDocument.tsx、AnswerEvidenceLayer.tsx、EvidencePopover.tsx、evidence-navigation.ts | 两个滚动控制器、投影、浮卡、双向定位、可中断动效；无业务写入 |
| 对话 UI | 拟新增 SourceConversation.tsx；复用 Composer/Markdown | 开场与持续消息，稳定片段引用，选文引用、历史选择 |
| 知识库入口 | library/SourceParts.tsx、source-status.ts、LibraryPage.tsx、SourceInspector.tsx | 唯一主入口、更多内博客；不删除已有产物 |
| 恢复与外观 | 既有读者 state/preferences；source_clear.py | bookmark 与 Cursor 分离，清除 fencing；比例/主题沿既有外观存储 |

当前环境 `.agents` 为只读根；本轮无需修改。正式开发涉及该目录时应在有相应写权限的工作环境执行，不能把核心逻辑临时复制到 Host 绕开。

## 3. 数据与协议设计

### 3.1 SourceDocument

最小快照 `{sourceId,bundleVersion,title,blocks,objects}`。block 包含稳定 ID、sourceLines、kind、受控渲染内容/原文；身份由 bundle + source range + block type 确定，禁止使用渲染顺序索引作为跨版本身份。objects 指向同版本解析资源，不接受模型任意 URL。按章节加载与全文索引分离。

### 3.2 Article Overview v2

建议 Source 级派生资产目录 `sources/<id>/reading/overview/<bundle>/<methodVersion>.json`，实际文件名由核心路径校验器生成。身份 `{sourceId,bundleVersion,methodVersion,revision}`，可带可选 legacyPlanId 但不依赖 Plan readiness。一次候选返回树和 guide，章节范围覆盖按原文验证，旧 chunk 绑定只作为兼容投影。

先读取当前同版本 v2，再只读验证并适配现有 v1；旧资产不覆写。原子临时文件/replace、attempt/lease 校验、取消和并发合并复用现有机制。上传后台准备不引入另一套 worker/任务面板。

### 3.3 AnswerEvidence

与讨论消息存同一业务权威/事务边界，消息历史摘要不能丢证据关联。Host 提供模型工具候选入口，完成验证后发送 evidence.validated，客户端无法自报验证成功。保留 answerRevision 与 runId，重复 SSE 不创建多条证据。回放从正式快照恢复完整当前消息与证据，不依赖浏览器缓存。

正文片段携带引用 ID，外部链接走独立 kind。旧消息无 evidence 字段兼容为空。模型直接生成普通 `[1]` 文本不会被自动提升为正式引用；必须有同消息修订下的验证对象。

### 3.4 位置、完成与历史

显示书签存独立 `readingView` 对象，不能复用 Reading Cursor 字段。自动证据跳转不覆盖 lastManualLocation；重新打开可恢复 selectedAnswer，但不自动执行其引用跳转。

新 Source-level completion 记录由显式操作产生，绑定 source/bundle/requestId，单独保存；统一 ReadingStatus 优先读取当前版本的新记录，其次兼容旧完成状态。只打开全文将来源视为已打开/阅读中（可用单独 openedAt），不写逐段进度。旧 progress 数字不展示为新对话完成百分比。旧端回滚忽略新字段，不伪造旧 chunks 完成记录。新旧双写只涉及兼容显示必要元数据，不重写旧历史。

清除/重置需要同时纳入新讨论证据与恢复状态，保持 lease、活动写者停止和 durable journal；不在第一轮打开时做不可逆批量迁移。

## 4. 任务依赖与完成定义

| 工单 | 主题 | 依赖 | 完成证据 |
| --- | --- | --- | --- |
| 01 | 契约、术语和迁移边界 | 用户同意正式开发 | 契约样例、ADR/CONTEXT/设计索引、兼容矩阵 |
| 02 | 完整原文与来源映射 | 01 | 真实解析样本全文、确定性块/文本/对象映射 |
| 03 | 联合开场与自动准备 | 01,02 | 单调用、去重、取消、版本/失败/v1兼容验证 |
| 04 | 回答证据生成、校验、流事件 | 01,02 | 一条真实回答垂直切片、伪引用拒绝、乱序重连验证 |
| 05 | 统一入口与双栏阅读 UI | 01,02 | 原文/聊天独立滚动，目录/笔记/窄屏，旧资料可达 |
| 06 | 证据联动与动效 | 04,05 | A05–A09/A12/A15 可操作浏览器证据 |
| 07 | 对话开场、选文与联网来源 | 03,04,05 | 普通对话/选文/外部来源/失败流完整 |
| 08 | 现场恢复、完成状态与兼容清除 | 01,05,07 | 旧库副本迁移、恢复/版本/清除幂等 |
| 09 | 无障碍、长文与整体验收 | 02–08 | A01–A17 矩阵、浏览器截图、性能/失败记录 |

每份独立工单均为 needs-triage：表示原型待用户确认，不是已有开发授权。开发时依赖满足后将可执行工单改为 ready-for-agent；完成情况记录在 Comments，不用未定义的 triage 标签代替五个规范标签。

## 5. 原型范围与验收方式

原型放在 `ui/apps/standalone/src/prototypes/conversation-reading/`，HTML 入口沿既有 `prototypes/<slug>/index.html`。直接导入真实 focus-tokens.css 与阅读字体，不改正式路由/Host。启动命令记录在原型 README。

单方向固定双栏；内存模拟首次开场、流式多处证据、图表依据、外部补充、无法定位/历史版本。实现真实的选择/高亮/浮卡/滚动/返回/选文/键盘交互；回答是演示脚本，不请求模型/网络。演示状态置于独立控制栏，不混进产品流程。提供浅深色、低动态与窄屏体验。

验证不是生产测试：类型检查；浏览器打开、交互与截图；检查浮卡是否遮挡、是否抢滚动、历史证据能否复现、手机是否溢出。真实定位算法、跨版本存储、模型语义、联网可信度需在正式任务中验证，不借原型宣称完成。

## 6. 实施风险与裁决

最大风险是把显示文本偏移误当原文证据；先做 02/04 再做装饰。第二个风险是现有 Plan/translation 准备与原文打开耦合；先提供 SourceDocument 独立入口，再替换 UI。第三是旧 Cursor/完成语义；通过单独书签/完成记录和只读兼容保留旧行为。

图片/公式/表格定位允许显式对象级降级，不对所有 PDF 承诺字符精确。渲染地图不确定时必须 unavailable/block，不做未经验证的近似匹配。当前版本不支持 web 的后端仍可完整本篇阅读，输入区不呈现虚假的联网开关。

发布条件：用户认可原型、01–09 完成、A01–A17 通过或经用户接受有明确范围的剩余项。先在真实知识库副本验证，再启用正式入口；原型代码不能直接作为生产组件搬运。未通过可关闭新界面开关，保留所有旧资产。
