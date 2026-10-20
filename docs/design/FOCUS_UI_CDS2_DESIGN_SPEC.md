# FOCUS UI 全面重构方案：对齐 open-claude-ui

日期：2026-10-16  
状态：调研完成后的设计提案；尚未实施、尚未完成视觉验收。  
本轮交付：独立方案文档。应用代码、依赖、构建与运行服务均不在本轮变更范围。

## 1. 设计结论

建议全面采用 open-claude-ui 所描述的 CDS 2.0 视觉语言，重构 FOCUS 工作台的导航、知识库、阅读流、讨论输入区、资料抽屉、任务反馈、设置和首次进入页面。目标是让这些页面具有同一套表面层级、字阶、控件尺寸、边框规则、焦点反馈和运动规律。

**采用“v2 手册为视觉目标，v1 组件与算法为实现参考，FOCUS 的领域契约为行为约束”的基线。** 这是本方案作出的版本选择，并非参考库已经提供的一套无冲突成品。实施者按本文裁决执行，不再自行在不同文件之间挑参数。

本次调研发现，open-claude-ui 不是可直接替换 FOCUS 的完整应用：它包含组件示例、算法、主题 CSS、手册和独立展示页。其 v2 文档、v1 CSS、AGENTS 指南和展示页存在明显差异，部分组件含演示数据和未接入业务的按钮。因此，“完全对齐”需要先形成可复现的参考规范，再逐页验收。

FOCUS 应保留自身名称和阅读业务：Topic、Reading Source、Source Anchor、Reading Cursor、Reading Note、FOCUS Discussion。将 Claude 的会话侧栏映射为来源与专题导航，将对话流映射为原文锚定的阅读与讨论流，将工具执行反馈映射为现有真实任务。原文、译文、笔记、进度、博客的身份和权限不能随外观更换而改变。

### 1.1 “对齐”的验收范围

| 层次 | 目标 | 允许的明确适配 |
| --- | --- | --- |
| 视觉 | CDS 2.0 画布、陶土色、低对比表面、单边界、密度、排版、浮层阴影 | FOCUS 标识、中文字体、技术文章的字号与长文宽度 |
| 动效 | 统一时间/曲线、按压、展开、关闭、流式反馈、滚动边缘、图片放大 | 原文不模拟流式；高频阅读不重复播放装饰性弹跳 |
| 组件 | 所有现有产品页面使用同一套 CDS 风格基础组件 | 保留 FOCUS 现有宿主能力与操作语义 |
| 信息结构 | 左侧统一导航、安静的内容画布、底部输入工作区、渐进披露 | 资料从左侧覆盖打开，符合已接受的 ADR 0023 |
| 质量 | 深浅色、紧凑/舒适密度、键盘、中文输入、低动态模式、失败恢复均覆盖 | 没有真实数据的 token 仪表、推理档位等不显示 |

“像 Claude”的判断应基于冻结的 open-claude-ui 规范与参考场景；本调研不声称已经核验官方 Claude 客户端的真实表现，也不以参考手册中的逆向来源声明替代验证。

## 2. 调研基线与证据范围

| 对象 | 本轮基线 | 证据性质 |
| --- | --- | --- |
| FOCUS | Git HEAD `6070204396beb03c2b5bfd8ce2590099bd4e4c77`，并读取当前工作树 | TSX、CSS、契约、测试源码、领域文档及 ADR |
| open-claude-ui | Git HEAD `02d021fceaf2a907f9e63a8125621bdda1b85d60` | README、AGENTS/CLAUDE、v1/v2 分卷、主题及组件/Hook 示例、展示页源码 |
| 运行态 | 本轮没有启动或构建新 UI，也没有执行双站浏览器录像比对 | 不作像素一致、帧率通过或设备体验通过的结论 |

FOCUS 开始调研时已有 6 个业务/测试文件修改：`.agents/core/article_blog.py`、`.agents/core/reading_application.py`、`host/blog_runtime.py`、`host/reading_runtime.py`、`tests/test_blog_dual_artifacts.py`、`tests/test_stage4_reading.py`；`external/` 未跟踪。本方案不覆盖这些工作。

文中证据分为：**源码确认**（当前文件直接支持）、**参考手册描述**（参考项目对设计的规定或解释）、**本方案决定**（FOCUS 的目标设计）、**待验收**（需要浏览器或实施后验证）。测试文件证明已有回归案例，不代表本轮执行通过。

### 2.1 阅读索引

| 编号 | 依据与定位 | 用途 |
| --- | --- | --- |
| F1 | [CONTEXT.md](../../CONTEXT.md) | 领域名词、权威状态、阅读与讨论边界 |
| F2 | [ADR 0004](../../docs/adr/0004-host-agnostic-reader-seam.md)、[ADR 0018](../../docs/adr/0018-confirmed-reader-operation-semantics.md) | ReaderHost 边界、历史继续、重置、任务、设置、草稿语义 |
| F3 | [ADR 0019](../../docs/adr/0019-reader-text-and-figure-side-space.md)、[ADR 0023](../../docs/adr/0023-mist-reader-left-drawer-and-inline-composer.md) | 图片与资料共用空间、最新左抽屉与输入区收起规则 |
| F4 | [WorkspaceApp.tsx](../../ui/apps/standalone/src/WorkspaceApp.tsx)，44–110、457–662 行 | 路由、共享任务、知识库、设置、对话框 |
| F5 | [standalone.css](../../ui/apps/standalone/src/standalone.css)，165–238、343–373 行 | 当前生效的工作台布局与后置覆盖 |
| F6 | [FocusReader.tsx](../../ui/packages/reader-ui/src/FocusReader.tsx)，18–99、223–295、530–636 行 | 草稿、视口、时间线、输入、资料与继续阅读 |
| F7 | [mist-tokens.css](../../ui/packages/reader-ui/src/mist-tokens.css)、[mist-reader.css](../../ui/packages/reader-ui/src/mist-reader.css)、[reader-figures.css](../../ui/packages/reader-ui/src/reader-figures.css) | 当前视觉和运动参数、抽屉最终规则 |
| F8 | [MarkdownContent.tsx](../../ui/packages/reader-ui/src/MarkdownContent.tsx)、[figures.ts](../../ui/packages/reader-ui/src/figures.ts) | Markdown、公式、HTML 表格清洗及图片身份 |
| F9 | [App.tsx](../../ui/apps/standalone/src/App.tsx)、[WorkspaceSelection.tsx](../../ui/apps/standalone/src/WorkspaceSelection.tsx)、[BackendSetupPanel.tsx](../../ui/apps/standalone/src/BackendSetupPanel.tsx) | 首次进入、访问口令、工作区切换、后端配置 |
| R1 | [参考项目 docs 索引](../../external/open-claude-ui/docs/README.md)、[package.json](../../external/open-claude-ui/package.json)、[导出入口](../../external/open-claude-ui/src/index.ts) | 版本、交付物和依赖事实 |
| R2 | [v1 设计令牌](../../external/open-claude-ui/docs/v1/01-设计哲学与设计令牌体系.md)，31–101、221–272、274–539、541–559 行 | 基础表面、单边界、字体、尺寸、运动 |
| R3 | [v2 架构与对比](../../external/open-claude-ui/docs/v2/03-架构重构与对比分析.md)，15–112 行 | v2 侧栏、画布、密度和圆角 |
| R4 | [v2 系统底座](../../external/open-claude-ui/docs/v2/04-系统底座全景解密.md)，15–73 行 | 动效族、组件分类、时间与曲线 |
| R5 | [cds-theme.css](../../external/open-claude-ui/code-examples/cds-theme.css) | v1 实际主题、双环阴影、状态色、关键帧 |
| R6 | [ClaudeMotionPresets.ts](../../external/open-claude-ui/code-examples/ClaudeMotionPresets.ts)、[CdsMotionEngine.tsx](../../external/open-claude-ui/code-examples/CdsMotionEngine.tsx) | 示例运动参数及实现差异 |
| R7 | [组件示例目录](../../external/open-claude-ui/code-examples)、[展示页源码](../../external/open-claude-ui/docs/claude-components-storybook.html) | 可复用外观、算法与展示局限 |
| R8 | [资产说明](../../external/open-claude-ui/assets/README.md)、[LICENSE](../../external/open-claude-ui/LICENSE) | 字体/音频资产实际提供情况与复制时的归属记录 |

