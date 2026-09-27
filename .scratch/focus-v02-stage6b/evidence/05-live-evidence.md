# Stage 6B / 05 — 当前环境真实验收（部分通过）

日期：2026-09-27。用户明确取消干净环境和首次登录测试。本轮使用当前 Windows x64、已有认证、新建隔离知识库；无需用户提供虚拟机或重新登录。票 05 保持未完成。

## 环境与边界

- 真实启动版本：所选 Codex `0.154.0`、DeepSeek Runtime `0.1.5-rc.1`，模型分别为 `gpt-6-astra`、`deepseek-v4-flash`。浏览器从设置页执行依赖准备和最小连通检查，复用已有 Codex 登录，实际连通成功。
- 显式选择 PATH 上的 Codex `0.130.0` 后实际启动失败，显示 Runtime／模型配置不兼容，未按版本号提前拒绝，未静默改回路径或服务。[版本](05-live/runtime-versions.json)、[非固定版本结果](05-live/nonpinned-runtime-check.json)。无 Linux 实测。
- 输入复用阶段 5 的原始 PDF、带图中文 HTML、无图英文 HTML，以及缺嵌入图片的损坏样例，但在两个新知识库中重新解析、发布与生成；PDF 使用真实 MinerU。输入来源为仓库内 `.scratch/focus-v02-stage5/live-20260926/inputs/`，没有复用旧 Blog/Plan。
- 首轮记录的 14 个原有修改保持原样；本次工作区证据仍包含这些未提交修复，不宣称只检出原 HEAD 能复现。新产物和原始浏览器记录留在本地 `05-live/`，不提交大篇正文、凭据或 Runtime 原始会话。

## 真实业务结果

| 来源 | Codex | DeepSeek |
| --- | --- | --- |
| Attention Is All You Need PDF | 新 Bundle、Blog、HTML；整篇问答及显式 Note；Plan 与 26/26 段全文准备通过 | 新 Bundle、Blog、HTML；整篇问答；Note 部分保存但出现请求 ID 冲突；全文 context 成功，Plan 失败 |
| 中文带图芯片文章 | 新 Bundle、Blog、ValueAnalysis、HTML；整篇问答及显式 Note；5/5 段准备；浏览器精读提问、Continue 到 chunk-002、进度记录 saved，Note 保留 | 新 Bundle、Blog、ValueAnalysis、HTML；整篇问答、显式 Note、5/5 段准备；浏览器精读提问、Continue 到 chunk-002、进度记录 saved，Note 保留 |
| Functional Programming HOWTO 无图英文文章 | 新 Bundle、Blog、HTML；阅读准备在 context 阶段显式取消，未计通过 | 新 Bundle、Blog、HTML；context 完成，Plan 失败，未进入翻译 |
| 缺图片 HTML | `article_image_missing`，后续有效项继续成功 | `article_image_missing`，后续有效项继续成功 |

两组批次均是 partial，因为损坏样例被拒绝；每组 3 个有效项全部 completed。PDF 和编程 HOWTO 的 ValueAnalysis 判定不适用；芯片文章适用。ValueAnalysis 保留 `paper_reading`、未取得原论文／目标源码、未运行实验／实现检索受限等 warning；这些是内容边界，不升格为论文结论或性能验证。

整篇 QA 本身不保存笔记或推进 Cursor。显式“记下来”后保存；DeepSeek PDF 的一次请求尝试保存两条 Note，第一条落盘，第二条因相同请求 ID 的不同内容被拒绝，UI 显示未保存／可重试。不能把这次操作算完整 Notes 验收通过。带图文章改为一个明确合并 Note 的请求，两 Backend 均显示已记下。

## 已修复：DeepSeek 候选输出截断

真实 PDF context 在原 `max_tokens=16000` 下 61.10 秒返回 `max-tokens`，响应 11,916 字符；不完整输出被拒绝，但原错误只有通用 Runtime 失败。仅提高候选用途额度至 65,536 后，相同源范围的真实调用 106.95 秒完成，返回 42,196 字符的完整 context。没有修改 Core 校验、手写候选或代为发布。

