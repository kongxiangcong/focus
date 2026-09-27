# FOCUS v0.2 阶段 2D 验收记录

## 2026-09-26 真实续跑结论：阶段 2D 通过

配置就绪后，以同一固定 DSH `0.1.7-rc.2 / 477b4f420553e8a52c2fbccc464d7561b239c443` 完成真实 DeepSeek V4.1 Flash 成功出口。结合下文既有票 01/02 的受控失败、竞争、中断和恢复证据，票 03 已 resolved，解除阶段 5 票 06 的 2D 前置阻塞。这里验证的是公开样例上的真实 Runtime 路径，不是实际论文解析或语义质量认证。

- 首次页面操作复现 `tools.restrict() requires a scoped context`：插件把 DSH 的共享服务列为普通 dependencies，安装得到另一份 scope 模块。按 DSH 公共插件装配规则改为 peerDependencies，插件版本升为 `0.2.0-stage2d.24`。没有改 DSH 内核或放宽工具限制；本机 profile 的 peer 安装提示由宿主运行时统一解析补足，实际 boot 与 Agent scope 均通过。
- 成功 attempt：`8e3b3bad-afec-4b71-9440-2d2a54c43506`，provider `deepseek-official`，model `deepseek-flash`，认证只记录 `DEEPSEEK_API_KEY` 环境引用。实际工具为 `focus_read_bundle`、`focus_read_method`、`focus_submit_candidate`；真实 `bash` 执行拒绝为 `UNKNOWN_TOOL`。
- 模型交回 4447 字符 Reading Blog 与 Evidence Map，worker 经共享 Reading Blog 路径校验并由 Core 发布；`reading_blog / html` 均为 completed，更新时间 `2026-09-26T08:03:36+00:00`。既有 Value Analysis 未重写，也未再次分类。保留警告“价值分析未说明实现是否实际运行”；内容深度未作自动认证。
- DSH 原生页面显示 `completed / archived`，点击“打开博客”看到新正文和原文锚点，图片实际解码（样例图片为 1×1），无 iframe。该极简样例图片不是阶段 5 的真实带图 HTML 验收证据。
- 后续真实取消 attempt：`91977816-3e17-409f-8a9e-f23a652aa088`，终态 `cancelled / archived`。两次任务均在公开 handle.dispose 完成、live handle 移除后执行归档；DSH 持久日志保留，不宣称永久删除。历史真实模型失败/归档见 09-25 记录，本轮未伪造服务故障。
- `.24` 完成 build/pack/install/boot，并 remove 后核实组合配置不再含插件，重新 add/boot；页面重连后查询到 `cancelled / archived`，已发布正文仍可打开。取消与重装重启前后所有已发布博客文件 SHA-256 一致；成功/取消专用 Session 关联仍在 DSH registry。
- 修复后 worker/Standalone Host 回归 18/18 通过（16.045 秒）；原生入口与归档生命周期 Vitest 命令汇总 6 个文件/9 tests 通过（含 workspace 重复运行）。Standalone 已在不加载 DSH 的独立进程正常启动；类型检查与构建见本日预检查。
- 本轮最小非聊天证据：`.scratch/focus-v02-stage2d/live-20260926.json`；浏览器截图：`tmp/stage2d-success-20260926.png`。FOCUS 不复制模型聊天或思考日志。

## 2026-09-26 充值后复验预检查

用户要求先以 DeepSeek V4.1 Flash 跑通阶段 2D，再执行阶段 5 票 06。当前 FOCUS 基准为 `d6ab8b48faef02785022da5bc7c06c2446326f9c`；DSH 仍为 `477b4f420553e8a52c2fbccc464d7561b239c443`，两仓库检查时工作树干净。插件版本仍为 `0.2.0-stage2d.23`。

