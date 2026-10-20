# FOCUS 知识库重设计：实施规范（方案 A · 列表 + 详情面板）

状态：方向已选定（2026-10-20），尚未实施。
基础：`main` @ `44ddbd9`（阅读页重设计已合入）。
参考原型：`ui/apps/standalone/src/prototypes/library-directions/`（入口 `ui/apps/standalone/prototypes/library-directions/index.html`，说明见同目录 `README.md`）。原型为合成数据，凡与本文冲突以本文为准。
截图：`docs/design/assets/library-redesign/`。
执行约束见 §12，任何实施前必须先读。

## 0. 已确认决策

| 决策 | 内容 | 影响 |
| --- | --- | --- |
| 方向 | **A 列表 + 详情面板**：一行一份 Reading Source，单一行内主动作；点击行在右侧打开详情面板，替代卡片内「详细」展开 | 展示层 |
| 卡片视图 | 保留为可选显示方式，与行展示同一组信息；不再有卡内展开 | 展示层 |
| 专题 | 侧栏显示 `已读完/总数`；新增展示层「未归类」筛选；专题视图显示序号、状态色带，支持拖拽与键盘排序（复用现有 `manageTopic(reorder)`） | 展示层 + 现有 Host 调用 |
| 继续阅读 | 「全部」视图顶部显示 Cursor State 当前 Source 的继续阅读条，数据来自已有 `ReadingWindow` | 展示层 |
| 本轮不做 | 「按专题阅读 · 下一篇」入口（需新增 ReaderHost 方法与 ADR）；最近阅读排序（无时间戳，不编造） | — |

不改变：上传、入库、准备阅读、开始/继续阅读、重新规划、重新阅读、删除、博客生成/取消/重试、来源与专题管理的 Host 调用、请求身份、确认对话框、忙碌锁与持久化格式。

## 1. 设计语言（与阅读页一致）

1. **一个页面级主按钮**：页头「上传」与继续阅读条的「继续阅读」、详情面板内的主动作为实心按钮；行内主动作为靛青文字按钮；其余操作收进 ⋯ 菜单或详情面板。
2. **颜色分工**：靛青 = 交互状态与位置（选中、进度、焦点）；状态色（success/warning/danger）只用于小色点、细进度条与短文字，文字始终承载含义；琥珀本页不使用。
3. **信息分层**：行只放“扫一眼就要知道”的内容（类型、标题、出处·日期·专题、状态与进度、笔记数、博客状态、主动作）；完整原题、Source ID、解析结果、博客三产物、链接与破坏性操作进入详情面板。
4. **不编造数据**：没有阅读时间戳、没有专题阅读接口时，不显示“最近”“下一篇”。

## 2. Token

不新增颜色。在 `ui/packages/reader-ui/src/focus-tokens.css` 几何段新增两项（仍是唯一数值来源）：

| Token | 值 | 用途 |
| --- | --- | --- |
| `--reader-inspector` | `400px` | 详情面板宽度 |
| `--reader-library-content` | `1080px` | 知识库主列最大宽度 |

其余全部复用现有 token：表面 `canvas / surface-1 / surface-2 / popover`；文字 `ink / secondary / faint`；状态 `accent* / success / warning / danger / *-bg`；阴影 `shadow / shadow-hover / shadow-popover`；动效 `duration-quick/move/travel/exit` 与 `ease-out/inout/in`；几何 `control-h / radius / card-radius / gap-*`。侧栏宽度保持 `--reader-nav` 288 / 56（原型 232 仅为截图紧凑，不采用）。

## 3. 状态词表（唯一映射）

新建纯函数模块（建议 `ui/apps/standalone/src/library/source-status.ts`），替代 `WorkspaceApp.tsx` 中 `library-summary` 与 `library-card-bottom` 两套并存文案。输入 `LibrarySource` 与 `view.preparations?.[sourceId]`，输出阶段、标签、色调、细节文字和主动作。

