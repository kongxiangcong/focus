# FOCUS 统一工作流、多宿主架构与开发计划

版本：0.2（架构决策修订，待实施）
日期：2026-09-21
适用产品：FOCUS 独立网页版与 FOCUS for DSH 原生插件
性质：独立的 v0.2 需求与架构计划；不是已完成实现、兼容性或端到端验证声明。

2026-10-06 后续范围修订：用户确认推进[工作区可迁移性与首次初始化](docs/requirements/workspace-portability-onboarding.md)，将完整 FOCUS 用户数据与项目程序分离，增加首次导入／新建、简洁 Backend 配置和停机目录备份恢复。后续明确取消独立 Windows 发行包，沿用现有启动方式，实施范围合并为三张票。按全新产品处理，不迁移当前用户记录；完整多宿主工程继续不实施。资产归属和后端配置的新决定见 ADR 0020／0021；此修订不表示相应功能已经实现。

2026-09-26 后续交付路线修订：用户决定跳过原阶段 6 的 DSH 原生 FOCUS 交付，改为 [阶段 6B：SDK Backend 接入与设置切换](docs/requirements/v0.2/stage-6b-sdk-backends.md)。保留现有 FOCUS 独立界面和 Host，通过官方 DeepSeek Harness SDK 及其配套 Runtime 接入 Backend，与 Codex 并列供设置界面选择。下文完整 DSH 原生应用、P4 及双 Host 停机接管描述保留为原计划背景，后续以阶段 6B 为准；Core／Application／Methods 单一权威、独占写入及既有阶段结果继续有效。阶段 2D 的历史证据不能替代 SDK 验收；本修订不宣称新 Backend 已实现。

## 0. 决策摘要与对 v0.1 的修订

根据新增约束，两种部署必须执行同一套业务工作流。推荐保持一个 `focus` 主仓库与业务主线，将 `focus-dsh` 定义为集成子项目和独立发布包，不再复制出长期分别演进的完整业务仓库。

架构上先解耦，交付上由现有 FOCUS 独立网页版先形成参考实现；DSH 在接口形成后尽早完成最小纵向验证，而不是等独立版全部完成才开始接入。后续两种部署共享工作流代码、方法资源、资产格式与验收用例，只在宿主和运行时适配层存在差异。

| v0.1 决策 | v0.2 替代决策 |
|---|---|
| 独立派生 `focus-dsh`，选择性同步业务改动 | 同仓共享业务实现；DSH 是集成目录与发布包，不是业务 fork |
| 现有 FOCUS 保留旧流程，DSH 执行新流程 | 两种部署都执行统一的新流程；旧版本用发布 tag 保留用于回滚 |
| 独立版只是新项目的 fixture／开发壳 | 独立网页版继续是正式生产交付，DSH 是另一种正式交付 |
| DSH 优先贯通完整产品 | 独立版承担主要功能交付；DSH 早期验证契约、随后完成原生集成 |
| 聊天统一归 DSH | 每个宿主维护其原生会话；FOCUS 共享业务绑定和可迁移的阅读资产 |
| 两个新版本始终必须使用不同格式、不同工作区 | 同一新 schema 可在兼容版本间停机切换宿主；仍禁止两个独立写入者同时写同一工作区 |
| 新版 Python Core 仅供 DSH worker 调用 | 同一 Python Core／Application 在独立 Host 内直接调用，在 DSH 中通过受管理 worker 调用 |

2026-09-21 阶段 0 grill 确认：忽略 v0.1，不继承其未见章节。需求以本文 v0.2、现有写作方法及后续明确确认的阶段记录为依据；上表仅保留决策演变背景。本文的 Topic Inbox、统一解析、博客、粗读、精读初始化准备和独立备注要求适用于两种部署。2026-09-26 阶段 5 Q19 修订：取消全部旧资产迁移，新版从空 `knowledge-base/` 开始，不再以 `workspace/` 命名数据目录；旧目录不参与新版运行。兼容新 schema 的本机宿主停机接管仍由阶段 6 验证，不能将其与已取消的旧数据迁移混同。参见 docs/adr/0017-start-fresh-in-knowledge-base.md。

## 1. 不变的产品闭环

