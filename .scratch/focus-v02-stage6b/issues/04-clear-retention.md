# 04: 主页清除本篇讨论与笔记及日志保留

Status: done

2026-09-26 用户已确认拆票范围与依赖。本票实现、双轴审查及分层验收已完成。

**What to build:** 用户仅在知识库主页 Bundle 卡片确认清除本篇讨论与 Notes；清除不可撤销，后台详细日志按七天规则自动清理。

**Blocked by:** 02：统一 Backend 的阅读准备、博客与讨论。

- [x] 清除／删除 Notes 按钮仅在知识库主页 Bundle 卡片，阅读界面不出现；确认框准确列出删除、保留范围与不可撤销。
- [x] 该 Source 有活动任务时 UI 禁止且 Host 拒绝清除；并发开始与清除必须由业务资格守卫一致处理。
- [x] 清除 Source 全部讨论、派生摘要、Reading Notes 及恢复副本，失效关联 Runtime 上下文；单条编辑撤销不能恢复整篇已清除内容。
- [x] 保留 Source／Bundle、Plan、Cursor、Blog Output 和 Reading Progress Entries，其他 Source 不受影响。
- [x] 重复请求安全；部分持久化失败可见并可恢复到一致结果，不允许成功提示后旧讨论或原生会话使内容复活。
- [x] FOCUS 管理的详细后台日志终态后保留七天并自动清理；必要业务状态和提交回执保留，讨论历史不按此规则到期。
- [x] 停止、释放、归档与删除分别报告 SDK 原生记录证据；不把 close 算删除，不清理个人无关日志。
- [x] 用公开操作和可控时钟验证忙时拒绝、确认取消、删除范围、恢复副本、七天边界；浏览器实际验证唯一入口和清除后保留的阅读状态。

## Evidence

验收遵循父 spec 的最高公共测试边界。记录通过、失败、未测试及阻塞事实；不将替身证据提升为真实 Runtime 或浏览器通过。


## Comments

### 2026-09-27 — 完成

按父 spec 已确认的 Host 公共操作边界实现。8 个本票 Host 测试、16 个 workflow 测试、64 个 UI 测试及 typecheck/build 通过；真实双 Runtime 清除后重建上下文、浏览器唯一入口/确认取消/忙时拒绝/阅读状态保留已验证。

[完整分层证据](../evidence/04-clear-retention.md)。全量 Python 366 tests / 8 failures / 32 errors，未宣称全绿；旧 check_backend 测试问题与一次 Windows 文件访问间歇失败单独记录，后者 Reading Progress 8 tests 重跑通过。SDK 原生永久删除为未验证，归档为未请求，均与关闭/释放区分。

两轴 review 的正确性发现已修复；仅保留可选 UI 条件分支整理建议。用户原有未提交改动保留。票 05 发布验收仍待完成。