| 阶段 | 判定（按顺序） | 标签 | 色调 | 细节 |
| --- | --- | --- | --- | --- |
| invalid | `parseStatus !== "ready"` | 解析失败 | danger | — |
| preparing | 准备 `status === "running"` 且 `!selected_ready` | 准备中 | accent | `completed/total 段` |
| prepFailed | 现有 `preparationFailed()` 且 `!selected_ready` 且提示未被关闭（`!preparationHidden()`） | 准备失败 | warning | — |
| completed | 现有 `readingStatus(s) === "completed"` | 已读完 | success | `total 段` |
| reading | `progress.completed > 0` | 阅读中 | accent | `completed/total` |
| ready | 准备 `ready \|\| selected_ready`，或 `readingStatus(s) === "ready"` | 可阅读 | muted | `total 段` |
| unplanned | 其余 | 待准备 | muted | — |

**主动作**：标签与可用性逐字沿用当前卡片按钮的判定（`WorkspaceApp.tsx` 约 596 行：阅读准备中… / 重试准备 / 准备阅读 / 查看已读 / 继续阅读 / 开始阅读），只抽成函数，不改条件；点击仍调用 `enterReading(sourceId)`。`invalid` 的主动作为「查看问题」：选中该行并打开详情面板（不调用 Host）。禁用条件与 `title` 提示（「请先完成或停止当前问答」等）保持不变。

**状态筛选**（展示层）：全部 / 阅读中（reading）/ 未开始（ready、unplanned、preparing）/ 已读完（completed）/ 需处理（invalid、prepFailed，或该来源任一博客产物 `failed` 或 `blogs[id].error`）。计数为 0 的筛选禁用（当前选中者除外）。

**博客摘要**（行内小标记）：读取 `blogs[sourceId]`（来自 `ReadingWindow.blog`，Host 已为每份来源投影，见 `host/service.py` `_blog_summary`）：未生成 / 生成中 / 部分失败 / 已完成；数据缺失时显示中性标记，不为列表新增请求。

## 4. 组件

### 4.1 页面结构

```
侧栏（现有）：知识库 / 阅读 / 设置 · 专题（全部 N · 各专题 已读完/总数 · 未归类 N · ＋新建专题）
页头：标题（知识库 | 专题名 | 未归类）+ 数量 · [窄屏专题选择器] · 搜索 · 列表|卡片 · 任务 · 上传
主列（max --reader-library-content，居中）：
  继续阅读条（仅「全部」且无搜索/筛选）| 专题头（专题视图）
  状态筛选
  入库中影子行
  材料列表 / 卡片网格 / 空状态
详情面板（右侧）
```

### 4.2 继续阅读条

- 数据：`view.source.sourceId` 对应 `sources` 中阶段为 reading 的来源；段落取 `view.navigationCurrent ?? view.current`，显示 `sectionPath.at(-1) · 第 index 段 / 共 total 段`（`index` 为 1 起，与阅读页定位器一致）。任一缺失则不显示，不猜测。
- 动作：「继续阅读」= `enterReading(sourceId)`；点击文字区 = 选中该来源并打开详情。

### 4.3 专题头（专题视图）

- 「已读完 X / N 篇 · M 篇阅读中」+「重命名」「删除专题」（文字按钮，打开现有 `management` 对话框，删除为 danger 色）。替代现在堆在列表上方的两个裸按钮。
- 状态色带：按专题顺序每份来源一段，色调取 §3；`title` 为「标题 · 状态」。
- 提示：「顺序就是专题阅读顺序。拖动左侧序号，或在标题上按 Alt+↑/↓ 调整。」

### 4.4 材料行

列：[序号（仅专题视图）] · 类型标记（PDF / HTML / Markdown，取 `format`）· 主体（标题 + 元信息行）· 状态（标签 + 细节 + 2px 进度条）· 产物（✎ 笔记数 · 博客色点）· 主动作 · ⋯。

