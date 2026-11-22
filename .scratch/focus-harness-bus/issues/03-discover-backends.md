# 03: 首次进入工作台与重新扫描 Backend

**What to build:** 从设置页发现本机程序和用户自定义条目，允许跳过配置进入知识库。

**Blocked by:** 01 用标准 Manifest 运行现有 Codex

**Status:** resolved

- [x] 首版内置 ID 固定为 codex、deepseek、agy、cursor；Claude Code 与 Codex ACP 通过独立自定义 ID 注册。
- [x] 显式 --backends-dir 优先，否则扫描实际设置文件同级的 backends 目录；覆盖 Windows 默认位置和自定义设置位置。
- [x] 零个可用程序时给安装和重检入口，一个可预选，多个供选择。首次使用 AI 前需确认；扫描、跳过初始化均不启动 CLI、自动安装或发起模型请求。
- [x] 启动扫描一次，手动重新扫描列出错误文件名与原因，内置 ID 冲突时内置条目可用；其他有效条目、在途任务及生效配置不受影响。

## Comments

Windows 暂存工作区和 Chrome 验收覆盖四个预置、自定义目录、错误文件、重复 ID 和无 Backend 进入。 [验收记录](../acceptance.md)