## 3. FOCUS 现状：应重构哪里，必须保留什么

### 3.1 架构与页面全景

现有 UI 使用 React 19、TypeScript、Vite 和普通 CSS。`reader-ui` 依赖 React、`reader-contracts`、Markdown/KaTeX 管线；其 package.json 没有 Framer Motion、Tailwind 或通用组件库。正式入口为 `FocusReader({ host })`，宿主适配在 standalone 中，Core/Host 提供权威数据。（F2、R1 及两项目 package.json）

| 产品面 | 当前实现 | 重构重点 | 不能丢的行为 |
| --- | --- | --- | --- |
| 启动与口令 | App 的 loading、login、expired 分支 | 统一进入页、错误与加载 | 过期工作区暂停旧操作，旧草稿不提交新工作区 |
| 工作区选择 | WorkspaceSelection 的 import/create/relocate | 清晰主次、路径字段、后端卡片 | 使用服务器目录、generation/requestId、失败后读取权威状态 |
| 应用导航 | 86px 桌面导航轨；窄屏顶部导航 | CDS 左侧导航及折叠结构 | Library/Reading/Settings 路由和直接访问 |
| 知识库 | Topic、搜索、卡片/列表、展开详情 | 统一项目行/卡片，收敛常驻按钮 | Source 唯一身份、Topic 关联与顺序、原件/正文入口 |
| 上传与入库 | dialog、批次、单项、范围确认 | 文件预览、目标与步骤状态 | parse-only、冻结 Topic/博客选项、未知结果与恢复 |
| 阅读准备 | 来源状态、可关闭失败提示、候选计划 | 统一 Banner/Progress/Disclosure | 超时/失败/取消分开；关闭不等于重试或取消 |
| 阅读正文 | 原文/译文、结构导读、统一时间线 | 取消浮雕玻璃卡片，正文成为视觉中心 | 开始/继续/回看/完成与 Cursor 一致；缓存内容直接呈现 |
| 讨论 | 用户消息、回复、输入、任务审批 | CDS 消息流、Composer Dock | SSE 真实增量、草稿引用、重试身份、审批和停止 |
| 资料 | 图片/笔记/进度/讨论共用左抽屉 | 统一 Aside/Tab/编辑器 | 不挤正文；草稿保留；图片归属当前 Source |
| 博客 | 两项产物状态及模态 iframe 查看 | 产物预览卡、统一查看器 | Reading Blog/HTML 分别报告 |
| 设置 | 字号、字体、亮度、后端 | 分组设置、深浅色与密度 | 预览/取消/保存；检查连接不等于保存配置 |
| 全局任务 | 标题旁单入口，可展开批次与单任务 | TurnStatusStep/Disclosure 风格 | 默认收起、取消单个尝试、断连不显示闲置 |

### 3.2 需要纠正的“旧印象”

1. **当前工作台主背景已是纯色。** `standalone.css:5` 虽保留径向渐变，`:165` 已覆盖为 `var(--reader-paper)`；首次进入页另有渐变。重构应替换最终生效层，不能只删除最早那条声明。
2. **当前正式 Mist 阅读是单列加左侧覆盖抽屉。** `reader-figures.css:88–119` 与 `standalone.css:355–373` 覆盖较早分栏规则；右侧 60/40 是非 Mist/历史方案。ADR 0023 明确接受了左侧抽屉。
3. **旧 README 不是当前全部事实。** `ui/README.md` 仍叙述渐隐历史、氛围控制和 companion；正式规格自身又标注被后续 ADR 覆盖。实施依据顺序应是当前业务约束、最新 ADR、源码行为、历史设计材料。
4. **已有真实复杂交互。** 当前不是几个静态页面：事件定位、人工滚动暂停、草稿引用、重置栅栏、后台任务与配置分离都已进入 UI。不得用参考库的本地演示状态覆盖这些逻辑。

### 3.3 当前视觉与动效差距

| 差距 | 源码证据 | 目标 |
| --- | --- | --- |
| 灰蓝 Mist 与 CDS 颜色/材质不同 | mist-tokens：`#f0eeef/#35414d/#778b97`、20px blur、17px radius | 中性画布、陶土强调、细线和低对比表面 |
| 多层 CSS 后置覆盖 | standalone.css 多次重定义 button/card/grid；reader-shell→mist→figures | 统一语义 token、组件状态，不继续追加末尾覆盖 |
| 所有按钮近似同等边界权重 | standalone.css:171，通用按钮边框；各页面再覆盖 | Primary/Secondary/Ghost/Danger/Icon 明确区分 |
| 阅读卡片、composer 仍有玻璃材质 | mist-reader.css:22、40 附近 | 实色内容层、局部阴影；正文去装饰边框 |
| 时间线自动定位偏 Mist | FocusReader.tsx:258–295，事件居中与 smooth settle | 明确 Continue 定位和 streaming bottom follow 两种策略 |
| 动效参数按区域定义 | Mist 的 160/280ms、drawer 160ms ease-out | 五档 CDS 时间、三条曲线、状态驱动可中断 |
| 正文和回答字体共享较多 | mist-reader.css 的 `.focus-markdown` serif | 原文/译文与对话/控件分别定义排版角色 |
| 没有全产品主题与密度体系 | 当前主要为 Mist tokens、字号和亮度 | light/dark/system × compact/comfortable |

