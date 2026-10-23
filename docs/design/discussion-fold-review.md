# PR26 editorial-ui 独立复核（2026-10-23）

审查起点：`09ef3a7f02e8adf91236ad78af845ef7ba415e65`；最新增量相对 `f8f0878`。
先按仓库 editorial-ui Review 路径检查，用户随后授权实际问题的最小修复、提交和安全推送；修复采用 Integrate + preserve。没有合并、部署或 GitHub 评论。

## 判断与发现

核心折叠交互符合阅读控制补充；发现一项新增的低严重度（P3）样式规范问题并修复，未发现本次增量导致的正文/批注功能回归。本次不是对 PR 所有后端变更的完整审计。

- **P3，新引入，已修复**：`mist-reader.css` 原第 373 行的专用 `button:focus-visible` 将焦点环固定为 `2px solid --reader-ink`，覆盖 `reader-shell.css:22,80` 的统一焦点 token 和高对比加粗。违反阅读重设计 §1.3/§2 的交互焦点语义及 editorial-ui Design authority 的单一 token 所有权。复现：键盘聚焦讨论折叠按钮，模拟 `prefers-contrast: more`，计算 outline 为 2px（应沿用共用规则 3px）。影响：新控件丢失已有增强焦点适配、颜色角色不一致；并非焦点完全不可见。最小修复是删除这条覆盖，继承共用规则，不改虚线、文字、布局或业务行为。浏览器新增断言先失败 `2px !== 3px`，修复后通过；另检查与普通 reader 按钮的焦点颜色一致。
- 既有问题：本次没有确认需要扩展修复的既有产品缺陷。构建仍有 >500 kB 分块提示；两份旧浏览器脚本的入口前置条件未满足，不能据此认定产品回归。

## 已符合项与证据范围

- SOURCE + RUNTIME：浅灰 `--reader-line` 细虚线、ghost 标签；内部查看 1440 深色与 390 浅色截图，分隔保持轻量。按钮使用 `aria-expanded/controls`；Enter/Space、焦点保留、隐藏后 Tab 不进入内容通过。
- SOURCE + RUNTIME：重复 chunk 的两个阅读事件独立；正文保留；刷新恢复；session 隔离；组件测试另覆盖 workspace 切换、存储失败内存回退、非法键及无讨论不显示。
- SOURCE：偏好 JSON 身份包含 workspace/source/session/discussion/event，不以 chunk 单独建键；无 event ID 时序号回退是当前补充规范明确接受的兼容边界。没有修改业务存储或数据库。
- RUNTIME：折叠后增量保持隐藏，停止调用生效，无滚动漂移；发送展开尾组；长回答底部收起后按钮仍在视口。
- RUNTIME：Light/Dark × Compact/Comfortable × 1440/390/320（高度 844），无页面横向溢出；减少动效、CSS 全屏入口、焦点 token 和高对比 3px 断言通过。初始桌面场景 1440×1000。
- RUNTIME：批注 fixture 验证重点、备注编辑保存、原译文层、句子备注资料显示、跟随卡片几何、吸附开关、讨论存笔记、小段笔记、390 窄屏、深色和 reduced-motion 最终态。使用合成数据，没有外部模型或真实用户库写入。

## 本次亲自执行

环境：Linux，Chromium `154.0.8037.57`，本地 Vite；Playwright 来自 `/opt/codex/cua_node/lib/node_modules/playwright`。

| 检查 | 结果 |
| --- | --- |
| `pnpm --filter @focus/reader-ui test` | PASS：33 文件 / 203 测试 |
| `pnpm --filter @focus/standalone test --maxWorkers=1` | PASS：12 文件 / 169 测试 |
| `pnpm reader:typecheck` | PASS：三个 TypeScript 项目 |
| `pnpm reader:build` | PASS：修复前及修复后构建；分块大小警告保留 |
| `tests/discussion_fold_browser.mjs` | PASS：先复现失败，再通过扩展 12 组合与焦点断言 |
| `tests/reading_annotations_browser.mjs` | PASS：A1–A10、A12–A14、A17 共 14 项场景 |
| `tests/reading_scroll_browser.mjs` / `tests/reading_motion_browser.mjs` | 未完成：5175 的默认 fixture 没有脚本要求的“进入正文”按钮，均在首个 click 等待 30 秒超时，未进入业务断言 |

浏览器命令使用 `FOCUS_PLAYWRIGHT_MODULE`、`FOCUS_CHROMIUM_EXECUTABLE=/usr/bin/chromium`；折叠测试端口 5173，批注测试显式 `FOCUS_BROWSER_PORT=5173`。批注首次运行使用默认 5174 导致连接拒绝，设置正确端口后重新运行通过；未放宽任何断言。

未覆盖：真实知识库/真实模型流式响应、Python 后端全套、Firefox/Safari、屏幕阅读器、物理 IME/触屏、200% 缩放、forced-colors、浏览器 Fullscreen API（本产品场景验证的是 CSS 全屏）。源/讨论两个隔离维度以源码核对为依据，没有单独浏览器切换断言。旧脚本的完整滚动和动效场景未通过；新折叠脚本及批注脚本只证明各自已执行的断言。
