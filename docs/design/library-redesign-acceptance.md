# 知识库重设计验收

日期：2026-10-20。范围：[实施规范](FOCUS_LIBRARY_REDESIGN_SPEC.md)方案 A，第 0–7 步。用户授权逐步本地提交并继续开发，免除截图要求；不包含 push、合并或部署。原型和规范保持只读。

## 证据口径

“单元通过”仅指纯函数、React/jsdom 或受控动画 API 测试，不等于浏览器布局、真实鼠标/触屏、视觉或辅助技术验收。“静态核对”只证明代码存在及其范围。“浏览器未验证”表示脚本虽已编写且语法通过，但环境在浏览器启动前阻断，不能把脚本中的断言当作通过结果。

逐步记录与最终命令结果见 [evidence/library-redesign](evidence/library-redesign/07-regression.md)，浏览器逐项状态见 [browser-inventory.json](evidence/library-redesign/browser-inventory.json)。没有新截图、录屏或伪造的几何结果；旧 CDS 截图不是本次验收证据。

## 基线与最终检查

最终 typecheck/build 通过；串行 reader-ui 86/86、standalone 150/150（10 文件，比原基线新增 60 项）通过；默认 reader:test 为 reader-ui 84 通过 / 2 个 5 秒超时失败，未继续 standalone。完整命令统计见 [第 7 步回归记录](evidence/library-redesign/07-regression.md)。第 0 步 typecheck/build 通过；默认 reader:test 在 reader-ui 为 82/86，串行 reader-ui 86/86；standalone 变更前补充基线为 84 通过 / 6 失败（90 项）；104/104 是第 2 步新增 14 项状态测试后的结果，并非第 0 步基线。默认 reader:test 的 5 秒资源敏感超时始终与串行补充结果分列，不将补充命令改称默认命令通过。

## 逐条验收：规范 §3–§8

