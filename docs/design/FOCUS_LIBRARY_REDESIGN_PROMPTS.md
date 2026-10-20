# FOCUS 知识库重设计：分步开发提示词

用法：在开发服务器的 FOCUS 仓库中，按顺序把每一步的提示词交给编码 Agent。**每一步都先粘贴“通用前置”，再粘贴该步正文。** 一步完成、你确认后再进入下一步。

规范：`docs/design/FOCUS_LIBRARY_REDESIGN_SPEC.md`（下称“规范”）。原型：`ui/apps/standalone/src/prototypes/library-directions/`。

---

## 通用前置（每一步都粘贴）

```text
你在 FOCUS 仓库中实施知识库重设计（方案 A：列表 + 详情面板）。

开始前必须阅读：
- AGENTS.md、CONTEXT.md（使用其中术语：Reading Source、Topic、Source Library、Reading Cursor 等）
- docs/design/FOCUS_LIBRARY_REDESIGN_SPEC.md 全文，尤其 §0「不改变」、§12 执行约束、§13 风险
- ui/apps/standalone/src/prototypes/library-directions/ 下的 README.md 与源码（只读参考）
- ui/apps/standalone/src/WorkspaceApp.tsx、ui/apps/standalone/src/standalone.css、ui/packages/reader-ui/src/focus-tokens.css

硬性约束：
1. 不 commit、不 push、不切换/新建分支，不 stash/reset/checkout 文件；只读 git 命令可以。
2. 原型目录与规范文件只读；生产构建不得包含原型。
3. 不重启、不覆盖正在使用的正式 FOCUS 服务；预览用隔离宿主 tests/confirmed_ux_browser.py（夹具数据，绑定 127.0.0.1，FOCUS_BROWSER_PORT 用空闲端口，PYTHONUTF8=1）。运行 pnpm reader:build 前确认正式服务不直接使用 ui/apps/standalone/dist；若使用，先停下问我。
4. 只做本步列出的范围；不顺手重构阅读页、设置页、任务框，不改 Host/Core/Python 代码，不改 ReaderHost 契约。
5. 业务语义不变：所有 Host 调用、请求身份、确认对话框、busy/active/managementBusy 锁与持久化格式保持原样。
6. 测试只能迁移定位方式、保留行为目的；不得删除或放宽断言来掩盖回归。基线已失败的测试先记录。
7. 代码风格与周边一致（单行 JSX 密度、命名、注释极少）；颜色/尺寸/动效只能引用 focus-tokens.css 的 token，组件 CSS 不得出现第二套数值表。
8. 本步结束时停下，按“汇报格式”汇报，等待我确认。

每步必须运行：pnpm reader:typecheck、pnpm reader:test、pnpm reader:build，以及本步列出的浏览器测试。截图放 /tmp/focus-library-redesign/shots/<步骤号>/。

汇报格式：
- 改动文件与要点（按文件）
- 验证结果（命令 + 通过/失败数，与基线对比）
- 截图路径与预览方式（隔离宿主端口；需要远程查看时给出 ssh -L 命令）
- 与规范的偏差及原因、未验证项、需要我裁定的问题
```

---

## 第 0 步：导入原型并记录基线

```text
本步只做准备，不修改任何生产代码。

1. 确认以下文件存在且未被修改（若缺失，停下告诉我）：
   - ui/apps/standalone/prototypes/library-directions/index.html
   - ui/apps/standalone/src/prototypes/library-directions/{README.md,data.ts,model.ts,store.ts,parts.tsx,Library.tsx,main.tsx,library.css}
   - docs/design/FOCUS_LIBRARY_REDESIGN_SPEC.md、docs/design/FOCUS_LIBRARY_REDESIGN_PROMPTS.md
   - docs/design/assets/library-redesign/*.png
2. 运行 pnpm reader:typecheck、pnpm reader:test、pnpm reader:build，记录通过/失败数（这是基线）。
3. 用隔离端口启动原型：cd ui/apps/standalone && npx vite --port <空闲端口> --strictPort --host 127.0.0.1，确认 /prototypes/library-directions/index.html 可打开、控制台无错误；确认 dist 中不含 library-directions。
4. 运行与知识库相关的浏览器测试作为基线：tests/confirmed_ux_browser.mjs、tests/preparation_dismiss_browser.mjs、tests/upload_dialog_browser.mjs（按各自脚本头部说明配合隔离宿主），记录结果。
5. 通读规范 §3 与 WorkspaceApp.tsx 约 19–21 行（readingStatus）、约 596 行（主动作按钮文案），列出你认为状态判定与主动作可能不一致的情形（规范 §13 第一条），不要修改。

汇报：基线结果、原型预览方式、§13 第一条的核对结论。
```