这些是静态代码差距；流畅度、对比度实际数值、窗口缩放时的视觉结果仍需实施后的浏览器验证。

## 4. 参考项目审计：吸收价值与实现缺口

### 4.1 可吸收的完整体系

v1 提供了设计哲学、原子控件、消息流、Composer、弹簧与渐隐、媒体查看、桌面/协作、工程资产及 Agent 指南八个分卷。v2 增加了更紧凑的尺寸、Composer Chin、状态列、CSS 动效族和标准组件分类。（R1–R4）

最值得整体吸收的不是单个橙色按钮，而是以下组合：内容优先的页面层级；一个容器只有一个主要闭合边界；按钮密度与文字密度相互独立；输入框 default/hover/focus 三态；消息和工具状态分层；真实状态驱动反馈；手动滚动优先；图片从缩略图过渡到查看器；统一可访问性与低动态降级。

### 4.2 冲突裁决表

| 冲突 | 参考库证据 | 本方案裁决 |
| --- | --- | --- |
| 浅/深画布不一致 | v2 `#FCFCFB/#151515`；主题 CSS `#f5f5f3/#0b0b0a`；AGENTS 又有 `#1b1b19` | 画布采用 v2；其余层见第 6 节明确表 |
| Composer 圆角 | v1/组件为 20px；v2 compact/comfortable 为 12/14px | 26/28px，单行药丸；来源 ADR 0028，取代先前 12/14px 裁决 |
| 控件尺寸 | v1 常见 32px；v2 compact 为 24px | 桌面 compact 24px；comfortable 32px；触控命中区单独扩展 |
| 运动引擎 | AGENTS 要求 springs；v2 主张 CSS；示例混用 | 基础动效 CSS；确需连续手势的模块单独采用算法/运动库 |
| 弹簧参数 | AGENTS 的 SNAPPY 为 600/30/.6；实际文件为 320/28/1（stiffness/damping/mass），其他预设也有差异 | 不把 AGENTS 数值当实际实现；保留代码来源记录，基础 UI 不依赖它 |
| 1.32 倍 pill | CdsMotionEngine 文案写 1.32x，class 是 scale-125 | 若采用该 v2 效果，按 1.32 明确实现；不复制示例近似值 |
| Storybook 的“2.0” | 页面标题写 2.0，内联主题仍有 v1 的色值/圆角 | 仅供组件构图参考；必须生成冻结后的 FOCUS 参考状态板 |
| “离线”展示页 | HTML:8–17 依赖 Tailwind CDN、React、Babel、Google Fonts | 本地打包资产；不能把此页直接当离线可验收应用 |
| 完整官方还原的声明 | 手册有逆向片段、性能百分比和实现原因推断 | 作为参考库主张记录，不进入 FOCUS 性能或官方事实承诺 |

### 4.3 示例不能原样投入产品的具体原因

- `ChatComposer.tsx:77–85` 调用可选回调后立刻清空输入；`:101` 起使用模拟附件。FOCUS 必须等待实际操作结果、保留失败草稿与提交时的引用。
- `ConfirmationDialog.tsx` 用普通 `div role=dialog`，Confirm 立即调用 `onConfirm()` 和 `onClose()`。示例本身没有提供与原生模态等价的完整焦点隔离、异步提交等待和失败留存。FOCUS 继续采用 `dialog.showModal()` 语义，迁移其外观。
- 历史参考 `ChatComposerChin.tsx`（本地形态已由 ADR 0028 取代）的 Attach/Send 按钮没有接业务；“已在 local storage 暂存”的文案不等于已实现队列。FOCUS 不显示没有真实支撑的状态。
- `useClaudeScrollPinning.ts` 有 40px/120px/150ms 规则，但用户回到底部的 scroll 事件也可能重设 pinned；接入时需测试冷却期与新内容竞争。不能覆盖 FOCUS 的历史 Chunk/Continue 定位。
- `ScrollFadeContainer.tsx` 注释写边界 1px，实际判断为 2px；所谓 7 档渐变列出 8 个 stop。方案按实际 8 个 stop 和 2px 边界定义。
- `src/index.ts` 同时导出浏览器组件和 `createClaudeMainWindow` 等桌面模块；FOCUS 不从根入口整体导入，避免把 Electron 边界引入浏览器。
- FOCUS 当前没有 Tailwind；参考示例中的 utility classes、插件式动画类和主题不能只复制 TSX 就期待生效。方案采用内部 CSS 组件实现相同视觉，确需依赖时在单独接入阶段锁定。
- 参考库的 `build` 只是 `tsc`，而 `tsconfig.json:16` 设置 `noEmit: true`；没有完整应用的构建交付。展示页自己内联组件，也不能替代对 `code-examples` 实际组件的验证。v2 列出的 40 个组件类别、47 项关键帧是手册清单，不能据此认为本库均已交付。
- `ScrollFadeContainer.tsx:123–138` 的水平遮罩是简化渐变，`both` 返回空样式；本方案将多档渐隐用于水平列表属于补齐工作。参考核心样式/示例也不能取代 FOCUS 已有的 reduced-motion 处理。

## 5. 目标信息架构与页面设计

### 5.1 工作台整体结构

```text
┌ 左侧统一导航 288px ─┬ 页面上下文标题 / 当前 Source ───── 任务 ▾ ┐
│ FOCUS     折叠      │                                          │
│ 知识库             │ 知识库列表 / 阅读时间线 / 设置正文         │
│ 阅读               │                                          │
│ 专题               │ 阅读时：资料抽屉从内容区左缘覆盖打开       │
│   Topic A          │                                          │
│   Topic B          │ 阅读操作：资料  结构  位置  新会话  继续   │
│                    │ 引用条 + Composer Editor（行内发送/停止） │
│ 设置 / 工作区      │ Notices（真实任务状态、审批与恢复）       │
└────────────────────┴──────────────────────────────────────────┘
```

288px 来自 v1 的 sidebar token（R2:94）；这是 v2 未明确替代该几何值时的继承。折叠宽 56px 为 FOCUS 适配值。桌面展开，较窄窗口折叠，小屏为菜单抽屉。导航只保留一套，移除独立 Topic 区与应用导航重复占据空间的情况。

Topic 点击在知识库执行筛选；阅读中的 Topic/Source 选择仍是独立业务动作，不能让筛选操作隐式打开来源或推进 Cursor。全局任务入口继续与页面上下文同行，默认收起。（F2、F4）

### 5.2 知识库

默认采用 CDS 风格列表，保留卡片切换及已有用户选择。每行包括来源图标、展示标题、原题或简要元信息、Reading Status、阅读动作与更多菜单。来源数量和搜索放在页面工具栏；Topic 从左导航选择。

