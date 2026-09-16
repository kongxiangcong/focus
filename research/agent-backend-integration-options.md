> 2026-09-17 更正：本文将国内 WorkBuddy 与 CodeBuddy SDK 混同，其“双后端已落地”结论不能用于国内 WorkBuddy。以 [后续官方核实](workbuddy-codex-agent-integration.md) 为准。原内容保留为历史调研记录。

# FOCUS 阅读界面的 Agent 后端接入评估（2026-09-16）

> 状态（2026-09-16）：本文的建议已落地。第 5–7 节的步骤 1–4 已实现为
> `host/backends/`（`base.py` 中立词汇、`codex.py`、`workbuddy.py`、注册表与
> `create_backend`），CLI 增加 `--backend`，见
> [ADR 0007](../docs/adr/0007-selectable-agent-backends.md) 与
> `docs/FOCUS_Web_Agent_Quickstart.md`。WorkBuddy 那条路尚未做真机 smoke：
> 本机没有桌面端之外的运行环境，SDK 只由 `tests/test_agent_backends.py` 里的假 SDK 驱动。
> 下文风险清单（daemon 端口争用、PyPI 不可用、认证、版本漂移、产品边界）仍然有效。

结论先行：**两条路都通，而且不必二选一。** FOCUS 的界面已经通过 `ReaderHost` 契约与后端彻底解耦
（ADR 0004），换 Agent 后端不需要动一行前端代码。真正要做的只有一件事：在 `host/` 里多一个 runtime adapter。

- **要接 WorkBuddy：有官方 SDK，直接可用。** Python 包 `codebuddy-agent-sdk`（PyPI `0.3.258`，Python ≥3.10，
  腾讯维护），FOCUS 的 Host 正好是 Python。工作量集中在一个新文件，界面零改动。
- **不要为了"改用 Codex SDK"去重写现有那条路。** FOCUS 现在用的就是官方 `openai-codex` 的 pinned runtime，
  并且是**刻意**绕开它的高层封装，因为动态工具/审批签名在 SDK 里还不稳定。换成高层 API 会丢掉 `focus` 动态工具，属于降级。

---

## 1. 界面侧的接入面：不用改

| 层 | 文件 | 作用 |
| --- | --- | --- |
| 契约 | `ui/packages/reader-contracts/src/index.ts` | `ReaderHost` 接口 + `ReadingWindow` 投影，明确不暴露 HTTP 路由、Workspace 路径、协议错误 |
| 适配 | `ui/apps/standalone/src/adapters/http-reader-host.ts` | HTTP + SSE，唯一的传输实现 |
| 服务 | `host/server.py` | `/reader/*` 路由、`/reader/events` SSE、上传、同源静态资源 |
| 编排 | `host/service.py` | 会话、审批、停止、快照；构造签名里已经有 `runtime_factory=AppServer` |
| 工具 | `host/core_bridge.py` | `focus` 动态工具的 15 个 action，Core 是阅读资产的唯一权威 |
| 运行时 | `host/runtime.py` | Codex App Server 的 stdio JSON-RPC 客户端（pin `0.154.0`） |

`service.py` 的 `runtime_factory` 参数就是为换后端预留的插槽。**所以"接入 focus 界面"= 在 `host/` 里加一个 runtime，
UI、`ReaderHost`、Core 都不动。**

## 2. WorkBuddy 有 SDK 吗：有，官方三套入口

### 2.1 官方 Agent SDK（推荐）

| 语言 | 包 | 要求 |
| --- | --- | --- |
| Python | `pip install codebuddy-agent-sdk` | Python ≥3.10（FOCUS Host 满足） |
| TypeScript | `npm install @tencent-ai/agent-sdk` | Node ≥18.20 |

认证三种：复用 CLI 已有登录 / `CODEBUDDY_API_KEY`（中国版须同时设 `CODEBUDDY_INTERNET_ENVIRONMENT=internal`）/
企业 OAuth Client Credentials（需旗舰版）。

关键能力（全部来自随 WorkBuddy 分发的官方文档）：