- 官方 V4.1 Flash 调用名为 `deepseek-flash`，后续真实运行须显式设置 `FOCUS_DSH_AI_MODEL=deepseek-flash`。依据：[官方发布说明](https://api-docs.deepseek.com/zh-cn/news/news260910/)。本次尚未发起真实模型请求，也未修改默认模型。
- 当前进程、User/Machine 环境与本仓库 `.env` 未提供 `DEEPSEEK_API_KEY`；`.env` 已被 Git 忽略，仅确认 MinerU 配置存在而未输出凭据。DSH checkout 无 `.env`，原隔离 profile 配置未发现 DeepSeek 凭据配置。已请求用户在本机提供凭据。
- ` .venv/Scripts/python.exe -X utf8 -m unittest tests.test_dsh_focus_worker tests.test_blog_host`：18/18 通过（15.964 秒），属于受控 Runtime／共享 Host 回归。
- `pnpm exec vitest run tests/dsh_focus_plugin.spec.ts tests/dsh_session_lifecycle.spec.ts`：命令汇总为 6 个测试文件、9 个测试通过（包含 workspace 重复运行，不能算 9 个独立场景）。这是自动化入口／生命周期证据，不是本轮真实 DSH 服务与模型验收。
- 插件 build、`pnpm reader:typecheck`、`pnpm reader:build` 均通过；Standalone build 保留大于 500 kB 的 chunk 警告。
- 本轮真实候选、公共校验／Core 提交、浏览器打开最终 HTML、真实成功 Session 停止／释放／归档均未测；没有重跑真实取消或插件安装生命周期。此前证据见下文，不计为本轮新证据。

当前阻塞是缺少可用凭据，不能把历史 HTTP 402 当成充值后实测，也不能据此推断当前余额。阶段 2D 票 03 仍 blocked；阶段 5 票 06 按依赖顺序尚未启动。凭据就绪后继续真实流程，无需再次确认模型调用授权。

日期：2026-09-25。当前结论：票 01、02 已通过；票 03 的实现、受限工具探针、真实失败与真实取消／归档已通过，但真实成功写作被 DeepSeek 官方账户余额阻塞。永久删除能力调查已完成；用户接受固定 DSH 基准采用“终止执行、释放资源并归档专用 Session”的明确例外。阶段 2D 因缺少真实模型成功、候选校验与 Core 提交证据，尚不能宣布完整通过。

## 固定基准

- FOCUS 任务起点：`eaf65de1608ff930d4d7e315d885bada8a7ffa5b`。
- DSH 目录：`D:/dsh-proj/deepseek-harness`。
- DSH 版本：`0.1.7-rc.2`。
- DSH 提交：`477b4f420553e8a52c2fbccc464d7561b239c443`。
- DSH 工作树：探针前后均无 tracked 改动。

## 删除能力核验

公共 `SessionPersistence` 契约仅提供 `create`、`open`、`flush`、`stat` 和 `list`。随附 JSONL 后端明确记录“Nothing deletes session files”；`WorkspaceRegistry.delete` 删除的是 workspace registration，不删 Session 历史，`archiveSession` 也只是归档及请求停止活动。

为排除“文档滞后但运行时已支持”，在 DSH workspace 中运行了一个临时 Vitest 探针：

1. 挂载真实 `SessionStore` 和 `JsonlSessionPersistence`，并使用隔离临时 root。
2. 创建 `focus-stage2d-probe-session`，获取持久化 handle，执行 `flush`、`close` 并 dispose 首个 Context。
3. 在同一 root 上新建 Context 并重新挂载公共服务。
4. `stat(session.id)` 仍有结果，`list()` 仍包含该 Session，运行时公共服务不存在 `delete` 操作。

可复现探针源码保存在 [`tests/probes/dsh_session_deletion_probe.spec.ts`](../../../tests/probes/dsh_session_deletion_probe.spec.ts)。它是 FOCUS 的验收资产；复现时临时复制到固定 DSH checkout 的测试目录，不把探针提交到 DSH：

```powershell
$dshRoot = 'D:\dsh-proj\deepseek-harness'
$probeTarget = Join-Path $dshRoot 'packages\session\session-persistence-jsonl\tests\focus-session-delete-probe.spec.ts'
Copy-Item -LiteralPath '.\tests\probes\dsh_session_deletion_probe.spec.ts' -Destination $probeTarget
Push-Location $dshRoot
try {
  pnpm exec vitest run packages/session/session-persistence-jsonl/tests/focus-session-delete-probe.spec.ts
} finally {
  Pop-Location
  Remove-Item -LiteralPath $probeTarget
}
```

结果摘要：Vitest `v4.1.8`，`Test Files 1 passed (1)`，`Tests 1 passed (1)`。该通过只证明“终止后仍持久化，且公共删除能力缺失”的探针断言。测试 teardown 对整个隔离临时 root 的外部删除仅用于回收测试资源，不是 Session 删除方案，也不计为验收证据。

## 原阻塞与后续决策

本轮调查没有通过直接删私有存储文件、隐藏、删除 workspace registration 或修改 DSH 内核规避原票据要求。因此在需求改变前，没有继续构建最小插件、pack/install/boot 或原生页面，也没有执行票 02/03。

随后用户明确同意改变清理语义。现采用 [ADR-0014](../../adr/0014-archive-dsh-attempt-sessions.md)：专用 Session 到达终态后确认停止、释放 live 资源并调用 DSH 公开归档能力；DSH 日志保留，不宣称永久删除。归档结果与业务结果独立，失败可见并在后续启动重试。上面的删除探针继续作为采用该例外的能力证据，而不是当前清理出口。

## 票 01 运行证据

- FOCUS 插件包：`@focus/dsh-native@0.2.0-stage2d`；`pnpm --filter @focus/dsh-native build` 通过，并打包为本地 tgz。
- 在隔离 `DSH_HOME` 的 `focus-stage2d` profile 上，实际执行本地 add、配置 dump、boot、remove、再次 add 和再次 boot；卸载后的配置不再包含插件，重装后插件注册恢复。
- DSH checkout 首次缺少构建产物；执行官方全量 build 后 Host、Client 与前端构建通过。期间仅为运行官方 clean 临时放宽一个生成目录白名单，完成后立即还原；最终 DSH tracked 工作树保持干净，提交仍为固定基准。
- 真实浏览器中可见全局侧栏入口“FOCUS 知识库”和原生根面板。面板不使用 iframe，并明确提示打开页面不创建 AI attempt 或 DSH Session。
- 隔离 DSH home 在打开面板前后均只有 1 个持久 Session 文件；该 Session 是 DSH 首次引导生成的“新会话”，打开 FOCUS 面板没有增加 Session。
- FOCUS 客户端单测验证根面板和侧栏注册，并以会抛错的 `sessions` getter 证明初始化不访问 Session 服务：Vitest `1/1` 通过。
- 归档生命周期探针使用真实 `SessionStore`、`JsonlSessionPersistence` 和 `WorkspaceRegistry`：创建并物化一个插件专用 Session，收到停止事件并释放探针资源，调用公开 `archiveSession`，重启 Context 后归档 ID 仍存在且持久日志仍可列出。Vitest `1/1` 通过。
- 两个探针都只操作隔离临时存储和插件专用测试 Session；没有读取、归档或清理用户 Session，也没有修改 DSH 内核或直接删除私有持久文件。

## 分层状态

| 层级 | 状态 | 证据／原因 |
| --- | --- | --- |
| 删除能力调查 | 通过 | 公共契约、后端限制与隔离持久化探针结论一致 |
| 永久删除能力 | 不支持（已接受例外） | 固定基准无可支持的公共删除路径；保留探针证据 |
| Session 停止／释放／归档 | 通过 | 真实公共服务、隔离持久状态、重启后归档与日志保留探针 1/1 通过 |
| 插件 build/pack/install/boot | 通过 | 本地包在隔离 profile 完成安装、两次启动、卸载和重装 |
| 无 Session 原生页面 | 通过 | 真实浏览器入口可见；打开前后持久 Session 数保持 1；客户端单测 1/1 通过 |
| 受控 Runtime 双 Host 业务闭环 | 通过 | 真实 DSH Remote/worker 页面闭环；双 Host 自动化 2/2、Host 自动化 14/14、前端相关自动化 25/25 通过 |
| 真实 DSH 受限 AI 权限边界 | 通过 | 实际 Agent 仅暴露三项 FOCUS 工具；真实 `bash` 调用返回 `UNKNOWN_TOOL` |
| 真实 DSH AI 成功写作 | 阻塞 | DeepSeek 官方 `deepseek-v4-flash` 在首个 token 前返回 HTTP 402／`QUOTA`（余额不足） |
| 真实 DSH AI 取消与归档 | 通过 | 页面即时取消得到 `cancelled / archived`；失败会话得到 `failed / archived` |
| 阶段 2D | 阻塞 | 票 01、02 通过；票 03 缺真实模型成功、公共校验、Core 提交与页面打开最终 HTML 证据 |

## 票 02 受控 Runtime 证据

- 插件 `@focus/dsh-native@0.2.0-stage2d.16` 通过 DSH `TypertRemoteService` 暴露公开 `listSources`、`status`、`regenerate`、`cancel`、`open` 动作；真实原生页面经 Remote 调用受管理 Python worker。worker 直接使用共享 `BlogApplication`、真实 Core 提交、共用候选校验与确定性 HTML 渲染，不启动旧 FOCUS Host、第二个 DSH 或第二个模型循环。
- 公开 Fixture Paper 包含合法 Bundle、图片、初始博客与 Value Analysis。真实页面完成单篇全部重新生成，最终 `blog.md`、`value-analysis.md`、Evidence Map 与双页 `index.html` 可打开，HTML 含 Bundle section/figure source anchors。
- 每次页面 attempt 先创建独立 DSH Session，FOCUS 的业务 run/step/attempt 保持由 Application 管理。一次普通完成与一次显式取消分别得到业务终态和独立 `archived` 清理回执；Session 日志仍由 DSH 保留。
- 受控取消使用 Runtime 同步屏障而非任意 sleep：取消先发生时，Application 先撤销 commit eligibility，再请求 Runtime 停止；迟到候选未替换旧发布资产。提交先完成时，后续取消被公共接口拒绝，已提交资产不回滚。HTTP/Standalone 与 DSH worker 都复用相同取消语义。
- 修复并回归了 run 启动与 article attempt 登记之间的竞态：attempt 创建和取消现在由同一 Application 锁串行化；已取消 run 不会创建新的可提交 article/HTML attempt。
- 双 Host 对照在两个隔离 workspace 中分别经 DSH worker 与 `HostService` 公共动作运行同一候选；`blog.md`、`value-analysis.md`、Evidence Map 字节一致，HTML 仅归一化 Host 执行生成时间后字节一致。正文、版本、校验结果、warnings、提交资格和业务终态均未从比较中排除。
- 实际中断验证从页面启动 `running / pending` attempt 后直接退出 DSH。安装并启动 `.15` 后，在未点击恢复动作前，持久 attempt 已自动变为 `failed / archived`；页面仅通过公共状态查询显示相同结果。显式重试创建新 attempt/Session 并从合法已发布资产继续，未自动重跑受控 AI。
- 插件退出通过有界 worker shutdown；活动 attempt 若随进程中断，则由 Application 下次启动恢复为失败并永久失去提交资格。清理状态单独持久化；`pending` 清理会在下一次启动重试公开 `archiveSession`，不触及其他 Session。
- FOCUS 的 `.dsh-attempts.json` 只保存 attempt、request/source、Session 关联、业务终态和清理回执；没有复制完整对话、思考或工具日志。DSH 自有 Session/日志按 ADR-0014 保留。

票 02 自动化结果：

- `tests.test_dsh_focus_worker`：2/2 通过，覆盖双 Host 规范化资产与 worker 取消迟到候选。
- `tests.test_blog_host`：14/14 通过，覆盖公共 Host/HTTP、生成、全部重生、失败、同步取消竞争、提交先完成、查看与 ingestion continuation。
- `dsh_focus_plugin.spec.ts`、`dsh_session_lifecycle.spec.ts`、Standalone Workspace/HTTP adapter：25/25 通过。
- `pnpm reader:typecheck` 与 `pnpm reader:build` 通过；build 仅保留既有大 chunk 警告。

本节只证明受控 Runtime、真实 DSH Host/Remote/worker/Core/归档层；它不证明真实模型调用、真实工具权限隔离或内容质量。后者属于票 03。

## 票 03 真实受限 Runtime 证据

- 插件 `@focus/dsh-native@0.2.0-stage2d.23` 将一个 DSH Agent／Session 接到票 02 的同一 `BlogApplication.regenerate(..., artifact="reading_blog")` 路径。模型仅产出候选；worker 仍调用共享校验器、Core 提交与确定性 HTML 渲染，不启动旧 Host、第二个 harness 或第二个模型循环。
- 每个 live attempt 在创建 Agent 后先屏蔽继承工具，再仅注册 `focus_read_bundle`、`focus_read_method`、`focus_submit_candidate`。运行时枚举确认完整可见工具清单恰为这三项；随后通过 Agent 的实际 scope 执行一次 `bash`，得到 `UNKNOWN_TOOL`。这项拒绝证据来自真实工具执行入口，不只是静态 allow 配置。
- `focus_read_bundle` 只返回选定公开 Fixture Paper 的 `content.md` 与可用图片名；`focus_read_method` 只返回 article-blog 方法资源；`focus_submit_candidate` 只接受一次 `blog.md` 与 `evidence/evidence-map.md`，候选仍须进入共享业务路径。Agent 不暴露 shell、网络、任意文件操作或正式资产直提工具。
- 实际 Runtime 为固定 DSH `0.1.7-rc.2` 的 Agent，provider 为 `deepseek-official`，model 为 `deepseek-v4-flash`，认证只记录 `DEEPSEEK_API_KEY environment credential reference`，没有把凭据写入 FOCUS 状态、仓库或报告。
- 真实写作 attempt `82a3ce0b-c5b7-4665-84b3-224f5bf4a376` 已通过三工具预检查和越界拒绝探针，但 provider 在首个 token 前返回 HTTP 402／`QUOTA`（余额不足）。该 attempt 以 `failed / archived` 终止；没有候选、没有形态／内容校验、没有 Core 提交，也没有用受控 fixture 冒充真实模型结果。
- 真实取消 attempt `72731010-06cd-45ca-8a18-3ba3be0897d7` 从页面发起后立即取消，得到 `cancelled / archived`。Agent live handle 已释放，专用 Session 通过公开 workspace 归档能力归档；DSH 自有会话日志仍保留。受控 Runtime 的迟到候选拒绝、worker 中断和 DSH 退出恢复继续由票 02 的确定性证据覆盖，未冒充真实模型完成证据。
- FOCUS 的最小状态只记录版本关联所需的 attempt／Session、source／request、provider／model、认证引用、完整工具清单、拒绝探针结果、业务终态及归档回执；不复制模型消息、思考、候选正文或完整工具日志。

票 03 自动化结果：

- `@focus/dsh-native` build 通过；DSH 原生入口／工具边界和真实归档生命周期 Vitest `3/3` 通过。
- `tests.test_dsh_focus_worker` 与 `tests.test_blog_host` 共 `18/18` 通过，包含 DSH live 候选进入公开 Reading Blog 路径、双 Host 对照、模型候选进入 worker 后的取消／迟到拒绝及 Standalone Host 回归。
- Reader UI 与 Standalone Vitest 共 `54/54` 通过；`pnpm reader:typecheck` 与 `pnpm reader:build` 通过。build 仅保留既有大 chunk 警告。
- 真实 DSH 页面确认失败和取消 attempt 都已归档；固定 DSH checkout 仍在 `477b4f420553e8a52c2fbccc464d7561b239c443` 且 tracked 工作树干净。

票 03 保持阻塞，解除条件是为同一显式 provider／model 提供可用额度后重跑真实写作，并取得候选返回、结构／图片／引用校验、质量 warnings、Core 提交、确定性 HTML 页面打开及成功 Session 释放／归档证据。无需改变权限范围，也不得静默切换 provider。
