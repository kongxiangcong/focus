# Stage 6B 已确认实施票

Status: ready-for-agent

2026-09-26 用户确认原票 02、03、04 合并，其余范围同意。现已发布五张独立实施票；父 spec 保持原范围，未修改。所有票尚未实施。

| 票 | 交付 | 阻塞 |
| --- | --- | --- |
| [01 依赖、认证与双 Backend 连通检查](issues/01-backend-setup-connectivity.md) | 安装准备、共享 Codex 登录、DeepSeek 认证、Runtime 路径与真实连通检查 | 无 |
| [02 统一 Backend 的阅读准备、博客与讨论](issues/02-unified-ai-workflows.md) | Plan／全文准备、Blog Output、统一讨论／Notes／阅读推进，共用业务入口 | 01 |
| [03 设置刷新生效与跨 Backend 批次恢复](issues/03-refresh-batch-switch.md) | 设置保存与刷新、忙时保护、多页面一致、批次换 Backend 恢复 | 02 |
| [04 主页清除本篇讨论与笔记及日志保留](issues/04-clear-retention.md) | 主页确认清除、恢复副本与上下文失效、七天日志清理 | 02 |
| [05 双 Backend 的干净安装与完整业务验收](issues/05-release-evidence.md) | Windows 干净安装与两种 Backend 的全流程分层证据 | 03、04；阶段 5 稳定业务出口 |

## 执行顺序

01 → 02 → {03、04} → 05。03、04 只依赖 02，不因编号人为增加彼此阻塞；实际修改共享模块时仍须协调。当前可开始的票只有 01，ready-for-agent 不表示可跳过依赖。

02 按用户要求合并，保留原三票全部 21 项验收标准，可按内部验收段推进，但必须全部完成才关闭。05 不用旧阶段证据替代本次 SDK 接入验收。

## 编号映射

原 01 → 01；原 02／03／04 → 02；原 05 → 03；原 06 → 04；原 07 → 05。drafts 下的文件仅作为已取代的审阅历史，不能再领取或执行。
