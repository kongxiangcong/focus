# FOCUS v0.2 阶段 2D 验收记录

日期：2026-09-25。当前结论：票 01、02 已通过。永久删除能力调查已完成；用户接受固定 DSH 基准采用“终止执行、释放资源并归档专用 Session”的明确例外。最小插件与受控 Runtime 博客闭环已完成真实 DSH 页面、双 Host 对照、取消、中断恢复和归档验收。票 03 的真实受限 AI 仍待执行。

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
| 真实 DSH 受限 AI | 未测 | 票 03 被票 02 阻塞 |
| 阶段 2D | 进行中 | 票 01、02 已通过，继续实施票 03 |

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
