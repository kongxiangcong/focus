# 13 阅读页控制台字体 CSP 与 404

Status: needs-triage
Blocked by: —
Covers: spec §6，最终浏览器验证发现的范围外问题

## 目标
查明并修复真实阅读页控制台错误，保持现有安全策略意图。

## 现状（对照当前代码核实后的文件与行号）
- `tests/reading_attachment_browser.mjs:58` 保留控制台零错误断言；最终运行到此失败，其前面的几何、锚点、焦点和减少动效断言已通过。
- `host/server.py:117` 主阅读页 CSP 未设置 font-src，data: 字体被 default-src 'self' 拦截。浏览器还报告两个 404，现有日志未包含资源 URL，不能推断是哪一资源。
- 尚未确认此现象相对基线是否新增；没有将其宣称为既有故障。

## 实施步骤
1. 维护者分诊后，在隔离 Host 中记录失败请求 URL 并与基线对照。
2. 优先评估字体独立静态资源部署，或在明确需要时审查最小 CSP 调整；分别定位 404。
3. 保留原控制台断言，复跑吸附脚本及视口矩阵。

## 验收标准
- 原脚本退出码为 0，控制台错误数组为空。
- 字体和相关资源返回 200，CSP 仍限制未授权资源。

## 测试
`FOCUS_BROWSER_LEGACY_INTRO=1 FOCUS_BROWSER_SCRIPT=tests/reading_attachment_browser.mjs ... .venv/bin/python .scratch/reader-usability-audit/validation/run_fixture.py`：FAIL；完整环境见 validation/environment.md。

## Comments
- 2026-10-21：仅记录证据，未修改安全策略或过滤错误。日志 `evidence/logs/focus-final-reading_attachment_browser.log`，截图 `evidence/final-reading_attachment_browser/`。此问题使03最终门禁未通过，等待分诊；不在03中顺手扩大修复范围。