- 标题：`displayTitle || title`，单行省略，`title` 属性为原题；标题是按钮（accessible name = 标题，`aria-expanded`/`aria-controls` 指向详情面板）。
- 元信息：`venue · publishedAt`、专题标签（点击切换到该专题筛选）、无专题时「未归类」。
- 行点击 = 选中并打开详情；双击 = 主动作；内部按钮 `stopPropagation`。
- 选中态：`accent-soft` 底 + 左侧 2px 靛青条。悬停只改底色。
- 候选新计划就绪（`preparation.candidate && ready`）时状态细节追加「· 新计划可用」。

### 4.5 ⋯ 菜单

顺序：管理来源（现有对话框）·［上移 / 下移（仅专题视图，作为拖拽的无指针替代）］· 重新规划 · 重新阅读 · 分隔线 · 删除…（danger）。禁用条件与现有按钮完全一致。点击外部或 Esc 关闭并把焦点还给 ⋯。

### 4.6 详情面板（替代「详细」展开）

自上而下：

1. 头部：类型标记 · 关闭 ×。
2. 标题（`displayTitle || title`，18px/600）；有 `displayTitle` 时下方显示原题。
3. 主动作区：状态（§3）+ 主动作实心按钮；若存在候选新计划，追加「打开新计划」（`activateCandidate`）；隐藏失败提示但 `selected_ready` 时的「准备阅读」按钮也放这里。
4. 提示区：现有 `preparationNotice(sourceId)`（含关闭与重试）；解析失败时显示 `s.error`。
5. **专题**：专题标签（只读，点击切换筛选）+「编辑」→ 打开现有「管理来源」对话框。不在面板内直接增删专题（避免引入不含标题的独立保存语义）。
6. **博客**：带读博客与 HTML 两项状态、错误；按钮沿用现有逻辑：打开博客（打开现有查看器）/ 生成博客 / 取消生成 / 按产物重新生成 / 重新生成。
7. **来源**：出处、日期、笔记 N 条、解析结果、Source ID（mono）；原件 ↗、正文 ↗（`host.sourceOriginalUrl/sourceContentUrl`）、编辑标题（现有对话框）。
8. **重置与删除**（danger 小标题）：重新规划、重新阅读、删除来源…（均走现有确认对话框）。

打开面板时若 `blogs[id]` 缺失则调用现有 `refreshBlog(id)`（替代 `toggleDetails` 中的同一调用）。

### 4.7 卡片视图

网格 `minmax(280px,1fr)`；卡片 = 类型 + 状态 + ⋯ / 标题（两行）/ 元信息 / 进度条 + 产物 + 主动作。点击卡片打开详情。卡片视图下不提供拖拽排序，显示提示「切换到列表视图后可调整专题顺序」。默认视图改为列表（`focus.libraryView` 已有值时保持用户选择）。视图切换按钮可见文字「列表 / 卡片」，accessible name 保持「列表显示 / 卡片显示」。

### 4.8 入库中影子行

- 数据：现有 `taskInbox` 与 `taskBatches` 中尚未成为来源（无 `sourceId` 或该 ID 不在 `sources`）且未完成的条目；专题视图只显示目标专题匹配的条目。
- 内容：虚线类型标记 · 文件名 · 「解析后端 · 状态 · 百分比」（复用 `statusText / itemStatusText` 与 `parserBackend / parserProgress` 文案）· 进度条 ·「将加入 #专题 / 不关联专题」。
- 动作：可恢复状态显示一个主动作（复用任务框中对应的「继续 / 重试未完成步骤」处理函数）；其余只给「任务详情」→ 展开页头任务框。重新提交风险等复杂分支只留在任务框。
- 不把每个百分比变化播报给读屏：`role="status"` 只在状态文字变化时更新。

### 4.9 空状态

