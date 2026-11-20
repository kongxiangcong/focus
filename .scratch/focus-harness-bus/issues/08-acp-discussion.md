# 08: 从工作台完成一轮 ACP 源文讨论

**What to build:** 兼容的 ACP 程序经同一驱动参与正式源文讨论并调用 Host 工具。

**Blocked by:** 01 用标准 Manifest 运行现有 Codex

**Status:** resolved

- [x] 经 stdio JSON-RPC 完成握手、创建会话、选择模型、发送提示；流式更新和仅最终回复都正确呈现，保留活动和终态。
- [x] 协议替身通过实际工具桥读取绑定来源，分别覆盖 HTTP MCP 与经 stdio 代理访问 MCP；工具和写入权由 Host/Core 控制。
- [x] 连续两轮各自启动并回收进程、使用全新原生会话；原文、近期消息和已有摘要由 FOCUS 注入，切换执行者可继续同一讨论。

## Comments

ACP 讨论覆盖 HTTP／stdio MCP 和全新会话，保留 FOCUS 讨论历史与摘要。 [验收记录](../acceptance.md)
