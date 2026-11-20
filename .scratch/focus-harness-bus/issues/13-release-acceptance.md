# 13: 正式工作台发布验收

**What to build:** 从交付给读者的正式入口复核首版，并发布可核对的逐项验收记录。

**Blocked by:** 03 首次进入工作台与重新扫描 Backend、04 从命令行临时选择 Backend、07 多页面安全地保存并应用、10 显式候选检查使用当前 Backend、11 真机验证 dsh 并替换 DeepSeek SDK、12 用第二个真实 CLI 验证 ACP 驱动复用

**Status:** ready-for-agent

- [ ] 覆盖四个固定内置 ID、文件冲突、首次检测后发送、跨页面保存、跨 Backend 继续讨论和无 AI 导入；确认各公开面沿用 backend/backends。
- [ ] 单独完成默认 Codex App Server 兼容回归，验证原路径、模型、共享登录、主动登录及取消、源文讨论和资源释放。
- [ ] 汇总 DSH 和第二个真实 ACP CLI 的平台、版本、往返及取消清理结果、两项耗时；区分协议替身与真机证据，明确失败及未实测预置。
