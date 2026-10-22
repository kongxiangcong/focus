# 12 Host 测试仍导入已删除 CLI

Status: done（2026-10-22）

## 处理结果
- 删除 `focus-map` / `focus-read` 两个已退役 CLI 的残留引用，不再恢复脚本。
- 新增 `tests/reading_fixture.py`：只构建 Workspace 数据，不经过任何 CLI。
- 原 CLI 测试改为直接调用 `core.WorkspaceCore`：`tests/test_reading_core.py`、`tests/test_reading_plan.py`、`tests/test_reading_journey.py`、`tests/test_article_reading_journey.py`、`tests/test_prepared_reading.py`。
- 其余 10 个测试模块与两个浏览器脚本改用共享 fixture。
- 规范命令现在可以收集全部测试；原先受影响的 18 个模块从 67 failed / 121 passed 变为 58 failed / 130 passed，零回退（既有 58 项失败与本工单无关）。
Blocked by: —
Covers: spec §6，验证基础设施

## 目标
修复现有 Python 测试 fixture 对删除文件的导入。
## 现状（修复前）
`tests/test_focus_read.py:26` 导入不存在的 `.agents/skills/focus-read/scripts/focus_read.py`；`tests/test_web_host.py:17` 依赖该模块。
## 实施步骤
独立审查旧 CLI 测试的保留范围，抽取可复用 workspace fixture；不在 UI 工单中顺手修复。
## 验收标准
规范 Python 命令可收集测试，旧断言仍有等效领域覆盖。
## 测试
`PYTHONPATH=tests:.agents .venv/bin/python -m unittest tests.test_web_host`：FAIL，FileNotFoundError。
## Comments
- 原样命令还需要 tests/.agents 导入路径。临时 browser runner 只省略无关 CLI 导入，保留 workspace fixture；不能将该兼容运行声称为规范原样命令通过。

- 补充证据：临时省略废弃CLI加载后，旧Host/Core测试仍因legacy fixture没有provenance、已失效的提示词断言失败。基线9f183cd在独立worktree同样失败，当前与基线失败测试名称相同（一次旧异步附件场景另有超时）。建议在独立工单重建fixture与过期断言；本次不顺手修改。新直接笔记测试完全不依赖废弃CLI，可独立通过。