```text
Topic / Inbox
  → 用户确认单个或批量处理
  → article-parser：Parse / Normalize / Metadata / Compose / Export
  → 发布可追溯 Bundle
  → article-blog：写作证据笔记 / Evidence Map / 中文细读长文 / 单文件 HTML
  → 粗读：围绕整篇原文自由提问、逐概念解释
  → 可选精读：规划 / 当前 Source 全 Plan 翻译与连贯性检查 / 就绪后阅读与明确授权推进
  → 两种阅读方式共同维护 Source 级独立阅读备注
```

解析失败、博客失败和问答失败是不同状态。解析成功后博客失败不得删除 Source 或要求重新上传。上传阶段不创建必须完成的全文翻译任务；进入精读才规划。2026-09-25 阶段 4 grill Q5–Q8 修订：初始化时准备当前 Source 整个 Plan 的译文并检查全文语境下的连贯性，全部就绪后才打开，以首次等待换取后续推进不被翻译打断；Topic 中不预译其他 Source。具体决定见 docs/requirements/v0.2/stage-4-reading.md。

Topic 只是 Source 的组织与标签关系；文章资产只有一份。`sanitized_title` 是路径名称，不是 Source 身份；解析 ID、Source ID、Bundle 版本各自独立。博客写作的 Reading Notes／Evidence Map 与用户阅读备注分开。

理解确认只控制当前概念的解释节奏；明确的 Continue Reading 意图才授权游标推进。阶段 3 grill（2026-09-25）明确双层记录：Source 级主动笔记只由用户明确记录意图触发，Chunk 推进或完成本篇时另存简短阅读进度记录；后者只依据用户明确表达记载理解，不作能力评价。问答默认结合例子解释、隐藏引用材料，内部仍校验原文证据。具体规则见 docs/requirements/v0.2/stage-3-discuss-notes.md。

## 2. 三层选择，而不是一个含糊的 backend 下拉框

### 2.1 应用宿主 Host

独立 Host 提供现有网页部署、HTTP／SSE 或其演进接口、上传、身份认证、资源服务和本地会话管理。DSH Host 提供原生插件加载、Web／Slots、Remote、Session 等宿主集成。

用户选择宿主，主要是在选择部署与交互方式。它不应改变 Topic、Bundle、Blog、Note 或 Reading Plan 的语义。

### 2.2 Agent Runtime

模型—工具循环由所选执行环境负责：现有 Codex App Server，拟接入的 OpenAI Agents SDK 或受限直接模型调用适配器、Pi，以及 DSH 原生 Runtime。

“OpenAI SDK”必须在实施 ADR 中区分普通模型客户端和 Agents SDK。普通客户端不等于完整 Agent Runtime；直接使用客户端就需要应用自己承担循环和工具管理。开放式问答优先复用已有运行时；固定输出任务可按需使用直接调用适配器，但不为此建设通用 harness。[S4]

每个 AI 子任务只能有一个权威模型—工具循环。DSH 原生部署不应再启动旧 FOCUS Host，也不应在 DSH 中通过另一个 SDK 启动第二个 DSH 实例。DSH 文档说明其 Python SDK 默认启动自己的 `dsh --profile sdk`，因此不能把它误当成调用现有 Web Host 的轻量函数库。[S3]

### 2.3 模型与凭据

模型提供商、具体模型、认证方式和运行时是不同配置。是否有 OpenAI 账号不直接决定必须选择哪一种 FOCUS 部署。ChatGPT 订阅与 API 计费分开；Codex 的 ChatGPT 登录与普通 API key 调用也不是同一路径。[S5][S6]

模型与解析器的凭据只进入所选适配器；切换运行时不能将旧服务的 token 或原生 session ID 交给新服务。未配置合法认证、缺少所需图像能力或缺少必要工具约束时，预检查应明确阻止对应任务，而不是静默降级。

## 3. 推荐共享边界

### 3.1 Core：知识资产与一致性

Core 负责 Source／Topic／Inbox／Bundle／Blog／Note／Plan／Cursor 的身份、关系、路径安全、版本、持久化与允许的状态转换。Core 不导入 OpenAI、Pi、DSH 类型，不包含品牌条件分支。

模型只返回候选结果，所有正式产物由 Core 校验后提交。模型输出“已经保存”不构成成功事实。Core 提交必须携带预期版本、请求 ID 与写入方身份；取消后的迟到结果不得提交。

