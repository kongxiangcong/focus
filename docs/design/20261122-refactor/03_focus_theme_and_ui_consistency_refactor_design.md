# 设计文档 03：简洁主题系统、布局错位清零与 UI/动效一致性重构（修订版）

> **所属序列**：Focus 重构体系 · 文档 03（底座可于 Batch A 提前交付；最终视觉回归于 Batch C 收口）
> **基线版本**：`focus-d4fb6a5a36af50e01611fe26ff949749226c0300`
> **核心修订**：修复正式 Host CSP 阻断（改用同源外部脚本）；**深色模式锁定单一炭灰极简方案，仅浅色模式支持 4 套配色**，真实视觉矩阵收敛为 5 套。

---

## 1. 视觉审美目标与现状污染清零

### 1.1 设计定位

彻底去除偏暖黄底色、暖橘外发光、重弥散阴影与底部渐隐遮罩，参考 **ChatGPT、Claude、deepseek-harness** 的极简克制审美：

- **浅色模式（4 套可选配色）**：主阅读画布恒为纯白 `#FFFFFF`，侧边栏为极浅冷灰 `#F7F7F8`，正文为高对比墨黑 `#111827`；边框、主按钮、激活态与焦点环支持用户选择 **钴蓝白 / 松青绿白 / 绯红白 / 极简黑白**（占画面 5%–10%）。
- **深色模式（单一权威方案）**：锁定一套三档低饱和中性炭灰层叠（`#161719` → `#1D1F23` → `#24272C`）+ 极细白透明边线，**不叠加彩色 Accent 变体**，从根源消除 `dark + red` 撞报错色与多余维护面。

### 1.2 现有视觉与 Token 污染清零清单

| 类别 | 精确文件与行号 | 清理动作 |
| :--- | :--- | :--- |
| 暖橘外发光与重弥散阴影 | `mist-reader.css:99`、`standalone.css:112`、`focus-tokens.css:103-105, 195-197` | 删除 `hsla(20,58%,52%,.14)` 橘色光晕与 `32px/44px` 浮空投影，改为 `1px` 细边框 + `0 1px 2px` / `0 4px 16px` 克制微投影 + `2~3px` 干净焦点环。 |
| 底部渐隐与渐变分割线 | `conversation-reader.css:38, 102`、`reader-figures.css:19` | 底部渐隐改为纯色 `var(--reader-canvas)` + `border-top: 1px solid var(--reader-line)`；拖拽分割线统一改为 `::after` 1px 纯色伪元素。 |
| 未定义幽灵 Token 与硬编码 | `conversation-reader.css:130, 133, 134, 213, 217, 220, 237`、`focus-tokens.css:11` | 替换未定义的 `--reader-shadow-rest`、`--reader-shadow-focus`、`--reader-surface-muted`（暗色下导致 PDF 容器变刺眼 `#e9e8e5`）；在暗色块补齐 `--reader-measure-panel-shadow`；全站 `::backdrop` 统一走 `--reader-backdrop`。 |
| 历史死别名与冗余抄写 | `focus-tokens.css:16-31, 141-143, 174-182`、`mist-reader.css:5-6` | 删除零引用别名（`--reader-glass*`、`--reader-blur`、`--reader-paper`、`--reader-sidebar`、`--reader-subtle`）、`.focus-mist` 无效短名变量，及暗色块重复抄写的几何尺寸。 |
| 暗淡降透原型感 | `conversation-reader.css:64-82`、`mist-reader.css:74`、`reader-shell.css:21`、`standalone.css:90` | 取消历史对话过度降透明度（`opacity: .54`）；全站按钮 hover 由 `filter: brightness(1.12)` 改为语义令牌 `background: var(--reader-action-hover)`。 |

---

## 2. 简洁主题 Token 架构（浅色 4 套 + 深色 1 套）

在 `<html>` 上挂载 **`data-theme="light|dark"`** 与 **`data-accent="blue|green|red|neutral"`**：