| 情形 | 判定 | 文案 | 动作 |
| --- | --- | --- | --- |
| 连接失败 | `listSources` 失败且无已加载数据 | 无法连接 FOCUS 后端，列表未能读取。已有数据未受影响。 | 重新连接（`refresh()`） |
| 空库 | 无来源 | 知识库还是空的。把 PDF 或 SingleFile HTML 拖到这里，或点击上传。 | 上传材料（主按钮） |
| 搜索无结果 | 有搜索词 | 没有标题匹配这次搜索。 | 清除搜索 |
| 筛选无结果 | 状态筛选非全部 | 当前筛选下没有材料。 | 显示全部状态 |
| 专题为空 | 专题内无来源 | 这个专题还没有来源。可从任意来源的「管理来源」中加入专题。 | 查看全部材料 |

### 4.10 拖入上传

整页投放层（虚线框 + 「松开即可上传」+ 解析说明）替代现在的 `outline` 虚线；松开后打开**现有上传对话框**，专题字段默认填当前专题名（用户仍可修改）。

### 4.11 侧栏专题

- 每项右侧 `已读完/总数`（`tabular-nums`），`title`「已读完 X / N 篇」。
- 「未归类」仅当存在无专题来源时显示，值为展示层常量（不得写入 Host，不得与真实 topicId 冲突）。
- 宽度 ≤ 1180px 侧栏收起时，页头显示专题选择器（同一 `topic` 状态），修复现在专题入口消失的问题。

## 5. 交互与键盘

| 操作 | 行为 |
| --- | --- |
| ↑ / ↓（焦点不在输入框、菜单或面板内） | 在可见行间移动焦点与选中；面板已打开时跟随切换内容 |
| Enter / Space（行标题） | 打开详情 |
| 双击行 | 主动作 |
| Esc | 关闭菜单；否则关闭详情并把焦点还给该行标题 |
| Alt+↑ / Alt+↓（专题视图、行标题） | 与相邻来源交换顺序（调用现有 `moveSource`），焦点留在原行 |
| 拖拽序号 | 拖动中仅本地预览；`drop` 时提交一次 `manageTopic(reorder, sourceIds)`；失败回滚并显示错误与「重试此操作」 |

排序在以下情况禁用并显示原因：`managementBusy`、有搜索词、状态筛选非全部、卡片视图。

## 6. 动效

| 场景 | 属性与参数 | 打断 | 低动态 |
| --- | --- | --- | --- |
| 详情面板开 | opacity + translateX(20px→0)，move/out | transition，可从当前帧反向 | 无位移 |
| 详情面板关 | 反向，exit/in；`visibility` 延迟到结束 | 同上 | 无位移 |
| 窄屏底部面板 | translateY(24px→0) + 背景遮罩，move/out | 同上 | 仅显隐 |
| ⋯ 菜单 / 任务框 | scale .98 + translateY(-4px) + opacity，move/out；退出 exit/in；origin 右上 | 同上 | opacity |
| 排序 | FLIP translateY，travel/inout | 新排序从当前位置改道 | 立即定位 |
| 新入库来源出现 | opacity + translateY(8px)，move/out，仅一次 | — | 无 |
| 进度条 | transform scaleX，move/out | — | 无过渡 |
| 投放层 | opacity，quick | — | 同 |
| 筛选 / 搜索 / 专题切换 | 无位移动画 | — | — |
| 按下主按钮 | scale .98，60ms | — | 无 |

禁止：hover 抬升行、列表整体入场、持续闪烁。低动态 = 设置 `focus.reducedMotion` 或 `prefers-reduced-motion`。

## 7. 响应式