常驻主动作按真实状态显示“准备阅读 / 继续阅读 / 查看已读”；博客作为产物入口。重命名、Topic 关联、重新规划、重新阅读、删除放入更多菜单，破坏性动作单独分区。详情展开承载完整原题、Source ID、原件/正文、准备状态与博客三产物状态。

卡片继续采用统一细边界：当前 `standalone.css:211–212` 已覆盖早期蓝/黄/绿状态边框，不应把这一点当成尚未修正的问题。状态通过文字、图标与小型色标表达；鼠标 hover 提升表面/边界，只有可点击卡片区域适用轻微抬升，内部按钮不触发卡片双重操作。

空库、搜索无结果、过滤无结果、连接失败使用不同空状态。空库引导上传，搜索无结果提供清除条件，失败提供针对性重试；不能共用“暂无材料”掩盖故障。

### 5.3 阅读与讨论时间线

正文主列建议最大 800px，输入区同轴最大 800px；这是适配中文技术长文的设计值。原文/译文直接排在画布上，采用小型 Source/Chunk 标识、标题和轻分隔。用户问题使用 18px 圆角浅色气泡；模型回答透明背景、无闭合卡片，行动栏在回答末尾。

保留 Reading Timeline 真实事件顺序。Source Chunk、UserMessage、AssistantMessage 三种内容有稳定 event identity，不以“当前卡片索引”代替身份。过去内容不逐渐降低正文可读性；滚动边缘遮罩仅表达容器边界，不对整条历史应用淡化。

原文/译文切换不重建事件、不启动翻译、不改变阅读位置。结构导读与正文是同一阅读上下文的两种视图；打开文章骨架不记为开始阅读。位置标签保留序号/总数和结构路径。长公式、代码、表格局部滚动，不拖宽页面。（F1、F6、F8）

阅读操作行遵循 ADR 0028 的无边框 ghost + 图标规则，位置徽标为浅灰药丸；只有 Continue 使用实心主按钮。功能区 compact/comfortable 高度 32/36px，触屏 44px；≤720px 新会话和全屏只显示图标，<600px 保持横向滚动。维持 ADR 0023 的功能顺序：资料在左，结构与位置在 Continue 之前，新会话与输入区展开入口可达。Continue/完成本篇是独立按钮，不合并到 Send。全屏隐藏工作台导航/页头，退出控件不能遮挡资料关闭按钮。

### 5.4 Composer Dock

采用 ADR 0028 的 Editor（含行内发送/停止）+ Notices 分层：引用条说明问题绑定的 Source/Chunk；编辑区单行时为 52/56px 高、26/28px 圆角药丸，多行自适应高度至 170px，发送/停止为右侧贴底圆按钮；独立提示区容纳真实任务反馈。取消下沿分隔条与可见快捷键提示，快捷键通过 textarea 的读屏描述提供。模型信息只显示当前真实配置，进入设置修改；运行中不能通过 UI 偷换后端。

FOCUS 当前正式 Mist 阅读不展示上传附件（MistReader 测试有此约束）；参考库 Attach 的结构吸收到知识库上传预览，不在阅读页凭空增加附件入口。输入保留现有中文输入法保护，并覆盖 `isComposing` 和 `keyCode === 229`。

输入区收起释放整行，引用和草稿仍保留。收起/提问是功能行中同一常驻开关，位于全屏之后、停止/继续之前；保留草稿时显示无文本圆点。审批、停止、错误和草稿恢复在收起时仍可见。发送 pending 禁止重复请求；成功只清除本次已提交且未被更新的草稿；失败保持草稿并使用原请求身份重试。（F2、F3、F6）

### 5.5 资料抽屉与媒体查看

沿用左侧覆盖抽屉，建议宽度 `min(420px, viewport - 24px)`，保持当前已接受几何。顶部 Tab 为图片、笔记、阅读进度、讨论；内部使用 CDS 的 Aside、分段选项与列表。

打开/关闭不得推动正文横向重排，也不得让新内容自动跟随策略重新接管手动滚动。Tab 切换保留笔记草稿、问题草稿、图片选择。关闭恢复到触发控件；窄屏模态化时应隔离背景焦点，桌面可保留非模态资料浏览。

保留现有新阅读事件的图集行为：切到有图的 Chunk 时选中该段第一张图并进入图片资料模式，无图时关闭资料空间；同一事件的普通刷新不重复重置用户选择。此行为由 `FocusReader.tsx:217–222` 的 pictureContext 驱动，后续若改为完全手动打开，应独立提出交互变更，不能在换肤中顺手改变。

图片查看器保留浏览器 top layer；吸收 `MediaLightboxViewer` 的光标锚点缩放、4px 拖动死区、缩略图进入放大图的共享元素过渡。支持适应窗口/原尺寸、可访问的放大/缩小、左右图导航。图片身份仍沿用 Source 相对路径与 Host URL 规范化逻辑；不按文件名跨来源去重。

共享元素过渡不支持或低动态模式时直接显示/关闭。图片从同一 Host 资产接口加载；不为视觉切换复制原图或重新生成图注。75vw 画廊跑道适合全屏查看器，可作为第二阶段增强，不强塞进 420px 资料抽屉。（F3、F8、R7）

### 5.6 上传、任务与失败反馈

上传采用一层 Dialog：文件列表 → Topic 选择 → 处理选项 → 开始。AttachmentCard 显示实际文件名/类型/大小，删除条目不改变其他文件。提交后使用现有批次投影展示排队、解析、入库、博客等真实步骤。

任务面板采用 TurnStatusStep、状态点、Accordion 和必要的 Banner。只有真实 running 状态有呼吸反馈；approval 明确等待用户；stopping 不显示完成；断连保留最后状态并标为未知；失败保留恢复入口。没有百分比就使用不定进度和已用时间。

Reading Preparation 的关闭提示与取消工作必须是两个动作。成功信息可安静收敛；失败和审批不自动消失，也不只留一个短暂 toast。（F2、F4、TaskProgress.tsx）

### 5.7 设置、进入与博客查看

设置分为外观、阅读、后端、工作区。外观增加浅色/深色/跟随系统、紧凑/舒适；阅读保留四档字号和已有本地字体。字号影响正文，不同时放大导航密度。现有亮度偏好先保留，迁移后重定义为阅读表面偏好需另行确认，不能悄悄丢失已保存设置。

保存/取消沿用现有行为，外观与后端分别报告成功/失败。连接检查不自动保存；检查期间改模型，使旧结果失效。首次进入把工作区与后端放入同一安静表面，用步骤式信息层级改善阅读，但不增加必须注册的账户或无关引导。

博客查看继续是 top-layer modal。先统一外壳、标题栏、加载/失败、关闭、外部打开；iframe 内 HTML 属于 Blog Output，外部 CSS 无法自然重设其正文。若要让博客产物本身也对齐 CDS，需要单独修改 HTML 生成模板并重新验收产物，不能声称仅改工作台就完成。这作为扩展阶段列入交付，保留已有历史 HTML 可读。