---

## 第 1 步：状态模型与 token

```text
目标：建立唯一的状态词表，并新增两个几何 token。规范 §2、§3。

1. 在 ui/packages/reader-ui/src/focus-tokens.css 几何段新增 --reader-inspector:400px 与 --reader-library-content:1080px（只加这两项）。
2. 新建 ui/apps/standalone/src/library/source-status.ts（纯函数，无 React）：
   - 输入 LibrarySource 与 ReadingPreparation | undefined，以及判断“提示已关闭”的布尔值；
   - 输出 { phase, label, tone, detail, ratio }，阶段与判定顺序严格按规范 §3 表格；
   - 导出 primaryAction(...)：把 WorkspaceApp.tsx 约 596 行按钮的文案与 disabled 判定原样抽出（不改任何条件），invalid 返回「查看问题」类型；
   - 导出状态筛选（all/reading/unstarted/completed/attention）与 needsAttention（含博客产物 failed 与 blogs[id].error）；
   - 导出 blogSummary(BlogStatus | undefined)。
   可参考原型 model.ts，但以规范与生产数据为准（preparations、blogs 来自 ReadingWindow）。
3. 新建 source-status.test.ts：表驱动覆盖每个阶段；主动作标签以“重构前的按钮判定”为基准逐条比对。
4. 让现有卡片的 library-summary 与 library-card-bottom 文案都改用该模块（这是本步唯一可见变化）。相应更新测试中的状态文案断言（只改文案，不改断言目的）。
5. 不做任何布局/样式改动。

验证：三条 pnpm 命令；知识库截图 1 张（1440 浅色）证明文案统一。
```

---

## 第 2 步：拆分知识库组件（零行为变化）

```text
目标：把知识库主区从 WorkspaceApp 抽出，为后续替换做准备。规范 §9。

1. 新建 ui/apps/standalone/src/library/LibraryPage.tsx，承接 WorkspaceApp.tsx 中 route === "/library" 的 <main className="library-page"> 整段（约 580–637 行）的渲染。
2. 所有状态与业务函数仍留在 WorkspaceApp；通过一个明确的 props 对象（例如 LibraryPageProps：数据 + 处理函数 + 忙碌标志）传入。不引入 Context、状态库或新依赖。
3. DOM、类名、文案、事件处理与顺序保持完全一致。
4. 现有单元测试与浏览器测试不改即全部通过——这是本步的验收标准。若必须改测试，停下说明原因。

验证：三条 pnpm 命令；tests/confirmed_ux_browser.mjs 与 tests/preparation_dismiss_browser.mjs 通过；git diff --stat 显示 WorkspaceApp 净减少、无其他文件的行为改动。
```

---

## 第 3 步：材料行 + 详情面板 + ⋯ 菜单 + 卡片视图