### 3.2 Application：共用业务工作流

Application 负责业务步骤：何时启动解析、生成博客、读取证据、编排当前 Source 全 Plan 的翻译准备与连贯性检查、整理备注、请求用户授权和提交结果；同时管理业务 Run／Step、重试边界与恢复策略。

这部分也必须共享，不能独立版写一份 Python 流程，DSH 再写一份原生 Workflow 来模仿。固定业务流程在 Application 中只实现一次；Runtime 可以自主进行一个受限 AI 步骤内的证据检索与推理。

业务 Run 并不等同于 Runtime turn。DSH Session 事件或 Pi／Codex 的完成事件可以结束一次 Runtime 调用，但只有 Application 检查业务结果并成功提交，才完成业务步骤。

### 3.3 Methods：统一的方法资源

`article-parser`、`article-blog`、`focus-discuss`、`focus-map`、`focus-read` 和笔记提炼准则由一个版本化资源包管理。博客 reference 文档只维护一份，不另建 DSH／Pi／Codex 私有规则副本。

适配器可以把同一资源转换成系统提示、按需加载的 Skill 或 Runtime 的技能注册，但不能改变业务要求。原生发现目录只作为生成／安装位置，不作为第二个编辑源。开发辅助 Skills 与产品运行 Skills 隔离。

结构化输出方式不同，可以由适配器转换；最终 schema、证据校验、有限修复策略与发布门槛仍由共用层决定。

### 3.4 Presentation：共用投影，宿主各自装配

共享 Inbox 状态、Blog、单 Chunk、Notes 编辑器等纯组件与 View Model。独立 Host 与 DSH 各自负责导航、流传输、认证与 Session 装配，不要求两个 UI 的 DOM 完全相同。

DSH 通过原生 Client／Slots／Remote 集成，不通过 iframe 包一层旧网页，也不导入其他插件的内部 UI 实现。[S8] 独立网页版不要求用户安装 DSH。

## 4. 建议代码目录

以下是目标目录，不要求一次性搬完全部旧文件。

```text
focus/
├── python/
│   └── focus/
│       ├── core/                   # 领域对象、规则、仓储、资产提交
│       ├── application/            # 两种宿主共用的业务工作流
│       │   ├── ingest.py
│       │   ├── blog.py
│       │   ├── discuss.py
│       │   ├── reading.py
│       │   └── notes.py
│       ├── ports/                  # Runtime / Parser 等宿主无关接口
│       └── worker/                 # 给 DSH 等非 Python 宿主的受控桥接
├── methods/
│   ├── article-parser/
│   ├── article-blog/reference/
│   ├── focus-discuss/
│   ├── focus-map/
│   └── focus-read/
├── contracts/                      # schema、事件、协议与测试样例
├── adapters/
│   ├── runtimes/
│   │   ├── codex/
│   │   ├── openai/
│   │   ├── pi/
│   └── parsers/
│       ├── mineru-cloud/
│       └── mineru-local/           # 单独能力验收；不能默认为已接通
├── host/                           # 正式的独立 Web Host，逐步变薄
├── ui/
│   ├── packages/focus-contracts/
│   ├── packages/focus-ui/
│   └── apps/standalone/            # 正式产品入口，不是 fixture-only
├── integrations/
│   └── dsh-focus/
│       ├── host/                   # 原生 Service、Tools、Remote、Runtime Adapter
│       ├── client/                 # Slots、会话绑定、投影装配
│       └── bundle/                 # 独立可安装的 DSH 发布包
├── profiles/                       # 可提交的脱敏配置示例
├── tests/
│   ├── core/
│   ├── workflows/
│   ├── runtime-contract/
│   ├── host-conformance/
│   ├── migration/
│   └── e2e/
└── docs/
```

Standalone 直接调用 Python Application；DSH TypeScript Host 通过受管理 worker 调用相同实现。Python Application 在 AI 步骤中通过 RuntimePort 请求 DSH Host 执行一个受限任务，并接收标准化事件和结果。桥接可以采用带关联 ID 的双向 RPC；Core 与 Application 在等待模型时不持有长期写锁。

这是一个业务服务进程，不是第二个 Agent harness。以后有实测理由可以调整语言与进程布局，但不得让同一业务出现两个实现。