- **`data-theme="light"`**：基础表面层恒定纯白/极浅灰；`[data-theme="light"][data-accent="..."]` 控制 7 个强调色 Token（`--reader-accent`、`--reader-accent-hover`、`--reader-accent-ink`、`--reader-accent-soft`、`--reader-accent-line`、`--reader-accent-ring`、`--reader-on-accent`），并将主操作 `--reader-action*` 映射至 `--reader-accent*`。
- **`data-theme="dark"`**：**不响应 `data-accent` 变色**，固定采用单一炭灰高可读配色（主控 `#E4E6EB` 配深墨字 `#161719`）；但 `localStorage` 中的 `focus.accent` 完整保留，切换回浅色或“跟随系统”自动切回浅色时立即恢复用户选定的浅色配色。
- **不可变语义层（仅受 `data-theme` 控制）**：`--reader-danger / success / warning`、`--reader-battery-*` 与 `--reader-mark-*` 独立锁定，永不随 Accent 漂移。

### 2.1 浅色基底与 4 套 Accent 配色矩阵

**浅色基底**：`--reader-canvas: #FFFFFF` · `--reader-surface-1: #F7F7F8` · `--reader-surface-2: #FFFFFF` · `--reader-user-bubble: #F3F4F6` · `--reader-ink: #111827` (17.74:1) · `--reader-ink-2: #4B5563` (7.56:1) · `--reader-ink-3: #667085` (4.97:1) · `--reader-line: #E5E7EB` · `--reader-line-strong: #D1D5DB` · `--reader-backdrop: rgba(17, 24, 39, 0.42)`。

| Token | 钴蓝白 `blue`（默认） | 松青绿白 `green` | 绯红白 `red` | 极简黑白 `neutral` |
| :--- | :--- | :--- | :--- | :--- |
| `--reader-accent` | `#1D4ED8` | `#0F766E` | `#9F1239` | `#18181B` |
| `--reader-accent-hover` | `#1E40AF` | `#115E59` | `#881337` | `#27272A` |
| `--reader-accent-ink` | `#1E40AF` | `#115E59` | `#881337` | `#18181B` |
| `--reader-accent-soft` | `rgba(29, 78, 216, 0.09)` | `rgba(15, 118, 110, 0.09)` | `rgba(159, 18, 57, 0.08)` | `rgba(24, 24, 27, 0.07)` |
| `--reader-accent-line` | `rgba(29, 78, 216, 0.42)` | `rgba(15, 118, 110, 0.42)` | `rgba(159, 18, 57, 0.40)` | `rgba(24, 24, 27, 0.35)` |
| `--reader-accent-ring` | `rgba(29, 78, 216, 0.18)` | `rgba(15, 118, 110, 0.18)` | `rgba(159, 18, 57, 0.16)` | `rgba(24, 24, 27, 0.14)` |
| `--reader-on-accent` | `#FFFFFF` | `#FFFFFF` | `#FFFFFF` | `#FFFFFF` |
| 主按钮对比度 | `6.70 : 1` (AA+) | `5.47 : 1` (AA+) | `8.02 : 1` (AAA) | `17.72 : 1` (AAA) |

#### 红白 / 绿白防语义冲突四重机制

1. **色相与明度正交**：红白主色选冷调印章绯红 `#9F1239`（H≈344°），系统错误锁死暖调警报红 `#DC2626`（H≈0°）；绿白主色选冷调松青 `#0F766E`（H≈175°），系统成功锁死正翠绿 `#15803D`（H≈142°）。
2. **非颜色冗余编码**：所有 Error / Success / Warning 提示条强制带语义图标 + 1px 语义边框（`#FECACA` / `#BBF7D0` / `#FDE68A`）；Accent 交互态永不带状态图标。
3. **85 / 10 / 5 面积克制**：阅读画布与正文占 85% 以上，Accent 仅覆盖边框、主按钮与激活态。
4. **实心主按钮 vs 描边危险按钮**：正向主操作为实心 Accent 底 + 白字；危险操作（删除/清空）统一采用白底 + `#DC2626` 警报红字 + 1px `#FECACA` 细框。

