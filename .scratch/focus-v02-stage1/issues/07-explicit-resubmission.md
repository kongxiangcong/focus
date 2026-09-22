# 07: 受理不明时明确提示后重新提交

What to build: 上次解析提交是否被服务受理无法查明时，用户看到重复解析风险后可明确重新提交；已有任务号则优先查询原任务。整个操作可恢复、可去重，并阻止被替代任务的迟到结果污染当前任务或正式 Source。

Blocked by: 06 — 重复添加找回未完成 Inbox 任务

Status: resolved

- [x] Application 提供与普通续接可区分的显式重提动作，校验受理无法查明的业务状态、有效确认和绑定当前任务的用户风险选择；Host 只转发该动作，直接请求同样受校验。
- [x] 网页区分查询／继续原任务、确认变更后的范围及重新提交。无法查明时，在“重新提交”旁说明“上次提交结果未知，重新提交可能重复解析”；未明确选择不产生新提交，不能把必然失败的普通继续作为唯一出口。
- [x] 已有任务号时优先查询并续接原任务；临时查询失败不自动触发重传。刷新、普通继续、重新确认和重复添加均不能替代重提选择，06 的原任务复用在此路径仍生效。
- [x] 重提复用原 Inbox、Run 和仍有效的业务输入，启动新解析 attempt，先永久关闭被替代 attempt 的提交资格；保留旧受理不明记录，不声称旧远端任务已经停止。
- [x] 使用既有持久请求幂等规则，相同重提请求重复点击、响应丢失或进程重启后重放不再次发起远端提交。再次受理不明时停回待核对，不形成自动重传循环；输入或服务变更使旧风险选择失效。
- [x] 重提前检查已有有效候选和已发布结果，复用合法进展；已发布 Source 不重新解析，关联待恢复只补关联。被替代 attempt 的迟到结果不能发布或改写当前状态，Core 发布约束保持有效。
- [x] Application 公开边界的故障测试覆盖明确选择前后提交次数、持久重放、再次受理不明、旧选择失效、迟到结果和已有产物复用；薄 Host／网页测试覆盖风险提示、正确动作与服务端拒绝绕过。
- [x] 运行本票相关回归、必要 UI 类型／构建检查，并刷新本轮综合证据与失败清单。分别记录确定性、Host、浏览器和实际执行的真实服务验证，未执行项不得标为通过；若 05 尚未完成，清楚保留其未验收状态，不为汇总而宣称全部完成。

Verification: 主边界为共享 Application，使用真实 Core、隔离持久状态和可控 Parser 注入受理不明及迟到响应；不为测试重复成本向真实服务故意重复上传。必要重构及故障处理纳入本票，不另拆防御或验收任务。

Spec coverage: 本轮 Q2 与 Q3 的防绕过交互；T10、T11、T11a、T11b、T11c、T25 的重提部分，以及 T07、T09、T13、T14、T17、T23 的相关回归。

Scope: 依赖 06 封住重复添加绕过风险提示的入口；与 05 无硬依赖。不增加已成功入库文档的主动重新解析产品或版本浏览。

## Comments

2026-09-22：用户批准三票补充方案；06 完成前不领取实施。保留现有未提交工作，不重置或覆盖无关修改。

## Answer

`IngestionApplication.resubmit(item_id, request_id, risk_choice_id)` 是与普通续接可区分的显式重提动作：仅在 `status_check_required`（受理无法查明）且有有效当前确认时可用；`resubmit_risk.choice_id` 在每次受理不明落盘时生成并绑定当前任务，请求必须携带当前 choice，输入或服务变更经重新确认后旧选择失效（confirm 绑定变化时清除）。重提复用原 Inbox、Run 与业务输入：在 `_state_lock` 内把步骤 checkpoint 归档进被替代 attempt 并永久关闭其 `commit_allowed`（保留旧受理不明记录与 error_id，不声称远端已停止），随后走同一 `_process` 管线——已发布 Source 或有效候选优先复用，未命中才启动新解析 attempt 并记录 `resubmit_request_id` 作为持久幂等标记。

封堵的绕过点：`_process` 对 `status_check_required` 且无任务引用（或 Parser 无 `resume` 查询能力）的项拒绝普通 `process`／`continue_run` 新起解析（`ingestion_resubmission_required`）；有任务引用时普通续接只 `resume` 查询原任务，不重传。新建 attempt 统一永久关闭所有未完成旧 attempt，任何路径的迟到结果都无法经 Core 发布（`attempt_cancelled`）。相同 `request_id` 的重提重复点击、响应丢失或重启后重放直接返回现状，不发起第二次远端提交；再次受理不明停回待核对并生成新 choice，不形成自动重传循环。