`host/service.py` 的业务编排逐步迁入 Application；旧 `Backend` 可以先通过桥接适配新的 RuntimePort，不必第一天全面重写。已有 Reader UI、校验修复、原子写入与原文引用能力优先复用。[S1][S2]

仓库外本地配置可以表达家用云解析与公司本地解析的差异，业务代码不按环境分叉。禁止提交 token、授权目录与私人 workspace。

## 5. 最小 RuntimePort 与所有权

先定义满足当前需求的接口，不建设表达所有 Agent 功能的万能接口。

| 对象／操作 | 语义 |
|---|---|
| `capabilities()` | 报告已验证的工具约束、流式、图像、取消、原生恢复等能力 |
| `execute(task_spec)` | 执行一个受限 AI 任务；返回 handle，产生标准化事件／结果 |
| `cancel(handle)` | 请求中断并报告实际终止状态；业务层立即禁止该 attempt 后续提交 |
| `TaskSpec` | 任务 ID、attempt ID、方法版本、来源版本、输入／证据、允许工具、输出契约、预算 |
| `TaskResult` | 候选正文或结构化结果、使用的证据引用、终态、错误信息和可获得的用量 |
| 原生会话引用 | 带 Runtime 类型的 opaque handle；只由对应 Adapter 解释 |

不要求所有 Runtime 原生具有相同的 JSON schema 输出机制。可以通过受控输出工具或文本解析加公共校验来实现同一终态契约；达不到所需能力则标为不支持，不能返回“成功”。

Pi SDK 提供自定义集成、会话、事件与中断等能力，但具体版本和工具配置必须验证；不能假定换包名即可兼容。[S7]

### 5.1 业务与 Runtime 各管什么

- Application／Core 管业务阶段、产物、游标、备注、幂等和断点。
- 所选 Runtime 管一次 AI 执行内部的模型调用、工具循环、原生消息与其私有恢复状态。
- Host 管浏览器接入、用户会话、网络传输和客户端状态投影。

上下文选择策略由共享 Application／Methods 定义：当前 Source、Bundle、任务范围、必要原文、相关备注和有限讨论背景。Adapter 决定如何把它传给原生 Runtime。切换 Runtime 后，使用这些可移植业务信息开启新会话，不承诺完整恢复另一 Runtime 的内部上下文或压缩状态。

### 5.2 完成与取消

每次 attempt 有独立 ID，并绑定运行时／模型配置。`Runtime completed` 只表示执行结束；`Artifact committed` 才表示业务成功。两类事件不得混用。

取消时先记录业务提交禁令，再调用 Runtime 中断；若外部服务无法立刻中断，UI 显示实际状态，不接收该 attempt 的迟到产物。已经提交的合法阶段产物保留。不能保证撤销已经发生的远端计费。

恢复时从最后已提交业务步骤继续；不盲目重放可能已发生的写操作。切换 Runtime 采用新的 attempt／会话，不伪装成原生续跑。

## 6. 开发顺序与阶段出口

### P0：先统一决策、对象和验收

在现有仓库建立短期集成分支，记录旧版发布 tag；不新建完整业务 fork。更新 CONTEXT／ADR，标明新流程同时适用于 Standalone 和 DSH。确定资产 schema、版本、方法包、RuntimePort、Run／Step 与 Host 操作契约。

出口：同一份样例能表达未精读但已有博客和备注的 Source；界面状态不强制包含当前 Chunk；取消、重试、推进和写入所有权无歧义。

### P1：抽取最小共享层，保留现有能运行的入口

将 `.agents/core` 中的领域实现逐步移为正常 Python 包；先保留薄包装防止迁移造成无关破坏。将 `HostService` 中的解析／博客／阅读／备注编排移到公共 Application。统一方法资源与工具 schema。

采用已能在目标环境真实工作的一个后端作为参考 Adapter。从公开主干看可复用的是 Codex 路线；本地若已有通过验证的 OpenAI SDK 路径，可复用同一接口，不要求先替换后端。

出口：共享工作流可脱离浏览器，以 fixture Parser／Runtime 运行；旧数据保护、取消和幂等测试通过。没有为抽象而新增通用工作流引擎。

### P2：最小产品闭环，同时完成 DSH 适配探针

