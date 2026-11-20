# 04: 从命令行临时选择 Backend

**What to build:** 脚本可以为本次 Host 进程明确选择执行程序、Backend 与模型。

**Blocked by:** 01 用标准 Manifest 运行现有 Codex

**Status:** resolved

- [x] --backend、--backend-bin 和模型选项遵循 CLI > 环境变量 > 保存值；发布脚本和示例采用统一参数，公开面不新增 harness 别名。
- [x] 显式选择视为本次确认，切换工作区仍生效；只有设置页主动保存并应用才持久化，重启后可读回原保存值。
- [x] 指定的 Backend 或路径无效时指出具体失败项，仍可进知识库；验证没有静默执行其他 Backend。

## Comments

CLI 和 HTTP 验收覆盖启动参数优先级、跨工作区复用、无效配置和重新启动。 [验收记录](../acceptance.md)
