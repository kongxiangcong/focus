# 01: 用标准 Manifest 运行现有 Codex

**What to build:** 让已有用户通过注册表选择原 Codex 配置并继续源文讨论。

**Blocked by:** None (can start immediately)

**Status:** resolved

- [x] 用内置 codex Manifest 指向现有 App Server；升级后原标识、模型和可执行路径仍有效，无须安装 codex-acp。
- [x] 从设置、现有 HTTP 入口到 Host 使用 backend/backends 和开放字符串 ID；显式覆盖路径时保留子命令和参数顺序。
- [x] 从工作台完成一次讨论；可用独立 ID 注册第二种接法，默认只展示一个 Codex 条目。业务服务通过注册表创建驱动。

## Comments

Manifest 注册和正式讨论已验收。Codex 默认接法沿用 App Server。 [验收记录](../acceptance.md)
