# Stage 6B / 03 — 设置刷新与跨 Backend 批次恢复

日期：2026-09-27；固定审查基线：`499b190`。本票完成，不代表 Stage 6B 整体发布验收完成。

## 实现

- 用户设置原子保存于 `%LOCALAPPDATA%/FOCUS/settings.json`（可用 `FOCUS_SETTINGS_FILE` 指定）；Knowledge Base 不保存 Backend 选择或凭据。设置文件仅保存配置和凭据文件引用，不复制凭据内容。
- Host 分开投影 saved/effective；保存不应用，启动新工作仍使用 effective。空闲网页初始化/Reload 应用 saved，运行中刷新只记录提示；结束后须再刷新。
- 同一 Host 锁协调保存、应用和各类 worker 准入；批次 reservation 覆盖等待 Application 锁、创建/控制到 worker 启动的窗口。
- 激活前按保存路径检查 Runtime 存在性，失败保持旧 effective 和 pending，并显示错误。不以路径存在性冒充认证或连通成功，不自动切换路径/服务。
- 右下角常驻差异提示；保存回 effective 时消失。所有 ReadingWindow 响应通过同一 revision 比较，防止保存、讨论、业务操作的迟到响应覆盖其他页面已经应用的配置。
- 阅读组件删除 Backend 快捷切换；旧 Host 切换接口明确拒绝。切换只使原生恢复键失效，FOCUS Discussion、资产与 Cursor 保留。

## 确定性 / Host / UI

- `03-configuration-tests.txt`：7 tests passed。真实 Core＋外部 Runtime/协议替身，覆盖保存后旧配置启动、跨 Backend 同一讨论、阅读/进度/单独博客/批次忙时门禁、取消后刷新、跨 Knowledge Base 设置、缺失指定 Runtime 拒绝、前三篇完成后停止/切换/显式恢复。
- 缺失 Runtime 预检用例先失败、实现后通过；UI 保存响应回退用例先失败、修复后通过。最终参数化覆盖保存与讨论两种迟到响应。
- `03-ui-full.txt`：62 tests passed；最终增加讨论响应回归后，`03-ui-final.txt` 中 WorkspaceApp 21 tests passed（其余套件未改变）。`03-typecheck.txt` 与 `03-build.txt` passed；build 保留现有大 chunk 提示。
- `03-python-full.txt`：356 tests，8 failures / 30 errors；与前置 02 的 `python-ticket02-final.txt` 逐个失败身份完全相同。见 [基线对比](03-baseline-comparison.json)。此后补充进度/单独博客门禁的定向 7 tests 全部通过。没有把既存失败写成全量通过。
- `git diff --check` passed。

## 真实 Runtime 与多页面浏览器

独立知识库/Host/设置位于本目录 `03-real/`；没有改写真实用户设置或业务库。材料为四份合成中文无图 HTML，实际本地解析与 Core 发布，Agent 生成使用真实服务。其目的为状态转换与恢复验收，不作为论文内容质量或 Stage 5 全样例验收。

当次 Runtime：DeepSeek Harness SDK/runtime `0.1.5rc1` / `deepseek-v4-flash`；最终成功 Codex `0.154.0` / `gpt-6-astra`。版本仅作证据。

1. 浏览器 A 保存 Codex，不刷新；上传四篇 HTML 并开始批次，实际 effective 仍为 DeepSeek。
2. 浏览器 B 打开设置、点击 Reload；运行继续，effective 保持 DeepSeek，显示“任务运行中，完成后请刷新以应用配置”，保存按钮禁用。A 同步相同提示。
3. 前两篇完成；第三篇首次返回非法 JSON 被拒绝，未发布非法博客。浏览器明确停止整批，只重试第三篇并成功，第四篇保持取消。前三篇完成后再次明确 stop，并保存 33 个已完成文件的 SHA-256。
4. 任务停止后 B 未自动切换；点击 Reload 才应用 Codex，A 的提示同步消失，批次仍暂停，刷新没有自动恢复。A 明确点击继续剩余工作。
5. Codex 默认本机路径 `C:\Users\72449\AppData\Roaming\npm\codex.CMD` 首次失败，错误为 Runtime/模型配置不兼容，系统没有回退。浏览器明确指定仓库 `.venv/Lib/site-packages/codex_cli_bin/bin/codex.exe`，保存、刷新后只重试第四篇。
6. 浏览器点击第四篇“取消此项”，待其显示已取消后再次明确重试；第四篇最终由 Codex 完成，整批 completed。前三篇 33 个文件哈希完全一致，第四篇已有适用性判断及其时间戳被复用。
7. B 保存 DeepSeek，A 立即显示常驻刷新提示；B 保存回当前 Codex＋相同 Runtime 路径，两个页面提示消失，没有执行刷新或启动新任务。

结构化结果：[停止后三篇快照](03-real/stopped-after-three.json)、[最终审计](03-real/final-audit.json)、[改回配置](03-real/reverted-settings.json)。浏览器原始操作/snapshot/截图留在本地 `03-browser/`；刷新提示截图已人工视觉检查。第一次非法 JSON、首次默认 Codex 路径失败、取消和显式重试分别保留为失败/恢复证据，没有伪装首次成功。

## Review

### Standards

原 1 项 P2：激活前缺少 Runtime 前置条件检查。已修复并补红→绿公共 Host 回归。最终复审 0 项未解决发现。

### Spec

原 1 项 P2：迟到视图响应可覆盖多页面新配置。保存、讨论、业务操作和订阅已统一 revision 接收，保存/讨论两类响应回归通过。最终复审 0 项未解决发现。

仅提交本票 Host/UI/契约/测试和精简证据。原有 Core、Stage 4/5、DSH 与需求文档改动保留在工作区。
