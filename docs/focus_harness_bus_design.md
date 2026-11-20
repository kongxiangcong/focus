# Focus 多 Agent Harness 解耦总线需求与架构设计文档

**设计状态：已定稿（2026-11-20）。** Q1–Q24 已确认，作为首版实现与验收依据。运行时改造及 §3.10 真机验收待执行。

## 一、背景与现状分析

### 1.1 问题定义与业务诉求

Focus 当前以本地 Python HTTP Host（`host/server.py`）配合 React/TypeScript 阅读器前端，通过外部 Agent 运行时驱动文章导读、结构化分析、源文讨论与候选摄入校验。现有默认后端绑定 `codex cli`（并附带 `deepseek-harness-sdk` 作为第二选项），在实际部署与演进中暴露出三个核心痛点：

1. **运行环境与依赖过重**：`host/backend_setup.py` 在检查连通性或首次使用时会自动执行 `pip install openai-codex` 或 `pip install deepseek-harness-sdk`（附带 `pydantic>=2.12` 与内置运行时二进制），且强依赖特定版本的私有 RPC/SDK 形态。
2. **外部 Harness 无法按需接入**：用户本地若已安装并登录了 `agy cli`（Google Antigravity CLI）、`cursor cli`（Cursor Agent CLI）、`dsh cli`（DeepSeek Harness CLI）、`claude code` 或自研 CLI，无法通过启动参数或设置面板直接挂载使用。
3. **扩展成本高且易引入补丁债**：每新增一个后端都要同步修改配置白名单、服务层字段、安装探测逻辑、代理特判、CLI 启动参数与前端 TS 枚举，违背低耦合、少补丁的工程约束。

核心诉求是将 Focus 的 Agent 调用层演进为**类似总线的轻量 Adapter 架构**：Host 与阅读器完全不感知具体 Agent 实现，外部 Harness 可通过配置在启动时或设置面板按需注册、切换与接入。

### 1.2 Focus 代码库现状审计：执行面已抽象，控制面存在 7 处强绑定

通过对 Focus 仓库全仓源码的逐行审计，结论明确：**Focus 并非全链路强绑定 Codex，而是处于“数据/执行面已初步解耦、控制/配置面被二元枚举锁死”的半解耦状态。**

- **已具备良好地基的模块**：`host/backends/base.py` 已经定义了与传输层无关的统一事件词表（`session/opened`、`turn/started`、`message/delta`、`message/completed`、`activity`、`tool/call`、四类 `approval`/`user_input` 请求与 `turn/completed`）；`host/backends/tool_bridge.py` 已经实现了本地 Streamable HTTP MCP 服务端，用于将 Focus Host 独占的业务工具（`focus`、`focus_user_input`、`focus_confirm`）安全暴露给外部运行时。阅读器 UI 和 Core 状态机本身零 Codex 依赖。
- **阻碍解耦的 7 处强绑定断点**：

| 序号 | 耦合层级与涉及文件 | 现状实证（硬编码与强绑定点） | 对外部 Harness 接入的阻塞影响 |
| :--- | :--- | :--- | :--- |
| 1 | 配置校验与注册表<br>`host/configuration.py`<br>`host/backends/__init__.py` | `DEFAULT_MODELS` 仅含 `codex`/`deepseek`，`normalize()` 遇到其他名称直接抛出“请选择 Codex 或 DeepSeek”；`BACKENDS` 与 `check_backend()` 硬编码 `if adapter is CodexBackend / DeepSeekBackend`。 | 任何第三方或自定义 Harness 在配置持久化与启动预检阶段即被拒绝。 |
| 2 | 依赖安装、认证与探测<br>`host/backend_setup.py` | `prepare()` 隐式执行 `pip install openai-codex` 或 `deepseek-harness-sdk`；`login_operation()`、`account()`、`discover()` 硬编码 `codex app-server` 的 `account/login/start`、`model/list` RPC 与 `DEEPSEEK_BASE_URL/models` HTTP 探测。 | 强迫宿主机下载重型包，且无法兼容外部 CLI 自身的登录态与模型发现机制。 |
| 3 | 服务层参数与实例路由<br>`host/service.py` | 成员变量写死 `self.codex_bin`、`self.deepseek_bin`、`self.deepseek_credentials`；界面后端列表硬编码 `{'codex': 'Codex', 'deepseek': 'DeepSeek'}`；`_build_backend()` 按名称分支拼装参数。 | 每接入一个新 Harness 都要侵入 `HostService` 核心类增删字段和分支。 |
| 4 | 独立候选检查器<br>`host/codex_ingestion.py` | 完全绕过 `base.Backend`，直接 `subprocess.Popen([codex_bin, "exec", "--ephemeral", "--output-schema", ...])` 执行候选文档校验。 | 显式检查仍依赖 Codex。默认导入只调用解析器。 |
| 5 | CLI 入口与代理环境<br>`host/__main__.py`<br>`host/proxy.py` | 启动参数暴露专属 `--codex-bin` / `FOCUS_CODEX_BIN`；`proxy.py` 对 `backend == 'codex'` 特判剥离 `OPENAI_API_KEY` 与 `CODEX_API_KEY`。 | 启动接口不对称，环境清洗规则无法声明式配置。 |
| 6 | 前端契约与设置 UI<br>`ui/packages/reader-contracts/src/index.ts`<br>`ui/apps/standalone/src/BackendSetupPanel.tsx` | TS 联合类型写死 `backend: "codex" \| "deepseek"`；面板硬编码两个单选按钮及 `input.backend === "codex"` 时才渲染的 OAuth 登录按钮。 | 前端无法动态展示注册表中的新 Harness，也无法按能力差异渲染设置项。 |
| 7 | 传输层与重 SDK 绑定<br>`host/runtime.py`<br>`host/backends/deepseek.py` | `runtime.py` 将 stdio JSON-RPC 类写死为启动 `[*command, 'app-server']`；`deepseek.py` 强依赖 `deepseek-harness-sdk` Python 包及 Cordis YAML patch。 | 通用 JSON-RPC 传输能力被 Codex 私有化；接入 DSH 被迫引入重 Python 依赖。 |

