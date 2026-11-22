# 11: 真机验证 dsh 并替换 DeepSeek SDK

**What to build:** 沿用 DeepSeek 用户的选择及凭据，用已验证的 dsh ACP 接法直接替换 SDK。

**Blocked by:** 05 按能力提供登录、模型和凭据配置、09 ACP 取消、确认过期与资源回收

**Status:** resolved

- [x] 保留 deepseek ID、模型偏好与 credentialFile；重新发现 dsh，忽略旧 SDK 专用路径。缺失时提供安装及指定路径入口。
- [x] 通过同一 ACP 驱动在真机完成阅读讨论、真实 read_range 往返、取消与资源释放；记录平台、CLI 版本、进程启动至握手完成及发问至首段输出耗时。
- [x] 实测通过后直接移除 SDK 接入与相应依赖；统一终止和释放，不保留双路径、DSH 专属原生 Session 归档或启动重试。

## 验收证据

2026-11-21 在 Windows 11 25H2 x64（26200.9974）用 DSH CLI `0.2.1-rc.2` 实测内置 `deepseek`，沿用显式凭据文件及模型 `deepseek-v4-flash`。

- 正式 Workbench HTTP 入口首次发问时显示检测状态，随后自动进入同一请求的讨论。通过实际 `focus.read_range` 读回绑定测试来源的随机标记。进程启动至 ACP 握手 1,812 ms，发问至首段输出 4,787 ms，含首次准入检测共 17,031 ms。
- 移除 SDK 后复测通过。正常讨论握手 1,673 ms，发问至首段输出 6,862 ms，含首次检测共 15,276 ms。第二轮使用新会话，握手 1,678 ms，点击停止后进入 `interrupted`。正常完成与停止均通过 Windows 进程句柄确认对应 PID 已退出，并验证隔离工作目录已删除。

## Comments

内置 DeepSeek 在 Windows DSH 原文往返和取消通过后已切换 ACP，SDK 路径已移除。 [验收记录](../acceptance.md)