### 2.2 深色单一权威配色（`data-theme="dark"`）

| 层级 | Token 与色值 | 说明 |
| :--- | :--- | :--- |
| 表面层 | `--reader-canvas: #161719` · `--reader-surface-1: #1D1F23` · `--reader-surface-2: #24272C` · `--reader-user-bubble: #2B2F36` | 三档中性炭灰 |
| 文字与边线 | `--reader-ink: #ECEEF1` (15.43:1) · `--reader-ink-2: #A6ACB6` · `--reader-ink-3: #8B929E` · `--reader-line: rgba(255,255,255,0.08)` · `--reader-backdrop: rgba(0,0,0,0.65)` | 全场景 AA/AAA |
| 交互主控（固定单一） | `--reader-accent: #E4E6EB` · `--reader-accent-hover: #F3F4F6` · `--reader-on-accent: #161719` (14.36:1) · `--reader-accent-soft: rgba(228,230,235,0.12)` · `--reader-accent-line: rgba(228,230,235,0.38)` | 克制无霓虹，零撞报错色风险 |
| 语义状态色 | `danger: #F87171` (`bg #2C1618`) · `success: #4ADE80` (`bg #132A1E`) · `warning: #FBBF24` (`bg #2B2212`) | 不可变锁定 |

### 2.3 正式 Host CSP 安全的防 FOUC 启动脚本（关键修正）

正式 Host（`host/server.py:120`）返回严格 `Content-Security-Policy: default-src 'self'`，**任何 `<head>` 内联 `<script>` 都会被浏览器拦截失效**。

- **正确方案**：在 `ui/apps/standalone/public/theme-init.js` 提供无依赖、同源的**同步外部脚本**，在 `index.html` 的 `<head>` 末尾以 `<script src="/theme-init.js"></script>` 同步引入（确保构建产物与正式 Host 静态路由均可同源访问）。
- **逻辑复用**：复用现有 `system`（`window.matchMedia("(prefers-color-scheme: dark)")`）解析逻辑，并对 `localStorage` 不可用/抛异常（隐私模式、权限受限）提供 `try/catch` 安全回退（`theme = "light"`, `accent = "blue"`）。
- **设置页 UI（`WorkspaceApp.tsx:736-750`）**：主题升级为 `跟随系统 / 浅色 / 深色` 三段式单选；下方仅在浅色（或跟随系统）时展示 4 组带色点的浅色配色胶囊（深色模式下显示“浅色配色已保留，切回浅色生效”提示）；右侧预览卡包含主按钮、激活标签、焦点环与错误/成功微徽章实时对照。

---

## 3. 全量布局错位修复、样式隔离与动效统一

### 3.1 布局错位修复清单（可随 Batch A 提前交付）