## 6. 冻结设计规范

### 6.1 颜色和表面

下表为本方案规范。v2 未提供完整层级的项，从 v1 实际 CSS 补齐或明确作 FOCUS 适配，不称为完整官方 v2 token。

| 语义 token | Light | Dark | 来源/裁决 |
| --- | --- | --- | --- |
| canvas | `#FCFCFB` | `#151515` | v2 R3 |
| sidebar / surface-1 | `#f5f5f3` | `#1a1a19` | FOCUS 层级适配，继承 R5 中性色 |
| surface-2 / content panel | `#ffffff` | `#20201e` | R5 层级颜色适配 |
| popover | `#ffffff` | `#222220` | R5 |
| text-primary | `#151515` | `#f5f5f5` | R5 |
| text-secondary | `#525252` | `#a3a3a3` | R5 |
| text-muted | `#8a8a8a` | `#666666` | R5，仅装饰/禁用；小字号有效信息改用 secondary |
| clay | `#d97757` | `#d97757` | R5；覆盖 AGENTS 深色不同值 |
| clay-hover | `#cc5a36` | `#e08264` | R5 |
| border | `hsla(0,0%,8%,.10)` | `hsla(0,0%,100%,.09)` | R5 |
| border-strong | `hsla(0,0%,8%,.20)` | `hsla(0,0%,100%,.18)` | R5 |
| ghost-hover / selected | `hsla(0,0%,8%,.05)` / `hsla(0,0%,8%,.10)` | `hsla(0,0%,100%,.05)` / `hsla(0,0%,100%,.09)` | R5 |
| user-bubble | `#f0f4f8` | 白 6% alpha | R5 |

单边界：Card、Dialog、Composer 外轮廓各有一条主边界；其内部普通按钮使用 Ghost，不再叠加闭合边框。Danger、Error、Warning、Success 单独命名，不挪用 clay 表示所有状态。

正文可读性优先：陶土作为强调/图标/焦点，不能未经对比度检验就作为小字号白字按钮背景。发送键可用深色填充+浅色箭头，或经验证的深陶土色。此项是明确的可访问性适配，记录差异，不隐藏在实现细节中。

### 6.2 阴影、焦点与材质

默认 Composer 阴影继承 R5：`0 4px 20px rgba(0,0,0,.035), inset 0 0 0 1px var(--border)`；hover 增强至 `0 4px 24px rgba(0,0,0,.06)` 加 strong 内环；focus 同形状 `.08` 阴影加内外双环。Dark 使用 R5 的 dark 阴影与亮边变量。

Popover 采用一条外轮廓与两档扩散阴影，Light 的 `0 8px 24px rgba(0,0,0,.12), 0 2px 6px rgba(0,0,0,.08)`；Dark 使用内侧白色 10% 的 1px 环与较深阴影。焦点不能只靠阴影：强制色模式提供可见 outline。

默认移除正文、列表和输入框的 backdrop blur；模态遮罩可保留 2px 局部 blur，关闭透明度时退为实色半透明遮罩。动效过程中避免全屏 brightness/filter 重绘。现有亮度偏好迁移需要验证其对新主题与浮层的影响。

Hairline 继承 R5 的 1px、DPR≥2 时 .5px、DPR≥3 时 1/3px 方案，仅用于分隔和非关键轮廓；控件可识别边界和焦点在高对比/强制色模式下恢复完整可见线宽。暗色字体轴 465/560/660 只对支持的可变字体生效，不能给静态中文字体设置后就宣称已完成光学补偿。

### 6.3 尺寸与排版

| 项 | Compact | Comfortable | 依据 |
| --- | --- | --- | --- |
| 控件可见高度 | 24px | 32px | v2 R3 |
| 内嵌控件高度 | 18px | 22px | v2 R3 |
| 控件圆角 | 6px | 8px | v2 R3 |
| Composer 圆角 | 26px | 28px | ADR 0028 |
| 功能区按钮高度 | 32px | 36px | ADR 0028；<600px 至少 40px，触屏 44px |
| Composer 发送/停止直径 | 36px | 40px | ADR 0028；触屏 44px |
| Composer 内距 | 7px | 7px | ADR 0028；触屏 6px |
| 功能区药丸圆角 | 999px | 999px | ADR 0028 |
| 卡片圆角 | 10px | 12px | v2 R3 |
| 图标 | 16px | 20px | v2 R3 |
| 间距序列 | 6/8/12/20/32px | 8/12/16/28/40px | v2 R3 |
| 消息气泡 / Dialog | 18px / 16px | 18px / 16px | 继承 v1 |

触控目标至少 44×44px（本方案目标），可见图标和底色保持 CDS 尺寸，通过实际布局留白实现；不能让扩大的伪元素热区互相覆盖。小屏采用 comfortable。紧凑侧栏行参考 v2 28px，但触控版本增高。

排版决定：UI 使用系统 sans + 已有思源黑体后备；标题使用系统 serif；原文/译文保留思源宋体/新致宋等既有选择。代码采用系统 mono，计时/序号使用 tabular nums。参考库没有分发商业字体；不以未提供字体作为验收前提。（R8、reading-fonts.ts）

FOCUS 字阶适配：辅助 12px、UI 13/14px、对话 16px/1.75、长文默认 18px/1.9，沿用 16/18/22/26px 阅读字号；章节标题 22–26px，页面标题 28px。正文与工具栏比例要独立验收，不能把 v2 24px 控件高误解为所有文字都应缩小。

## 7. 动效与交互规范

### 7.1 统一令牌

采用 R4:49–73：fast=60ms、snap=120ms、base=200ms、sheet=300ms、slow=450ms；out=`cubic-bezier(.165,.84,.44,1)`，snap=`cubic-bezier(.32,.72,0,1)`，overshoot=`cubic-bezier(.34,1.3,.64,1)`。

时间 token 是语义档位，不是每次操作都必须等待这么久。网络提交、焦点可达与状态更新不等待动画完成。普通 CSS transitions 负责可逆状态；进入/退出需要显式 presence 状态，退出动画结束再卸载，快速反向操作从当前视觉状态继续。

### 7.2 动效逐项规格

除明确继承参数外，下表位移和触发规则为 FOCUS 适配决定。