| 条款 | 状态 | 证据与边界 |
| --- | --- | --- |
| §3 七阶段、有序优先级、标签/色调/细节 | 单元通过 | source-status.test.ts 表驱动，含 selected_ready、隐藏失败与候选状态 |
| §3 主动作逐字沿用、busy/active/能力条件 | 单元通过 | 原表达式的状态组合穷举；invalid 仅打开问题详情，不请求 Host |
| §3 五筛选、需处理含博客失败、零计数规则 | 单元通过 | source-status.test.ts；library-filtering.test.ts，Topic+搜索范围后计数 |
| §3 博客缺失/未生成/生成中/失败/完成摘要 | 单元通过 | source-status.test.ts；列表不新增博客请求，详情缺失时复用 refreshBlog |
| §4.1 侧栏、共享页头、主列、单一详情区 | 静态核对；浏览器未验证 | WorkspaceApp/LibraryPage/CSS；library_browser.mjs 响应式几何断言待运行 |
| §4.2 Continue Reading 来源/段落/条件与动作 | 单元通过 | library-filtering.test.ts，真实 navigationCurrent 优先与十类抑制条件；缺失不猜测 |
| §4.3 Topic 计数、状态色带、顺序提示与管理 | 单元通过 | topic-ordering.test.ts；TopicHead 重用现有管理入口，按 manifest 顺序 |
| §4.4 行信息、标题名称/展开语义、单击/双击、候选提示 | 单元通过；视觉未验证 | WorkspaceApp.test.tsx；SourceRow/SourceParts；原件/正文/博客断言保留 |
| §4.4 行悬停仅换背景、选中标识、截断与进度 | 静态核对；浏览器未验证 | standalone.css/token；LibraryProgress 可访问值单元通过，真实截断待测 |
| §4.5 更多菜单顺序、锁、Esc/外部关闭与焦点 | 单元通过 | WorkspaceApp.test.tsx、library-accessibility.test.tsx；闭合保留 DOM，但 inert/aria-hidden |
| §4.6 详情八分区及全部既有业务按钮 | 单元通过；布局未验证 | SourceInspector；迁移后的 WorkspaceApp.test.tsx 保留准备/博客/链接/候选/确认意图 |
| §4.6 专题只读标签 + 编辑、博客缺失才刷新 | 单元通过 | SourceInspector 现有管理对话框；原 refreshBlog 条件与测试 |
| §4.7 可选卡片、无卡内展开、默认列表/保留旧偏好 | 单元通过；网格未验证 | WorkspaceApp.test.tsx、topic-ordering.test.tsx；卡片停用排序且显示说明 |
| §4.8 影子行与任务框同源、排除已注册/完成、Topic 匹配 | 单元通过 | library-filtering.test.tsx；taskInbox/taskBatches 同一投影，无新增轮询 |
| §4.8 安全继续/重试复用、风险重新提交只在任务框 | 单元通过 | library-filtering.test.tsx 检查相同回调及风险隔离 |
| §4.8 live status 不包含百分比 | 单元/静态通过；读屏未验证 | IngestionRows 百分比为独立 sibling；原生读屏播报频率待实测 |
| §4.9 连接失败、空库、搜索空、筛选空、专题空及恢复 | 单元通过；浏览器未验证 | library-filtering.test.tsx 覆盖失败结果/拒绝/同步抛错、保留旧数据及每个动作；新浏览器五场景待执行 |
| §4.10 全页投放层、现有上传对话框、默认当前专题 | 单元通过；真实文件拖入未验证 | library-filtering.test.tsx；upload_dialog_browser.mjs 新默认值断言；Unfiled 不传入 Host |
| §4.11 侧栏已读完/总数与 Unfiled、窄屏共用选择器 | 单元通过；布局未验证 | topic-ordering.test.tsx；展示 sentinel 与合法 Topic ID 不冲突，空选中值可恢复 |
| §5 ↑/↓ 可见行焦点/选中、Enter/Space 打开 | 单元通过；浏览器未验证 | WorkspaceApp.test.tsx；library_browser.mjs 增加真实键盘断言 |
| §5 Esc 菜单优先、否则详情、标题/更多焦点归还 | 单元通过；浏览器未验证 | library-accessibility.test.tsx，包括移至共享页头后的搜索框/选择器与 IME/native dialog 例外 |
| §5 Alt+↑/↓、拖拽预览/drop 一次提交、失败回滚重试 | 单元通过；原生拖拽未验证 | topic-ordering.test.tsx；library_browser.mjs 实际 HTTP 计数、顺序、错误与重试断言待运行 |
| §5 busy/搜索/状态筛选/卡片排序禁用且解释 | 单元通过 | topic-ordering.test.tsx、library-filtering.test.tsx，三个排序入口共享 guard |
| §6 面板/菜单/任务框可逆 transition、退出 visibility | 单元/静态通过；真实中间帧未验证 | library-accessibility.test.tsx retained DOM；CSS transition；新浏览器中间帧反向断言未执行 |
| §6 排序 FLIP 可改道、新来源仅一次入场 | 单元通过；浏览器未验证 | use-library-motion.test.tsx，模拟 WAAPI、滚动坐标、不因重挂载再次入场 |
| §6 筛选/搜索/专题切换无位移、无整体入场/悬停抬升/闪烁 | 单元/静态通过；视觉未验证 | use-library-motion.test.tsx 上下文/成员 guard；CSS 核对 |
| §6 进度 transform scaleX、投放层 opacity、按钮按下 | 单元/静态通过；浏览器未验证 | LibraryProgress/use-library-motion 与 token CSS；无业务等待动画 |
| §6 用户与系统低动态、进行中动画取消 | 单元通过；真实浏览器未验证 | use-library-motion.test.tsx；新浏览器双偏好 reorder、panel、progress 断言待运行 |
| §7 内容区 ≥1040 停靠让位，否则覆盖进入焦点 | 静态/焦点单元通过；几何未验证 | ResizeObserver+容器查询；新浏览器列表 right ≤ panel x 断言未执行 |
| §7 ≤1180 侧栏收起/专题入口/隐藏产物 | 静态核对；浏览器未验证 | CSS+共享 header Topic 状态；1024 矩阵待执行 |
| §7 ≤760 两行页头/行、底部模态、背景 inert、≥40px | 模态单元通过；几何未验证 | library-accessibility.test.tsx 焦点陷阱与 native dialog；390 矩阵含宽高命中断言待运行 |
| §7 coarse pointer 手柄常显、菜单替代 | 静态核对；触屏未验证 | CSS pointer:coarse；HTML5 DnD 不宣称支持触屏 |
| §8 list/listitem、标题 aria、complementary/dialog | 单元/静态通过；辅助技术未验证 | SourceRow、SourceTitle、SourceInspector、library-accessibility.test.tsx |
| §8 状态文字/对比度沿用 token | 静态核对；实测未验证 | 无新增颜色；状态文字独立于色点。没有宣称完成对比度仪器测量 |
| §8 中文搜索 composing 不触发额外行为 | 单元通过；真实 IME 未验证 | library-accessibility.test.tsx compositionend；Esc 跳过 isComposing/keyCode229 |