| 级别 | 问题现象 | 精确位置 | 修复方案 |
| :--- | :--- | :--- | :--- |
| **P0** | `AnnotationRail` 窄屏折叠算错且卡片压正文 | `AnnotationRail.tsx:33-38`、`FocusReader.tsx:676, 681`、`reader-annotations.css:46-49` | 读取 `.reading-group-source` 真实 `getBoundingClientRect().width` 替代 `parseFloat("calc(...)")`；父级统一下发单一折叠布尔值。 |
| **P0** | 全屏退出钮与笔记抽屉/博客浮钮重叠 | `standalone.css:487-495, 603`、`conversation-reader.css:168` | 全屏退出钮收归工具条或在抽屉打开时避让；全屏博客浮钮增加 `right: 60px`。 |
| **P0** | 批注浮层被裁切或掉出底边 | `annotations/placement.ts:1-13`、`mist-reader.css:11` | 按 `[root.left + 8, root.right - width - 8]` 与 `innerHeight - height - 8` 双向 clamp（或 Portal 挂至 `body`）。 |
| **P1** | 管理/确认弹窗按钮全宽堆叠或无间距 | `WorkspaceApp.tsx:778-779, 803`、`standalone.css:425-426` | 统一显式类名 `.workspace-dialog-actions`，废弃 `form > div:last-of-type`。 |
| **P1** | 右下角通知条叠放且 `.configuration-notice` 缺 `z-index` | `standalone.css:412-417`、`WorkspaceApp.tsx:810-818` | 统一右下角 `flex-direction: column; gap: 8px; z-index: 30` 通知栈。 |
| **P1** | `761~1180px` 知识库双倍水平内边距 | `standalone.css:120-124, 307, 502` | 从 L502 / L522 移除 `.library-page`，仅调整 `.library-sources`。 |
| **P1** | 侧栏阅读分支折叠钮触屏下偏位 | `standalone.css:531, 565-572`、`WorkspaceApp.tsx:571-585` | 链接与折叠钮改用 `display: flex; align-items: center` 包裹，取消负 `top` 绝对定位。 |
| **P1** | 证据卡与划词浮条重合、`content-visibility:auto` 跳转偏移 | `conversation-reader.css:28, 161, 176`、`ConversationReader.tsx:358, 423` | 共享底部 flex 栈；长距离跳转后二次校正 `scrollTop`。 |
| **P1** | `UploadTopicPicker` 键盘选中项不可见 | `UploadTopicPicker.tsx:51`、`standalone.css:437-440` | 补全 `.upload-topic-options button[data-active=true]` 高亮样式。 |
| **P2** | 窄屏精读抽屉跳闪 & 文库末行菜单裁剪 | `mist-reader.css:157-169, 312-319`、`standalone.css:169` | `<= 720px` 抽屉改覆盖层；`.library-more-menu` 动态向上展开或走 Portal。 |

### 3.2 样式隔离与动效一致性

- **解除 `ConversationReader` 壳层污染**：`standalone.css:78-97` 排除范围扩至 `:not(.focus-reader *, .unified-reader *)`，清零 `conversation-reader.css` 中 12 处 `!important`；统一双模式 Composer、气泡、工具条、三大抽屉及全站 `1px` 边框与 `<h1>` 字号。
- **消除重排与高频采样**：`.reading-lens` 移除 `height` 过渡改用 `clip-path` 或 `transform`；`updateChatFocus` 改用 rAF 合并采样或 `IntersectionObserver`；所有 `<dialog>` 统一 `@starting-style` + `allow-discrete`，`.source-notes-drawer` 保持挂载做位移动效。
- **统一低动态模式**：移除 `standalone.css:535` 与 `reader-shell.css:78` 的 `* { ... !important }`，在 `focus-tokens.css` 同步覆盖 `@media (prefers-reduced-motion: reduce)` 与 `:root[data-reduced-motion="true"]`，关闭进度条、2.4s 区域闪烁与位移动画，仅保留轻量 `opacity` 淡入。

---

## 4. 验收标准

1. **正式 Host 冷启动零 FOUC 与 CSP 合规**：直接通过正式 Host 访问 `/reading` 冷启动深色模式，首帧无闪白、浏览器控制台 0 条 CSP 报错；`localStorage` 禁用时安全回退浅色钴蓝白。
2. **5 套真实主题组件级颜色与行为验收**：
   - 对 **浅色 4 套（蓝/绿/红/黑白）+ 深色 1 套** 全部执行**组件级**对比度校验（含实际按钮底/字、悬停态、焦点环、激活导航、错误/成功提示条与电量框并列），代表组合执行全页截图回归；
   - **行为用例（`theme="system"`）**：切换操作系统浅色 ↔ 深色，验证界面自动切入单一炭灰深色并在切回浅色后完整恢复用户选定的 `focus.accent`。
3. **样式纯净度与响应式**：`conversation-reader.css` `!important` 归零；`pnpm --filter @focus/reader-ui test`（含 `reader-annotations-css.test.ts`）全绿；`720px / 1024px / 1440px` 与触屏模拟下无错位、无裁切。