| 场景 | 效果与参数 | 触发/打断/降级 |
| --- | --- | --- |
| Ghost hover | 背景/文字 120ms snap | 键盘焦点立即可见；无浮起 |
| 按钮按下 | scale 1→.98，60ms out；松开 120ms | disabled 不动画；reduce motion 只改颜色 |
| 菜单/Popover | opacity 0→1，scale .98→1，200ms out；退出 120ms | transform-origin 跟随锚点；Esc 关闭并还原焦点 |
| Dialog | opacity + scale .98→1，200ms out；遮罩 120ms | 原生 top layer；提交失败留在原处 |
| 左侧资料/导航抽屉 | translateX(-24px)→0 + opacity，300ms out；退出 200ms | overlay 不改正文宽；重复开关反向，不积累定时器 |
| Disclosure/任务详情 | chevron 120ms；内容 reveal 200ms out | 无需位移整页；高度变化保留当前阅读锚点 |
| 新用户消息 | translateY(8px)→0 + opacity，200ms out | 仅新 event 播放一次；恢复历史不重播 |
| 新 Reading Chunk | 可选 opacity 120ms，无缩放 | 已缓存文本一次完整呈现；Continue 先完成业务动作 |
| 回复流式增量 | 实际增量直接出现，尾部轻淡入最多 120ms | 不按字符 setTimeout 排队；公式/表格保持完整语义节点 |
| 任务运行点 | 2s 周期 opacity .6→1→.6 | 仅真实 active；后台页/结束立即停；低动态静态点 |
| Skeleton | 列表 lockstep 2s；大卡 wave 105°、90ms 错峰 | 只在真实加载显示；恢复已有内容不盖回 skeleton |
| Attachment/Chip | scale .8→1、opacity、200ms out；最多 30ms 错峰 | 只对新加入项；大量条目限制总延时 |
| Pill 确认反馈 | v2 1→1.32→1，80ms out + 120ms overshoot | 仅低频确认类 chip，禁止每次继续/每个 token 播放 |
| 卡片 hover | 边界/阴影 200ms out，最多上移 1.5px | 只用于真正可点击卡片，列表行只改背景 |
| 复制成功 | 图标变勾，2.5s 后恢复 | 剪贴板成功后才显示；失败提示可见 |
| 图片放大 | 缩略图几何→查看器，200ms out | 支持共享元素时使用；不支持则淡入；reduce 直接开关 |
| 路由/主题/密度切换 | 直接切换，必要时局部 opacity≤120ms | 不使用 450ms 整页滑动；正文滚动和草稿保留 |

不默认启用着色器环境光、整页呼吸和交互音效：这些能力的参考出处和处置见第 9 节。若后续采用，必须绑定真实状态、提供关闭，并独立验证开销。

### 7.3 滚动规则是本次重构的关键

现有 `settle()` 把新事件居中，并在内容增长时 smooth 滚动。参考 Hook 使用底部 pinning。本方案将两者拆为不同动作，不能机械替换函数。

1. **Continue/打开 Chunk：**保留以事件为单位的定位，短 Chunk 可完整进入视口，长 Chunk 顶端可读；用户刚主动滚动则不抢夺视口。定位不改变 Cursor，Cursor 只由真实业务操作改变。
2. **回复 streaming：**距离底部≤40px 时跟随；用户 wheel/touch/滚动键立即暂停，至少 150ms 冷却；暂停后仅用户回到底部或点击“回到最新”恢复。自动跟随用即时对齐并按帧合并，避免每个增量叠加 smooth。
3. **离开底部：**距离>120px 且有新内容时出现“回到最新”；不在没有新内容时不断闪现。
4. **资料/字体/窗口变化：**不视为新阅读事件；以可见事件 ID+相对偏移恢复锚点，避免只保留旧 scrollTop 导致换行后位置变化。
5. **低动态：**取消 smooth 与位移，保留位置和新内容提示。回看、切语言、关闭抽屉不触发重新定位。

滚动渐隐继承 28px fade，alpha stop 依次为 0/.05/.15/.30/.50/.70/.85/1，位置 0/15/30/45/60/75/87/100%；距离容器边缘≤2px 时该侧关闭。优先用于横向标签和资料列表；正文需确保焦点、首末行能完整滚入无遮罩区域。

## 8. 实施架构方案

### 8.1 模块边界

```text
Core / Host 权威数据
        ↓
reader-contracts 的 ReaderHost / ReadingWindow
        ↓
standalone 工作台控制层 ── reader-ui 阅读控制层
        ↓                         ↓
             @focus/ui-primitives（拟新增）
        tokens / controls / overlays / motion / typography
```

新增的 `ui/packages/ui-primitives/` 是方案中的目标，不是现有模块。该包只依赖 React 和自身基础实现；不包含 ReaderHost、Source 路径、HTTP 或业务数据。standalone 与 reader-ui 分别组合基础组件，继续保持 ReaderHost 边界。

`WorkspaceApp` 拆分为工作台布局、知识库、任务面板、设置、上传和管理浮层；`FocusReader` 先保留业务控制逻辑，再抽出 ReadingTimeline、ReadingActions、ReadingComposer、MaterialsDrawer。第一轮拆分不同时重写请求/恢复状态机，避免外观迁移与业务语义变化混在一起。

### 8.2 基础组件与状态契约

| 组件组 | 建议组件 | 必需状态 |
| --- | --- | --- |
| 基础控件 | Button、IconButton、Input、Textarea、Checkbox、Select、SegmentedControl | default/hover/focus/pressed/disabled/pending/error |
| 结构 | Surface、Card、Panel、Toolbar、SidebarItem、Prose | light/dark、compact/comfortable、窄屏 |
| 浮层 | Dialog、Drawer、Popover、Menu、Tooltip | opening/open/closing、焦点恢复、嵌套关闭次序 |
| 反馈 | Banner、StatusDot、Progress、Skeleton、Disclosure | idle/loading/approval/stopping/success/error/unknown |
| 业务组合 | SourceRow、ReadingEntry、Message、ComposerDock、FigureViewer | 通过现有契约绑定真实数据 |

引用参考代码时保留文件来源、commit、许可说明及本地适配摘要。默认采用有明确文件边界的受控移植，不依赖 `external/` 的可变运行时代码；后者继续作为只读参考。

### 8.3 样式与依赖决策

使用一份语义 token 定义加组件 CSS；不为了复制示例类名整体切换到 Tailwind。CDS 视觉不依赖 Tailwind 语法。基础动画使用 CSS；图片共享元素用浏览器能力检测，缺失有直接显示回退；只有验证确有价值的连续手势再决定是否引入 Framer Motion。

图标统一为一种可审计的 SVG 系统。若移植 Lucide 示例，则锁定依赖与图标尺寸；参考手册讨论 Phosphor/duotone 并不意味着仓库示例已经统一使用它。禁止 Emoji、文字符号和两套图标混搭。

移除旧 Mist CSS 必须在所有 consumer 切换后进行。旧非 Mist appearance、Fixture、Lightfield prototypes 分别盘点：生产 reader 的两种 appearance 需要兼容或显式退役决定；隔离原型不因视觉重构直接删除。

## 9. 参考库吸收与处置清单

