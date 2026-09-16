# WorkBuddy / Codex 网页 Agent 接入核实

核实日期：2026-09-17；本轮补查按用户指定的**国内 WorkBuddy**重新判定。范围：官方能力与 FOCUS 接入边界；本文不是已完成真实账号验收的声明。已有 `agent-backend-integration-options.md` 保留，本文纠正其过强或已过期的表述。

## 结论

**先前把 CodeBuddy SDK 标成 WorkBuddy 后端的建议撤回。** 随 WorkBuddy 分发同一引擎，不能证明 CodeBuddy 的登录、账号权益与国内 WorkBuddy 等价。没有证据支持把 `CODEBUDDY_INTERNET_ENVIRONMENT=internal` 当作 WorkBuddy 国内账号接入；该变量在 CodeBuddy 文档中对应的是 CodeBuddy 中国版。Codex 继续使用现有 App Server；国内 WorkBuddy 应使用其独立开放平台。[CodeBuddy SDK](https://www.codebuddy.cn/docs/cli/sdk)、[WorkBuddy 第三方应用](https://open.workbuddy.cn/docs/third-party-app)、[Codex App Server](https://developers.openai.com/codex/app-server)

**真正 WorkBuddy 的官方接入路径已找到：OAuth 2.1 + HTTPS Open API + 云任务 ACP 通道。** 平台支持调用用户本地助理和创建云端 Agent 任务；需注册应用、配置回调与 Scope、通过审核启用，再取得用户授权。公开页面给出 API 协议，不等于提供与 CodeBuddy SDK 相同的无头进程接入或自动复用桌面登录。[WorkBuddy 第三方应用](https://open.workbuddy.cn/docs/third-party-app)

## 国内 WorkBuddy：已确认与未确认

认证入口在 `https://www.workbuddy.cn/openapi/v2/authorize`，服务端在同域 `/openapi/v2/token` 换取与刷新凭证。需要平台发放的 `client_id` / `client_secret`、已注册回调地址和批准的权限范围；密钥和 refresh token 只存后端。不能用 CodeBuddy API Key 代替，也不能抽取桌面凭据绕过注册流程。[WorkBuddy Open API](https://open.workbuddy.cn/docs/openapi)

| 路线 | 官方能力 | FOCUS 边界 |
| --- | --- | --- |
| 本地助理 | 查在线、发消息、查询历史；Scopes 为 `user.localassistant.readable` / `user.localassistant.invokable` | 驱动用户 PC 上 WorkBuddy，依赖在线桌面；并非独立服务器 runtime |
| 云端任务 | `/tasks` 创建任务；ACP 支持流式工具活动、审批和续聊 | 执行在 WorkBuddy 云会话；接入本地 Core 还需要独立且经验证的工具通道 |
| Connector | MCP + Skill 或 CLI + Skill，把第三方能力供 WorkBuddy 调用 | 可以设计 FOCUS 工具连接器，但方向是 WorkBuddy 调用 FOCUS，不能代替网页登录授权 |

本地与云端能力来自 [第三方应用文档](https://open.workbuddy.cn/docs/third-party-app)；Connector 方向来自 [连接器文档](https://open.workbuddy.cn/docs/connector)。

云任务接入细节：创建或读取任务取得 `task_id`、`link`、临时 `token`；GET `link` 建立 SSE，POST 同地址发送 JSON-RPC，两者关联 `Acp-Connection-Id`。流程为 `initialize → session/load → session/prompt`，加载 ID 就是 task ID。`session/update` 提供流；`session/request_permission` 要求响应；`session/prompt` response 是本轮完成依据。未核实独立停止接口，不能仅凭通用 ACP 规范承诺 WorkBuddy 的 `session/cancel`。[WorkBuddy Open API](https://open.workbuddy.cn/docs/openapi)

**文档冲突需实测：** 中文接口页允许本地助理消息类型 `permission_response`，英文页明确只允许文本、审批留本机。中文 token 示例 `expires_in=3600`，第三方应用概览写 24 小时。应以实际返回有效期为准；本地审批能力在厂家确认或真实接口验收前标为未确认。[中文 Open API](https://open.workbuddy.cn/docs/openapi)、[英文 Open API](https://open.workbuddy.cn/en/docs/openapi)

账号额度结论：官方开放平台是在授权 WorkBuddy 用户身份下调用任务，英文文档还提供个人 credits 查询；但未找到“CodeBuddy SDK 可消费国内 WorkBuddy 订阅额度”的官方保证，也没有本次已授权任务的计费验证。不能承诺旧 SDK adapter 复用 WorkBuddy 额度。[英文 Open API](https://open.workbuddy.cn/en/docs/openapi)

本机官方 `acp-meta-reference.md` 还区分标准 process-login 与 WorkBuddy 私有准入通道，并明确第三方不能自行构造私有授权材料。这再次说明随附 CLI 不是桌面身份可复用的证据；无需也不应读取凭据来推断公共接入能力。

## CodeBuddy 接口与包（仅作对照，不能冒充 WorkBuddy）

2026-09-17 registry 只读查询结果：`@tencent-ai/agent-sdk` 为 `0.3.259`，`@openai/codex-sdk` 为 `0.154.0`，`codebuddy-agent-sdk` 为 `0.3.258`、Python `>=3.10`。这些是查询时版本，不应自动替换 FOCUS 已固定的 runtime。PyPI JSON 本次成功返回；旧报告“本机 PyPI 不可用”不能作为现状结论，也不能由元数据可读推导 wheel 一定可下载。[腾讯安装文档](https://www.codebuddy.cn/docs/cli/sdk)、[PyPI 元数据](https://pypi.org/pypi/codebuddy-agent-sdk/json)、[Codex SDK](https://developers.openai.com/codex/sdk)

| 能力 | 腾讯 Python SDK | Codex App Server |
| --- | --- | --- |
| 长驻会话 | `CodeBuddySDKClient.connect/query/receive_messages` | stdio JSON-RPC 连接、`thread/start`、`turn/start` |
| 文本流与工具事件 | `include_partial_messages=True`、`StreamEvent`、Assistant/Tool blocks | item 通知、agentMessage delta、命令/文件/MCP items |
| 自定义 FOCUS 工具 | `@tool` + `create_sdk_mcp_server` | 现有 `dynamicTools`（实验接口） |
| 会话恢复 | `resume=session_id`、`persist_session=True` | `thread/resume` |
| 审批 | `can_use_tool`、Allow/Deny | 命令、文件、权限审批请求与响应 |
| 中断 | `interrupt()`，文档标为实验 API | `turn/interrupt`，结束状态 `interrupted` |

腾讯字段见 [Python SDK 参考](https://www.codebuddy.cn/docs/cli/sdk-python)；自定义工具见 [SDK Custom Tools](https://www.codebuddy.cn/docs/cli/sdk-custom-tools)；Codex 字段见 [App Server 官方参考](https://developers.openai.com/codex/app-server)。上表描述可接入的协议能力，不保证两个运行时行为完全等价。

常驻 Host 需要持续读取 `receive_messages()`。`receive_response()` 在一个 `ResultMessage` 停止；顶层 `query()` 还会默认禁用后台任务，无法承担跨轮后台完成通知。会话 ID 必须与创建它的 provider 绑定，不能传给另一家 runtime。[Python SDK 参考](https://www.codebuddy.cn/docs/cli/sdk-python)

腾讯认证支持已完成 CLI 登录的凭据、`CODEBUDDY_API_KEY` 或企业 OAuth。中国版 key 要配 `CODEBUDDY_INTERNET_ENVIRONMENT=internal`。SDK 默认不读取文件系统配置；需要项目 Skills 等资源时应明确指定 `setting_sources` 或由 Host 提供所需能力，不能认为安装桌面端后 SDK 自动继承全部插件和权限。[腾讯 SDK 概览](https://www.codebuddy.cn/docs/cli/sdk)

## 必须修正的边界

- `can_use_tool` **仅在需要权限确认时触发**。`permission_mode='default'` 不证明每个工具都会回调。`allowed_tools` 是自动允许列表，不能当作完整可用工具白名单；`tools=[]` 才是文档给出的禁用内置工具、只留 MCP 的方式。仅回调审批不能宣称 OS 沙箱。[权限文档](https://www.codebuddy.cn/docs/cli/sdk-permissions)
- 禁用 `WebFetch` / `WebSearch` 不等于系统断网，Shell、PowerShell 或其他工具仍可能发起网络访问。这是工具能力推导；要求网络隔离时必须由部署环境执行。
- 普通 OpenAI API SDK、Codex SDK、Codex App Server 不应混称。官方 Codex TypeScript SDK 运行在服务端，支持启动/恢复本地 threads；FOCUS 已使用 App Server，满足富客户端集成方向，无需仅为“使用 SDK”重写协议层。[Codex SDK](https://developers.openai.com/codex/sdk)
- 原报告关于高层 Codex SDK“必然丢失能力”的绝对判断未在本次逐版本核实。可靠理由是现有 App Server 已承载所需行为、官方支持该集成方向；保留它可减少重写风险。
- 尚未确认本机账号、模型权益、真实执行、失败恢复、桌面 daemon 并存以及 WorkBuddy 桌面会话同步。不能从文档和假 SDK 测试推导生产可用。

## FOCUS 实现建议

沿既有 `ReaderHost → HTTP/SSE Host → AgentBackend → CoreBridge → Core/Workspace` 接入。**WorkBuddy 选项必须绑定真实 WorkBuddy Open API，未配置审核通过的应用时应显示不可用及具体原因，不能启动 CodeBuddy SDK 冒充。** 前端只投影 provider 状态、操作记录和审批；密钥、进程与文件权限留在 Host。切换必须拒绝正在执行或等待审批的 run，启动所选 provider 后再持久化选择；失败不能把界面置为已切换。Source Library、Reading Plan、Cursor State 与 Reading Notes 保持原权威，Agent session 单独存放。

两个 provider 的最低验证应包含：真实工具调用、流式文本、拒绝审批不执行、停止、中途断开后的终态、重启恢复和两次 provider 切换。模拟 SDK 用于验证适配逻辑；真实账号验证单独记录，不能合并证据等级。

## 本机官方分发材料

交叉核对目录：`E:\Program Files\WorkBuddy\resources\app.asar.unpacked\cli\dist\web-ui\docs\cn\cli\`，读取了 `sdk.md`、`sdk-python.md`、`sdk-permissions.md`、`sdk-custom-tools.md`。它们的标题和公共包名均是 CodeBuddy。该路径用于记录本机证据，不作为部署依赖；公共官方链接见各段。

另用项目 `.venv/Scripts/python.exe` 检查实际已安装的 `codebuddy-agent-sdk==0.3.258`，未安装或修改依赖：

- `.venv/Lib/site-packages/codebuddy_agent_sdk/transport/subprocess.py:339-346`：子进程环境先展开 `os.environ`，再展开 `options.env`；因此传入环境是覆盖合并，省略代理变量不会清除父进程代理。把同名代理变量设为空字符串会覆盖原值，但 CLI 如何解释空值还需真实启动验证。
- `types.py:645-648`：`can_use_tool` 注释明确仅在需要权限审批时触发；实际 `CodeBuddyAgentOptions` 有 `tools`、`codebuddy_code_path`、`env`、`setting_sources` 等字段。
- 实际 `PermissionResultAllow` 支持 `updated_input` / `updated_permissions`；`PermissionResultDeny` 要求 `message`，有 `interrupt=False`。

尝试下载 wheel 的探测已停止；`.scratch/agent-provider-research/` 中只有本次下载探测材料，不属于产品依赖或验收结果。代理路径出现连接重置，直接读取 metadata 成功，均不构成实际 Agent 账号联通结论。
