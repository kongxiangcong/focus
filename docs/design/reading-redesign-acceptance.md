# 阅读页重设计：第 7–9 步验收

日期：2026-10-20。范围：在第 1–6 步工作区基础上完成按需图片、引用与回答交互，执行全量回归。所有浏览器验证使用隔离的确定性 Host/Runtime 夹具、Edge Chromium、`FOCUS_BROWSER_FIGURES=1`；不代表真实模型、真实用户数据或非 Chromium 验收。

## 基线与最终检查

第 1 步记录位于 `D:/tmp/focus-reader-redesign/evidence/step1/`：typecheck/build 通过，reader-ui 67 项、standalone 90 项通过。最终 typecheck/build 通过，reader-ui 86 项、standalone 90 项通过（新增 19 项，包含先前第 4–6 步的测试）。构建的 >500 kB 提示在基线已存在。

浏览器结果及测量见本目录 `evidence/reading-redesign/`。完整截图和录屏保留在 `D:/tmp/focus-reader-redesign/shots/step9/`（Windows 下本任务的 `/tmp` 为 `D:/tmp`）。`matrix.json` 为 4 宽度 × 2 主题 × 2 动态偏好 × 2 全屏状态的逐项清单；PNG 为静态布局，WEBM 包含资料和定位器开合。

## 逐条验收：规范 §4–§7