独立网页版先贯通“一个 Inbox 文件 → Bundle → 博客 → 一次整篇问答 → 一条独立备注”。外部服务用真实凭据验收，失败状态同样验收。

在此阶段，DSH 同时只实现最小切面：插件 build／pack／install／boot；无聊天会话也能进入知识库；通过原生 Host 接口调用公共 Application；执行一个受限 AI 步骤；回传结果并处理取消和卸载。使用隔离的测试 workspace，不访问私人资料。

出口：至少一个相同的受控场景通过 Standalone 和 DSH 运行，调用的是同一工作流实现。若 DSH 的 Session、工具或 Remote 约束与接口冲突，先修正接口，不在 DSH 增加私有业务分支。

### P3：优先交付独立网页版的新流程

完善 Topic CRUD、单个／批量 Inbox、PDF／HTML 实际解析、Evidence Map 与博客发布、粗读问答、全 Plan 初始化准备后进入的精读、显式保存的 Source 笔记与被动阅读进度记录、编辑撤销与失败恢复。从空 `knowledge-base/` 验证初始化与完整新流程，重启保留新增资产；不交付旧数据迁移或迁移 dry-run。

这一阶段 DSH 不必拥有全部美化界面，但持续运行已经接通的契约和最小流程测试，防止接口重新向独立 Host 偏移。

出口：用户可通过独立网页完成新流程；无需先安装 DSH；没有旧上传全文翻译规则继续参与新版执行。

### P4：完成 DSH 原生交付

接入完整知识库、Inbox、Blog、Notes 与单 Chunk 视图；复用公共组件和投影，使用 DSH 原生导航、Session、工具、Remote 与生命周期。原生工作流组件可以展示或触发公共业务 Run，但不能复制其状态机。

出口：两种 Host 通过同一业务验收套件；干净安装与打包验证通过；移除 DSH 集成不会影响 Standalone。

### P5：逐个扩展 Runtime 并发布能力矩阵（后续扩展已跳过）

2026-09-26 范围修订：以阶段 6B 的 Codex／DeepSeek SDK Backend、统一设置和共同业务验收为本轮交付范围。[阶段 7 覆盖核对](docs/requirements/v0.2/stage-7-runtimes.md) 确认公共 Runtime 要求已由 6B 承接；其余 OpenAI、Pi 适配器暂无独立必要需求，阶段 7 已跳过，不另建能力矩阵产品，不作为 v0.2 发布条件。以下保留为未来按需扩展的原则，不构成本轮实施承诺；6B 的未完成实现及验收仍归 6B。

OpenAI、Pi 按凭据、接口可用性与实际优先级逐个接入；不需要全部完成才交付 P3。每个 Adapter 必须通过工具限制、来源隔离、取消、流式终态、结果校验与业务幂等测试。

不能仅用 fake SDK 测试作为真实后端已支持的依据。

### 开发中的约束

同一功能变更若必须分别修改 Standalone 和 DSH 的业务代码，应触发架构评审。宿主 API、组件装配或事件转换的修改允许分开；解析后的步骤选择、笔记内容准则、游标推进规则不允许各写一套。

## 7. 一致性怎样验证

一致性不等于不同模型逐字输出相同。至少需要四层验证：

**源码与版本一致。** 使用同一个工作流实现、方法资源版本、schema 与校验器。发布包记录 FOCUS 版本和 DSH 兼容基线。

**确定性行为一致。** 同一输入配 fixture Parser／Runtime，通过两个 Host 执行后比较规范化的业务状态、产物、引用与游标；忽略时间、随机 ID 和原生 Session ID 等运行实例差异。

**安全与失败语义一致。** 未确认 Inbox 不得外发；普通问题不推进；重复请求不重复写入；取消后不提交迟到结果；博客失败保留 Bundle；重读不删除备注；所有写操作经 Core。

**真实模型质量达到同一门槛。** 分别检查博客方法深度、图表证据、引用可追溯性、解释粒度和备注纠错准确性。不通过质量门槛的后端不得标称完整支持；不能以使用同一个 Skill 为理由忽略差异。

