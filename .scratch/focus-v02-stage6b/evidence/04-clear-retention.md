# Stage 6B / 04 — 清除与日志验收

日期：2026-09-27。实现基线：`9fc4f58964b3a01777a8ef642d099e5d800961d6`。本票不替代票 05 发布验收。

## 实现

- 仅知识库 Bundle 卡片提供“清除讨论与笔记”，确认框列出不可撤销的删除范围与保留项。阅读页移除单条 Notes 删除按钮，保留编辑与普通撤销。
- Host 共享准入锁检查讨论、阅读准备、博客、进度 worker 及批次/入库调度；UI 直接投影 Host 的忙状态。Source 清除不会取消在途任务。
- 先持久化清除意图，再由 Core 事务删除全部 Notes/恢复槽并撤销旧请求，最后事务清理 Host 全部讨论、摘要、请求正文、会话归档和相关执行日志。失败不返回成功；后续操作/重启收敛。幂等回执防止重试扩大范围。
- 讨论绑定 Core 清除代次；旧候选失去提交资格。原生上下文键失效，新讨论只从现存 FOCUS 上下文建立。
- 终态详细日志单独保存，从终态起七天到期；启动、公开读取及每小时自动清理。崩溃恢复的 interrupted 任务及既有终态任务也迁入该保留规则。讨论全文不按日志规则到期；业务状态、必要回执及 Runtime 生命周期回执保留。

## 公共边界与浏览器

- 8 个新增 Host 测试通过：取消确认、Source 隔离、全部 Notes/恢复副本清除、旧请求拒绝、重复请求不删除新内容、并发开始/清除、部分 SQLite 持久化失败及重启收敛、Plan/Cursor/Progress 保留、七天边界与下一任务、真实子进程崩溃后日志保留。
- 16 个 Stage 6B workflow tests 通过；UI 64 tests、TypeScript typecheck、生产 build 通过。仓库边界检查 7 tests 通过。
- 使用 kimi-webbridge 在隔离知识库副本、真实 Host 8774 实际操作：阅读页无 Notes 删除/整篇清除按钮；主页唯一入口；确认文案；取消后 3 条 Notes、3 条消息不变；确认后均为 0。
- 清除后仍显示第 2/3 段、1 条 Reading Progress Entry；23 个来源 Bundle、Plan/译文与博客文件哈希不变。state.json 因再次打开阅读新增幂等请求回执，未声称整文件哈希不变；Cursor 保持 chunk-002。
- 真实 Codex 运行期间，主页清除按钮 disabled=true；直接 HTTP 清除得到 400，提示活动任务拒绝。Host 重启后旧 Notes/讨论未复活，后续新讨论仍可用。
- 本次复用了已有合成阅读/博客资产作为删除保留对象，不把这些旧产物算作本次新生成验收。浏览器截图保留在本地 `04-reading-after.png`。

## 真实 Runtime 与原生记录

当次 Codex CLI/SDK 0.154.0，模型 gpt-6-astra；DeepSeek SDK/runtime 0.1.5rc1，模型 deepseek-v4-flash。版本仅为证据。

- Codex 浏览器新保存一条 Notes，清除后新请求完成，Notes 仍为 0，前后 nativeSessionId 不同。
- DeepSeek 真实 Host 操作：完成显式 Notes（1）、清除（Notes 0 / messages 0）、新讨论完成（Notes 0 / messages 2），前后 nativeSessionId 不同。
- 停止：收到各自 terminal_event。释放：Codex process_closed；DeepSeek sdk_close_returned。归档：not_requested。SDK 原生永久删除：not_verified。
- Codex 使用 ephemeral_requested；DeepSeek 使用独立临时 home，关闭后该受管临时目录已移除。临时目录移除不等同 SDK 永久删除证明；没有遍历或清理个人无关日志。
- 原生归档/删除没有声明通过，也不是本票清除 FOCUS 讨论的恢复来源；两种适配器的新讨论均不复用旧原生上下文。

## Standards

最终无文档标准违反或未解决正确性发现。已修复清理回执写入失败可能卡住 close 的问题；保留一个可选低优先级建议：后续可整理 UI 确认框重复 action 分支。

## Spec

最终无剩余功能发现。已修复“下一任务覆盖上一任务详细日志”及“崩溃恢复任务未进入七天保留”两项问题。

Standards：0 项必须修复、1 项可选低优先级建议；Spec：0 项剩余发现。

## 全量回归

最终全量 `04-python-final.txt`：366 tests / 8 failures / 32 errors。与票 03 留存的全量报告相比，原 38 项失败身份仍在；另外两项见 `04-regression-comparison.json`。其中 `state.json` Windows PermissionError 仅出现于最终全量，单独重跑全部 8 个 Reading Progress tests 通过；未将这一间歇失败声称为已修复。初轮发现新增测试文案触发旧领域禁词检查，已修正并通过检查；另有旧 test_replan_preserves_previous_assets 引用已不存在的 host.service.check_backend。已直接载入起始 HEAD 的 Host 模块确认该符号原本就不存在，且该测试原本就存在；未修改这项既存测试或添加兼容层。

所有用户原有未提交修改保留，只提交本票文件。

紧凑证据：`04-native.json`、`04-codex-native.json`、`04-browser-cancel.json`、`04-browser-after.json`、`04-browser-busy.json`、`04-browser-restart.json`、`04-preexisting-test.json`、`04-regression-comparison.json`。详细运行日志与截图留在本地 evidence 目录。
