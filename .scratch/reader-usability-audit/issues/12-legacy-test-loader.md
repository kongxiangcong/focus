# 12 Host 测试仍导入已删除 CLI

Status: needs-triage
Blocked by: —
Covers: spec §6，验证基础设施

## 目标
修复现有 Python 测试 fixture 对删除文件的导入。
## 现状
`tests/test_focus_read.py:26` 导入不存在的 `.agents/skills/focus-read/scripts/focus_read.py`；`tests/test_web_host.py:17` 依赖该模块。
## 实施步骤
独立审查旧 CLI 测试的保留范围，抽取可复用 workspace fixture；不在 UI 工单中顺手修复。
## 验收标准
规范 Python 命令可收集测试，旧断言仍有等效领域覆盖。
## 测试
`PYTHONPATH=tests:.agents .venv/bin/python -m unittest tests.test_web_host`：FAIL，FileNotFoundError。
## Comments
- 原样命令还需要 tests/.agents 导入路径。临时 browser runner 只省略无关 CLI 导入，保留 workspace fixture；不能将该兼容运行声称为规范原样命令通过。
