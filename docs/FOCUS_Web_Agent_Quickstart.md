# FOCUS 网页 Agent：启动与本地验收

目标：浏览器操作已有 Reader；Python Host 管理官方 Codex App Server。
后台机器就是文件执行机器。`--workspace` 可指向本地或服务器目录；浏览器选择的
PDF/HTML 上传到该目录的 `uploads/`，不会把服务器路径映射成访问者电脑路径。

## 启动

要求 Python 3.10+、Node.js 20.19+ / 22.12+（推荐 24）、pnpm。
从仓库根目录执行，使用独立虚拟环境避免影响现有 Python：

```bash
python -m venv .venv
# Linux / WSL
source .venv/bin/activate
# PowerShell 改用：.\.venv\Scripts\Activate.ps1
python -m pip install -r host/requirements.txt
pnpm install --frozen-lockfile
pnpm reader:build
python -m host --check-runtime
python -m host --workspace ./workspace --network
```

打开 http://127.0.0.1:8765，输入后台打印的本机访问口令。
此后输入、文件选择、阅读、追问、审批、停止均在网页完成，不需要打开 Codex 交互界面。
`--network` 允许 Agent 的网络请求，供 MinerU 解析使用；不带时由 Codex 的网络/审批策略处理。
不支持沙箱的平台/系统配置应报错；Host 不自动降级成无沙箱执行。

固定依赖 `openai-codex==0.154.0`，随包 `openai-codex-cli-bin==0.154.0`。
Host 使用该包提供的可执行文件，通过 stdio JSON-RPC 直连 App Server，避免依赖 SDK
尚未稳定封装的动态工具/审批签名。`--codex-bin` 可指定已有的 **0.154.0** 二进制；
版本不匹配会在启动时拒绝。无需额外 `npm install -g codex`。

模型认证任选其一：

- 复用 **运行 Host 的操作系统用户**已有的 Codex 登录状态。
- 在该后台进程环境中设置 `OPENAI_API_KEY`；Host 通过官方 `account/login/start`
  建立 API-key 认证。该操作沿用运行时自身的凭据保存策略，可能更新该用户的 Codex 登录。

`FOCUS_MODEL` 可选；省略时沿用 Codex 配置，不强制模型名称。
新 PDF / HTML / URL 的解析需要 `MINERU_API_TOKEN`。直接导出到进程环境，或按现有
Parser 规则放在 **Workspace 工作目录**下被忽略的 `.env`。已有解析 Source 的阅读
不需要再次调用 MinerU。模型/Parser 凭据不要填进聊天或前端配置。

Linux / WSL 配置示例：

```bash
export FOCUS_MODEL='your-account-supported-model'
export MINERU_API_TOKEN='your-token'
# 如无已有登录，再设置 OPENAI_API_KEY
python -m host --workspace /home/me/focus-workspace --host-data /home/me/focus-host-data --network
```

PowerShell：

```powershell
$env:FOCUS_MODEL = 'your-account-supported-model'
$env:MINERU_API_TOKEN = 'your-token'
python -m host --workspace 'D:\Reading\workspace' --host-data 'D:\Reading\host-data' --network
```

`host/config.example.env` 仅为配置示例，**不会自动加载**。不要使用示例占位值运行真实调用。

默认聊天数据目录是 Workspace 同级的 `.focus-host-<路径标识>/`；包含会话数据库、
运行状态和上传引用。Codex thread 历史由运行时自己的 Codex home 保存。
恢复需保留 **Workspace、Host data 与该用户的 Codex home** 三者；仅复制 Workspace
只能恢复阅读资产，不能恢复聊天上下文。Host data 不允许放在 Workspace 内。
默认只监听 loopback；浏览器访问口令与模型认证互相独立。

## 网页操作

1. 空工作区：选择 PDF/HTML，输入“我要阅读这篇论文”。选择文件后点击发送才让
   Agent 执行解析。也可以输入文章 URL 或后台机器上 Workspace 内的文件路径。
2. 已有数据：用来源/Topic 下拉框开始，或输入 Source ID。复用既有 Plan，缺失时
   Agent 按 `focus-map` 规则生成草案，Core 校验并安装。选择 Topic 前补齐所需 Plan。
3. 普通追问不推进 Cursor。点击“继续阅读”，或发送“继续阅读”“下一段”“回到文章继续”
   时 Host 捕获 receipt、执行一次 Core Continue，再让 Agent 展示/翻译当前段。
   其他自然表达由 Agent 解释；若请求 Continue 工具，网页显示一次明确的推进确认。
   一个任务最多执行一次 Continue。“继续”只继续解释，不自动推进。
4. “把刚才的解释保存成一条 clarification Note”通过 Core 落盘。聊天仍留在宿主数据库。
5. 运行时审批显示本次命令/变更/权限；允许、拒绝或回答问题会回传同一个运行时请求。
   执行记录可展开查看命令输出和文件 diff（每项保留末尾 16 KB，最多 30 项）。
6. 刷新页面恢复已收到的全文回复及待审批状态。断线不取消任务；点击“停止任务”才
   发送 `turn/interrupt`，无响应时终止 App Server。已经落盘的文件不回滚。