Host 只薄转发：`inbox_resubmit`（同步，直连测试用）与 HTTP `POST /library/inbox/{id}/resubmit`（`inbox_start_process` 先同步 `validate_resubmit` 使陈旧 choice 得到 400 拒绝，长解析进 worker）。网页在“远端状态待核对”行内展示“上次提交结果未知，重新提交可能重复解析。”与“重新提交”按钮；有任务引用（`remote_reference`）时另提供“查询并续接原任务”（普通续接查询），无引用时不再展示必然失败的“继续”/“重新确认并开始”作为出口。未点击重提前零新提交。

双轴 review 发现的问题已在本票修复：

- **取消后的死路**：受理不明任务取消后，普通继续被防绕过闸门拦住、重提又被状态校验拒绝。修复：取消保留 `resubmit_risk`，`resubmit` 接受"取消且仍有风险选择"的任务作为明确恢复出口；`continue_run` 在改动任何状态前先做同样的闸门检查（受理不明且无法查询时拒绝，不把任务写成既非取消也非待核对的僵死状态）。
- **无查询能力的任务引用**：`remote_reference` 投影现要求 Parser 具备 `resume` 查询能力，网页不再对查不回的任务展示"查询并续接原任务"。
- **并发不同 request 的 TOCTOU**：重提在锁内持久化 `resubmit_pending` 标记后才开始执行，另一 request 的并发重提被拒绝（`ingestion_not_resubmittable`）；标记在 attempt 建立、取消、重新确认或重启恢复时清除，不留永久锁。
- 网页为待核对任务补回"重新确认并开始"（spec 35 的"确认变更后的范围"）：绑定未变时服务端仍拒绝（`remote_status_check_required`），配置漂移后重新确认即清空旧 Run 并按新确认重新开始，不与重提混同。

Standards 轴确认 ADR 0011/0012/0003 无硬性违反；提取 `_supersede_unfinished_attempts`/`_acceptance_unresolved`/`_unresolved_original_published` 助手消除重复。ADR 0012 与"变更后重新确认即新起提交"的张力为既有四票设计（新绑定=新授权，旧 Run 清空），本票维持并在此记录。

验证（Application 主边界 + 真实 Core + 可控 Parser）：
- 明确选择前：`process`／`continue_run`／陈旧 choice 重提均被拒绝且零额外 Parser 调用（T11a）；
- 持久重放：同 request 重复点击、重启后重放均不二次提交；再次受理不明生成新 choice 后原 request 重放仍不提交（T11b）；
- 有任务号优先查询：checkpoint 存在且 Parser 可查询时 `continue_run` 走 `resume`（零新提交）且旧 attempt 被关闭；Parser 无 `resume` 时 `remote_reference` 为 false、查询出口不展示（T10/T11 相关）；
- 取消恢复：取消后普通继续被拒且状态不变，显式重提恢复完成（T17/T18 相关回归）；
- 迟到结果：被替代 attempt 携归档 checkpoint 且 `commit_allowed=False`，直接经 Core 发布被 `attempt_cancelled` 拒绝，Source 仍唯一（T11c）；
- 已有产物复用：同原件 Source 已发布时重提直接 `reused`，零新提交（T13/T14 相关回归）；
- 输入/服务变更：Parser 配置漂移使旧 choice 失效；重新确认清除 `resubmit_risk`，旧选择重提被拒，随后正常新起（T11c/T02 相关）；
- 并发重提：同 request 与不同 request 均恰好一次新提交（`resubmit_pending` 持久标记）；
- Host/HTTP：陈旧 choice 的直接请求返回 400，正确请求 202 后经轮询完成；Host 同步入口与投影一致（T25 重提部分）；
- 网页：风险文案紧邻"重新提交"、点击携带当前 choice；有引用时展示查询按钮且不误触重提；取消后不再展示必然失败的"继续"。

回归：Python 全套 168 项通过（本票新增 12 项）；UI 类型检查 3 包、vitest 47 项（reader-ui 28 + standalone 19）、生产构建通过（仅既有 >500 kB chunk 警告）。真实 MinerU/Codex 层未重复执行（沿用 05/06 及阶段 1 既有真实证据，本票未引入新的真实服务行为），浏览器层由 jsdom 交互测试覆盖风险提示与动作，未做手动浏览器操作记录。05、06 历史验收状态不变。
