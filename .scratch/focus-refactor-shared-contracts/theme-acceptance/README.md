# 06 · 正式阅读界面五主题验收

2026-11-23。复验使用专题 01 的双栏论文旋转件和实际 PDF.js 渲染。第 8 页顺时针旋转 90°，回答 B 的编号 4 引用 `a scalable high-bandwidth`。问答及译文使用与既有验收相同的确定性运行时，证据签发、讨论保存、原件交付和定位均通过正式 HTTP Host。测试在已入库工作区的临时副本开始，进行三次精读推进以取得 75% 的真实电量，然后在对话中签发引文。 [专题 01 Batch B 真实 PDF 验收](../../evidence-backannotation-unified-ir/batch-b-acceptance.md)

## 结果

Chromium 156.0.8078.4 共通过 25 种组合。视口高度均为 1000 px。设置测试另确认首次渲染前应用深色、正式 Host 无 CSP 错误、本地存储不可用时回到钴蓝白，以及四种浅色配色各自在系统浅色 → 炭灰深色 → 浅色过程中恢复。 [逐组合尺寸、RGB、对比度及 HTTP/SSE 实测结果](./results.json)

| 配色 | 桌面 1440 | 桌面 1024 | 桌面 720 | 触屏 720 / 系统低动态 | 应用低动态 1024 / 展开侧栏 | 代表阅读页 |
| --- | --- | --- | --- | --- | --- | --- |
| 钴蓝白 | 通过 | 通过 | 通过 | 通过 | 通过 | [PDF](./blue-1440-desktop-pdf.png) |
| 松青绿白 | 通过 | 通过 | 通过 | 通过 | 通过 | [PDF](./green-1440-desktop-pdf.png) |
| 绯红白 | 通过 | 通过 | 通过 | 通过 | 通过 | [PDF](./red-1440-desktop-pdf.png) |
| 极简黑白 | 通过 | 通过 | 通过 | 通过 | 通过 | [PDF](./neutral-1440-desktop-pdf.png) |
| 炭灰深色 | 通过 | 通过 | 通过 | 通过 | 通过 | [PDF](./dark-1440-desktop-pdf.png) |

以下为各主题在已测布局中的最低对比度。悬停列使用桌面测量值。

| 配色 | 主按钮 | 悬停 | 键盘焦点 | 激活下划线 | PDF 框 | 译块框 | 错误文字 | 成功文字 | 电量边界 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 钴蓝白 | 6.70 | 8.72 | 6.70 | 6.70 | 4.63 | 17.74 | 4.58 | 4.79 | 7.13 |
| 松青绿白 | 5.47 | 7.58 | 5.47 | 5.47 | 4.63 | 17.74 | 4.58 | 4.79 | 7.13 |
| 绯红白 | 8.02 | 9.57 | 8.02 | 8.02 | 4.63 | 17.74 | 4.58 | 4.79 | 7.13 |
| 极简黑白 | 17.72 | 14.89 | 17.72 | 17.72 | 4.63 | 17.74 | 4.58 | 4.79 | 7.13 |
| 炭灰深色 | 14.36 | 16.30 | 12.00 | 14.36 | 4.63 | 15.43 | 6.15 | 8.75 | 12.78 |

- 1024 px 展开侧栏、应用低动态，退出全屏后保持第 8 页证据。 [松青绿白 PDF](./green-1024-app-reduced-pdf.png)
- 720 px 触屏且系统低动态，保持第 8 页证据及译块开头的编号。 [钴蓝白 PDF](./blue-720-touch-system-reduced-pdf.png) · [炭灰深色译文](./dark-720-touch-system-reduced-translation.png)
- 知识库可辨认电量数字和 75% 填充。 [松青绿白桌面](./green-1440-desktop-library.png) · [炭灰深色触屏](./dark-720-touch-system-reduced-library.png)
- 设置成功与阅读错误在两种基底上均可辨认。 [绯红白设置](./red-1440-desktop-settings.png) · [绯红白错误](./red-1440-desktop-error.png) · [炭灰深色设置](./dark-720-touch-system-reduced-settings.png) · [炭灰深色错误](./dark-720-touch-system-reduced-error.png)

## 验收方法

- 运行 Chromium 实际组件检查。取已渲染组件的前景色与相邻底色，将透明底色逐层合成。PDF 框的背景包含实际 Canvas 渲染像素。按钮、编号和提示条文字要求 4.5:1，焦点环、激活下划线、证据边界与电量轮廓要求 3:1。两套深浅基底的语义色在各自配色中同时检查。
- 每个组合从正式 `/reading` 打开有可见证据的讨论。通过编号跳到 PDF 第 8 页，只在标记和证据卡均可见时读数和截图。退出全屏后再检查定位，依次验证 PDF 与长译块的编号 4 都能回到回答中的编号 4。
- 在进全屏、完成定位、退全屏、切译文及 SSE 断线重连后读取 `GET /reader/window` 的 Reading Cursor 和修订号，以及 `GET /library/sources` 的精读进度。实测重连关闭旧连接，重开同源原生 EventSource 并等待 Host 新快照。每个组合对比同一个 Cursor，已读 3/4 段。
- 触屏组合启用 Chromium 粗指针并实际 tap，键盘焦点另以 Tab 检查。系统低动态与应用低动态分别检查证据卡的入场动画和电量填充的过渡。桌面 1024 px 默认收起侧栏；该宽度的应用低动态组合展开侧栏，覆盖全屏下双栏到窗口下单栏的切换。
- 成功提示由切换设置中的界面密度触发。错误提示由测试在文献加载 HTTP 边界返回可重试的文档错误，复验错误文字、语义图标和重试按钮。

## 实测修正

- 浅色电量的绿填充与自身边框由 2.88:1 提高至 4.09:1。炭灰主题的填充直接与轨道区分。
- 将译块中的证据编号放到译块开头。22 段长译块定位后，标记与正文起始段都能直接看到。
- 冷启动后直接全屏并点回答编号，修正前在钴蓝白 1440 px、绯红白 1024 px 偶发第 8 页框和引文已出现，PDF 画布仍为黑色且文字层缺失。诊断显示 PDF.js 已返回渲染指令，页面可见时画布宽度却被清为 0。画布以原文滚动容器作为可见性观察根，采用回调中最近的状态，完成一次绘制后处理最新尺寸。浏览器矩阵从对话直接点击证据，并等待实际 PDF 文字层和截图。
- 在 1024 px 展开侧栏时，退出全屏会改变 PDF 页宽与段落纵坐标。已落地的证据跟随相同区域重定位。额外用例先手动回第 1 页再退出，保留手动位置。既有延迟加载与手动中断回归仍检查待定位意图。

## 复验命令

```sh
pnpm --filter @focus/standalone build
python tests/pdf_evidence_browser.py /path/to/standard-ir-workspace --port 18878
FOCUS_BROWSER_URL=http://127.0.0.1:18878 FOCUS_THEME_ARTIFACTS=/tmp/focus-theme-acceptance node tests/reading_theme_acceptance_browser.mjs
FOCUS_TEST_URL=http://127.0.0.1:18878 node tests/reading_theme_preferences_browser.mjs
```

浏览器脚本从 `FOCUS_PLAYWRIGHT_MODULE` 指定的位置加载 Playwright，也支持使用环境中已安装的模块。设定 `FOCUS_THEME_CASE=green` 可单独复验一个主题。 [真实 PDF Host 工具](../../../tests/pdf_evidence_browser.py) · [组件测试](../../../tests/reading_theme_acceptance_browser.mjs) · [主题偏好测试](../../../tests/reading_theme_preferences_browser.mjs)