- `candidate` 使用 65,536；连通检查仍 64，讨论仍 16,000。
- 截断终态映射为“生成达到 Runtime 输出长度上限，结果未完成，请显式重试”，不输出供应商原始错误或秘密。
- 公共 Host 回归先红后绿：即使截断响应恰好是合法 JSON，也不得发布准备成果或推进 Cursor。
- 修复后重启 DeepSeek Host，再通过浏览器显式重试 PDF 和无图 Blog，均完成。重启前 39 个已有 Bundle/Blog 文件哈希在重启后不变。
- [真实 context 失败](05-live/deepseek-context-before.json)、[修复后成功](05-live/deepseek-context-diagnostic.json)。诊断脚本只调用候选 Runtime，不写 Core 产物。

## 尚未通过与未测

1. DeepSeek PDF Plan 经内置三次候选／反馈仍失败：`Reading Chunk section path is not anchored to source headings`。[只读真实重现](05-live/plan-failure.json)定位到第 24 段 `[319,327]`：模型生成 `['Attention Is All You Need','Attention Visualizations']`，该位置合法继承路径为 `['Attention Is All You Need','References']`。非 Markdown 的可视化标题不能当新章节。Core 正确拒绝，未发布无效 Plan。
2. DeepSeek 无图英文 Plan 失败：`Only reference lists may be excluded`。未放宽排除范围校验，也未手工补 Plan。
3. DeepSeek PDF 多 Note 的请求 ID 冲突需修复／复验。Codex 无图阅读准备已显式取消；其后续翻译、QA/Notes、阅读推进未测。
4. PDF 和无图文章的完整精读／推进、两个 Backend 的 Topic／Source 管理、真实整批停止与换 Backend 恢复、设置改回／忙时刷新／多页面同步、清除讨论与笔记完整浏览器矩阵尚未完成。不能用 03/04 的旧浏览器证据填充本轮通过。
5. 取消、崩溃、迟到 attempt、越界、Source 隔离、结构／图片／引用、七天保留等仍按公共 Host/Core 测试层记录，不宣称真实外部网络／额度故障全部实测；原生 SDK 永久删除仍为 not_verified。

这些结果已足以判定本次完整发布门槛未通过。保留成果及失败终态，停止后续有费用的验收调用；修复上述真实失败后从保存的进度恢复。取消的环境／首次登录测试不会重新成为门槛。

## 自动化与复核

工作流定向回归 17 tests 通过；新增截断测试有红／绿日志。前端 typecheck 通过。最终 Python 全量 367 tests / 329.449 秒，8 failures / 31 errors，未通过；失败身份与首轮一致，没有新增失败。结果及日志哈希见 [回归汇总](05-live/regression-summary.json)；首轮 UI 64 tests 和 build 已通过，本次没有 UI 改动。

`05-live/audit_live.py` 只读两套本地 Host 的公开 API 和业务产物，写入本地证据快照；[紧凑汇总](05-live/final-summary.json)保留正式文件 SHA-256、Cursor、Note 数量、Progress ID/状态与原有 dirty 文件保护结果，不含讨论或笔记正文。执行前需使用该目录的 `server.py codex 8875` / `server.py deepseek 8876` 启动已有隔离知识库；它依赖本机保留的输入与产物，紧凑报告不能替代原始材料。原始快照和浏览器记录仅留本地。

## Review

### Standards

代码复审无新增问题；初审发现报告输入相对路径错误，已改为仓库相对路径。审计脚本明确只读业务资产、写本地证据；正文快照不提交，紧凑汇总移除进度主题和理解文本。

最终复核日志 SHA-256、39 个失败身份、两 Backend 的 Cursor/Notes/Progress 及原有 14 个文件哈希一致，0 项剩余 Standards 发现。

### Spec

初审指出 Codex 带图文章精读／推进缺覆盖说明；随后完成真实浏览器提问和 Continue，公共快照确认 chunk-002、Note 1、Progress saved，已补矩阵。两个 Plan 失败、Notes 冲突、剩余未测及全仓失败仍明确保留，本票未完成。

最终复核 0 项剩余报告发现；这只确认报告与证据一致，不构成完整发布验收通过。最终快照确认无运行中的讨论／准备任务后，已停止本轮两个隔离 Host 和观察脚本，并关闭本轮创建的四个浏览器标签。
