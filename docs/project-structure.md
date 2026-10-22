# 项目目录结构

本文说明仓库里每个目录的职责、哪些是生成物、以及从哪里开始读文档。运行方式见 [README](../README.md)。

## 运行时链路

```text
浏览器
  -> host/server.py            HTTP/SSE、静态 dist、访问口令
  -> host/service.py           HostService：任务、状态、单写者约束
  -> host/core_bridge.py       进程内调用确定性 Core
  -> .agents/core/             来源库、阅读计划、Cursor、笔记、讨论、入库
  -> host/backends/            Codex / DeepSeek Runtime 适配
```

前端是独立的 `ui/` 工作区：`reader-ui` 提供组件与样式，`standalone` 提供入口与 Host 适配器。构建产物落在 `ui/apps/standalone/dist/`，由 Host 直接托管。

## 源码目录

| 目录 | 职责 | 备注 |
|---|---|---|
| `host/` | 本地 Web Host、HTTP 服务、AI Backend 适配、工作区生命周期 | `python -m host --network` 启动 |
| `.agents/core/` | 确定性 Core：Source Library、Reading Plan、Cursor、Notes、Discussion、Ingestion、Blog | 不依赖 UI，也不读环境凭据 |
| `.agents/skills/` | 仍在使用的 Agent skill | `article-parser` 为解析入口；其余为设计/动效参考包 |
| `methods/` | 写作方法包 | `article-blog`（带读博客）+ 内置 KaTeX 资源；`source-discussion` |
| `ui/` | pnpm 工作区：`packages/reader-ui`、`packages/reader-contracts`、`apps/standalone` | 依赖方向固定为 Host → Adapter → ReaderHost → Reader UI |
| `integrations/` | DSH 插件（`dsh-focus`）与 Linux 启动脚本 | 可选集成，不属于网页主路径 |
| `tests/` | Python Core/Host 测试、浏览器验收脚本、`probes/` 探针 | 见“测试”一节 |
| `docs/` | 规范、ADR、设计与验收记录 | 入口见“文档入口” |
| `research/` | 选型与调研记录 | 历史材料，不是运行时配置 |
| `.scratch/` | 议题（issue）、spec 与本地验收证据 | 多数文件被忽略，只有评审过的文档入库 |

## 生成物与本地数据（不入库）

| 路径 | 内容 | 处理方式 |
|---|---|---|
| `knowledge-base/` | 用户阅读数据（来源、专题、笔记、讨论） | 唯一需要备份的数据；不要删除 |
| `workspace/` | 旧格式数据目录 | 新版本不读取，确认无用后可自行清理 |
| `ui/apps/standalone/dist/` | 前端构建产物，Host 的静态入口 | `pnpm reader:build` 生成；改前端后必须重新构建 |
| `tmp/` | 测试临时工作区（`tmp/test-runs/`） | 可随时清空，测试会自动重建 |
| `.scratch/` 未跟踪部分 | 本地截图、日志与运行证据 | 可清理；已跟踪的 101 个文件不受影响 |
| `.focus-runtime/` | 下载的 Runtime（Codex 等） | 删除后需重新准备，通常保留 |
| `.focus-host-*/` | 按工作区隔离的 Host 数据库 | 含讨论恢复信息，通常保留 |
| `.venv/`、`node_modules/` | 依赖 | 由部署步骤生成 |
| `external/` | 第三方参考仓库 | 可重新获取 |

## 测试

- Python：`python -m pytest tests`（需要 `.venv`；Core 与 Host 用真实模块，模型与 MinerU 用替身）。
- 前端：`pnpm reader:typecheck`、`pnpm reader:test`、`pnpm reader:build`。
- 浏览器验收脚本是 `tests/*_browser.py`（启动 Host 与 Chromium）与配套的 `*.mjs`（页面内步骤）。
- 结构约束由 `tests/test_repository_boundaries.py` 守护：不得入库凭据、私有工作区文件或已退役模式。

## 文档入口

| 想了解 | 从哪里开始 |
|---|---|
| 产品术语与业务契约 | [CONTEXT.md](../CONTEXT.md) |
| 需求主线 | [FOCUS_Shared_Workflow_MultiHost_Plan_v0.2.md](../FOCUS_Shared_Workflow_MultiHost_Plan_v0.2.md)、[docs/requirements](requirements/v0.2/README.md) |
| 已接受的决策 | [docs/adr](adr/) |
| UI 设计与验收 | [docs/design/README.md](design/README.md)（当前设计索引） |
| 开发调试 | [FOCUS_Debug_CLI.md](FOCUS_Debug_CLI.md) |