“改造吸收”表示实现同样的视觉/交互意图并对接 FOCUS；不等于直接复制整份文件。该清单覆盖当前 `code-examples` 的全部 35 个文件（音频两文件合并为一行）。

| 参考文件 | FOCUS 去向 | 处置与约束 |
| --- | --- | --- |
| cds-theme.css | tokens/theme | 提取并按第 6 节统一，补 v2 密度 |
| tailwind.config.js | token 映射参考 | 不引入其构建体系，翻译为组件 CSS |
| CdsButton.tsx | Button/IconButton | 吸收变体、反馈；补状态/触控/对比度 |
| SegmentedControl.tsx | 显示方式、资料 Tab | 吸收选中底板，保留正确键盘语义 |
| StatusIndicators.tsx | 任务和来源状态 | 绑定真实状态、无伪进度 |
| ConfirmationDialog.tsx | 管理/重置/删除 Dialog | 吸收外观，保留原生 modal 与异步失败 |
| AttachmentCard.tsx | 上传文件列表 | 使用真实 File 与批次数据 |
| ChatComposer.tsx | ReadingComposer | 吸收结构/IME/三态阴影，替换演示业务 |
| ChatComposerChin.tsx（历史参考） | 原 Composer 下沿 | 已由 ADR 0028 的行内发送/停止取代，不再实现该下沿 |
| ChatMessageBubbles.tsx | User/AssistantMessage | 保留现有 Markdown 管线和事件 ID |
| ThinkingAccordion.tsx | TaskDisclosure | 只显示真实步骤/摘要，不虚构思维过程 |
| RichComposerWithMentions.tsx | 引用条与来源选择 | 先吸收 quote chip；@ 搜索作为有需求后的扩展 |
| ModelSwitcherWithTokenGauge.tsx | 后端设置/状态 | 选择器样式可用；无 usage 数据不显示仪表 |
| ModelSelectorEffort.tsx | 后端能力扩展 | 当前不提供统一 effort 契约，不显示假档位 |
| McpToolDecisionCard.tsx | AgentControls 审批 | 视觉适配现有 ReaderApproval，不新增执行协议 |
| ClaudeMotionPresets.ts | 手势运动参考 | 记录实际参数，仅连续运动按需使用 |
| CdsMotionEngine.tsx | 验收状态板参考 | 演示组件不进产品，按规范重建效果 |
| ScrollFadeContainer.tsx | 标签/资料溢出 | 吸收渐隐与边界逻辑，补内容变化/低动态处理 |
| ReasoningAmbientGlow.tsx | 可选状态装饰 | 本次默认关闭，不能替代真实任务提示 |
| MediaLightboxViewer.tsx | FigureViewer | 吸收锚点缩放、平移、预加载；保留 Source 身份 |
| useClaudeSharedElementTransition.ts | 图片进入/退出 | 能力检测、稳定身份、降级、top layer 兼容 |
| ArtifactsSplitPaneResizer.tsx | 非 Mist/未来产物空间 | 不取代当前左抽屉；如启用保留键盘与宽度约束 |
| CodeBlock.tsx | Markdown code renderer | 吸收标题/复制反馈，源码内容不变 |
| EpitaxyIframeBridge.tsx | 博客/产物查看研究 | 不引入任意 postMessage 执行，当前只统一 viewer 外壳 |
| StreamingDiffViewer.tsx | 暂无对应业务 | 后续出现真实版本差异数据再接入 |
| DraggableSessionList.tsx | Topic/Source 列表参考 | 先吸收行样式；拖拽需映射现有 Topic 顺序，不拖动权威 Cursor |
| ContainerResponsiveBar.tsx | ReadingActions/工具栏 | 吸收容器宽度适配，关键操作不得消失 |
| useClaudeRovingFocus.ts | Tab/菜单/选项组 | 审核后使用；普通文档按钮仍遵循自然 Tab 顺序 |
| useClaudeScrollPinning.ts | 阅读跟随控制 | 按第 7.3 节融合，保留 Continue 定位 |
| useRateLimitBackoff.ts | 反馈样式参考 | 不从 UI 自动重发业务请求，重试仍服从 Host 身份 |
| ClaudeDesktopHeader.tsx | WorkbenchHeader | 吸收标题/工具分组；无原生窗口控制伪按钮 |
| createClaudeMainWindow.ts | 无 Web 对应 | 不导入 Electron；未来桌面包装单独项目处理 |
| CoworkAgentCanvas.tsx | 无当前对应 | 不为视觉一致新增多代理协作业务 |
| ClaudeAudioPlayer.ts / LiveMicActivityBars.tsx | 可选未来语音 | 当前无音频任务来源，不增加假波形或自动提示音 |

## 10. 已接受决策的兼容与替代

| 现有决策 | 本方案处理 | 实施前要记录的设计变更 |
| --- | --- | --- |
| ADR 0004：宿主无关 Reader | 保持 | 新 primitives 不跨业务依赖 |
| ADR 0005 / 0008：Mist 正式视觉、旧导航 | 视觉被本提案替代 | 新 ADR 说明 CDS 2.0 是正式外观，不能仍宣称 Mist 是当前基线 |
| ADR 0018：阅读/重置/任务/设置语义 | 保持 | 布局更新不能改语义；任务仍单入口、默认收起 |
| ADR 0019：资料共用空间与图片身份 | 保持内容规则 | CDS 只改样式和放大交互 |
| ADR 0023：左抽屉、功能行、输入收起、全屏 | 保持空间/行为；更新材质和动效 | 左抽屉 160ms 改为规范 300ms，明确属于展示修订 |
| ADR 0020 / 0021：工作区和后端 | 保持 | 首次进入重新布局不引入另一份配置权威 |

当前文档只是提出这些替代关系，没有修改现有 accepted ADR。实施启动时先记录新的视觉 ADR，再更新 README/spec 的过期描述。

## 11. 分阶段执行方案

每阶段先交付可审查结果再进入下一阶段；完成基础 token 不等于完成整个 UI 重构。下面是待执行工作划分，本轮没有开始实施。

| 阶段 | 主要工作/文件面 | 交付物与退出条件 |
| --- | --- | --- |
| P0 冻结参考 | 参考 commit、本文 token、全状态场景 | 本地可运行设计状态板；深浅色×密度；截图/录像基线；裁决表无未定参数 |
| P1 设计基础 | 新 ui-primitives、theme、controls、overlays | Button/Input/Select/Dialog/Tab/反馈全状态；键盘和低动态通过 |
| P2 工作台与知识库 | WorkspaceApp 拆分、standalone.css | 左导航、Topic/Source、上传、任务、管理浮层；保留原操作测试 |
| P3 阅读与输入 | FocusReader 展示拆分、ReadingChunk、Markdown 样式 | CDS 阅读流/Composer/功能行；草稿、Cursor、流式、重试回归通过 |
| P4 资料与媒体 | FigurePanel、资料 Tab、Note/Progress 编辑 | 左抽屉、全屏、图片缩放/共享元素；关闭与焦点恢复正确 |
| P5 设置与进入 | App/WorkspaceSelection/BackendSetupPanel | 主题/密度/字号设置、工作区/后端流程、错误/恢复一致 |
| P6 集成验收 | 两主题/两密度/响应式/可访问性/性能 | 固定场景逐项签收；清理迁移完成后的重复 CSS；更新 ADR/设计文档 |
| P7 产物内页扩展 | Blog Output HTML 模板 | 新生成产物也对齐；旧 HTML 兼容；业务产物校验单独通过 |