## 测试迁移和最终回归修复

- “详细”定位迁移到来源标题与共享详情区；原准备提示、博客状态、原件/正文、候选计划和确认语义仍断言。关闭后的面板/菜单/任务框保留退出帧，改查不可访问/hidden/inert，而不是要求 DOM 删除。
- Topic 选择器与影子行增加同名内容后，只限定查询区域，不删除状态/动作断言。专题上传默认值按新要求检查，再显式选“不关联专题”继续原 parse-only/请求范围检查。
- 异步删除确认与初始渲染通过 React act 同步，不扩大查询 timeout。终态清理 fixture 的 listInbox 与 getReadingWindow 返回同一清理后快照，不以禁用产品轮询掩盖旧状态回流。
- 最终发现共享页头不再处于 LibraryPage 冒泡路径：新增作用域明确的 document Escape 监听，菜单优先于详情，保留焦点归还，忽略 IME 与已打开 native dialog。三项新增测试覆盖搜索框、选择器与例外；未修改 Host 调用或数据逻辑。

## 已知差异与未验证项

- “有 Plan、无准备记录”的来源仍可显示“可阅读”而主动作仍为“准备阅读”。这是原判断的保留，不自行推断准备完成；第 0–1 步已有审计。真实数据验证未完成。
- 两个隔离 Python fixture 仍依赖 checkout/HEAD 不存在的 focus_read.py；未更改 Python/Core/Host 以规避。其余浏览器入口及新 HTTP mock suite 均因 Chromium 本地 socket 权限失败，页面没有打开。没有重复被拒绝的提权或访问受限路径。
- 截图要求由用户免除，不等于视觉、动效反向、响应式几何已经验收。新脚本的 six-cell 宽度/主题矩阵及两个低动态场景仍待在允许 Chromium 的隔离环境执行。
- 未验证真实私人数据、Parser/Runtime、真实鼠标原生 HTML5 拖拽与文件拖放、触屏、中文输入法、读屏、forced-colors、Firefox/Safari。模拟 DragEvent/WAAPI 和 Chromium 脚本即使以后通过，也不能替代这些验证。

## 建议 PR 说明

方案 A 的 Source Library 列表/卡片 + 单一详情面板；统一状态模型；Topic 展示层计数/Unfiled 与现有 reorder；Continue Reading、状态筛选、同源入库影子行和五类空状态；响应式/低动态/可访问性。业务合同与持久化不变。默认并行测试资源敏感失败和浏览器阻断必须随结果公开，不能标为全量绿色。已有草稿 PR #22；是否 push/更新该草稿或合并须以后续用户指示为准。本轮未 push、合并或部署。
