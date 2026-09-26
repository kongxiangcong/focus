# 阶段 2D：DSH 早期适配探针

状态：已 grill 定稿（2026-09-25）；用户确认暂不实施探针。DSH 原目录已按用户追加授权同步到最新源码基准，旧本地改动与临时基准 worktree 已清理。依据：总计划 P2、§4–5、§7。入口：阶段 1 的共享入口已可用；选择博客步骤时依赖阶段 2 的相应最小能力。

## 本阶段交付

本阶段是同一个 FOCUS 项目的 DSH 原生集成探针，不是另建业务项目或完整 DSH 产品交付。Standalone Host 可通过 Codex 适配器执行 AI 步骤；DSH Host 使用 DSH 原生 Runtime。两条路径共用 Application、Core、Methods 和资产格式，不共享原生聊天 Session，也不要求 Codex 与 DSH 的版本号一致。DSH 框架源码位于独立的 `deepseek-harness` 仓库，FOCUS 的业务实现仍归本仓库；完整 DSH 产品界面在阶段 6 交付。

在隔离 workspace 完成 DSH 插件 build／pack／install／boot；无聊天 Session 时也能打开最小知识库入口。DSH 原生 Host 通过受管理 worker 调用与 Standalone 相同的 Python Application，并由 DSH Runtime 执行一个受限 AI 步骤。

最小场景确定为单篇 Reading Blog 重新生成：使用预置的公开样例 Bundle 与合法博客初始资产，通过共享 Application 执行一个 AI 写作步骤，经共用校验器校验、Core 提交后确定性渲染 HTML。成功时能打开结果；取消或失败时已有合法产物仍可访问。必须经过真实的业务提交和取消边界，不扩大为完整博客生成流程。

保持一个 AI 子任务只有一个模型—工具循环；worker 是业务服务，不启动旧 FOCUS Host 或第二个 DSH 实例。只验证最小双向任务／结果桥接，不在此复制完整产品界面。

仅支持本机部署：浏览器、DSH 服务端插件、受管理 worker 与 workspace 位于同一台机器。Remote 在此指 DSH 页面与服务端之间的真实调用通道；验证页面断连／重连后可重新查询业务状态。页面刷新或断连本身不取消业务任务，显式取消仍须禁止迟到提交。跨机器部署不在本阶段或阶段 6 范围内。

每个 AI attempt 使用独立的 DSH 原生 Session；打开知识库不创建 Session，启动 AI 步骤时才创建。业务 Run／Step／attempt 由 Application 管理，DSH Session ID 只保存在 Host 侧关联记录中；重试创建新 attempt 和新 Session。

模型工具仅允许读取选定 Bundle／方法资源及交回候选内容，不开放通用 shell、任意文件写入或联网工具。Application／Core 负责校验与正式提交。验收记录模型实际可见及可执行的完整工具集合，并验证越界调用被拒绝，不能只凭配置的 allow 清单宣称限制生效。

每个插件实例管理一个绑定隔离 workspace 的 Python worker；探针同时仅运行一个 AI attempt，插件卸载时停止任务并回收 worker。worker 崩溃、插件卸载或 DSH 退出后，当前 attempt 永久失去提交资格；重启显示已中断，由用户显式重试创建新 attempt 和新 Session。取消回执只表示已请求取消，须另行确认执行停止与资源释放；已有合法提交不回滚。

取消与提交竞争以 Core 原子提交边界判定：取消先使 attempt 失效则禁止发布；提交先完成则保留资产，并明确显示“已提交，取消未撤销该结果”。成功、失败或取消的专用 DSH Session 均在确认执行终止并释放 live 资源后，通过 DSH 公开能力归档。

FOCUS 仅保留最小非聊天验收记录：DSH／方法版本、业务 attempt、Session 关联、最终工具权限清单、校验与提交结果、取消／停止／释放／归档回执；不复制 DSH 对话、模型思考或完整工具交互日志。DSH 自有日志仍保留，不宣称永久删除。业务结果与清理结果分别报告：归档失败不使已提交资产变为失败，另报“清理未完成”；旧 attempt 不得再次提交，保留待清理关联并在下次启动重试归档。实际归档成功前，清理验收仍记未通过。

## 验收出口

- 插件生命周期和无 Session 入口有真实 DSH 证据，兼容版本被记录。
- 同一受控 fixture 场景经两个 Host 调用同一工作流、方法版本与校验器，规范化资产结果一致。
- DSH Runtime 的一次真实受限 AI 步骤有工具限制、候选结果、共用校验与提交证据；fixture 通过不能代替此项。
- 取消／卸载／worker 中断能禁止迟到结果提交并释放资源；已提交资产保留，不用长时间写锁等待模型。
- 页面断连／重连后可重新查询业务状态，不因断连自动取消；执行端中断后旧 attempt 不再有提交资格，显式重试使用新 attempt／Session。
- 专用 Session 在执行终止、资源释放后被归档，最小非聊天验收记录足以核查结果；清理失败单独报告并可于下次启动重试，不将“已请求取消”冒充“执行已停止”“资源已释放”或“已归档”。
- 契约冲突回到公共接口修正；最迟在阶段 2＋3 最小闭环验收时给出探针结论，后续持续跑已接通用例。