P2–P5 依赖 P1，P3 的滚动模型是 P4 的前置，P6 必须在所有主页面完成后验收。P7 涉及生成产物，可以独立交付，不能阻塞已完整迁移的工作台，也不能把其未完成隐藏为“全部一致”。

预计实现风险：P1/P2 中等；P3/P4 高（状态、滚动与媒体竞争）；P5 中等；P7 中高（产物兼容）。不根据静态调研给出虚假的人日精度。未来拆票遵循 `.scratch/<feature>/issues/NN-*.md`，每票给出输入、文件范围、行为约束及验收场景。

### 11.1 迁移与回滚

开发阶段可保留单一内部外观开关对照旧/新 Renderer，共享同一个控制层与 ReaderHost；不复制业务状态机，也不增加长期产品主题分叉。每阶段独立提交，失败能回退该层。正式切换后再移除旧样式与内部开关。

已有字体、字号、列表选择与草稿存储先兼容读取；新增主题/密度使用独立版本化偏好。旧 brightness 的映射需要明文定义。不得因重构清空 sessionStorage/localStorage 来“解决”旧状态问题。

## 12. 验收矩阵

### 12.1 固定视觉场景

建立合成公开数据集，不能把私人 Workspace 内容放入截图基线。固定字体、浏览器、DPR、视口、主题、密度和数据；使用同一份长标题、中英混排、公式、HTML 合并单元格表格、代码、长列表及缺图案例。

| 场景组 | 必测状态 |
| --- | --- |
| 页面 | 登录/首次进入/过期工作区、空库/满库、阅读开始/导读/正文/完成、设置 |
| 组件 | hover/focus/pressed/disabled/pending/error、Popover、Dialog、Drawer、Tooltip |
| 任务 | 上传批次、准备超时、approval、stopping、连接未知、博客部分失败/不适用 |
| 阅读 | 缓存打开、真实流式、历史回看、草稿引用、收起输入、打开资料、全屏 |
| 主题/设备 | Light/Dark × Compact/Comfortable；390/768/1024/1440px；至少一组短高度窗口 |
| 辅助条件 | 200% 缩放、键盘全程、中文 IME、reduced-motion、强制色、触屏键盘 |

视觉验收先比构图、几何、字体层级、颜色、边界、阴影，再看图标光学对齐和动画关键帧。跨平台字体抗锯齿不做零差异要求。Token/几何目标要精确；截图阈值由 P0 的固定环境标定，不能先写任意百分比冒充质量标准。

### 12.2 必须保留的行为回归

1. Continue 到前沿只推进一次；历史继续只回看；已完成 Source 不因回看变未完成。
2. 新会话持久空屏；旧讨论仍可访问；下次继续以持久前沿为准。
3. 草稿在切 Tab、切字体/主题、收起输入、打开资料、路由往返时不丢失，引用不偷换。
4. 网络错误重试使用原 requestId/input；刷新只对账，不自动重发；未知结果不显示成功。
5. 用户滚离底部后 streaming、字体变化、图片加载不抢滚动；点击“回到最新”可恢复。
6. 缓存原文/译文无伪打字效果；SSE 只有真实 delta；旧 revision 不覆盖新事件。
7. 图片选择、笔记编辑、资料 Tab 不改变 Cursor；关闭放大/博客/抽屉恢复合理焦点。
8. IME 候选确认不发送；Enter/Shift+Enter 规则与实际提示一致。
9. Reset 与 Delete 仍有正确影响说明、确认和活动任务栅栏；异步失败留在可恢复状态。
10. 连接检查与保存分开；外观预览可取消；后端失败不冒充外观失败，反之亦然。
11. parse-only 不运行博客；Topic/博客范围冻结；重复原件指回同一未完成任务。
12. 小屏/全屏的工具条不溢出；资料关闭、继续、停止和审批都能触达。

现有可继承测试位于 `WorkspaceApp.test.tsx`、`WorkspaceSelection.test.tsx`、`BackendSetupPanel.test.tsx`、`FocusReader.test.tsx`、`MistReader.test.tsx`、`Figures.test.tsx`、`ArticleStructure.test.tsx`、`TaskProgress.test.tsx`、`MarkdownContent.test.tsx` 及 Host Adapter tests。修改视觉定位断言时保留其行为目的，不能为新布局删除语义测试。

仓库还已有 `tests/confirmed_ux_browser.mjs`、`tests/reader_figures_browser.mjs`、`tests/backend_setup_browser.mjs`、`tests/workspace_binding_browser.mjs` 等浏览器脚本，实施时先检查其 fixture/启动前提，再复用场景；文件存在不等于本轮浏览器验收通过。

### 12.3 验证命令与证据边界

实施阶段执行仓库现有 `pnpm reader:typecheck`、`pnpm reader:test`、`pnpm reader:build`；浏览器验收单独记录 fixture 和隔离真实 Workspace 结果。组件测试通过不能证明动效、截图、焦点 top layer 和触控通过。

性能场景包含长时间线、持续增量、图片加载、拖拽缩放与快速开关抽屉。录制 frame/long-task/layout 轨迹，检查动画是否持续触发布局、是否创建随字符线性增长的动画节点、页面后台是否还在运行装饰循环。以固定设备旧/新版本对照报告；不把“纯 CSS”直接等同“GPU 合成/120Hz 已保证”。

本轮验证仅覆盖文档路径、源码证据与方案内部一致性；上述应用命令和体验验收均未执行。

## 13. 决策清单与后续落地入口

本方案已经决定：v2 优先；保留 v1 有用算法；全页面统一；主导航改为可折叠侧栏；资料维持左抽屉；CSS 作为基础运动实现；保留 ReaderHost/领域状态；不引入假模型能力；正文采用 FOCUS 中文阅读适配；新基础组件包不绑定业务；Blog Output 内页单独交付。

实施第一步是 P0：将本文数值和状态矩阵变为可运行的参考状态板，并保存对照截图与短录像。该步骤解决的是参考项目版本冲突和视觉目标冻结；随后按 P1–P6 完成正式重构。只有页面覆盖、状态覆盖、领域行为和运动体验都验收后，才可宣称 FOCUS 已按本方案完成对齐。