# 12: 用第二个真实 CLI 验证 ACP 驱动复用

**What to build:** 用 agy 或 Cursor CLI 中的一个验证同一 ACP 驱动可复用。

**Blocked by:** 09 ACP 取消、确认过期与资源回收

**Status:** ready-for-agent

- [ ] 通过标准 Manifest 在正式工作台选择受测 CLI，完成阅读讨论、真实 read_range 往返、取消和资源释放。
- [ ] 记录具体 CLI、版本、平台、握手耗时与首段输出耗时，保留失败及未覆盖场景；未经真机验证的预置标为「未实测」。
- [ ] 验收使用通用驱动和 Host 工具桥；无需等待 DSH 迁移即可独立执行此票。