```text
目标：用材料行与右侧详情面板替换卡片与「详细」展开。规范 §4.4–§4.7、§5（键盘中的 ↑/↓、Esc）、§10。

1. 新建 SourceRow.tsx、SourceCard.tsx、SourceInspector.tsx（以及需要时的小组件），结构与视觉参考原型 parts.tsx / library.css，数值全部用 token。
2. 行：§4.4 全部列；标题为按钮（accessible name = 标题，aria-expanded/aria-controls 指向面板）；单击打开详情、双击执行主动作；主动作调用 enterReading 并沿用全部禁用条件与 title 提示；invalid 的「查看问题」只打开详情。
3. ⋯ 菜单：§4.5 的顺序与禁用条件；复用现有 moreSource 状态与“点击外部关闭”逻辑；Esc 关闭并归还焦点。
4. 详情面板：§4.6 的八个分区，内容全部来自原「详细」展开（preparationNotice、解析状态、format、venue/publishedAt、原件/正文、打开新计划、专题标签、博客区全部按钮）。专题只读 +「编辑」打开现有「管理来源」对话框；不在面板内直接增删专题。打开面板时若 blogs[id] 缺失调用 refreshBlog。
5. 删除 expandedSources / toggleDetails 与「详细」按钮。卡片视图保留（§4.7）；默认视图改为列表，但已有 focus.libraryView 值优先；视图切换可见文字「列表/卡片」，accessible name 保持「列表显示/卡片显示」。
6. 停靠/覆盖：用 CSS 容器查询（内容区 ≥ 1040px 停靠，主列让出 --reader-inspector + gap；否则覆盖）。本步只做静态布局，开合动效留到第 6 步，但面板关闭必须真正移出可访问树（hidden 或 inert）。
7. 键盘：↑/↓ 在可见行间移动；Esc 关闭面板并把焦点还给行标题。
8. 测试迁移（规范 §10）：WorkspaceApp.test.tsx 中所有「详细」改为点击行标题打开面板后断言；约 433 行按钮顺序断言改为 [标题, 主动作, 更多] 且「打开博客」在面板内；tests/confirmed_ux_browser.mjs 约 152–153 行、tests/preparation_dismiss_browser.mjs 改为行 + 面板定位。新增单元测试：面板开合、焦点归还、↑/↓。

验证：三条 pnpm 命令；上述浏览器测试；截图 1440 列表、1440 面板打开、1440 卡片、1024 面板覆盖、1440 深色面板。对照 docs/design/assets/library-redesign/ 中对应截图说明差异。
```

---

## 第 4 步：专题

```text
目标：专题信息与排序。规范 §4.3、§4.11、§5（Alt+↑/↓、拖拽）。

1. 侧栏专题：每项显示「已读完/总数」（completed 阶段计数），新增展示层「未归类」（仅存在无专题来源时显示；用不可能与真实 topicId 冲突的常量；筛选为 topicIds.length === 0）。
2. 视口 ≤ 1180px 侧栏收起时，页头显示专题选择器，与侧栏共用同一 topic 状态。
3. 专题头（新组件 TopicHead.tsx）：已读完 X/N · M 篇阅读中、重命名/删除专题（打开现有对话框），状态色带，排序提示。删除现在堆在列表上方的两个裸按钮。
4. 专题视图行前显示序号（专题内顺序，非筛选后序号）与拖动柄。
5. 拖拽排序：拖动中只做本地预览顺序；drop 时调用一次 host.manageTopic(topicId, "reorder", { sourceIds })（经由现有 manage()，因此沿用 busy 与错误/重试）；失败回滚本地预览。Alt+↑/↓ 调用现有 moveSource，焦点留在原行。⋯ 菜单中的上移/下移保留。
6. 排序在 managementBusy、有搜索词、状态筛选非全部、卡片视图时禁用并显示原因（规范 §5）。本步若状态筛选尚未实现，先按“有搜索词/卡片视图/忙碌”实现，筛选条件在第 5 步补上。
7. FLIP 排序动画可在本步实现（参考原型 useFlip），低动态时立即定位。

测试：单元测试覆盖计数、未归类、拖拽一次只提交一次 reorder、失败回滚、Alt+↑/↓、禁用条件。
验证：三条 pnpm 命令；截图 1440 专题视图、1024 专题选择器。
```

---

## 第 5 步：继续阅读条、状态筛选、影子行、空状态、拖入上传