| 条件 | 布局 |
| --- | --- |
| 内容区宽度 ≥ 1040px（容器查询） | 详情面板停靠右侧，主列右侧让出 `--reader-inspector + gap`，列表不被遮挡 |
| 内容区 < 1040px | 详情面板覆盖在列表右侧（浮层阴影），焦点进入面板，Esc 归还 |
| 视口 ≤ 1180px | 侧栏收起为 56px；页头出现专题选择器；行内隐藏产物列 |
| 视口 ≤ 760px | 页头两行（标题 + 专题选择器 + 任务 + 上传 / 搜索）；行改为两行网格（标题行 + 状态/主动作行）；详情面板为底部弹层（顶部留 12dvh）且为模态（背景 inert）；点击区域 ≥ 40px |
| `pointer:coarse` | 序号旁拖动柄常显；仍保留 ⋯ 菜单上移/下移 |

## 8. 可访问性

- 列表 `role="list"`，行为 `listitem`；标题按钮承担选中/展开语义。
- 详情面板：停靠时 `role="complementary"`、`aria-label="来源详情"`；覆盖/弹层时作为对话框处理焦点。
- 所有状态有文字，不只靠颜色；对比度沿用 token（`secondary` ≥ 4.5:1）。
- 中文输入法：搜索框不在 composing 期间触发额外行为。

## 9. 相对现有代码的修改点

| 文件 | 修改 | 复用 |
| --- | --- | --- |
| `ui/packages/reader-ui/src/focus-tokens.css` | 新增 §2 两个几何 token | 全部现有 token |
| 新增 `ui/apps/standalone/src/library/`（建议拆分：`source-status.ts`、`LibraryPage.tsx`、`SourceRow.tsx`、`SourceCard.tsx`、`SourceInspector.tsx`、`TopicHead.tsx`、`IngestionRows.tsx`、`LibraryEmpty.tsx`、`use-flip.ts`） | 知识库视图组件；状态模块带单元测试 | 原型 `model.ts`、`parts.tsx`、`Library.tsx` 的结构与样式 |
| `ui/apps/standalone/src/WorkspaceApp.tsx` | 知识库主区（约 580–637 行）改为渲染 `LibraryPage`；侧栏专题（约 495–500 行）加计数与未归类；删除 `expandedSources/toggleDetails` 与「详细」；`chooseUpload` 预填当前专题；默认视图改为列表 | 所有业务函数：`operate`、`enterReading`、`retryPreparation`、`activateCandidate`、`moveSource`、`manage`、`openManagement`、`confirmDelete`、`blogAction` 系列、`controlBatch`、`ingest`、确认/管理/上传/博客对话框、任务框 |
| `ui/apps/standalone/src/standalone.css` | 替换 `/* ---------- library ---------- */` 段中卡片/详情相关样式；新增行、面板、筛选、专题头、影子行、空状态、投放层；`.library-inbox*` 仍服务任务框，保留 | 控件、对话框、任务框、响应式骨架 |
| 测试 | 见 §10 | — |
| 文档 | 新 ADR 0027（知识库列表与详情面板；替代 CDS 规范 §5.2 中“详情展开承载……”的表述）；`docs/design/focus-cds-ui.md` 增补；验收记录 | — |

## 10. 测试迁移（保留行为目的，不得以删除断言掩盖回归）

- `ui/apps/standalone/src/WorkspaceApp.test.tsx`：所有「点击 详细」改为点击行标题（accessible name = 来源标题）打开详情面板，再在面板内断言原内容（准备提示、博客状态、原件/正文、打开新计划等）。约 433 行“卡片按钮顺序”断言改为行内按钮顺序：`[标题, 主动作, 更多]`，并断言「打开博客」位于详情面板。「暂无匹配材料」改为 §4.9 新文案。「列表显示 / 卡片显示」accessible name 不变。
- `tests/confirmed_ux_browser.mjs`（约 152–153 行，`.library-card` + `aria-controls="source-details-…"` 定位「打开博客」）：改为打开该来源详情面板后定位按钮。
- `tests/preparation_dismiss_browser.mjs`（`.library-card` 与「详细」）：改为行 + 详情面板；`.preparation-notice` 断言不变。
- `tests/upload_dialog_browser.mjs`：增加“专题视图下打开上传，专题默认为当前专题”断言。
- 新增 `source-status.test.ts`：§3 每个阶段、主动作标签与现有判定逐条一致（以重构前的标签为基准表驱动）。
- 新增 `tests/library_browser.mjs`（隔离宿主）：详情开合与焦点归还、↑/↓、专题排序（拖拽 1 次只发 1 个 reorder 请求；失败回滚）、Alt+↑/↓、筛选暂停排序、空状态四类、1440/1024/390 × 浅/深截图、低动态无位移、面板停靠时列表未被遮挡。

