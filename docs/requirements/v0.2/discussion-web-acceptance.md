# 讨论联网补充验收（2026-10-08）

基线：`76b4b9e3ead657ca77dc84850ee659036b7455f3`（main）。需求及范围见 [ADR 0022](../../adr/0022-source-discussion-web-evidence.md)。

## 已验证

- Codex 原生 App Server 0.161.0 实际启动并读取生效配置：`web_search=live`，`shell_tool=false`。协议测试验证只有 discussion 启用实时搜索，其他任务保持禁用；只读沙箱、无审批、来源工具范围保留。
- DeepSeek Harness SDK / Runtime 0.1.5rc1 实际启动。在本地 HTTP 模型端点夹具下，模型实际看到绑定原文工具、交互工具、`web_search` 与 `web_fetch`；没有 shell、任意文件读写或执行工具。原生搜索提供方实际调用独立 Messages 路径，返回可引用 URL；原生页面读取拒绝私网地址，错误回到模型。搜索／读取活动正确投影为开始、完成／失败。非 discussion 任务实际工具目录不含 web 工具。
- `FOCUS_TEST_REAL_DEEPSEEK_RUNTIME=1 python -m unittest discover -s tests -p 'test_discussion_web.py' -q`：3 项通过，其中原生 Runtime 用例验证四类任务。
- `test_source_discussion.py`：7 项通过，验证来源隔离、显式笔记与取消等 Core 约束。`test_backend_setup.py`：11 项执行，1 项平台限定跳过，其余通过。
- `pnpm reader:typecheck`、`pnpm reader:test`、`pnpm reader:build`：通过，前端共 127 项测试通过。构建仍有现有大包提示。
- `git diff --check` 与修改的 Python 文件编译检查：通过。

## 验证边界

原生 DeepSeek 测试替换的是两个模型 HTTP 端点，Runtime、工具注册、搜索提供方解析、页面读取保护和事件处理均真实运行。没有使用真实账号调用公网搜索，没有将夹具回答视为模型质量验收；Codex 验证实际生效配置与协议边界，未执行真实模型搜索。联网时的回答质量、引用完整性与服务可达性仍取决于运行环境和实际模型。

全量 Python 测试另与未修改的 main 对照执行；该基线已有阅读游标投影、旧 Host 行为断言、博客及仓库边界等失败，不能声称全量测试全绿。基线工作树的项目复制测试还受 `.git` 为文件的工作树布局影响。本次范围不修改这些既有问题。

全量结果：修改后 449 项执行，12 failure / 30 error / 5 skip；未修改 main 446 项执行，12 failure / 31 error / 4 skip。逐项比较失败身份，本次没有新增失败；基线独有的一项是工作树布局影响的项目复制测试。
