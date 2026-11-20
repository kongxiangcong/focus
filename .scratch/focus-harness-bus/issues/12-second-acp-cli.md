# 12: 用第二个真实 CLI 验证 ACP 驱动复用

**What to build:** 用 agy 或 Cursor CLI 中的一个验证同一 ACP 驱动可复用。

**Blocked by:** 09 ACP 取消、确认过期与资源回收

**Status:** ready-for-human

- [ ] 通过标准 Manifest 在正式工作台选择受测 CLI，完成阅读讨论、真实 read_range 往返、取消和资源释放。
- [ ] 记录具体 CLI、版本、平台、握手耗时与首段输出耗时，保留失败及未覆盖场景；未经真机验证的预置标为「未实测」。
- [ ] 验收使用通用驱动和 Host 工具桥；无需等待 DSH 迁移即可独立执行此票。

## Comments

### 2026-11-21 · Windows 预验收，发布门槛仍开放

平台为 Windows 11 25H2 x64，构建 26200.9974。使用官方 Windows 便携副本，预验收未变更系统 PATH 或已有 FOCUS 设置。真实 CLI 的握手时间测自本机启动至 ACP 初始化完成。

| 预置 | 实际 CLI 版本 | 真机预验收 | 启动至握手 | 发问至首段 | 真机结果 |
| --- | --- | --- | --- | --- | --- |
| `agy` | Antigravity CLI 1.5.13 | ACP 初始化通过。服务返回 `FAILED_PRECONDITION (400)` 并报告当前地区不可用。 | 423 ms | 未实测。1,393 ms 收到服务错误。 | 原文读取、讨论、取消及回收未实测。 |
| `cursor` | Cursor Agent CLI 2026.11.19-f005e9d | ACP 初始化通过。CLI 状态要求登录，`session/new` 返回 `-32000`。 | 2,326 ms | 未实测。 | 原文读取、讨论、取消及回收未实测。 |

`da608b2` 上的正式 Workbench HTTP 验证确认四个内置 ID 均可列出。对 `agy` 和 `cursor` 指定便携程序路径，设置的 `inspect` 均返回 `installed`，`account` 均返回各自的 `external-login` 指引。临时知识库可浏览，记录到零个子进程启动，保存配置与生效 Backend 仍为空。

同一提交运行 `test_acp_discussion` 和 `test_backend_registry` 共 8 项，全部通过。协议替身覆盖通用 ACP 驱动与 Host 工具桥的 HTTP、stdio 原文读取，会话隔离，确认过期和重试，停止时释放子进程，以及 Manifest 发现与重新扫描。这些结果对应协议替身。实际 `agy` / `cursor` 仍待完成真机验收。

自动批准审查拒绝追加真实 CLI 的握手、模型目录及启动阶段停止检查，因为会话与目录调用可能触发未经授权的提供方交互。本次复核未发起登录或模型请求。发布门槛需要获得 Cursor 登录授权并使用可用账户，以及为 ACP 选择实际模型；也可在服务支持的环境使用 `agy` 再跑同一套正式工作台验收。收到账号授权或具备可用服务之后，再测原文标记往返、首段输出、取消和资源回收。
