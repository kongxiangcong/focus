# Focus Reader 原型生成工具与工作流调研

> 调研日期：2026-08-30  
> 证据范围：只使用产品官方文档、官方仓库，以及本仓库当前领域文档；价格、席位、配额和 beta 状态均可能变化，采用前需再次现场确认。  
> 调研问题：能否让用户只用自然语言描述沉浸式阅读体验，生成多个可运行的 Focus Reader UI 原型供选择；`mattpocock/skills`、Figma 与代码原型工具各应处于什么位置。

## 1. 结论

**可以，而且当前最合适的第一步不是先画一套完整 Figma，也不是把 Focus 接入某个云端 app builder，而是在本仓库旁边做一个只读、fixture 驱动、可在浏览器切换的代码原型。**

推荐直接采用 `mattpocock/skills` 的 `prototype` UI 工作流：用一段自然语言 brief 生成默认 3 个、最多 5 个**结构和交互时序真正不同**的方案，在同一个原型路由通过 `?variant=`、浮动切换栏和左右方向键切换。用户不需要先掌握设计术语；可以先描述感受、节奏、想保留和不想看到的东西，再通过真实渲染指出“要 B 的进入节奏、C 的历史层级”。[`prototype` 官方说明](https://github.com/mattpocock/skills/blob/main/skills/engineering/prototype/SKILL.md)及其 [UI 分支](https://github.com/mattpocock/skills/blob/main/skills/engineering/prototype/UI.md)正是为这个判断问题设计的。

对 Focus，应把原型问题写成：

> 哪一种阅读空间、信息层级和推进时序，最能让当前 Reading Chunk 清晰出现、历史内容低干扰退场，同时让对话输入仍然自然可用？

Figma 的合理位置是**第二阶段的设计探索、精修和交接**，不是 Focus 状态或实现的权威：

- 如果只想快速看常见页面布局，Figma First Draft 可从文字生成可编辑 wireframe/design；
- 如果要验证“旧字退灰、新 Chunk 渐亮、控件隐退”等时间维度，Figma Make 的 code-backed functional prototype 比静态 frame 更合适；
- 如果最终需要代码与画布往返、读取 tokens/components 或把代码界面写回可编辑 Figma primitives，再接 Figma MCP；
- 如果用户自己评审且代码就是最终媒介，Figma 可以完全跳过，避免维护第二份视觉权威。

## 2. Focus 不可被原型工具改写的边界

本仓库术语与状态边界已经明确：Reading Plan 定义有序的 Reading Chunks；Cursor State 是极小持久化对象；Reading Cursor 只引用当前 Chunk；只有 Continue Reading 能移动 Cursor；宿主保存原始对话，Focus 不保存聊天 archive。[`CONTEXT.md`](../CONTEXT.md)与 [ADR-0001](../docs/adr/0001-replace-paper-learning-with-reading-workspace.md)是权威。

DSH 集成也已经限定为薄 Adapter：它投影现有深模块接口，不建立第二套领域状态，不复制 Workspace 权威；原始对话留在宿主 Session。[Phase 2 DSH Integration Contract](../docs/FOCUS_Phase2_DSH_Migration_and_Deployment.md)

因此 UI 原型必须遵守以下约束：

1. **Fixture-first**：只用合成 Reading Chunk、Source Anchor、翻译、图、公式、表格和对话占位；不读取私人 Workspace，不上传真实来源。
2. **无第二状态**：原型只保留浏览器内存中的视觉演示状态，例如 `activeVariant`、`animationPhase`。它不创建 cursor database、localStorage 进度、事件账本或聊天 archive。
3. **Continue 只是演示**：原型可在固定 fixture 序列内模拟一次推进，用来判断动画；不得写 `state.json`。正式实现的 Continue 必须委托 Focus Core，并携带 Core 所需的当前 Plan/Chunk 回执。
4. **Chunk 是单位**：视觉上允许把当前 Chunk 与围绕它的宿主对话投影为一个临时“episode”，但 episode 不是新领域对象或持久化权威。
5. **薄宿主接口**：正式 Reader 只消费窄 projection/command contract；Standalone fixture adapter 与后续 DSH Adapter 都实现该接口，Reader UI 不直接访问 Workspace 文件或 DSH Session 内部结构。
6. **原型不是生产代码**：选择结果是“视觉结构、motion tokens、交互规则和可访问性约束”；胜出方案需按正式质量门重新实现，不直接把无测试的原型晋升为产品。

建议的最小方向不是先决定目录树，而是先固定一条依赖关系：

```text
Focus Core (唯一 Reading Cursor / Reading Chunk 权威)
  -> Reader projection + Continue command
  -> Standalone Fixture Adapter（原型）或薄 DSH Adapter（后续）
  -> 同一个 host-agnostic Reader UI
```

## 3. `mattpocock/skills` 能提供什么

该仓库不是一个 UI 生成模型或托管平台，而是一组“小、可组合、可修改”的 agent 工作纪律；Codex 等 agent 可通过 `npx skills@latest add mattpocock/skills` 选择性安装。仓库强调保留开发者控制权，而不是由一套大流程接管项目。[官方 README](https://github.com/mattpocock/skills)

对本任务最有价值的是 `prototype`：

- 先把问题分为逻辑/状态问题和 UI 外观问题；Focus 当前属于 UI 分支。
- UI 默认生成 3 个变体，最多 5 个；变体必须在布局、信息层级、主操作或时序上有实质差异，不能只是换颜色。
- 多个方案挂在同一路由，使用 `?variant=A|B|C`、浮动底栏和键盘左右键切换，URL 可分享、刷新后仍指向同一方案。
- 原型默认无持久化、无生产抽象、无真实 mutation；状态留在内存，mutation 指向 stub。
- 用户选定后，把结论写入 issue/ADR；正式代码吸收决策，完整原型作为 primary source 留在不合并 main 的 throwaway branch。

来源：[`prototype/SKILL.md`](https://github.com/mattpocock/skills/blob/main/skills/engineering/prototype/SKILL.md)、[`prototype/UI.md`](https://github.com/mattpocock/skills/blob/main/skills/engineering/prototype/UI.md)、[工作流说明](https://github.com/mattpocock/skills/blob/main/docs/engineering/prototype.md)。

它不能自动保证审美质量。最终质量仍取决于：同一份代表性 fixture、足够不同的设计假设、浏览器中的真实动效、截图/录屏反馈，以及用户对方案的选择。对“高级感”这种难以言传的目标，这种对照实验比继续抽象讨论更有效。

## 4. 建议生成的 4 个方案

第一轮建议生成 4 个，而不是一次做满 5 个。所有方案使用**同一份 fixture、同一段对话入口、同一 Continue 脚本和相同可访问性条件**；区别只在视觉结构与推进时序。

| 方案 | 核心假设 | 当前 Chunk | 历史内容 | 对话入口 | 主要风险 |
|---|---|---|---|---|---|
| A：舞台聚光 | 单一视线焦点最安静 | 居中、窄列、弱径向亮度 | 上方只留 1–2 层低对比文本 | 底部极窄 command dock | 过度“展示化”，长 Chunk 容量不足 |
| B：连续余晖 | 保留空间连续性可减少断裂感 | 连续文流中固定在视口 42–46% | 按距离降低颜色与 opacity | 输入框随闲置淡出 | 容易像普通滚动阅读器，焦点不够强 |
| C：逐层显影 | 信息按语义块出现可提升节奏感 | 段落/公式/图逐步显影，关键块轻强调 | 完成块沉入石墨灰背景 | 对话以当前块为锚 | 若显影过慢会妨碍快速阅读，也可能误导“关键内容”由谁判定 |
| D：双语镜面 | 原文与译文的空间关系是主要负担 | 原文/译文不对称双列或可翻面 | 历史只保留较细的一侧轨迹 | command dock 横跨两列 | 窄屏与长公式复杂，可能提高而非降低干扰 |

这里的“关键内容渐进高亮”必须分两种：

- **视觉结构高亮**：当前 Chunk 内标题、公式、figure、引用等根据已有语义节点顺序出现；原型可以安全演示。
- **内容重要性高亮**：判断哪些句子“关键”属于解释或生成结果，不能由 CSS/动画擅自猜测。若要测试，只能把 fixture 中显式标注的 `emphasis` 当输入；未来仍由 Focus/宿主的正式 contract 提供，不由 Reader 自己推断并持久化。

## 5. 从自然语言到选择结果的流程

### 第 1 步：把“感觉”转成最小 brief

用户只需回答或自由描述四类信息，无需使用设计术语：

- 想感受到什么：安静、克制、黑场、电影字幕感、纸张感、空间连续性等；
- 哪些内容绝不能消失：当前 Chunk、上一个 Chunk、Source/章节、进度、对话框；
- 哪些东西最讨厌：卡片墙、霓虹、玻璃拟态、过强 blur、粒子抢正文、控件常驻；
- 推进应是什么节奏：旧内容退灰、新内容进入、关键块显影、何时允许再次 Continue。

Agent 将其整理为一页 prototype brief，但不先写完整 PRD。

### 第 2 步：固定可比较 fixture 与动作脚本

一份合成 fixture 至少覆盖：中英文混排、长短段落、公式、表格、图片与 caption、代码块、相关术语、当前/上一个/上上个 Chunk，以及一轮解释对话。固定动作脚本：进入阅读 -> 聚焦当前 Chunk -> 提问/解释 -> Continue -> 新 Chunk 稳定。四个方案不得各自修改内容或推进语义。

### 第 3 步：一次生成 3–5 个结构性变体

在一个显式命名为 prototype 的路由实现变体，通过 `?variant=` 与浮动 switcher 切换。允许各变体独立布局，不要抽出一个共享 Layout 把差异抹平；只共享 fixture、领域类型和原型 switcher。所有 mutation 为 stub，刷新不恢复假 cursor。

### 第 4 步：浏览器对照评审

每个变体执行同一脚本并录制短屏幕片段。建议按 1–5 分评价：

1. 进入 5 秒内能否自然定位当前 Chunk；
2. 历史内容是否仍提供上下文但不抢注意力；
3. Continue 的 550–800ms 过渡是否连贯、不跳动；
4. 中英、公式、表格和图是否仍可读、可选中；
5. 对话入口是否可发现但不过度常驻；
6. 窄屏、键盘与 `prefers-reduced-motion` 是否可用；
7. 是否出现“模板化 AI 网站”特征。

用户可选完整方案，也可以明确“B 的信息层级 + C 的显影节奏”。不要按总分机械决定；先记录淘汰原因，再做最多一轮混合方案。

### 第 5 步：固化决策，重写正式切片

在 issue/ADR 中只保留胜出的信息架构、motion tokens、状态转换、适配边界、fixture 验收脚本和拒绝项。原型留在 throwaway branch；正式实现从 Focus Core seam 写合约测试，再用 Standalone Adapter 接 fixture。后续接 DSH 时只新增薄 Adapter，不重做 Reader，也不迁移原型状态。

## 6. Figma 在流程中的准确位置

### 6.1 First Draft：早期常规布局探索

First Draft 能把文字描述转成可编辑 wireframe/design，提供主题预览，并允许继续用 prompt 或颜色、排版、间距、圆角控件修改。官方建议复制 frame 来比较 riffs。但它基于 Figma 自建的常见 web/mobile pattern libraries；非常规界面可能表现不佳，且旧 First Draft 不能使用自己的 design system。自 2026-05-20 起，新 Figma agent 正作为该能力的新入口逐步 beta rollout。它要求付费计划和文件编辑权限。[官方说明](https://help.figma.com/hc/en-us/articles/23955143044247-Use-First-Draft-with-Figma-AI)

**对 Focus 的角色**：可快速试字体层级、留白、顶栏/command dock 布局；不应被用来判断精细推进动画，也不是首选。

### 6.2 Figma Make：交互与运动探索

Figma Make 是 prompt-to-app 工具，可从自然语言、图片或现有 Figma design 生成 code-backed functional prototype/web app/interactive UI；支持预览、代码编辑、继续对话修改，并可把 Make preview 复制成可编辑 Design layers。官方提示应先做 layout、再加 functionality，并分步迭代，而不是一次描述整个复杂应用。[Figma Make FAQ](https://help.figma.com/hc/en-us/articles/31722591905559-Figma-Make-FAQs)、[创建 Make 文件与 prompting 建议](https://help.figma.com/hc/en-us/articles/31304485164695-Create-a-Figma-Make-file)、[复制为 Design layers](https://help.figma.com/hc/en-us/articles/35060759685015-Copy-a-Figma-Make-preview-as-design-layers)

**对 Focus 的角色**：用户如果更喜欢在设计画布中点选、批注和调色，可用它对胜出方向做一轮动效/视觉精修；但仍使用 fixture，不接私人 Workspace。

当前需注意：

- 完整 Figma Make 主要面向付费计划 Full seat；其它 plan/seat 可试用但创建、分享、发布权限不同；组织还需启用 AI。
- 每个 prompt 使用 AI credits，消耗量随模型、任务复杂度与上下文变化，事前不能准确预测；credits 按月重置且不结转。[AI credits 官方说明](https://help.figma.com/hc/en-us/articles/33459875669015-How-AI-credits-work)
- 普通 Make -> GitHub 是 Make 创建仓库后的**单向 push**，不是把现有 Focus repo 作为双向源；GitHub 修改不会回流，下一次 push 可能覆盖。直接处理本地代码库的新工作流截至调研日仍是少量用户 closed beta。[GitHub push 限制](https://help.figma.com/hc/en-us/articles/35463818346647-Push-from-Figma-Make-to-GitHub)、[Make in local codebase beta](https://help.figma.com/hc/en-us/articles/40775535020695-Make-in-your-local-codebase)

因此不要把普通 Figma Make 项目直接同步进 Focus 的 `main`。

### 6.3 Figma MCP：代码与画布之间的桥

Figma MCP 当前可向 agent 提供 frames、components、variables、layout 等结构化设计上下文；能从选中 frame 生成代码、检索 Make resources，也已支持 agent 创建/更新 native Figma frames、components、variables 与 auto layout。Figma 官方推荐多数用户使用 remote server；Codex 在官方支持的 client 列表中。[Figma MCP 官方介绍](https://developers.figma.com/docs/figma-mcp-server/)

这里需要澄清：“Dev Mode MCP”不是唯一形态。桌面 MCP 的启用入口在 Figma Desktop 的 Dev Mode 中，但 remote MCP 功能更广、无需桌面 app，是官方首选。最终代码由所连接的 coding agent 生成，不是 MCP server 自动产出完美代码。

写 canvas 能力截至调研日仍为 beta；官方帮助页称付费 Full/Dev seat 可用，Dev seat 在 drafts 外只有只读权限，并且未来会转为 usage-based paid feature。读取工具还有依 plan/seat 的日/月和每分钟限额，且 Figma 保留调整权利。[开始使用 Figma MCP](https://help.figma.com/hc/en-us/articles/39216419318551-Get-started-with-the-Figma-MCP-server)、[权限与 rate limits](https://developers.figma.com/docs/figma-mcp-server/rate-limits-access/)

**对 Focus 的角色**：当胜出方向需要设计师式精修或形成 token/component library 时，让 coding agent 读取/写回 Figma；它不应成为 Cursor、Chunk 或推进命令的中间层。

## 7. 当前代码原型工具比较

| 路线 | 自然语言与多方案能力 | 与现有 Focus repo 的关系 | 权限/成本（2026-08-30） | 结论 |
|---|---|---|---|---|
| **本地 coding agent + `prototype` skill** | 明确要求同一路由 3–5 个结构性变体；浏览器可直接判断 motion | 可在本地 fixture 下工作；最容易遵守 Core/Adapter seam；无云端项目副本 | 无额外原型平台费；仍消耗已有 agent/model 用量 | **首选** |
| **Figma Make** | 文字/图片/design -> functional prototype，可继续 prompt、点选与设计精修 | 普通 GitHub 流是新建仓库单向 push；本地现有 repo 流仍 closed beta | 完整能力依 plan/seat；AI credits 变动；组织可关闭 AI | **第二阶段可选** |
| **v0** | 自然语言生成 working app，可对话迭代、Design Mode 点选修改；适合 React/Next/Tailwind | 可导出或使用 GitHub 工作流，但仍应在隔离原型项目/分支使用 | Free 当前含有限 credits；Plus $30/user/月、Business $100/user/月；生成按 credits；价格需复核 | **最佳外部代码备选** |
| **Replit Agent** | 文字生成 app；有 preview、Design Canvas、Visual Editor、Plan/Build modes；MCP 可从外部 client 创建/更新 app | 云端 Replit App；适合分享，不适合直接成为 Focus 私人数据运行时 | Starter 有 daily cap/Lite；Full build 与 Plan Mode 需 Core/Pro；Agent 按 effort 计费 | 仅在需要托管分享时考虑，**只用 fixture** |
| **Lovable** | 自然语言生成全栈 web app；可迭代、发布 | 代码起初在 Lovable；可连 GitHub 双向 sync，但不能导入已有 GitHub repo，只能从 Lovable 创建/导出 | Free workspace 官方当前 5 daily credits；付费与任务消耗需现场复核 | 对现有 Focus repo 迁移成本较高，不优先 |
| **Bolt** | 单 prompt 生成 working web/mobile app，有 preview、editor，可对话修改 | 云端独立项目；适合快速孤立 demo | 免费额度和 token 消耗随计划变化；只支持 JS-based backend | 可做一次性备选，不胜过本地 flow/v0 |

来源：

- v0：[Quickstart](https://api2.v0.dev/docs/quickstart)、[Text prompting](https://api2.v0.dev/docs/text-prompting)、[Pricing](https://api2.v0.dev/docs/pricing)
- Replit：[自然语言 app/MCP](https://docs.replit.com/platforms/mcp-server)、[Agent billing](https://docs.replit.com/billing/ai-billing)
- Lovable：[官方介绍](https://docs.lovable.dev/introduction/welcome)、[GitHub integration 与既有 repo 限制](https://docs.lovable.dev/integrations/github)、[workspace credits](https://docs.lovable.dev/features/workspace)
- Bolt：[QuickStart](https://support.bolt.new/building/quickstart)、[prompting guidance](https://support.bolt.new/best-practices/prompting-effectively)

两项看似相关但截至调研日不应进入新项目候选：

- **GitHub Spark**：官方公告从 2026-08-04 起不接受新用户或创建新 app，既有用户需导出代码。[GitHub 官方说明](https://docs.github.com/en/copilot/concepts/spark)
- **Firebase Studio App Prototyping agent**：官方已于 2026-06-22 禁止创建新 prototyping workspace，并引导迁往 Google AI Studio/Antigravity。[Firebase 官方迁移说明](https://firebase.google.com/docs/studio/migrating-project)

## 8. 明确推荐

现在执行以下单一路径：

1. 用本地 coding agent 调用 `prototype` UI 流，先生成上述 4 个 fixture-only 方案；
2. 同一路由、同 fixture、同动作脚本，在真实浏览器中比较，而不是各工具各做一份不可比的 mockup；
3. 用户选定或拼合一次，记录胜出的信息层级、动效时序、reduced-motion 和内容承载边界；
4. 如用户仍难以在代码上进行视觉微调，再把胜出方向带入 Figma Make/Design；需要结构化 design context 或代码/画布往返时才启用 Figma MCP；
5. 正式实现重新建立测试和错误处理，通过 Standalone Fixture Adapter 验收；DSH 部署阶段只增加薄 Adapter，Focus Core 继续拥有 Reading Cursor/Reading Chunk，宿主对话继续负责推进与解释。

不建议同时在 Figma、v0、Replit、Lovable 各生成一套。模型和默认组件库差异会污染比较，用户最后难以判断自己选择的是阅读体验还是某个平台的模板风格。只有本地首轮无法产出足够不同且可运行的方案时，才用 v0 做一次外部 challenger；Figma 则服务于精修与交接，而不是另建产品路径。

## 9. 未决项与下一轮验证

- 本仓库当前还没有被本次调研验证过的 Web runtime、UI route 或 DSH Adapter；本文是工具/流程决策，不是实现或 live acceptance。
- Figma agent、Make local-code workflow、MCP write-to-canvas 都在快速 rollout/beta；账户、地区、组织 AI 开关、seat 与 file permission 会决定实际可用性。
- v0、Replit、Lovable、Bolt 的 credits、价格、隐私和数据训练选项会变化；任何真实 Source、私人 Workspace 或对话在上传前都需单独确认权限与条款。本轮比较只允许合成 fixture。
- 第一个浏览器原型应先回答“布局与推进时序”，不要同时实现 WebGL 粒子、真实 Markdown 安全链、DSH 接入和生产数据；粒子应在胜出结构证明安静可读后再作为受控 challenger 加入。
- 需要在真实的中英文、公式、表格、图片、长 Chunk 和 `prefers-reduced-motion` fixture 上做视觉验收；仅看首屏截图不能证明沉浸阅读体验。
