# 阅读文字与图片分栏实现与验收

基线：PR #12 `fix/quiet-ui-layout`，`9b8f233`。已先读 AGENTS.md、CONTEXT.md 与相关 ADR，实施计划见 [FOCUS_Reader_Figures_Plan.md](FOCUS_Reader_Figures_Plan.md)，展示决策见 [ADR 0019](../adr/0019-reader-text-and-figure-side-space.md)。

## 完成行为

- 桌面约 60% 正文、40% 右侧区域，分隔条支持拖动与键盘左右键，Home 恢复 60%。文字至少 340px，右侧至少 280px；栏宽在浏览器本地保存。正文卡片与上下留白收紧。
- 当前段有图默认展示本段图片；无图或主动关闭时文字居中，保留全文图片入口。下一段、回看和来源切换按当前段重置图片范围和选择。
- Markdown、引用式 Markdown、链接包装图片、HTML 图片与补充绑定按规范化 Source 图片身份去重。源图片的位置显示轻量定位按钮；原始图号和说明保留。公式、HTML/Markdown 表格、扫描表格与公式图片留在正文。
- 原文顺序决定图片顺序，当前语言提供完整图注；缺失时回退已有源内容。切换语言不增加图片，也不请求翻译。默认收起的导航支持本段/全文范围、图号、简短标题、缩略图和稳定替代标签。
- 全文导航包含未读段的图片，明确标注全文范围，可返回本段。文字和图片独立滚动；重复选择同图仍会定位，懒加载后继续校正定位，用户手动滚动图片时停止校正。
- 图片可放大并按原尺寸横纵滚动。放大层使用浏览器模态顶层，支持关闭、Escape、焦点返回图片按钮。
- 图片与笔记/记录/历史讨论共用右侧区域；资料切换保留编辑草稿。1050px 以下使用抽屉；390px 下不会强行并排，继续和提问仍可操作。
- 图片操作不发业务 POST，不推进 Cursor、不增加进度记录、不改变草稿的 Source/Plan/Chunk。时间线事件顺序、历史继续、新会话恢复、流式回复及手动暂停自动跟随保留。
- 讨论中的来源图片替换为侧栏入口，目录以外图片继续在回复中显示。

## 修改文件

| 范围 | 文件 |
| --- | --- |
| 阅读状态与分栏 | `ui/packages/reader-ui/src/FocusReader.tsx`、`reader-figures.css`、`ui/apps/standalone/src/standalone.css` |
| 图片提取、定位与放大 | `ui/packages/reader-ui/src/figures.ts`、`FigurePanel.tsx` |
| 正文与回复入口 | `ui/packages/reader-ui/src/MarkdownContent.tsx`、`ReadingChunk.tsx` |
| 只读全文目录 | `host/core_bridge.py`、`host/figure_catalog.py` |
| 依赖声明 | `ui/packages/reader-ui/package.json`、`pnpm-lock.yaml`（仅新增已有语法树依赖的直接声明） |
| 前端回归 | `ui/packages/reader-ui/src/Figures.test.tsx`、`FocusReader.test.tsx`、`MistReader.test.tsx` |
| Host/浏览器验收 | `tests/test_figure_catalog.py`、`reader_figures_fixture.py`、`reader_figures_browser.mjs`、`confirmed_ux_browser.py`、`confirmed_ux_browser.mjs` |
| 文档 | 本报告、实现计划、ADR 0019 |

## 验证结果

- 类型检查与生产构建通过。前端 110 项通过：reader-ui 46 项，standalone 64 项。
- 相关 Python 53 项通过：确认版 UX、图片目录、reader 边界、Stage 4 阅读与全文目录投影。
- 真实 Chromium + 隔离 HTTP Host 图片验收 8 组通过，浏览器 pageerror 为零。
- 原有真实浏览器 10 组流程通过，覆盖时间线/流式手动滚动、历史继续、新会话刷新、笔记编辑删除撤销、记录修改、390px 大字号、完成/重置、任务折叠和博客模态关闭。
- 浏览器中实测正文与图片区几何关系、60/40 比例、独立 scrollTop、展开/关闭/选图/导航/放大/调宽后的正文位置。全部图片展示动作不产生业务 POST，前后 Cursor/进度投影一致；第一段草稿在继续第二段后仍用第一段引用发送。
- 原文/译文图注、HTML 未读图、同图重复选中、Source 切换与刷新、来源外回复图片均通过实际页面检查。

可复现命令（浏览器环境需自备 Playwright、Chromium 与 Pillow）：

```bash
pnpm install --frozen-lockfile
pnpm reader:typecheck
pnpm reader:test
pnpm reader:build
PYTHONPATH=tests:.agents:. python -m unittest test_confirmed_ux test_figure_catalog test_reader_ui_boundaries test_stage4_reading test_web_host.WebHostTests.test_snapshot_exposes_bound_images_across_the_source

FOCUS_BROWSER_FIGURES=1 \
FOCUS_BROWSER_SCRIPT="$PWD/tests/reader_figures_browser.mjs" \
FOCUS_PLAYWRIGHT_MODULE=/absolute/path/to/playwright/index.mjs \
FOCUS_CHROMIUM_EXECUTABLE=/absolute/path/to/chromium \
PYTHONPATH=tests:.agents:. python tests/confirmed_ux_browser.py

FOCUS_BROWSER_SCRIPT="$PWD/tests/confirmed_ux_browser.mjs" \
FOCUS_PLAYWRIGHT_MODULE=/absolute/path/to/playwright/index.mjs \
FOCUS_CHROMIUM_EXECUTABLE=/absolute/path/to/chromium \
PYTHONPATH=tests:.agents:. python tests/confirmed_ux_browser.py
```

## 限制与基线失败

- 用户指定的 `/home/kongxiangcong/dsh-proj/focus` 在当前执行环境不存在。本次在获取的 PR 分支副本中修改，副本起始干净；没有访问、修改或提交用户原机器的本地文件。
- 浏览器验收确实执行 Chromium 渲染、输入、原生 dialog、HTTP Host 和 Core 文件读写；论文内容、图片和模型输出为确定性隔离夹具。没有验收真实模型/MinerU，也没有部署用户机器。
- 只增加展示目录投影，不更改 Parser Bundle、Reading Plan 或译文。Core 对合法 Bundle 的原有绑定要求仍在，HTML 场景在符合原契约的 Bundle 中验证。
- 同一环境扩大运行 `test_focus_read`、`test_web_host`、`test_stage4_reading`，有 7 failure、18 error；在修改前提交的独立 `git archive` 副本复现相同 25 个失败名称，新增失败名称为零。原因包括旧 CLI 阅读行为断言、过时的卡片指令契约和不可定位的旧引用；未修复无关基线项，未声称全量 Python 通过。原基线记录见 [FOCUS_UX_REGRESSION_BASELINE.md](FOCUS_UX_REGRESSION_BASELINE.md)。
- 构建仍提示单个 JS 产物超过 500kB；本轮没有进行无关打包重构。浏览器环境中文截图字库不足，但中文 DOM 文本、按钮和图注断言通过。Firefox、Safari 和触屏真机未验收。
