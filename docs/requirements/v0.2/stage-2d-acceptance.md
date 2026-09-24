# FOCUS v0.2 阶段 2D 验收记录

日期：2026-09-25。结论：票 01 的专用 Session 永久删除前置未通过，阶段 2D 阻塞；按票据顺序和停止条件，票 02、03 未开始。

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

## 决策

不通过直接删私有存储文件、归档、隐藏、删除 workspace registration 或修改 DSH 内核来规避票据要求。删除能力是票 01 的实施前置，因此未继续构建最小插件、pack/install/boot 或原生页面，也未执行票 02/03 的业务和真实 AI 路径。

可恢复条件是以下之一：

- 固定 DSH 基准增加可支持的公共永久 Session 删除能力，可在实际持久状态上验证；
- 经明确需求变更，改变“必须永久删除”的验收语义。

## 分层状态

| 层级 | 状态 | 证据／原因 |
| --- | --- | --- |
| 删除能力调查 | 通过 | 公共契约、后端限制与隔离持久化探针结论一致 |
| 专用 Session 实际删除 | 阻塞 | 固定基准无可支持的公共删除路径 |
| 插件 build/pack/install/boot | 未测 | 删除前置失败后按票据停止 |
| 无 Session 原生页面 | 未测 | 同上 |
| 受控 Runtime 双 Host 业务闭环 | 未测 | 票 02 被票 01 阻塞 |
| 真实 DSH 受限 AI | 未测 | 票 03 被票 02 阻塞 |
| 阶段 2D | 阻塞 | 必需的真实 Session 删除出口缺失 |