## 11. 实施顺序

每步独立可验证，结束后停下等待用户确认。

1. **状态模型与 token**：`source-status.ts` + 测试；新增 token；现有卡片文案改用该模块（唯一可见变化：状态文案统一）。
2. **拆分**：把知识库主区抽成 `LibraryPage` 等组件，props 传入现有状态与处理函数；**零视觉与行为变化**，全部现有测试不改即通过。
3. **材料行 + 详情面板 + ⋯ 菜单 + 卡片视图**：替换卡片与「详细」；迁移 §10 相关测试。
4. **专题**：侧栏计数与未归类、窄屏专题选择器、专题头、序号、拖拽与键盘排序。
5. **继续阅读条、状态筛选、影子行、空状态、拖入上传默认专题**。
6. **响应式、动效、可访问性**：§6–§8。
7. **全量回归与证据**：新浏览器测试、截图矩阵、ADR 0027 与文档；用户确认后再决定合并。

## 12. 执行约束（实施者必须遵守）

1. **Git**：不 commit、不 push、不切换或新建分支，不 `stash/reset/checkout -- <file>`，除非用户明确要求；只读的 `git status/diff/log` 可以。
2. **原型与规范只读**：`ui/apps/standalone/prototypes/library-directions/`、`ui/apps/standalone/src/prototypes/library-directions/` 与本文件不得修改或删除；生产构建不得包含原型。
3. **不替换正在使用的界面**：开发服务器上若运行着正式 FOCUS 服务，不重启、不在其产物上验收。预览用隔离宿主 `tests/confirmed_ux_browser.py`（夹具数据，`FOCUS_BROWSER_PORT=<空闲端口> PYTHONUTF8=1`，服务 `ui/apps/standalone/dist`，绑定 127.0.0.1）。注意 `pnpm reader:build` 会重写 `dist`，若正式服务直接使用该目录，先确认或改用独立输出目录。
4. **范围最小**：每步只改该步列出的文件与关注点；不顺手重构阅读页、设置页或任务框。
5. **每步验证**：`pnpm reader:typecheck`、`pnpm reader:test`、`pnpm reader:build`，以及该步相关浏览器测试；截图放 `/tmp/focus-library-redesign/shots/<步骤>/`。先记录基线失败，不得以修改断言掩盖回归。
6. **每步结束停下**：汇报改动文件与要点、验证结果、截图路径、预览方式与未验证项，等待确认。
7. **不改业务语义**：§0 “不改变”所列全部保持；新增的唯一 Host 调用模式是拖拽一次提交一次现有 `reorder`。

## 13. 风险与待核对

- §3 中 `ready` 阶段标签与现有主动作“准备阅读/开始阅读”在“有 Plan 但无准备记录”时可能不一致；第 1 步用夹具与真实数据核对，若不一致记录并请用户裁定，不擅自改主动作条件。
- `view.navigationCurrent` 仅在当前 Source 的阅读窗口中可靠；知识库首屏加载时若 `ReadingWindow` 尚未就绪，继续阅读条延迟出现而非显示占位数据。
- HTML5 拖拽在触屏不可用：以 ⋯ 菜单上移/下移与 Alt+↑/↓ 为保底。
- 影子行与任务框展示同一条目：两处状态必须来自同一数据，不得各自轮询。
