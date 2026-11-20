# 11: 真机验证 dsh 并替换 DeepSeek SDK

**What to build:** 沿用 DeepSeek 用户的选择及凭据，用已验证的 dsh ACP 接法直接替换 SDK。

**Blocked by:** 05 按能力提供登录、模型和凭据配置、09 ACP 取消、确认过期与资源回收

**Status:** ready-for-agent

- [ ] 保留 deepseek ID、模型偏好与 credentialFile；重新发现 dsh，忽略旧 SDK 专用路径。缺失时提供安装及指定路径入口。
- [ ] 通过同一 ACP 驱动在真机完成阅读讨论、真实 read_range 往返、取消与资源释放；记录平台、CLI 版本、进程启动至握手完成及发问至首段输出耗时。
- [ ] 实测通过后直接移除 SDK 接入与相应依赖；统一终止和释放，不保留双路径、DSH 专属原生 Session 归档或启动重试。
