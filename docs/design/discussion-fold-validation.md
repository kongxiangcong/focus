# 段下讨论折叠验证（2026-10-23）

基线：重新 fetch PR26 与 codex/reading-annotations，head `f8f0878d7179a53935c250ecd57789675220e44d`。独立分支 `codex/discussion-fold`，工作树 `/workspace/focus-discussion`。使用 editorial-ui Integrate + preserve；本地工单 `.scratch/discussion-fold/spec.md` 与 `issues/01-discussion-fold.md`。

实现：FocusReader 保留正文/笔记节点，隐藏整组讨论；新增前端版本化偏好，隔离重复正文事件和会话；发送时展开接收组。ReadingScroll 为折叠操作保留按钮几何锚，隐藏输出不标记 streaming；已有停止和 composer 独立。

## 本次执行

- PASS `pnpm reader:typecheck`（reader、standalone、相关工作区类型检查）。
- PASS `pnpm reader:test`：reader-ui 33 文件、203 测试（含新增 4 项折叠测试）；standalone 12 文件、169 测试，均为本次执行结果。
- PASS `pnpm reader:build`，Vite 生产构建；仍有大于 500 kB 的 bundle 提示。
- PASS `tests/discussion_fold_browser.mjs`，Chromium 154.0.8037.57：重复 chunk / 多组独立折叠、正文保留、刷新记忆、会话隔离、持续生成时保持收起、停止、不追随隐藏输出、键盘 Enter/Space/Tab、长回答底部收起真实几何、新问题展开。
- PASS `tests/reading_annotations_browser.mjs`：A1/A2/A3/A4/A10/A17/A5/A6/A7/A8/A9/A13/A14/A12（笔记/高亮回归，含移动端、深色、减少动效）。零页面错误。详细指标在本地 `tmp/test-runs/annotations/browser/metrics.json`。
- PASS 深浅主题、1440/390/320 宽度、全屏和减少动效，检查无页面横向溢出；内部检查 light-1440 与 dark-320 截图，入口与虚线可辨，正文、现有笔记布局保留。截图位于本地 `tmp/test-runs/discussion-fold/`。
- 单元测试覆盖知识库隔离、旧/损坏值忽略、存储写入失败后的内存降级、无讨论不显示入口。

浏览器命令：先 `pnpm reader:dev --host 127.0.0.1 --port 5173`，再设置 `FOCUS_PLAYWRIGHT_MODULE=/opt/codex/cua_node/lib/node_modules/playwright`、`FOCUS_CHROMIUM_EXECUTABLE=/usr/bin/chromium`，运行上述脚本；原注释脚本额外设置 `FOCUS_BROWSER_PORT=5173`。所有数据为独立 Vite fixture，无付费模型或真实知识库操作。

## 修复与边界

初次新增测试因遗漏 jsdom dialog 模拟和 fixture 必填类型字段失败，补齐后重跑通过。离线安装缺元数据，改用可用网络正常安装并通过锁文件供应链检查；依赖/锁文件未修改。

未运行：真实模型、真实知识库、Safari/Firefox、原生移动设备、屏幕阅读器和原生 IME。本任务未改变模型/后端合同，fixture 测试不能宣称验证真实模型服务。用户不要求截图交付，内部视觉检查文件保持为忽略的本地生成物。