| 用例 | 应当一致的结果 |
|---|---|
| 未确认的 Inbox 文件 | 不开始远端解析或模型处理 |
| PDF／HTML 成功解析 | 发布同一契约的 Bundle；不进入全文翻译 |
| 博客生成失败 | Source 保留，只重试未提交的博客阶段 |
| 粗读纠正 A→B→C 为 A→D→C | 不自动保留未接受纠正；用户明确要求后保存简洁笔记，作为用户理解保存时须有明确接受表达，不推进精读 |
| 明确继续一次 | 游标仅推进一次；重放请求不重复推进 |
| 后端返回无效引用／不合法结构 | 共用校验失败，不发布正式产物 |
| 取消后远端仍返回结果 | 标记已取消的 attempt 无法提交 |
| 重建精读计划 | Source 级 Notes 和历史引用仍可访问 |
| 更换 Runtime 后开启新会话 | 读取同一篇 Source 的业务状态，不误用旧原生 session ID |
| 第二个 Host 尝试写同一工作区 | 被写入租约／锁拒绝，而不是竞争写入 |

## 8. 切换的支持范围

同一宿主内，允许在任务空闲时选择新的 Runtime，用于后续任务或新会话。运行中的任务不热切换；先停止，确认业务断点，再由新 Runtime 创建新的 attempt。不会静默改用另一个付费模型或外发到另一个服务。

宿主之间切换采用停机接管：检查兼容版本与 schema → 完成或停止任务 → 释放写入方 → 新 Host 获取独占写入权 → 从业务状态恢复。兼容的新版本无需重新解析已有资料。

原生聊天和执行轨迹继续保留在原宿主或 Runtime；Source、Blog、Note、Plan、Cursor 可继续使用。不把原生会话无损迁移或执行中途热切换列为第一版目标。必要时新会话读取经过选择的原文、备注和可移植讨论摘要；这不等于原生 Session 恢复。

单 Knowledge Base 只允许一个权威写入者，新版数据目录名为 `knowledge-base/`。首版适用单机本地持久目录，不以共享网络盘或云盘双向同步代替并发控制。未来如需两种 UI 同时写，必须共享唯一 Application Service，而不是两个进程直接写相同文件。

## 9. 当前核查与局限

FOCUS 基线仍为 `1de307f51c9bd674b8c7efc053e57e5e5b777276`。其 `Backend` 已有 Session／turn／工具／中断的统一事件词汇，可作为桥接起点；但接口存在不代表业务流程已完成解耦。[S1]

本次核查了 DSH 的宿主／运行时架构与 Pi SDK、OpenAI 官方说明；未执行工程修改、真实部署或模型验收。本文所有新目录、RuntimePort 和阶段出口都是设计提议。

博客写作方法以 `methods/article-blog/reference/` 下的方法副本为输入，按 v0.2 阶段讨论更新；MinerU 实际 PDF／HTML 接口行为、真实图像分析能力仍按功能验收补齐。它们不影响先建立共享业务与宿主边界，但会影响相应功能是否可以发布。缺失 v0.1 不再是需求或验收阻塞。

## 10. 参考资料

[S1] FOCUS `host/backends/base.py`，固定提交：
https://github.com/kongxiangcong/focus/blob/1de307f51c9bd674b8c7efc053e57e5e5b777276/host/backends/base.py

[S2] FOCUS `host/service.py`，固定提交：
https://github.com/kongxiangcong/focus/blob/1de307f51c9bd674b8c7efc053e57e5e5b777276/host/service.py

[S3] DSH Architecture：
https://github.com/deepseek-ai/deepseek-harness/blob/ddefc45fbc7f8e46dd73185e68295696d1297887/docs/architecture.md

[S4] OpenAI Agents SDK，Agents SDK 与直接 Responses API 的职责区别：
https://openai.github.io/openai-agents-python/

[S5] OpenAI 官方，ChatGPT 与 API 独立计费：
https://help.openai.com/en/articles/8156019-i-want-to-move-my-chatgpt-subscription-to-the-api

[S6] OpenAI 官方，Codex 认证方式：
https://developers.openai.com/codex/auth/

[S7] Pi 官方 SDK 文档，本次读取旧地址重定向后的当前项目资料；实施时重新锁定版本：
https://raw.githubusercontent.com/badlogic/pi-mono/main/packages/coding-agent/docs/sdk.md

[S8] DSH Web Client architecture：
https://github.com/deepseek-ai/deepseek-harness/blob/ddefc45fbc7f8e46dd73185e68295696d1297887/docs/subsystems/web-client.md
