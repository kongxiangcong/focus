# 06: 重复添加找回未完成 Inbox 任务

What to build: 用户再次添加相同 PDF 时，找到并展示已有未完成 Inbox Item，继续理解和处理原任务，不产生第二次解析，也不暗中更换原目标或确认。

Blocked by: None (can start immediately)

Status: resolved

- [x] 按原件身份识别已有未完成任务，文件改名或应用重启不影响识别。重复接收返回原任务及其真实状态，不另建可执行的同原件解析任务。
- [x] 待确认、处理中、失败、待核对、取消、冲突及关联待恢复等未完成状态均不能借重复添加另起解析。找到任务不自动继续或重新提交；已取消任务仍需用户明确继续。
- [x] 原目标、确认和有效进展保持不变；本次选择不同 Topic 时展示原任务目标，不自动覆盖或补关系，后续目标变更遵守既有确认规则。
- [x] 已完成入库仍沿用 Source 复用与缺失 Topic 关联规则，不改变已发布 Bundle、Plan、Cursor、Records 或 Notes；发布成功但关联未完成时找回原关联恢复任务。
- [x] 识别依赖持久化业务状态并处于既有写入保护下；重复请求和重启不产生多个新执行任务。保持单写者边界，不引入第二份身份权威或持久反向索引；Host 可保留忙碌时拒绝新操作的规则。
- [x] Host 接口返回可定位的原任务，网页接收重复添加结果后展示该任务及真实状态，而不是显示新任务已开始；直接调用 Application 或 Host 也不能绕过身份复用。
- [x] Application 测试覆盖改名、持久恢复、不同目标和主要未完成状态，断言原任务身份、确认、进展与零额外 Parser 提交；少量 Host／网页测试验证定位和展示，运行相关回归及受影响的 UI 检查。

Verification: 使用真实 Core 与隔离持久目录，外部 Parser 可控。测试用户动作与资产结果，不依赖浏览器缓存或仅验证内部查找调用。必要重构在本票先完成，不改变原四票的历史状态。

Spec coverage: 本轮 Q3；T07a、T07b、T25 的重复添加部分，以及 T06、T09、T18、T21 的相关回归。

Scope: 本票可独立演示重复添加返回原任务；受理不明时的新显式重提操作由 07 实现，不能在本票静默以新任务替代。

## Comments

2026-09-22：用户批准三票补充方案；本票与 05 无依赖。保留现有未提交工作，不重置或覆盖无关修改。

## Answer

识别以内容指纹为原件身份（与 Source Identity 一致）：`IngestionApplication.stage_pdf` 在 `_state_lock` 内经 `_unfinished_original` 查找同指纹且未完成的持久化 Inbox Item，命中即返回原任务及其真实状态并标记 `duplicate: true`，不写入新任务、不自动继续、不重提、不覆盖原目标或确认；未命中才创建新任务。文件改名、应用重启均不影响识别；已完成任务不参与找回，继续按既有 Source 复用与 Topic 关联规则处理。发布成功但关联未完成（`topic_attachment_pending`）时找回的是原关联恢复任务。Host `inbox_stage` 与 HTTP `POST /library/inbox` 是同一 Application 的薄转发；网页收到 `duplicate` 后展示"该原件已有未完成任务，已回到原任务；不会重复解析"，并显示该任务真实状态行。

双轴 review 发现的绕过点已修复：`update_staged` 换源现在先按新指纹做同样的未完成任务查重，替换原件属于另一未完成任务时拒绝（`ingestion_duplicate_original`）；重选本任务当前原件仍合法。识别在 `_state_lock` 内完成，并发重复暂存只产生一个任务；单写者与既有 Host 忙碌拒绝规则不变，未新增第二身份权威或反向索引。

验证（Application 主边界 + 真实 Core + 可控 Parser）：
- 改名、重启找回原任务并保留原目标与确认（含 `topic_title` 原样返回、不创建新 Topic）；
- 十种未完成状态（待确认、处理中、失败、待核对、取消、冲突、关联待恢复等）均只返回原任务、零额外 Parser 调用；已取消任务需 `continue_run` 明确继续；
- 关联待恢复任务的重复添加返回原恢复任务，补建 Topic 后续接完成关联（T09 相关回归）；
- 并发四次重复暂存：唯一 item、3 个 duplicate、无 Topic 产生；
- HTTP 真实入口重复添加（改名+不同 Topic）返回原任务，`GET /library/inbox` 投影不含 transient `duplicate` 标记；
- 网页测试断言定位展示与"不重复解析"提示；
- T21 相关：完成后重复添加走 `document_status=reused`，`reading_started` 不被改写。

回归：Python 全套 156 项通过（本票新增 4 项：待恢复找回、并发唯一、HTTP 入口、update_staged 绕过拒绝）；standalone UI 15 项通过。受理不明的显式重提由 07 票实现，本票未引入任何重提操作。
