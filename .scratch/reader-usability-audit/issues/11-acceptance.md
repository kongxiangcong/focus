# 11 验收证据与文档更新

Status: ready-for-agent
Blocked by: 01, 02, 03, 04, 05, 06, 07, 08, 09, 10
Covers: spec §6，问题 P1–P11

## 目标
按以下已确认条款实现（05 仅领域记录；06 仅 Host/合同/适配器；07 仅投影布局；08 仅编辑器与入口）。

执行 spec §6 的命令、四视口×浅深色截图及隔离 Host 真实 Paper Source 回归。

## 现状（对照当前代码核实后的文件与行号）
基线 PR #24 `9f183cd`；相对审计 HEAD 的增量为技能文档清理，产品问题仍存在。FigureViewer 实际与 FigurePanel 同文件。
- `tests/reading_width_browser.mjs:19`：`await page.getByRole('button',{name:'宽幅',exact:true}).click();await wait();const wide=await measure();assert.ok(wide.content.width>standard.content.wi`
- `tests/reading_standard_settings_browser.mjs:34`：`await page.getByRole('button',{name:'宽幅',exact:true}).click();await wait();`
- `tests/reader_figures_browser.mjs:36`：`assert.equal(await stream.locator('img:not(.reader-thumbnail img)').count(), 0);`
- `tests/reader_figures_browser.mjs:91`：`results.push('figure selection, zoom top layer, natural size and Close/Escape focus restore do not move the Cursor');`

## 实施步骤
1. 先将状态改为 claimed；核对依赖。
2. 为本工单行为增加失败测试并记录红灯。05 为纯文档例外。
3. 按目标修改，数值统一由 focus-tokens.css / typography.ts 管理。
4. 运行验收命令、检查截图并追加证据；通过后 resolved，独立 commit，不 push。

## 验收标准
- 上述目标每条行为由对应单元/浏览器断言验证，未运行不得计为 PASS。
- spec §5 阅读锚点、草稿、输入法、Reading Cursor、鉴权与减少动效红线保持。
- 界面在 1600×1000、1280×800、1024×768、390×844 触屏的浅/深色截图中无溢出与不可达控件。
- 图片/笔记工单在真实 Knowledge Base 副本隔离 Host 中验证；图片 HTTP 200 且 naturalWidth > 0。

## 测试
- `pnpm reader:typecheck`
- `pnpm reader:test`
- 界面：`pnpm reader:build` 和受影响的 `tests/*.mjs`。
- Host：`.venv/bin/python -m unittest tests.test_web_host` 及相关测试。

## Comments
- 2026-10-21 SOURCE/PASS：已核对以上代码位置。待记录红/绿结果与截图。