```text
目标：规范 §4.2、§3（状态筛选）、§4.8、§4.9、§4.10。

1. 继续阅读条：仅在「全部」、无搜索、筛选为全部、view.source 对应阶段为 reading、且 (view.navigationCurrent ?? view.current) 存在时显示；文案 sectionPath.at(-1) · 第 index 段 / 共 total 段；按钮调用 enterReading；点击文字区打开该来源详情。任何数据缺失则不显示。
2. 状态筛选：五个筛选按钮带计数，计数为 0 时禁用（当前选中除外）；作用于当前专题与搜索结果；筛选非全部时专题排序暂停（补齐第 4 步条件）。
3. 影子行（IngestionRows.tsx）：数据只来自现有 taskInbox / taskBatches（与任务框同一数据，不新增轮询）；规则见规范 §4.8；可恢复状态复用任务框对应处理函数；「任务详情」展开页头任务框。复杂的重新提交风险分支只留在任务框。
4. 空状态：五类（规范 §4.9），连接失败需与“空库”区分（依据 listSources 失败且无已加载数据）。
5. 拖入上传：整页投放层替代 outline 虚线；松开后打开现有上传对话框，chooseUpload 预填当前专题名（用户可改）；点击「上传」在专题视图下同样预填。

测试：单元测试覆盖继续阅读条显示条件、各筛选、影子行与任务框数据一致、五类空状态；tests/upload_dialog_browser.mjs 增加“专题视图默认专题”断言。
验证：三条 pnpm 命令；截图：全部视图（含继续阅读条与影子行）、需处理筛选、空库、连接失败、搜索无结果。
```

---

## 第 6 步：响应式、动效、可访问性

```text
目标：规范 §6、§7、§8。

1. 动效：按 §6 表实现。面板/菜单/任务框用 transition（不用 keyframes），可从当前帧反向；关闭时 visibility 延迟到过渡结束；新入库来源只入场一次（挂载时一次性标记，不用 setTimeout 清除）；筛选/搜索/专题切换无位移动画；禁止 hover 抬升行。
2. 低动态：focus.reducedMotion 或 prefers-reduced-motion 下按 §6 最后一列降级。
3. 响应式：按 §7 表。≤ 760px 行为两行网格、页头两行、详情为底部模态弹层（背景 inert，Esc/关闭归还焦点），点击区域 ≥ 40px；pointer:coarse 时拖动柄常显。
4. 可访问性：§8 全部；影子行 role="status" 只在状态文字变化时更新。
5. 不改业务逻辑。

验证：三条 pnpm 命令；截图矩阵 1440/1024/390 × 浅/深，外加 1440 低动态；录屏或逐帧截图证明面板快速开合可反向、关闭无残留。
```

---

## 第 7 步：全量回归、证据与文档

```text
目标：规范 §10 新浏览器测试、§11 第 7 步。

1. 新增 tests/library_browser.mjs（隔离宿主，风格参照 tests/reading_*_browser.mjs）：详情开合与焦点归还、↑/↓、拖拽排序只发 1 个 reorder 请求且失败回滚（可用 page.route 模拟失败）、Alt+↑/↓、筛选暂停排序、五类空状态、面板停靠时列表右侧未被遮挡（几何断言）、低动态无位移、截图矩阵。
2. 全量运行：三条 pnpm 命令，以及 tests/ 下全部浏览器测试；与第 0 步基线逐项对比。
3. 文档：
   - 新增 docs/adr/0027-library-list-and-details-panel.md（status: accepted）：记录方案 A、卡片保留、详情面板替代展开、专题计数/未归类为展示层、拖拽一次提交一次现有 reorder；明确替代 docs/design/FOCUS_UI_CDS2_DESIGN_SPEC.md §5.2 中“详情展开承载……”的表述；不改变的业务语义列表。
   - docs/design/focus-cds-ui.md 增补知识库一行与新截图链接。
   - 新增 docs/design/library-redesign-acceptance.md：逐条对照规范 §3–§8 的通过/未验证表（格式参照 docs/design/reading-redesign-acceptance.md），证据放 docs/design/evidence/library-redesign/。
4. 不合并、不提交；汇报后由我决定。

汇报：全量结果对比表、未验证项（真实数据、触屏、非 Chromium、中文输入法等）、建议的 PR 说明要点。
```