### 1.3 外部多 Agent 调度方案调研与取舍

对比 2026 年主流多 Agent 调度层与协议标准，不同路线的定位与工程代价差异显著：

| 参考方案 | 架构定位 | 工具与权限桥接 | 运行环境重量 | 实证教训与对 Focus 的适配度 |
| :--- | :--- | :--- | :--- | :--- |
| [Tencent/LoopForge](https://github.com/Tencent/LoopForge) | 自托管团队交付平台（Go + MySQL + Docker），内置 10 种 CLI 的 `command_binding` 胶水层与私有 HOME 隔离 | 平台统一 MCP 工具网关 + 人工审批门禁 | 重（需 Docker daemon、MySQL、镜像内置或首用 npm 安装 CLI） | 其“按角色/会话选执行器”思路值得借鉴，但每 CLI 维护独立胶水代码已引发维护割裂（如 [Issue #899](https://github.com/Tencent/LoopForge/issues/899) 中旧执行器独立列与统一 `agentCliCredentials` 脱节，[Issue #897](https://github.com/Tencent/LoopForge/issues/897) 中私有 HOME 切断本机 Bearer 鉴权）。**不适合 Focus 直接照搬。** |
| [Agent Client Protocol (ACP)](https://agentclientprotocol.com/protocol/v2/transports) | 开放标准 JSON-RPC 2.0 协议（stdio / Streamable HTTP / WebSocket），编码 Agent 领域的“LSP” | [`session/new`](https://agentclientprotocol.com/protocol/v2/session-setup) 原生透传 `mcpServers`（stdio/HTTP）+ `session/request_permission` | 极轻（标准库直写或使用仅依赖 `pydantic` 的官方 [Python SDK](https://pypi.org/project/agent-client-protocol/)） | **最契合 Focus**。截至 2026 年，目标 CLI 中 `dsh`、`agy`、`cursor`、`codex` 及 `claude code`、`kiro`、`copilot` 均已原生或官方支持 ACP。 |
| [OpenClaw Agent Harness](https://docs.openclaw.ai/plugins/sdk-agent-harness) | 插件化 Harness SDK，严格划分宿主核心所有权（Core Ownership）与单轮执行器边界 | 宿主独占工具策略与审批权，Harness 仅负责单轮执行与原生会话映射 | 中（TS 插件体系 + Gateway 守护进程） | **核心借鉴边界设计**：Focus Host 必须继续独占知识库写入、审批与主状态，外部 Harness 仅作受控执行器。 |
| [Dagu Harness](https://docs.dagu.sh/step-types/harness/) | 声明式双轨执行器（同一套配置 Schema 支持 [`protocol: acp`](https://docs.dagu.sh/step-types/harness/acp) 与 `protocol: cli`） | ACP 权限策略声明 + CLI 标志模板化映射 | 轻（单二进制，零强绑容器） | **借鉴配置模型**：通过声明式 Manifest 描述外部 CLI，允许用户注册独立配置。 |

### 1.4 本次设计的目标与非目标

**目标（Goals）**：
1. **彻底解除二元硬编码**：Focus Host、配置层、启动参数与前端设置页不再出现 `codex` / `deepseek` 专属分支，支持启动期（`--backend`）与运行期（设置面板）按需选择和切换。
2. **协议总线化、零重 SDK 依赖**：以 **ACP（stdio JSON-RPC）作为默认主总线**，复用现有 `ToolBridge`（Streamable HTTP MCP）统一注入 Focus 业务工具，移除强制 `pip install` 重依赖路径。
3. **外部 Harness 零代码接入**：用户只需在配置目录新增一份 JSON Manifest（指定协议、命令、参数、环境清洗与能力声明），即可接入 `agy`、`cursor`、`dsh`、`codex`、`claude` 或使用受支持驱动且可调用 `focus(action="read_range")` 的自定义 CLI。
4. **向后兼容现有核心体验**：保持 `base.Backend` 事件模型、阅读器交互流与知识库写入安全边界不变，支持平滑分阶段迁移。

**非目标（Non-Goals）**：
1. 不在 Focus 内构建 Docker 容器沙箱、多租户工作流引擎（DAG/SOP 编排）或服务端账号/计费系统（避免滑向 LoopForge 的重平台复杂度）。
2. 不在 Focus 内包办各家 CLI 的二进制下载、自动更新或私有 OAuth 浏览器登录流；默认复用用户本机已安装的 CLI 与登录凭据。
3. 不在单次 Turn 执行中途做跨 Harness 热切换（遵循 OpenClaw 边界，切换仅在空闲态/新 Turn 生效）。

---

## 二、整体架构与核心方案设计

设置页每条独立配置称为 **Backend**。每个 CLI 默认展示一个条目，用户显式注册第二种接入方式时才以不同名称并列展示。Harness（外部执行运行时）与 Driver（FOCUS 与运行时通信的方式）仅用于内部架构。

所有 Backend 统一承诺取消时终止执行、结束时释放资源并清理临时隔离环境。外部 Harness 管理原生日志。DSH 经 ACP 实测跑通阅读讨论、工具回调与取消后直接替换 SDK；不保留双路径、原生 Session 归档或启动归档重试。见 [ADR 0014 修订](adr/0014-archive-dsh-attempt-sessions.md) 和 [ADR 0021 修订](adr/0021-simple-backend-setup-and-apply.md)。

### 2.1 分层总线架构

保留 Focus 现有的 `HostService` 业务调度与 `base.Backend` 事件词表，将底层重构为**控制面注册表 + 工具面 MCP 桥 + 协议驱动**的四层轻量总线：

1. **业务与状态层（Host & UI）**：`HostService`、`CandidateTurns`、`AgentReadingRuntime`、`AgentBlogRuntime` 及前端 `BackendSetupPanel`。只消费 `HarnessRegistry` 暴露的元数据与 `Backend` 抽象实例，不感知任何具体 CLI。
2. **总线控制面（Harness Bus）**：
   - `HarnessRegistry`：加载内置预置 Manifest 与用户自定义 Manifest（`<settings-dir>/backends/*.json`），提供列表查询、配置校验与实例构造。
3. **统一工具与权限平面（ToolBridge MCP）**：继续由 Focus Host 独占，通过本地 `127.0.0.1` 随机端口 + 一次性随机 Token 的 Streamable HTTP MCP 暴露 `focus`、`focus_user_input`、`focus_confirm` 等业务工具，所有写操作与人工审批均回流至 Host 裁决。
4. **协议驱动层（Drivers）**：
   - **主轨道 `acp`（`AcpBackend`）**：标准 ACP JSON-RPC 2.0 客户端（stdio 优先，预留 Streamable HTTP），一套代码覆盖 `dsh --profile acp`、`agy acp`、`agent acp`（Cursor）、`codex-acp`、`claude-code-acp` 等所有 ACP Harness。
   - **Codex 迁移驱动**：内置 `codex.json` 以标准 Manifest 注册现有 `codex-app-server`。迁移保留原有标识、路径与模型，无需安装 `codex-acp`。只有用户显式注册时才展示独立的「Codex（ACP）」条目。

### 2.2 声明式 Harness Manifest 契约

参考 Dagu 的声明式定义与 LoopForge 统一凭证模型的经验，所有内置与外部 Harness 共享同一套 Manifest Schema（支持从内置目录 `host/backends/manifests/` 加载，并允许 `<settings-dir>/backends/<id>.json` 新增独立条目）：

```json
{
  "id": "deepseek",
  "label": "DeepSeek Harness (ACP)",
  "driver": "acp",
  "command": ["dsh", "--profile", "acp"],
  "binaryHint": "dsh",
  "env": {},
  "envStrip": [],
  "credentialEnv": ["DEEPSEEK_API_KEY"],
  "defaultModel": "deepseek-v4-flash",
  "capabilities": {
    "mcpTransport": "streamable-http",
    "streaming": true,
    "structuredOutput": "prompt-json",
    "modelDiscovery": "acp-config-option",
    "authMode": "external-cli"
  },
  "acp": {
    "permissionPolicy": "forward-to-host"
  }
}
```

关键字段约束：
- 内置 Backend ID 保留。自定义接法使用独立 ID；设置页指出重复 ID 的冲突文件，内置项继续可用。指定已有程序的安装位置使用 `runtimePath`。
- `driver`：枚举值 `"acp" | "codex-app-server"`，决定底层驱动实现，严禁按 `id` 写业务分支。
- `command` & `binaryHint`：支持用户通过设置页的 `runtimePath` 仅覆盖 `command[0]`，其余子命令参数（如 `["--profile", "acp"]` 或 `["acp"]`）由 Manifest 保持不变。
- `env` & `envStrip`：替代 `proxy.py` 中的 `if backend == 'codex'` 特判，将环境变量注入（如 Antigravity 的 `AGY_CLI_DISABLE_AUTO_UPDATE=true`）与剥离（如 Codex 强制登录态时剥离 `OPENAI_API_KEY`）完全声明化。
- `credentialEnv`：沿用已保存的 `credentialFile` 路径。Manifest 只声明所需环境变量名；启动子进程时按声明从指定文件读取并注入。文件缺失或缺少所需键时提示修正路径或改用外部 CLI 认证。密钥值不写入设置、Manifest 或检测回执，服务层按相同规则处理各 Backend。
- `capabilities`：声明驱动可提供的能力；生效资格仍须通过配置检测。例如 `authMode` 为 `"external-cli"` 时，前端只展示“本机 CLI 认证状态检测”和引导文案，不再硬编码 Codex OAuth 按钮；`modelDiscovery` 决定“加载模型清单”按钮是否启用及如何获取模型列表。

### 2.3 协议驱动事件映射规范

#### 主轨道：ACP 协议到 Focus `base.Backend` 的精确映射

| Focus `base.Backend` 生命周期 / 事件 | ACP v1/v2 JSON-RPC 对应方法与行为 | 说明与容错策略 |
| :--- | :--- | :--- |
| `open_session(resume_key, instructions)` | `initialize` →`session/new`（携带 `cwd` 与 `mcpServers`）→ 可选 `session/set_config_option`（设置 `model`） | `mcpServers` 直接挂载 Focus `ToolBridge` 的 Streamable HTTP URL（若某 Harness 仅声明支持 stdio MCP，则由轻量 stdio-to-HTTP 代理脚本桥接）。 |
| `start_turn(prompt, skills)` | `session/prompt`（传入文本块、图片附件与系统指令前缀） | 异步在后台线程等待 `session/prompt` 结算；将 `stopReason` 映射为 `turn/completed`。 |
| `message/delta` / `message/completed` | `session/update`（`agent_message_chunk` / 已提交消息块） | 若运行时仅发最终提交块（如 [`@deepseek-ai/dsh-acp`](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/acp/acp/README.md) 仅发 committed 更新），自动发出 `message/completed` 保持前端兼容。 |
| `activity` | `session/update`（`agent_thought_chunk`、`tool_call`、`tool_call_update`） | 仅投影工具名、状态与截断摘要，不向前端泄露敏感正文。 |
| `tool/call` | 由 `ToolBridge` MCP 服务端接管回调，触发 `Backend.emit('tool/call', ...)` | Host 仍完全掌控工具权限校验与执行；注意规避部分 CLI 的 MCP 调用超时限制（见 3.4 节）。 |
| `command/approval` / `file/approval` | 入站请求 `session/request_permission` | 依据 `purpose` 决定：连通性/候选校验自动拒绝写权限；阅读讨论按 `approval_policy` 转发给 Host UI 裁决并通过 JSON-RPC 应答。 |
| `interrupt()` / `close()` | `session/cancel` / `session/close` | 取消在途 Prompt 并等待静默排水（quiescence）；每轮结束后关闭并回收本轮进程。 |

### 2.4 启动、切换与连通性探测流

1. **启动期选择**：`python -m host --backend <id> [--backend-bin <path>] [--model <name>] [--backends-dir <dir>]`（兼容环境变量 `FOCUS_BACKEND`、`FOCUS_BACKEND_BIN`、`FOCUS_MODEL`）。若未指定，则读取 实际设置文件 中保存的激活配置；若首次运行，则仅发现路径：一个候选可预选，多个供用户选择，零个给安装指引和重新检测入口。用户可直接进入知识库，首次使用 AI 前确认 Backend；已有有效配置继续生效。 启动优先级为 CLI 参数 > 环境变量 > 已保存配置。显式选择即本次确认，仅对当前 Host 进程生效，跨工作区沿用。指定 Backend 检测失败时允许进入知识库，显示该 Backend 的失败原因，禁止静默回退。仅设置页主动「保存并应用」才改写 `settings.json`。
2. **设置期探测（去重安装化）**：
   - `inspect`：检查 `command[0]` 是否在 `PATH` 或指定路径存在且可执行，返回发现的路径或缺失提示（仅提示用户安装命令，不再后台静默 `pip install`）。
   - `check`：每次探针创建独立临时来源，仅开放只读动作 `read_range`，随机标记只通过本次 `focus(action="read_range")` 返回。Host 同时观察到工具调用成功和最终回复带回正确标记才判定通过。探针不访问用户知识库；以一次工具往返替换 `FOCUS_OK`，界面只显示一个检测结果。
   - **应用与首次使用**：通过回执绑定 `(backend_id, resolved_binary_path, resolved_model, command_args)`，使用实际解析的路径、模型和有序参数。点击「保存并应用」时复用匹配的通过回执，否则先检测，失败保留原生效配置。旧文本探针记录自然视为未验证，无专门迁移；下次使用 AI 或保存并应用时补测。
   - 首次使用未验证配置时，界面显示「正在检测 Backend」。仅向候选 Backend 发送临时来源探针；通过后自动执行本次请求，无需重新发送。失败时保留用户输入并显示原因，用户文章和问题均不发送。
   - **切换并发**：普通「检测」只验证候选配置。「保存并应用」在检测开始前取得 Host 独占切换权，持有至应用完成或失败。已有前台任务时拒绝切换；仅有后台预生成摘要时取消预生成，并拒收旧摘要的迟到结果。切换期间允许浏览知识库，新 AI 任务及第二次应用返回「正在应用 Backend，请稍后重试」。
3. **讨论上下文**：每轮都开启全新原生会话，由 FOCUS 注入绑定来源、近期消息和已有摘要，切换 Backend 后继续使用同一份 FOCUS 讨论历史。

---

## 三、各模块技术选型与修改建议

### 3.1 模块一：注册表与 Manifest 加载层

- **涉及文件**：新增 `host/backends/registry.py`、`host/backends/manifests/*.json`；重构 `host/backends/__init__.py`。
- **技术选型对比**：
  - *方案 A：Python entry_points 插件机制* — 适合第三方 pip 包分发，但要求用户用 Python 打包安装，与“纯外部 CLI 配置接入”目标背道而驰。
  - *方案 B：JSON Manifest 静态清单 + 目录扫描（推荐）* — 零额外依赖（标准库 `json` + `pathlib`），内置预置 JSON 与 `<settings-dir>/backends/*.json` 合并加载，保留内置 ID，冲突文件单独报告，借鉴 [Dagu Custom Harness](https://docs.dagu.sh/step-types/harness/) 的极简风格。
- **修改建议**：
  用户 Manifest 默认从实际设置文件所在目录的 `backends/` 子目录加载，显式 `--backends-dir` 优先。Windows 默认目录为 `%LOCALAPPDATA%/FOCUS/backends/`，使用 `FOCUS_SETTINGS_FILE` 时跟随该文件位置。

  Host 启动时扫描一次 Manifest，设置页可手动「重新扫描」。扫描仅读取配置并发现可执行路径，不启动 CLI 或文件监听线程。格式错误和 ID 冲突按文件名列出原因，其他条目照常使用。在途任务和当前生效 Backend 不因扫描结果而改变。

  1. 在 `host/backends/registry.py` 定义 `HarnessSpec`（dataclass）与 `HarnessRegistry`，提供 `list_specs()`、`get_spec(harness_id)`、`create_backend(harness_id, workspace, **options)`、`probe_binary(spec, explicit_path)`。
  2. 重构 `host/backends/__init__.py`：删除硬编码字典 `BACKENDS = {'codex': CodexBackend, 'deepseek': DeepSeekBackend}` 及 `check_backend()` 中的 `if adapter is ...` 分支，改为全权委托 `HarnessRegistry`；驱动工厂表仅按 `driver` 类型映射：`DRIVERS = {'acp': AcpBackend, 'codex-app-server': CodexBackend}`。
  3. 首版内置 Backend ID 固定为 `codex`、`deepseek`、`agy`、`cursor`。Claude Code 与 `codex-acp` 通过用户自定义 Manifest 注册。验收报告逐项标注真机实测状态。

### 3.2 模块二：传输层与通用 ACP 驱动

- **涉及文件**：重构 `host/runtime.py`；新增 `host/backends/acp.py`；逐步下线 `host/backends/deepseek.py`。
- **技术选型对比**：
  - *方案 A：引入官方 Python SDK [`agent-client-protocol`](https://pypi.org/project/agent-client-protocol/)* — 优点是自带完整 Pydantic v2 Schema 校验与 v1/v2 协商；缺点是需在 `host/requirements.txt` 引入 `pydantic>=2.7` 且为 `asyncio` 模型，与 Focus 当前同步线程 + `queue.Queue` 的 Host 架构需加一层事件循环桥接。
  - *方案 B：基于 Focus 现有 `host/runtime.py` 抽离标准库 `JsonRpcStdioTransport` 自写轻量 ACP Client（推荐）* — 优点是 **0 新增第三方依赖**、与现有 `queue.Queue` + 线程模型 100% 契合（`host/runtime.py` 本身只有 103 行，已经处理了 Windows `taskkill /T /F` 子进程树回收、读写锁与超时控制）；ACP 核心客户端仅需对接约 8 个 JSON-RPC 方法，代码量可控在 ~250 行以内。
- **修改建议**：
  1. 将 `host/runtime.py` 中的 `AppServer` 拆分为通用 `JsonRpcStdioClient(command, cwd, env=None)`（去掉硬编码的 `'app-server'` 子命令参数和 `'Codex App Server'` 错误文案），原 `codex.py` 只需传入 `[*command, 'app-server']` 即可无痛兼容。
  2. 新增 `host/backends/acp.py` 实现 `AcpBackend(Backend)`：
     - `open_session`：执行 `initialize` → 检查 `capabilities` → 启动 `ToolBridge`（若 `tools` 非空）→ 调用 `session/new`（挂载 `mcpServers`） → 若指定 `model` 且服务端支持配置项，调用 `session/set_config_option`。
     - `_pump`：消费 `session/update` 通知与 `session/request_permission` 入站请求，映射到 `base.Backend` 词表。
     - `interrupt` / `close`：发送 `session/cancel`，终止在途执行，释放工具桥并回收本轮进程。
  3. 用 `deepseek.json`（指向 `dsh --profile acp`）替代依赖 `deepseek-harness-sdk` 的 `host/backends/deepseek.py`，彻底卸掉 `deepseek-harness-sdk` 与 `pydantic>=2.12` 依赖。

### 3.3 非 ACP CLI 的接入条件

纯文本 CLI 无法通过 Backend 配置检测。本期延后 `cli-json`；出现必须支持且能调用 Host 工具的非 ACP CLI 时，再依据其实际接口设计驱动。

### 3.4 模块四：工具桥（ToolBridge）与人工确认

- **涉及文件**：演进 `host/backends/tool_bridge.py`、`host/backends/base.py`。
- **技术选型与避坑要点**：
  - Focus 现有 `ToolBridge` 使用 Streamable HTTP MCP（`http://127.0.0.1:<port>/<token>`），与 [`@deepseek-ai/dsh-acp`](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/acp/acp/README.md) 及 ACP v2 规范天然兼容。
  - **关键风险点 1（stdio-only MCP 兼容）**：ACP v1 规范要求所有 Agent 必须支持 `stdio` MCP，而 `http` MCP 为可选能力（见 [ACP Session Setup](https://agentclientprotocol.com/protocol/v1/session-setup)）。若某个外部 ACP Agent 仅支持 `stdio` MCP，直接传 HTTP URL 会被拒（`-32602`）。
  - **关键风险点 2（人工交互工具超时）**：Cursor CLI 的 `agent acp` 存在 MCP `tools/call` ~60s 固定超时限制（见 [Cursor Forum #163925](https://forum.cursor.com/t/agent-acp-mcp-tools-call-times-out-at-60s-with-no-way-to-configure-it/163925)），若 `focus_user_input` / `focus_confirm` 阻塞等待用户回复超过 60s，会导致工具调用失败。
- **修改建议**：
  1. 在 `host/backends/tool_bridge.py` 旁提供一个约 40 行的纯标准库 `mcp_stdio_proxy.py`：当 `initialize` 协商结果显示目标 Agent 仅支持 `session.mcp.stdio` 时，自动向 `session/new` 注入 `[sys.executable, "-m", "host.backends.mcp_stdio_proxy", bridge.url]`，透明转接到同一个 `ToolBridge` 实例，无需重写工具逻辑。
  2. 人工输入和确认：外部运行时提前超时或断开时，Host 立即作废待确认请求并禁用旧按钮，显示「本次请求已过期，请重试」。迟到的答复无效。用户手动重试时在原讨论开启新一轮，需要确认的操作重新询问。

### 3.5 模块五：配置持久化、环境探测与代理管理

- **涉及文件**：重构 `host/configuration.py`、`host/backend_setup.py`、`host/proxy.py`。
- **修改建议**：
  1. **`host/configuration.py`**：
     - 删除硬编码 `DEFAULT_MODELS = {'codex': ..., 'deepseek': ...}`，改为向 `HarnessRegistry` 查询 `defaultModel` 与合法 `id`。
     - 将用户设置结构统一为通用 Schema：`{"backend": "<id>", "model": "...", "runtimePath": "...", "extraArgs": [], "credentialFile": null, "preferences": { "<id>": { ... } }}`；沿用现有字段名，仅将 Backend ID 放宽为字符串。
     - DeepSeek 保留 Backend ID `deepseek` 和原模型偏好，标准 Manifest 启动 `dsh --profile acp`。迁移时重新发现 `dsh`，不沿用旧 SDK 专用路径。缺失时提供安装指引和指定路径入口，首次使用前按新规则检测。
  2. **`host/backend_setup.py`**：
     - **移除 `prepare()` 中的隐式 `pip install`**，改为纯只读的依赖检查（`inspect`）：仅发现目标可执行路径，缺失时返回清晰的安装指引文本。
     - **下沉 `discover()`（模型发现）与 `account()`（认证检查）**：改为调用对应驱动的可选方法（如 `AcpBackend.discover_models()` 读取 ACP `session/new` 返回的 `configOptions` 模型目录），不再在 `backend_setup.py` 里写死 `codex_account_runtime` 或 `api.deepseek.com/models`。
     - 以 `(backend_id, resolved_binary_path, resolved_model, command_args)` 标识新探针回执，与 §2.4 的配置应用使用同一解析结果。
  3. **`host/proxy.py`**：
     - 删除 `if backend == 'codex': env.pop(...)` 特判；改为 `backend_environment(spec: HarnessSpec)`，按 `spec.env_strip` 剥离变量、按 `spec.env` 合并注入，再应用通用 `FOCUS_<HARNESS_ID>_PROXY` 代理规则。

### 3.6 模块六：独立候选检查器

默认单文档导入仅调用解析器，不检查 Backend，也不触发 AI 探针或模型请求。仅显式调用独立候选检查器时，才使用当前 Backend，并由 Host 校验结构化结果。

- **涉及文件**：重构 `host/codex_ingestion.py`（重命名或保留兼容别名指向 `host/ingestion_inspector.py`）。
- **修改建议**：
  1. 废弃直接 `subprocess.Popen([codex_bin, "exec", "--output-schema", ...])` 的旁路实现。
  2. 在 `host/candidates.py`（已有通用 `CandidateTurns`）基础上增加 `run_structured_json(prompt, schema, images=())` 辅助方法：
     - 构造严格 JSON 输出提示并经由当前激活的 `HarnessRegistry` 驱动执行（`purpose='candidate'`，只读、无工具、限时超时）；
     - 返回后在 Host 侧使用纯 Python 校验响应结构（替代对 Codex 私有 `--output-schema` 参数的依赖）。
  3. 仅当所选 Harness 支持图片输入时附带提取图片，否则明确标注 `image_observed: false` 并记录能力降级原因。

### 3.7 模块七：服务层、启动入口与 HTTP API

- **涉及文件**：重构 `host/service.py`、`host/workbench.py`、`host/server.py`、`host/__main__.py`。
- **修改建议**：
  1. **`host/__main__.py`**：
     - 新增通用参数 `--backend`（默认读 `FOCUS_BACKEND`）、`--backend-bin`（默认读 `FOCUS_BACKEND_BIN`）、`--backends-dir`（自定义 Manifest 目录）。
     - 更新现有启动脚本和使用示例，统一使用这三个 Backend 参数。
     - `--check-runtime` 改为列出所有已注册 Harness 的可用状态或校验指定的 `--backend`。
  2. **`host/service.py` & `host/workbench.py`**：
     - 将 `self.codex_bin`、`self.deepseek_bin`、`self.deepseek_credentials` 收敛为通用 `self.harness_id` 与 `self.harness_overrides: dict[str, dict]`。
     - `_build_backend()` 不再按名称做 `if name == 'deepseek'` 分支，统一调用 `self.registry.create_backend(name, workspace, **options)`。
     - 状态快照中的 `backends` 列表直接由 `self.registry.describe_all()` 生成，携带每个 Harness 的 `id`、`label`、`driver`、`available` 与 `capabilities`。
  3. **`host/server.py`**：
     - 保持 `/reader/configuration`、`/reader/backend`、`/reader/backend/setup` 路由路径兼容，仅在响应体中补充 `backends` 元数据数组，平滑过渡。

### 3.8 模块八：前端契约与设置面板

- **涉及文件**：`ui/packages/reader-contracts/src/index.ts`、`ui/apps/standalone/src/BackendSetupPanel.tsx`。
- **修改建议**：
  1. **契约泛化（`reader-contracts`）**：
     - 将 `backend: "codex" | "deepseek"` 改为开放字符串 `backend: string`；`preferences` 改为 `Record<string, BackendPreference>`。
     - 扩展 `BackendDescriptor` 类型：`{ id: string; label: string; driver: string; available: boolean; capabilities: { authMode: string; modelDiscovery: string; streaming: boolean }; defaultModel?: string; installHint?: string }`。
  2. **面板能力驱动渲染（`BackendSetupPanel.tsx`）**：
     - 单选/下拉列表从后端下发的 `backends` 数组动态渲染，并显示本机探测状态（已找到路径 / 未找到路径）。
     - 根据 `selected.capabilities.modelDiscovery !== "none"` 决定是否显示“加载模型清单”按钮，同时始终保留手动输入自定义模型 ID 的能力。
     - 默认 Codex 的 Manifest 声明 `authMode: "interactive-oauth"`，由 `codex-app-server` 驱动负责发起和取消登录。设置页按能力显示主动登录按钮；使用外部 CLI 登录的 Backend 显示各自的登录指引。
     - 根据 `selected.capabilities.authMode === "interactive-oauth"` 才渲染浏览器登录按钮；对于绝大多数 `"external-cli"` 模式，展示清晰的一行引导（如“请先在终端完成 `agy login` / `agent login`”）与“检测连通性”按钮。
     - 提供可选的“可执行文件路径覆盖（`runtimePath`）”折叠输入项，方便用户在未配置 `PATH` 时直接指定本地 CLI 路径。

---

### 3.9 四大目标 CLI 预置 Manifest 要点与边界汇总

| 目标 Harness | 推荐驱动与启动命令 | 推荐 `env` / `envStrip` | 关键能力与已知边界 |
| :--- | :--- | :--- | :--- |
| DeepSeek（Backend ID `deepseek`） | `acp`：`["dsh", "--profile", "acp"]`（[`@deepseek-ai/dsh-acp`](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/acp/acp/README.md)） | 显式 `credentialFile` 按 `credentialEnv` 注入 `DEEPSEEK_API_KEY`，否则沿用本机认证 | 原生支持 Streamable HTTP MCP和模型切换；可彻底移除 `deepseek-harness-sdk` 依赖。 |
| Antigravity CLI (`agy`) | `acp`：`["agy", "acp"]`（[Antigravity ACP 文档](https://antigravity.google/docs/cli/acp/)） | `env: {"AGY_CLI_DISABLE_AUTO_UPDATE": "true"}` | 复用本机 `agy` 登录；验收记录 Windows 实测冷启动与首段回答耗时。 |
| Cursor CLI (`cursor`) | `acp`：`["agent", "acp"]`（[Cursor ACP 文档](https://cursor.com/docs/cli/acp)） | 默认复用 `agent login`（`cursor_login`） | 原生支持 `agent`/`plan`/`ask` 模式与模型目录；需关注 [MCP `tools/call` ~60s 超时限制](https://forum.cursor.com/t/agent-acp-mcp-tools-call-times-out-at-60s-with-no-way-to-configure-it/163925)。 |
| Codex CLI (`codex`) | 默认 `codex-app-server`，经内置 Manifest 启动现有 Codex | `envStrip: ["OPENAI_API_KEY", "CODEX_API_KEY"]`（使用 ChatGPT 登录态时） | 用户可显式注册「Codex（ACP）」。服务、配置、探测层统一通过注册表和驱动接口调用。 |

---

### 3.10 分阶段实施与验收路线

| 阶段 | 核心交付物 | 验收标准（DoD） |
| :--- | :--- | :--- |
| **Phase 1：控制面去硬编码** | `HarnessRegistry` + 内置 Manifest + 泛化 `configuration.py` / `service.py` / `proxy.py` / `__main__.py` / 前端契约与面板 + 独立候选检查器迁移；取消自动安装 | 全仓 `host/`（除驱动目录外）与 `ui/` 零 `codex`/`deepseek` 业务硬编码；验收覆盖临时来源标记往返、回执复用与失效、启动覆盖失败且不回退、跨页面并发应用与迟到摘要、默认 Codex 的登录入口和免装 ACP、无 Backend 时正常导入且零模型请求、首次探针失败时保留输入且不发送文章或问题；按新契约更新的 `test_agent_backends.py`、`test_backend_setup.py`、`test_stage6b_*` 全量通过。 |
| **Phase 2：通用 ACP 主驱动落地** | `JsonRpcStdioClient` + `AcpBackend` + `mcp_stdio_proxy.py`；以 `dsh --profile acp` 替换 `deepseek.py`；配置接入 `agy acp` 与 `agent acp` | 真机验证 `dsh` 经 `AcpBackend` 完成阅读讨论、真实 `focus(action="read_range")` 往返、取消与资源释放，验收通过后移除 SDK。2026-11-21 用户豁免 Antigravity 和 Cursor 的真机端到端验收，保留预验收记录。 |
| **Phase 3：真实 CLI 验收** | 自定义 Manifest 接入与生命周期验证 | 验证独立 ID 注册、冲突提示、超时或断开后拒绝迟到答复及手动重试。每轮启动并回收进程，验证无遗留句柄与子进程；分别记录从启动到握手完成、从用户发问到首段回答的耗时。报告逐项记录平台、CLI 版本与两项耗时；默认 Codex 单独进行 `codex-app-server` 兼容回归，其余未经真机验证的预置标为「未实测」。根据实测影响另行决定是否引入进程池。 |

---

## 四、参考资料

1. Tencent/LoopForge 仓库与架构说明：[github.com/Tencent/LoopForge](https://github.com/Tencent/LoopForge)
2. LoopForge 执行器配置割裂与私有 HOME 鉴权问题实证：[Issue #899](https://github.com/Tencent/LoopForge/issues/899)、[Issue #897](https://github.com/Tencent/LoopForge/issues/897)
3. Agent Client Protocol (ACP) 传输层与会话 MCP 规范：[Transports (v2)](https://agentclientprotocol.com/protocol/v2/transports)、[Session Setup (v1)](https://agentclientprotocol.com/protocol/v1/session-setup)、[Session Setup (v2)](https://agentclientprotocol.com/protocol/v2/session-setup)
4. ACP 官方 Python SDK：[pypi.org/project/agent-client-protocol](https://pypi.org/project/agent-client-protocol/)
5. OpenClaw Agent Harness 插件边界规范：[docs.openclaw.ai/plugins/sdk-agent-harness](https://docs.openclaw.ai/plugins/sdk-agent-harness)
6. Dagu 声明式 Harness 与 ACP 配置模型：[docs.dagu.sh/step-types/harness](https://docs.dagu.sh/step-types/harness/)、[docs.dagu.sh/step-types/harness/acp](https://docs.dagu.sh/step-types/harness/acp)
7. DeepSeek Harness 原生 ACP 服务端 `@deepseek-ai/dsh-acp`：[github.com/deepseek-ai/deepseek-harness/.../acp/README.md](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/acp/acp/README.md)
8. Google Antigravity CLI (`agy`) ACP 与无头模式文档：[antigravity.google/docs/cli/acp](https://antigravity.google/docs/cli/acp/)、[Headless Mode](https://antigravity.google/docs/cli/headless/)、[Windows Cold-Start Discussion](https://discuss.ai.google.dev/t/acp-server-1-1-1-official-agy-acp-server-cold-starts-in-16s-on-every-windows-spawn/183427)
9. Cursor CLI ACP 与 Stream-JSON 输出规范：[cursor.com/docs/cli/acp](https://cursor.com/docs/cli/acp)、[Output Format](https://cursor.com/docs/cli/reference/output-format)、[MCP Timeout Issue #163925](https://forum.cursor.com/t/agent-acp-mcp-tools-call-times-out-at-60s-with-no-way-to-configure-it/163925)
10. Codex CLI 官方 ACP 适配器：[github.com/agentclientprotocol/codex-acp](https://github.com/agentclientprotocol/codex-acp)