| 条款 | 状态 | 证据 |
| --- | --- | --- |
| 4.1 时间顺序与段落讨论归属 | 通过 | `MistReader.test.tsx` 中央流唯一回复/部分 timeline；`discussion-grouping.test.ts` |
| 4.1 单一镜头几何、pointer-events:none、无业务 Cursor 写入 | 通过 | `reading_lens_browser.mjs` 精确几何与 Host progress 不变 |
| 4.1 focus/near/far、回看虚线和定位器 | 通过 | `reading-lens.test.ts`；`reading_lens_browser.mjs` |
| 4.1 新事件仅一次入场、恢复历史不入场 | 通过 | `reading_motion_browser.mjs`；`TimelineEvent` 挂载标记 |
| 4.1 段落工具 hover/focus-within | 通过 | CSS 状态检查；matrix 截图；hover 不改变镜头的浏览器断言 |
| 4.2 手动吸附、默认关、本地持久化 | 通过 | `reading_attachment_browser.mjs` 默认/开关/刷新断言 |
| 4.2 ≥1240 且资料关闭才生效；暂停保持偏好 | 通过 | attachment 浏览器 1100/1440 与资料开合 |
| 4.2 原文 720px、40px 间隔、讨论 sticky、长回答撑高 | 通过 | attachment 浏览器宽度、sticky 14px、长回答行高断言 |
| 4.2 按 reference 归属、重复段落取最近出现 | 通过 | `discussion-grouping.test.ts` |
| 4.2 锚点保持、切换不写 Cursor | 通过 | attachment 浏览器误差 ≤2px；Host 调用单元检查 |
| 4.2 无讨论入口与移动端隐藏 | 通过 | attachment 浏览器引用并聚焦、390px 隐藏 |
| 4.3 段尾 92×58 缩略图、图号、单行图注、固定 | 通过 | `Figures.test.tsx`；`reader_figures_browser.mjs`；CSS 尺寸 |
| 4.3 不自动开合、固定后选中、Source/URL 身份不变 | 通过 | `Figures.test.tsx`、`MistReader.test.tsx`、figures 浏览器 |
| 4.3 查看器缩略图放大/回源 | 通过 | `reading_figures_motion_browser.mjs` 约 89ms 时 reverse，播放速率 -1；关闭无残留 |
| 4.4 提问引用条、摘录、点击高亮 2.4s | 通过 | `reading_discussion_browser.mjs` 注册/2.6s 后清除 CSS Highlight |
| 4.4 悬停高亮、无 CSS.highlights 时仅跳转 | 通过 | discussion 浏览器悬停/移出，以及移除 API 后点击 |
| 4.4 选区引用写入输入区并聚焦 | 通过 | discussion 浏览器选取 `Paragraph 1:`，检查引用条与 activeElement |
| 4.4 回答动作、静态流式块、380px 回答缩略图 | 通过 | `MistReader.test.tsx` 富文本/图片唯一性；CSS 静态块；discussion 浏览器 |
| 4.4 存为笔记沿用原请求，未删除笔记 +1 | 通过 | discussion 浏览器 1→2；检查请求字段与 chunk-001 receipt；单元测试保留草稿 |
| 4.4 回看答案来源不调用 review/continue | 通过 | `MistReader.test.tsx`；discussion 浏览器 POST 数与 readingRevision 不变 |
| 4.5 功能区顺序、继续段号、提问草稿点 | 通过 | `ArticleStructure.test.tsx` 控件顺序；matrix 窄屏与全屏 |
| 4.5 独立结构入口移至定位器顶部，保留 ArticleStructure | 通过 | ArticleStructure 单元与 discussion 浏览器 |
| 4.5 定位器进出、Esc/焦点归还 | 通过 | motion 浏览器退出帧；ArticleStructure 单元与 discussion 浏览器 |
| 4.6 收起保留草稿/引用、释放高度 | 通过 | MistReader 单元、scroll/motion 浏览器 |
| 4.6 IME composing 与 keyCode 229 防发送 | 未验证 | 代码包含双条件；真实中文输入法未实测 |
| 4.7 左侧资料、图片/笔记计数、四类内容 | 通过 | figures 与 discussion 浏览器；matrix |
| 4.7 大图、图注、返回来源、三列网格 | 通过 | Figures 单元；figures 浏览器选择、大图、三列坐标 |
| 4.7 Esc 关闭资料并归还资料按钮 | 通过 | MistReader 单元；figures 浏览器；matrix 真实关闭点击 |
| 4.8 返回刚才位置与回到最新 | 通过 | scroll 浏览器返回偏差 0px；discussion 浏览器入口 |
| 5 动效 token 与无持续闪烁 | 通过 | `focus-tokens.css`；静态 streaming block；motion 浏览器 |
| 5 继续滚动可打断、低动态即时落位 | 通过 | `reading-scroll.test.ts`；scroll/lens 浏览器 |
| 5 镜头 travel/inout、快速改变目标 | 通过 | lens 浏览器 3 次停留=3 次提交，跳过短暂停留 |
| 5 吸附淡入、锚点修正、低动态 | 通过 | attachment 浏览器 |
| 5 资料与输入区可逆 transition | 通过 | motion 浏览器 3 次真实中间帧反向；scroll 收起位移 0px |
| 5 图片 300ms 打开、220ms 关闭、途中 reverse | 通过 | figures-motion 浏览器；WAAPI timing 源码 |
| 5 来源不可见淡出、低动态纯 opacity、Esc/左右键 | 通过 | figures-motion keyframes；figures 浏览器左右键/原尺寸/焦点恢复 |
| 6.1 起读线 max(24,10%) | 通过 | reading-scroll 单元与 scroll 浏览器 |
| 6.2 继续落位、镜头锁定 | 通过 | scroll 误差 ≤2px；lens 浏览器 Continue 到 6 |
| 6.3 程序跳转 +40px、返回位置、不推进 Cursor | 通过 | reading-scroll 单元；discussion/scroll 浏览器 |
| 6.4 阅读线 32%、24px 滞回、140ms 停留 | 通过 | reading-lens 单元与 lens 浏览器 |
| 6.5 布局锚点保持 | 通过 | figures-motion 正文 720→720px、右移 64px、垂直误差 0px；attachment ≤2px |
| 6.6 尾部空间与输入区收起预留 | 通过 | reading-scroll 单元；scroll 收起/展开均 0px |
| 6.7 流式跟随、手动滚动停止、回到最新 | 通过 | scroll 浏览器暂停位移 0px、最新回答距底约24px；confirmed UX |
| 7 ≥1240 吸附/让位，空间不足覆盖 | 通过 | attachment/figures-motion 浏览器；matrix |
| 7 600–1240 单栏、<600 隐藏导航/吸附、横向控件 | 通过 | matrix 1024/768/390，无页面横向溢出 |
| 7 窄屏 ≥40px 命中高度 | 通过 | matrix 实测可见功能按钮最小高度 ≥40px；真实触屏另列未验证 |
| 7 全屏规则一致，抽屉关闭不被退出按钮遮挡 | 通过 | matrix 390px 全屏真实点击；修复 stacking context |

## 修改的断言及理由（未降低阈值）