7. 关闭 Host 后重启：未结束任务标记为 interrupted；下一次发送续用保存的 thread。
   如果该 thread 在运行时目录丢失，任务报错，不会悄悄清空上下文。

首次 Host 不包含通用 MCP 表单交互、多租户管理或浏览器内模型账号登录向导。
原生 Codex 命令、文件、权限审批和 `requestUserInput` 已接入；MCP elicitation 明确拒绝。
模型账号首次配置由运行后台的人完成，用户的日常阅读只需要网页。

## 本地验收（需要真实凭据）

先用专用工作区测试，按顺序确认：

| 操作 | 应观察到的证据 |
| --- | --- |
| 空目录启动，选择一份真实 PDF 并发送阅读需求 | MinerU 成功后 Source Bundle、固定 Plan、首段原文/图/译文出现；失败显示真实错误 |
| 选择已经解析的 Source | 复用 Plan，文件数和 plan_id 不变，不再次解析 |
| 问“这段机制怎么理解”，再说“继续” | 流式回复延续上下文；`state.json` 的 chunk 不变 |
| 点击继续阅读；双击；刷新 | 一次前进一个 Chunk；旧 Source/Plan/Chunk receipt 不能再次推进 |
| 说“记一条简短 clarification Note” | 对应 `records/<chunk>.json` 出现精简 Note，没有原始聊天 |
| 说“创建 experiments/demo.py，打印 1+1 并运行” | Workspace 实际文件、命令输出 2、执行记录与 diff；Cursor 不变 |
| 使用 `--approval-policy untrusted` 重启并发起需审批命令 | 网页显示审批；分别验证拒绝和本次允许；刷新仍可回答 |
| 运行稍长的前台任务，然后停止 | runtime turn 中断，UI 显示停止；核实子命令退出；不回滚已有文件 |
| 对话中刷新；关闭 Host 后重启 | 历史与阅读位置恢复；下一次问答继续同一 thread |
| 故意提供无效凭据、损坏 Source 或断开网络 | 显示失败，无 Fixture fallback，无成功伪装 |
| 尝试在 Workspace 之外写文件并拒绝升级审批 | 运行时阻止写入；Host 不自行扩大 writable roots |
| 两个 Host 同时绑定同一 Workspace | 第二个被文件锁拒绝；勿用 CLI 与 Host 同时写该 Workspace |

`workspace-write` 限制写入，不声称限制所有读取；0.154.0 生成的 schema 不包含官网
较新页面的 `readOnlyAccess` 字段。不同操作系统的沙箱需在本地验收。此实现按单个
可信用户设计，Core 资产与普通文件在同一 Workspace，模型通过协议约束只使用 Core
修改阅读资产；这不是恶意代码的租户隔离边界。

## 开发和已执行验证

```bash
python -m unittest discover -s tests -p test_web_host.py -v
python -m unittest discover -s tests -v
pnpm reader:typecheck
pnpm reader:test
pnpm reader:build
```

- 新增后台测试使用 **真实 Core + App Server 协议替身**，验证持久化、去重、审批、停止、
  HTTP/SSE、上传和路径检查；不能据此声称模型已接通。
- 前端测试覆盖无当前论文时输入/附件、流式更新、审批、停止和旧快照拒绝。
- 已安装官方 0.154.0 运行时，`--version`、schema 导出与 `initialize` 握手通过。
  本环境 `thread/start` 超时（包括隔离配置下的无模型请求探测）；诊断日志显示
  运行时启动同步插件时 DNS/网络请求失败。没有执行真实模型 turn，不能把握手通过当作会话接通。
- 类型检查、前端测试、生产构建通过。完整 Python 测试保留一个起始提交已有失败：
  `test_active_skill_surface_contains_only_five_public_skills` 假定只有五个 skill，
  但 c4e27fa 已含 12 个额外 UI/开发 skills；本次未删除它们或放宽该断言。
- 浏览器截图验收未完成：环境没有 Chromium，尝试下载超时；前端交互证据来自 jsdom 测试。
- 未调用付费模型 API、未做真实 MinerU 上传、未部署；上表真实链路由本地验收确认。

正式启动由 Python Host 同源提供已构建 UI；不依赖 Node 后端。视觉开发可显式设置
`VITE_FOCUS_READER_BASE_URL=fixture pnpm reader:dev`，只用合成数据。
真实模式不应把一个跨域 Vite 地址当作生产启动方式；使用 `pnpm reader:build` 后从 Host 打开。

## 协议来源（2026-09-16）

- [Codex SDK 官方文档](https://learn.chatgpt.com/docs/codex-sdk)
- [App Server 官方文档](https://learn.chatgpt.com/docs/app-server)
- 实施以固定二进制的 `codex app-server generate-json-schema --experimental --out <dir>`
  为准。例如 thread 的 sandbox 是 `workspace-write`，turn 的 policy 类型是 `workspaceWrite`。
  动态工具需要 `initialize.capabilities.experimentalApi=true` 和工具 `type=function`。