- `query(prompt, options)` 异步消息迭代器；`CodeBuddySDKClient` 用于长连接多轮对话
- **进程内自定义工具**：`create_sdk_mcp_server(name, tools=[@tool(...)])`，无需起独立 MCP 进程
- **`can_use_tool` 回调**：`PermissionResultAllow / PermissionResultDeny`，原生审批
- 流式：`receive_messages()` / `StreamEvent` / `include_partial_messages`
- 会话：`resume=<session_id>`、`ResultMessage.session_id`、`fork_session`、`persist_session`
- 中断：`interrupt()`；权限：`permission_mode`；工具白/黑名单：`allowed_tools` / `disallowed_tools`
- 系统提示：`system_prompt` / `AppendSystemPrompt`；Hook：8 类事件
- **环境隔离**：默认**不加载** settings / CODEBUDDY.md / MCP / 子代理 / 斜杠命令 / Rules / Skills，
  需要时用 `setting_sources` 显式打开 —— 正是产品化 Host 想要的干净环境

### 2.2 不装 SDK 也有三种无头入口

CLI（本机 `E:\Program Files\WorkBuddy\resources\app.asar.unpacked\cli\dist\codebuddy.js`，bin 名 `codebuddy`/`cbc`）：

| 方式 | 参数 | 特点 |
| --- | --- | --- |
| JSONL | `-p --output-format stream-json --input-format stream-json` | 最接近 FOCUS 现在手写协议的做法 |
| ACP | `--acp`（`--acp-transport stdio\|streamable-http`） | Zed 的开放协议，客户端可代理 `fs`/`terminal` |
| HTTP | `--serve --port --auth password\|none` | REST API + ACP over SSE + Web UI |

官方文档在本机可直接查阅：
`...\cli\dist\web-ui\docs\cn\cli\` 下的 `sdk.md`、`sdk-python.md`、`sdk-custom-tools.md`、`sdk-permissions.md`、
`sdk-hooks.md`、`acp.md`、`headless.md`、`http-api.md`。

## 3. Codex 那条路现在是什么状态

`host/runtime.py` 只做传输（94 行）；协议编排在 `service.py`：
`account/login/start`、`thread/start`、`thread/resume`、`turn/start`、`turn/completed`、
`item/commandExecution/requestApproval`、`item/fileChange/requestApproval`、
`item/permissions/requestApproval`、`turn/interrupt`。

官方 Codex 生态对照：

- TS `@openai/codex-sdk`（`0.128.0`）—— 只是包一层 CLI 的 JSONL，`startThread/resumeThread/run/runStreamed`
- Python `openai-codex` —— **直连 app-server 的 JSON-RPC**，并要求 Python ≥3.10

也就是说：**FOCUS 用的就是官方 Python 路线**，只是自己写协议客户端而不是用 `thread.run()` 便捷封装。
ADR 0006 与 Quickstart 里写明了原因：SDK 尚未稳定封装动态工具/审批签名。

## 4. 能力对照

| 能力 | FOCUS 现在（Codex App Server 手写） | WorkBuddy Agent SDK | Codex Python SDK 高层 API |
| --- | --- | --- | --- |
| `focus` 自定义工具 | ✅ 动态 `type=function`，需 `experimentalApi` | ✅ 进程内 MCP 工具（Decorator） | ❌ 未稳定暴露 → **会丢掉** |
| 审批回流 | ✅ 3 类审批 + `requestUserInput` 手动分派 | ✅ `can_use_tool` 一个回调 | ❌ 需绕开 |
| 流式输出 | ✅ 自己解析事件队列 | ✅ `receive_messages()` / `StreamEvent` | ✅ `runStreamed()` |
| 会话恢复 | ✅ `thread/resume` + host SQLite | ✅ `resume=<session_id>` | ✅ `resumeThread()` |
| 中断 | ✅ `turn/interrupt`，无响应则杀进程 | ✅ `interrupt()` | ✅ AbortSignal |
| 文件系统沙箱 | ✅ `workspace-write` + writable root | ⚠️ 无等价物；只能 `permission_mode`/`can_use_tool`/hooks/`--sandbox`(容器/E2B) | ✅ `Sandbox.*` 预设 |
| 配置隔离 | ✅ 由 Host 自己控制 | ✅ 默认全关，`setting_sources` 显式开 | ⚠️ 继承环境 |
| 模型来源 | OpenAI（需 ChatGPT 订阅或 API Key） | WorkBuddy/CodeBuddy 账号额度（含 deepseek / glm / kimi 等） | 同左 |

**最大差异是沙箱**：Codex 的 `workspace-write` 在 SDK 选项里找不到 1:1 等价物；
如果 FOCUS 需要 OS 级隔离，走 WorkBuddy 时要么用 `--sandbox container`，要么自己上容器。

## 5. 建议做法：加 adapter，别替换

1. 把 `service.py` 对 `AppServer` 的依赖抽成一个 `Runtime` 协议（`request / events / close`）。
   两条路都需要这一步，是纯重构，行为不变。
2. 新增 `host/runtime_workbuddy.py`，用 SDK 实现同一协议，例如：

```python
from codebuddy_agent_sdk import (
    CodeBuddySDKClient, CodeBuddyAgentOptions,
    create_sdk_mcp_server, tool,
    CanUseToolOptions, PermissionResultAllow, PermissionResultDeny,
)