1. `MistReader.test.tsx`：移除“可自动打开后再关闭”的兼容分支，明确断言初始资料关闭，再验证手动打开。符合按需图片的新行为。
2. `Figures.test.tsx`：正文图片总数改为“受保护的表格/公式图片仍为2，独立缩略图为2”，先断言关闭再点击固定。保留公式/表格、URL、Source 隔离、草稿、请求 receipt、不推进 Cursor 检查。
3. `Figures.test.tsx`：旧无图片的文字目录/`details.open` 改为三张网格缩略图；保留目录顺序、选中图及重开后选中项。布局从列表改为大图+网格，不再验证已移除的 details 容器。
4. `Figures.test.tsx`：无图段落与回看不自动开抽屉；通过固定显式打开。对应不再随 pictureContext 改变展示偏好。
5. `MarkdownContent.test.tsx`：译文未内嵌图片时仍能访问图片的入口改为“在资料栏固定”；原文/译文数学表达与图片可达性断言保留。
6. `MistReader.test.tsx`：回答图片由“没有 img，打开资料栏”改为一个可放大缩略图；显式 Markdown 图片仍只有一个缩略图。跨 Source 禁止错误解析的断言不变。
7. `reader_figures_browser.mjs`：自动打开改为初始关闭+固定；正文零 img 改为仅允许段落缩略图；全目录5个 figure 改为5个网格项+选中大图；滚动至图5改为验证选中图5；有/无图继续均保留抽屉；单行目录改为前三项同排、第四项换行。宽度、原尺寸、Source/进度、POST数量、焦点恢复仍检查。
8. 图片关闭的即时断言改为等待动画结束后检查隐藏/焦点；资料栏放大按钮增加区域限定，避免与正文缩略图同名冲突；新增左右键、reverse、不可见来源淡出及低动态 keyframes 检查。
9. `ArticleStructure.test.tsx`：控件顺序去掉独立结构按钮；从定位器进入总览；补 native dialog 测试替身及 Esc 焦点检查。保留结构节点/草稿/前沿语义。
10. `MistReader.test.tsx`：历史提问栏的存在断言改为中央流中问题存在、旧栏不存在；部分 timeline、唯一回答、过期 revision 丢弃断言保留。
11. 收起后的控件名称由“展开对话框”改为“提问”，继续显示目标段号；相关查询/顺序断言同步，保留原草稿与高度目的。
12. `confirmed_ux_browser.mjs`：所有地址使用隔离端口；资料/更多/博客选择器按 fixture-paper 精确限定；重新阅读后等待真实“进入正文”状态，不用固定400ms。原重置、进度和笔记断言保留。
13. `reading_attachment_browser.mjs`：锚点用实际正文文字定位，不假设第9个p；等待最终回答文字及非流式状态再量几何。图片夹具第2段加长，明确满足“原文长于回答”的 sticky 前提；第3段仍验证“回答长于原文”。720px、≤2px、sticky14px、组高度断言不变。
14. `reading_motion_browser.mjs`：等待入场结束事件；抽屉反向在同一个页面 rAF 中读取中间帧并关闭，避免跨进程65ms等待错过缩短后的反向动画。仍要求0<opacity<1、连续反向且正文宽度不变。
15. 笔记新增验收严格比较未删除笔记1→2，记录完整 Host 请求形状；修正夹具 Source Anchor，未放宽产品的引文校验。

## 发现并修复的问题

- Windows sandbox 临时目录 rename EPERM：改用仓库临时目录；Edge 启动受限：授权范围内在隔离环境运行。未改产品代码。
- 删除历史栏 CSS 时连带移除入场 keyframes：恢复 opacity+translateY(8px) 入场，motion 浏览器保持结束事件与中间帧检查。
- 全屏退出按钮覆盖窄屏资料关闭：`filter:brightness` 形成父级 stacking context，不能只比较子级 z-index；资料打开时提升整个阅读容器，真实点击验证。
- 窄屏40px规则被工作台通用按钮样式覆盖：提高阅读组件选择器特异性，并加入 matrix 实测高度断言，重采390px全部8组。
- 原图片夹具沿用 Stage4 的 `alias address` 锚点，当前 Bundle 中不存在：确定性 Runtime 改用当前 Bundle 实际文本；Host校验、保存 API、产品持久化未改。
- 正在采集时重建 dist 会移除旧哈希资源：最终矩阵在冻结构建上重采，不把中断结果计为通过。

## 保护边界与未验证项

规范文件在第7–9步开始时已有未提交修改，实施阶段未改其字节；后续按用户要求提交，并纳入统一发布分支。开始/结束 SHA-256 为 `93eaec519d965cbb3fc979b5a76b5c4f4ae067ab431979c77d366995f9f876a4`。Vite入口哈希为 `5a66328b4d075e8e2d3d84e0f40a5a5e7a90c79f2b4013ddd86c101a622f83fb`，未改。原型目录无本轮 diff，构建产物搜索 `focus-directions|TimelineC|fd-viewer` 无匹配。

未验证：真实中文输入法、真实触屏、forced-colors/高对比度、Firefox/Safari、真实 Runtime 生成内容与真实私人长文、真实系统剪贴板权限失败路径。非 Chromium 的 Custom Highlight 降级已在 Chromium 移除 API 的条件下验证，不等于其他浏览器实测。

统一发布分支为 `codex/cds-ui-motion-theme`，包含阅读页实现、规范、原型、editorial-ui 技能安装、focus-map/focus-read 技能删除以及 external 忽略规则。重复的实现分支不再维护。`evidence/reading-redesign/changed-files.txt` 记录实施提交的变更统计；完整 PR 范围还包含此前准备提交及后续规范、发布说明修改。
