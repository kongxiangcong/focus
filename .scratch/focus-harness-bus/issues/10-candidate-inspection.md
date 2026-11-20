# 10: 显式候选检查使用当前 Backend

**What to build:** 保留独立候选检查入口，以当前 Backend 替代专属 Codex 命令；普通导入继续只使用解析器。

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

- [ ] 显式检查走现有 Backend 工厂，在只读、无业务工具且限时的环境执行；Host 校验结构化结果。无效输出或运行失败可见。
- [ ] 覆盖有效结果、无图、图片可用及不支持图片的配置；未观察图片时记录事实及原因。
- [ ] 验证超时和取消能释放资源。无 Backend 时普通导入仍成功，不触发探针或模型请求。
