# DeepSeek 直接集成 FOCUS 调研

调研日期：2026-09-26。证据层级：官方文档与官方仓库静态核查；未安装新依赖、未调用计费 API、未运行真实 Runtime 或浏览器验收。在线文档与 GitHub `master` 是可变内容，实施时需要另行固定版本。

## 结论

**有：官方 DeepSeek Harness SDK 可以直接嵌入 FOCUS 的后端，无需再做一个由 DSH Web UI 承载的 FOCUS。** 它提供 Python 和 TypeScript 客户端，底层仍启动 DSH Runtime。若要求连 Runtime 也完全不依赖 DSH，官方同时支持直接使用 OpenAI Python/Node SDK 调用 DeepSeek API，但后者只解决模型访问。[Python SDK](https://github.com/deepseek-ai/deepseek-harness/blob/master/python/sdk/README.md)、[TypeScript SDK](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/sdk/client/README.md)、[DeepSeek API 入门](https://api-docs.deepseek.com/)

在本次官方入口和仓库检索范围内，未找到另一套独立于 Harness、由 DeepSeek 发布并提供完整工具执行循环的通用 Agent SDK。这是检索范围内的结果，不是对所有项目不存在的证明。

| 路线 | 是否依赖 DSH Runtime | 可复用能力 | FOCUS 需要承担什么 |
| --- | --- | --- | --- |
| OpenAI SDK → DeepSeek API | 否 | 模型请求、流式输出、Function Calling、JSON 输出 | 受控工具执行循环、上下文、取消、重试、任务限额和状态映射 |
| DeepSeek Harness Python/TS SDK | 是，无需 DSH Web UI | 现成 Agent 执行循环、事件与会话、工具及进程管理 | Runtime Adapter、配置组合、权限与业务提交边界 |
| Codex Runtime → DeepSeek provider | 否，依赖 Codex Runtime | 复用现有 Codex 工具循环与客户端协议 | 验证版本兼容、provider/catalog 配置、模型差异 |

表中职责分配是依据下述公开能力作出的架构判断；不是 FOCUS 已完成集成的声明。

## 无 DSH 的 API 路线

官方示例直接 `from openai import OpenAI`，配置 `base_url="https://api.deepseek.com"` 和 DeepSeek API Key。Chat Completions 可以流式返回，模型负责生成工具调用参数，具体函数由调用方执行。因此 SDK 解决 API 访问，不自动获得本地文件工具、MCP Client、持久会话或自主循环。[API 入门](https://api-docs.deepseek.com/)、[Tool Calls](https://api-docs.deepseek.com/guides/tool_calls/)

当前需要单独处理的契约：

- Thinking 支持工具调用；带 `tools` 的后续请求必须完整回传先前的 `reasoning_content`，包括未调用工具的轮次，否则可能返回 400。适配器不能随意丢弃该字段。[Thinking Mode](https://api-docs.deepseek.com/guides/thinking_mode/)
- `json_object` 保证 JSON 语法，不等于业务 Schema 验证；官方提示可能出现空内容或截断，需要本地校验。[JSON Output](https://api-docs.deepseek.com/guides/json_mode/)
- Function Calling `strict` 是 Beta，需要 `/beta` endpoint 和 `strict: true`；支持的 Schema 子集有限。Thinking 模式不支持强制 `required` 或指定函数的 `tool_choice`。[Strict Tool Calls](https://api-docs.deepseek.com/guides/tool_calls/)、[Chat API](https://api-docs.deepseek.com/api/create-chat-completion/)
- 官方已支持 Responses 格式，但它是无状态 API：`previous_response_id`、`conversation`、`store`、`background` 不支持；内置 `web_search`、`file_search`、`code_interpreter`、`mcp` 等忽略，`max_tool_calls` 也忽略。FOCUS 必须在本地落实循环次数、取消与工具权限，不应依赖这些服务端参数。[Responses 兼容矩阵](https://api-docs.deepseek.com/guides/responses_api/)

## 官方 Harness SDK 路线

Python 包名是 `deepseek-harness-sdk`，导入 `deepseek_harness.DeepSeekHarness`，安装时携带同版本的 `deepseek-harness-runtime-bin`。它通过 stdio JSON-RPC 启动 `dsh --profile sdk`，显式传入 `dsh_home`、`cwd`、provider 和 model，普通运行不需要系统 Node.js。Windows x64 有发布目标。[Python SDK](https://github.com/deepseek-ai/deepseek-harness/blob/master/python/sdk/README.md)、[Runtime wheel](https://github.com/deepseek-ai/deepseek-harness/blob/master/python/sdk-runtime/README.md)

实时 PyPI JSON 核查结果：SDK 和 runtime 的当前发布版本均为 `0.1.5rc1`；SDK 要求 Python `>=3.10`，依赖同版本 runtime 和 `pydantic>=2.12,<3`；runtime 文件列表包含 Windows x64 wheel。**这证明包已发布，不证明该 RC 包拥有 GitHub `master` 文档展示的全部能力**；后续探针须对齐发布版本的源代码与文档。[SDK 发布元数据](https://pypi.org/pypi/deepseek-harness-sdk/json)、[Runtime 发布元数据](https://pypi.org/pypi/deepseek-harness-runtime-bin/json)

TypeScript 包 `@deepseek-ai/dsh-sdk-client` 同样启动同版本 DSH 子进程，提供 `DeepSeekHarness.run()`、会话句柄、事件通知及底层 `HarnessClient`；不是把 Web UI 嵌入 FOCUS。[TypeScript SDK](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/sdk/client/README.md)

需要注意 `sdk-minimal` 的真实含义：它有独立配置树，但仍经 DSH launcher 启动。默认仅含持久 shell、本地执行与 JSONL Session；没有 compaction、subagents、本地指令发现等完整能力，而且固定 `danger-full-access`，`cwd` 不构成文件访问隔离。不能仅因名称含 minimal 就认为适合 FOCUS 的最小权限需求。[Python SDK 教程](https://deepseek-harness.github.io/deepseek-harness/en/guide/python-sdk)

由此推断：若用户希望“不依赖 DSH 页面、不维护另一个 DSH 应用”，官方 SDK 能满足这个方向；若希望“部署和运行都完全没有 DSH”，则必须选择 API 路线或其他 Runtime。SDK 仍保留 DSH 的会话持久化与配置概念，不能视作自动消除了会话生命周期问题。[Harness 架构](https://deepseek-harness.github.io/deepseek-harness/en/reference/)

## 值得先验证的第三条路线

DeepSeek 官方提供 Codex provider 配置指南，并明确其 API 原生支持 Codex 使用的 Responses 格式。官方方案涉及 provider 配置和模型目录，而不仅是替换模型名。**复用 FOCUS 已有 Codex Runtime Adapter 连接 DeepSeek 是另一个候选方案**；是否比官方 Harness SDK 更省成本，需要对 FOCUS 固定的 `openai-codex==0.154.0` 做兼容性探针，不能由当前在线指南推定可用。[DeepSeek 接入 Codex](https://api-docs.deepseek.com/quick_start/agent_integrations/codex/)

不应直接运行官网修改用户全局 Codex 配置的一键脚本来完成 FOCUS 集成。更合适的验证对象是 FOCUS 自己的 Runtime 配置、独立进程环境和固定依赖版本。这个建议源于避免改变研究范围外的个人配置，并非官方限制。

## 后续验证门槛

1. 固定 SDK/Runtime、模型与 provider 版本，验证最小文本请求和一次真实工具往返。
2. 验证 Thinking 字段回传、Schema 失败、流中断、超时取消、循环限额和进程退出。
3. 验证输出仅作为候选，经 FOCUS Host/Core 校验和提交；失败或旧 attempt 不得写入有效业务资产。
4. 分别验证 Reading Plan、Reading Preparation、Reading Blog 和阅读问答的内容质量，再做浏览器完整流程。API 通与 SDK 能启动不构成这些验收。

以上是建议验证清单，本次未实施探针或迁移。

取消语义尚未验证：关闭本地 HTTP 流不应被当作服务端推理已停止或费用已停止的证据；Harness SDK 的关闭进程能力也不能直接代替 FOCUS 所需的单任务 interrupt、终态和迟到结果隔离验收。
## 本地 Focus 接入判断（当前源码核对）

核对基线：2026-09-26，HEAD `d6ab8b4` 加当前未提交修改。以下是源码静态分析；未安装新 SDK、未调用模型、未做浏览器或 Runtime 验收。

- [Backend](../host/backends/base.py) 已定义会话、回合、回复、打断、关闭和事件边界；[注册入口](../host/backends/__init__.py) 当前只有 Codex 与 WorkBuddy 项。DeepSeek SDK 可作为新增 Backend 的候选，无须在 DSH UI 中重新实现 Focus。工具回调、审批、恢复和事件语义仍需逐项映射验证。
- [CodexBackend](../host/backends/codex.py) 当前直接驱动固定版本 App Server JSON-RPC；[依赖](../host/requirements.txt) 为 `openai-codex==0.154.0`。它不是直接调用 OpenAI 模型 API。官方 [Codex Python SDK](https://learn.chatgpt.com/docs/codex-sdk) 同样通过本地 App Server 和配套运行时提供 Agent 能力；因此 DeepSeek 的子进程 SDK 在集成层级上更接近 Codex SDK。
- [ReadingRuntime](../.agents/core/reading_application.py) 已有 `context/plan/translate/check/cancel` 候选接口；[AgentReadingRuntime](../host/reading_runtime.py) 向后端提供任务数据、接收 JSON，并拒绝工具请求。固定任务可考虑 API 适配器，但需继续满足 Core 的校验和取消契约；不能只替换调用地址就宣称完成。
- [BlogApplication](../.agents/core/blog_application.py) 接收 Runtime 的 `files`，由可信应用代码写入候选目录，再校验和提交；[CodexBlogRuntime](../host/blog_runtime.py) 的正文生成也已是给定来源和方法后的结构化输出。不过 `search_implementation` 还承担官方实现检索，API 路线需要明确检索工具的执行者，不能把只有生成的适配器标为完整博客能力。
- 当前 [DSH 集成](../integrations/dsh-focus/index.js) 是另一条 Host 路线；[阶段 6](../docs/requirements/v0.2/stage-6-dsh.md) 仍要求 DSH 原生工作台。改为 SDK 嵌入独立 Focus 会改变该交付目标，需要后续明确修订需求，不能直接把 SDK 接入算作原阶段 6 完成。
- [阶段 7](../docs/requirements/v0.2/stage-7-runtimes.md) 已要求按适配器记录真实能力与验收证据；固定输出适配不扩展成通用 harness。[ADR 0014](../docs/adr/0014-archive-dsh-attempt-sessions.md) 的停止、释放、归档是特定 DSH attempt 的决策，SDK 的 `close()` 不能未经验证被解释成永久删除会话。

建议结构（架构推断）：Focus UI → Focus Host → DeepSeek SDK Backend → SDK 自带 Runtime → DeepSeek 模型；业务工具回到既有 Application/Core。Focus 保持唯一产品界面和业务权威。如果要求彻底移除 DSH Runtime，才选择直接 API；需要自主工具循环时可评估通用 Agent 框架。OpenAI [Agents SDK](https://developers.openai.com/api/docs/guides/agents/sdk) 负责应用内 Agent 循环，[模型与 Provider 文档](https://developers.openai.com/api/docs/guides/agents/models) 提供非 OpenAI 模型适配路线，但这不是 DeepSeek 全能力兼容的实测证明。

建议的下一次独立探针只验证一个来源：启动与凭据、Focus 工具执行与越权拒绝、流式终态、取消后的迟到提交拒绝、重启恢复、结构化候选校验。SDK 原生会话仅作运行记录，不能成为第二份 Source/Plan/Cursor/Notes 权威。当前调研不改变路线、不开始实施。