## Grill 决策记录

### 已确认的决策（2026-09-25）

- Q2：允许在本阶段补齐所选最小场景必需的公共接口；Standalone 同步使用该接口并通过回归验证。若需要改造 DSH 内核、扩大到完整博客流程或复制业务状态机，则记录未通过项与后续工作，不纳入探针实施范围。
- Q1：仅本机部署，经过真实 Remote 通道并验证页面断连／重连恢复；断连不自动取消业务任务。跨机器部署不在阶段 2D 或阶段 6 范围内。
- Q3：用户要求先由子代理同步并拉取 DSH 最新版本，再固定该版本作为探针基准；已获取 `0.1.7-rc.2`，完整提交与隔离目录见下方基线记录。
- Q4：最小场景为单篇 Reading Blog 重新生成，复用公开样例 Bundle、合法初始资产和公共校验提交路径，随后确定性渲染 HTML。
- Q5：每个 AI attempt 使用独立 DSH 原生 Session，Session ID 仅作为 Host 侧关联信息，业务身份由 Application 管理。
- Q6：只开放选定 Bundle／方法资源读取与候选交回工具；校验提交归 Application／Core，并验证实际完整工具集合及越界拒绝。
- Q7：每个插件实例管理单个绑定隔离 workspace 的 Python worker，同时只运行一个 AI attempt；卸载停止任务并回收 worker。
- Q8：执行端中断使当前 attempt 永久失去提交资格，重启后显式重试；取消请求回执与执行停止、资源释放分别确认。
- Q9：取消与提交竞争以 Core 原子提交边界判定；不撤销已完成的合法提交。
- Q10：执行终止并释放 live 资源后归档专用 DSH Session；固定 DSH 基准不支持永久删除，DSH 自有日志继续保留。
- Q11：FOCUS 仅保留版本、业务 attempt、Session 关联、工具权限、校验提交与取消／停止／释放／归档回执等最小非聊天验收记录，不复制 DSH 日志。
- Q12：业务结果与清理结果独立；归档失败记录待清理关联并在下次启动重试，实际归档成功前不宣称清理验收通过。

## DSH 基线记录（2026-09-25）

- 版本：`0.1.7-rc.2`；对应标签：`dsh-v0.1.7-rc.2`。
- 精确提交：`477b4f420553e8a52c2fbccc464d7561b239c443`；获取完成后重新核对，同官方远端默认分支 `master` 的 HEAD 一致。
- 当前基准目录：`D:/dsh-proj/deepseek-harness`，本地 `main` 跟踪 `origin/master`，HEAD 与上述远端最新提交一致，工作树干净。
- 用户追加授权无需保留旧 DSH 改动后，重新 fetch 并将原目录 reset 到 `origin/master`，清除旧的本地删除状态及过时的未跟踪 `packages/examples/`。本次创建的临时 worktree `D:/dsh-proj/deepseek-harness-focus-stage2d-477b4f4` 已移除，仅使用原目录作为基准。
- SSH 获取未成功后，通过同一官方仓库 HTTPS 获取更新，未修改 remote 配置。未安装依赖、build、启动服务、调用模型或实施探针；干净检出与源码接缝核查不代表运行验收通过。
- 新版源码接缝仍存在：`packages/client/ui-layout/src/client/index.ts:69` 的 root keyed main panel 支持非 conversation 面板不绑定 Session；`packages/core/agent-loop/src/index.ts:643` 的 create 创建同标识 Agent／Session；`packages/core/tools/src/index.ts:1090` 的 restrict 仍仅过滤全局工具、作用域新增工具仍可见，`:1126` 起的 guard 提供执行拒绝约束。需在后续探针中验证实际完整工具集合。

### 已确认的能力边界：专用 Session 不支持永久删除

在上述基准的 `packages` TypeScript 源码、session-controller commands/types、SessionPersistence、AgentHandle 与 WorkspaceRegistry 中，尚未发现永久删除已持久化 Session 的公共接口。`SessionPersistence`（`packages/session/session-persistence/src/index.ts:150–201`）的 create/open/flush/stat/list 能力不能直接证明删除可用；`AgentHandle.dispose`（`packages/core/agent/src/index.ts:147–162`）停止执行、释放 live handle，不等于删除持久日志；workspace 的 detachSession 明确不触及存储日志，archiveSession 仅归档。

隔离持久化探针进一步证明 close／dispose 后 Session 仍存在，固定基准没有受支持的永久删除路径。用户已明确接受 [ADR-0014](../../adr/0014-archive-dsh-attempt-sessions.md) 的例外：以公开归档能力作为阶段 2D 清理出口，如实说明 DSH 日志仍保留；不得直接操作私有存储、改造 DSH 内核或把归档描述为永久删除。后续实施须分别验证停止、释放与归档，并使归档失败可见、可重试。

用户已于 2026-09-25 确认整体共同理解并结束本轮 grill；当前只定稿需求，暂不实施探针。

不含全量 Inbox／阅读 UI、美化、旧数据迁移和正式 DSH 发布；环境阻塞应记录未通过出口，不能用 mock 宣告探针完成。