@tool("focus", "FOCUS Core 操作入口", {"action": str, "arguments": str})
async def focus_tool(args):           # 直接复用 host/core_bridge.py 的 CoreBridge
    return core.tool(args["action"], args["arguments"])

def build_options(workspace, catalog, bridge):
    async def can_use_tool(name, input_data, options: CanUseToolOptions):
        # 映射到 ReaderAgentState.approvals：等待 /reader/approval 回传后返回
        decision = wait_for_user_approval(name, input_data)
        return PermissionResultAllow(updated_input=input_data) if decision else \
               PermissionResultDeny(message="用户拒绝")

    return CodeBuddyAgentOptions(
        cwd=str(workspace),
        can_use_tool=can_use_tool,
        mcp_servers={"focus": create_sdk_mcp_server("focus", tools=[focus_tool])},
        setting_sources=[],           # 默认就是干净环境，显式写出来避免误加载
        resume=saved_session_id,      # 替代 thread/resume
        extra_args={"network": None}, # 需要 MinerU 时放行网络
    )
```

3. CLI 增加 `--runtime codex|workbuddy` 开关（`host/__main__.py`）。
4. 用 `CodeBuddySDKClient` + `receive_messages()`，**不要用 `query()`**：
   FOCUS 是长驻 Host，`query()` 在首个 `ResultMessage` 处停止并自动禁用后台任务，
   收不到跨轮回推的后台完成事件。
5. 事件映射：`AssistantMessage` → `ReadingWindow.conversation`；`ToolUseBlock`/`ToolResultBlock` → 活动记录；
   `can_use_tool` → `ReaderAgentState.run.approvals`；`interrupt()` → `/reader/stop`；
   `ResultMessage.session_id` → host SQLite 里的会话键。

## 6. 落地前的实测风险（本机已验证）

1. **CLI 与桌面端抢 daemon 端口**。冒烟测试 `cbc -p "reply PONG"` 报
   `EADDRINUSE 127.0.0.1:55035`，该端口被 WorkBuddy Desktop 的进程占用，CLI 挂住无输出。
   → headless 部署请放在**没有桌面端**的机器/容器，或用 `codebuddy daemon` 显式管理。
2. **PyPI 在本机不可用**（代理返回拦截页），`pip install codebuddy-agent-sdk` 会失败。
   两个绕法：把 SDK 装到真正的 runtime 机器上；或完全不装 SDK，用 `CODEBUDDY_CODE_PATH`
   指向 CLI 走 `stream-json` / `--acp`。
3. **认证不要想当然**。SDK 复用 CLI 登录（`~/.codebuddy`）；本机该目录下只有 `diagnostics/` 和 `logs/`，
   没有凭据文件。正式部署要显式提供 `CODEBUDDY_API_KEY` + `CODEBUDDY_INTERNET_ENVIRONMENT`，或企业 OAuth。
4. **版本漂移**。SDK 处于 Preview，Custom Tools 更是 Preview；CLI 版本已到 2.1xx。
   照抄 ADR 0006 的做法：pin 版本 + 本地验收，不靠官网示例。
5. **产品边界**。把 WorkBuddy/CodeBuddy 的 CLI 或 SDK 嵌进 FOCUS 这类第三方产品、消耗账号额度，
   是否被允许需要跟腾讯侧确认 —— 这一条我无法替你判断。
6. **ACP 是备选而非首选**。协议最干净（`fs`/`terminal` 可代理、`loadSession` 重放历史、推送斜杠命令清单），
   但 Python 侧要自己写 ACP 客户端（数百行），只有在"坚决不装 SDK"时才划算。

## 7. 建议顺序

1. 抽 `Runtime` 协议（两条路都要，纯重构）
2. 用假 Runtime 跑通事件映射，保持现有测试全绿
3. 在无桌面端的环境做一次真实 smoke（`-p` 或 `SDKClient.query("PONG")`），确认认证与 daemon
4. 再决定默认后端：日常阅读走 WorkBuddy（省 API Key），需要强沙箱/强动态工具时切 Codex
