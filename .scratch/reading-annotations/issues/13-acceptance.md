# 13 验收：浏览器测试、截图矩阵、交付记录

Status: resolved
Type: task
Blocked by: 01, 02, 03, 04, 05, 06, 07, 08, 09, 10, 11, 12
Covers: spec §10 A1–A17

## 目标

用自动化浏览器测试和截图证明产品行为与原型一致（含 spec §2.1 的三处差异），并留下交付记录。

## 现状与约定

- 浏览器测试写法：`tests/reading_attachment_browser.mjs`——在 `ui/apps/standalone/tmp/<随机目录>` 写入 `index.html` + `main.tsx`（内联 host 与 view JSON），通过 `pnpm reader:dev`（端口 5173）的 `/@fs` 路径加载 `FocusReader`，用 Playwright Chromium 跑断言。
- 环境变量：`FOCUS_PLAYWRIGHT_MODULE`（Playwright 入口绝对路径）、`FOCUS_CHROMIUM_EXECUTABLE`、可选 `FOCUS_BROWSER_PORT`、`FOCUS_BROWSER_OUTPUT`（截图目录）。
- 参照原型：`.scratch/reading-annotations/prototype.html` 可直接用同一 Playwright 打开做对比截图；原型中的检查脚本思路见本工单末尾。

## 设计

### 1. 新测试 `tests/reading_annotations_browser.mjs`

- 夹具：读取 `tests/fixtures/reading-annotations-demo.json`（工单 05），内联一个内存 host：实现 `getReadingWindow`、`subscribe`（可选）、`createHighlight`、`changeHighlight`、`highlightRequestResult`、`createSourceNote`（支持 `sentence`）、`changeSourceNote`、`sourceNoteRequestResult`、`sendMessage`（“存为笔记”时往 `sourceNotes` 追加 `dialogueNote` 并设置 `noteFeedback: {status:"saved"}`）。种子用 `seedMarks()` 生成（得到 `sourceHighlights` 与带 `sentence` 的 `sourceNotes`）。可通过 `window.__annoHost.fail = "failed" | "bundle_changed"` 注入失败，`window.__annoHost.failNext = "highlight" | "note"` 让下一次某类写操作失败。
- 视口：1600×1000、1280×800、1024×768、390×844（触屏 `hasTouch:true, isMobile:true`）；浅色与深色（`document.documentElement.dataset.theme = "dark"`）。
- 场景与断言（对应 spec §10）：

| 场景 | 断言 |
|---|---|
| A1 | 用 Range API 选中 c1 第 1 段一句 → 气泡含 `重点` `备注` `引用提问`；选中跨两段 → 只有 `引用提问` |
| A2 | 点重点 → `.reader-anno--hl` 出现，`getComputedStyle().fontWeight === "700"`，`backgroundImage` 含 `linear-gradient`；重载页面（host 内存保留）仍在 |
| A3 | 点备注 → `.reader-anno-pop textarea` 位于标注最后行框下方（top 差 0–20px）；输入“面积开销很小，”→Shift+Enter→“但没算布线。”→Enter；`.reader-anno--note` 与 `.reader-anno-bulb` 出现；点灯泡 → 查看框文本含换行 |
| A4 | 点标注 → 标注气泡；取消重点；编辑备注；删除“重点 + 备注”标注 → host 收到两次 delete（重点、笔记各一）→ toast → 撤销 → 两条都恢复（数量前后一致） |
| A17 | 写一条备注后打开资料栏“笔记”页 → “句子备注”组出现「原句」+ 备注；该条不在任何段的小段笔记中；host 中该记录是 `sourceNotes` 的一项且带 `sentence` |
| A5 | 打开吸附 → 所有灯泡 `visibility === "hidden"`；标注片段 `backgroundImage` 不变；每个 rail 内卡片两两不重叠；`!is-displaced` 卡片与句子首行 top 差 ≤ 8px；小段笔记区 top ≥ 正文 bottom − 1 且 ≥ 最后卡片 bottom；c2 的 placement 笔记出现在 c2 小段笔记且带“来自讨论” |
| A6 | 吸附开写备注：编辑框在句子下方（不在 rail 内）；Enter 后 150ms 截图（中间帧），此时存在 target 为卡片的动画；600ms 后卡片在 rail 内 |
| A7 | 关闭吸附 → 900ms 后飞行层为空、灯泡 `visibility === "visible"`；折叠行“小段笔记 · N”数量正确，展开/收起 `aria-expanded` 切换 |
| A8 | 讨论“存为笔记”（引用 c3）→ c3 小段笔记新增条目、toast 含“第 3 段”；无引用时 toast“已存为整篇笔记” |
| A9 | 记小段笔记 → 调用 `createSourceNote` 且参数带 chunk；注入 `note_bundle_changed` → 出现“存为整篇笔记” |
| A10 | （需一个带译文的 Chunk，夹具里给 c3 加 `translation`）切换译文 → 原文层标注不显示；在译文层新建标注，切回原文不显示 |
| A12 | `browser.newContext({ reducedMotion: "reduce" })` 重跑开关、删除：`document.getAnimations().length === 0`，最终状态正确 |
| A13 | 390×844 吸附开：`data-anno-rail="stacked"`，卡片在正文下方、小段笔记之上；`document.documentElement.scrollWidth <= innerWidth`。390×844 吸附关：灯泡命中区（含 `::after`）≥ 43px（用 `elementFromPoint` 在灯泡中心 ±21px 处命中灯泡） |
| A14 | 深色截图人工检查并在 Comments 记录 |
| 控制台 | 全程无 `pageerror`、无 console error、无 ≥400 响应 |

### 2. 截图

输出到 `FOCUS_BROWSER_OUTPUT`，命名 `anno-<场景>-<宽>x<高>-<light|dark>.png`；把关键截图（吸附开/关 1600 浅色、A6 中间帧、390 堆叠、深色吸附开）复制到 `.scratch/reading-annotations/evidence/product/`，与原型截图（同目录上层的 `attached-1440.png`、`detached-1440.png`、`save-flight-1440.png`）并排对比。

### 3. 真实数据

在开发服务器的真实 Knowledge Base **副本**（复制到 /tmp，启动隔离 Host，不碰原库）中手动走：选一篇有译文和公式的 Source → 原文、译文各标 1 条重点和 1 条备注（含跨公式的句子）→ 引用某段说“记一下” → 刷新 → 吸附开/关 → 清除讨论与笔记。记录每步结果。没有真实库时状态写 `NOT_RUN`，不能用 fixture 代替。

### 4. 交付记录

按 editorial-ui 交付模板写 `.scratch/reading-annotations/delivery.md`：变更清单、用户可见结果、验收矩阵每行的状态（PASS/FAIL/NOT_RUN + 证据路径）、手测记录（物理输入法、深色、真实库）、遗留问题。完成后更新 `docs/design/README.md` 验证记录列表，加入本交付记录链接。

## 实施步骤

1. `Status: claimed`。
2. 写测试，逐场景跑通；失败回到对应工单修复并在该工单 Comments 记录。
3. 全量回归。
4. 写交付记录。

## 验收标准

- `reading_annotations_browser.mjs` 全部场景 PASS；旧浏览器测试 `reading_attachment_browser.mjs`、`reading_discussion_browser.mjs`、`confirmed_ux_browser.mjs` PASS。
- 全量：`pnpm reader:typecheck`、`pnpm reader:test`、`pnpm reader:build`、`PYTHONPATH=tests:.agents:. .venv/bin/python -m unittest discover -s tests` 全部通过（或在交付记录中列出与本功能无关的既有失败及证据）。
- 交付记录完整，NOT_RUN 有原因。

## 测试

```bash
pnpm reader:dev &   # 端口 5173
FOCUS_PLAYWRIGHT_MODULE=/abs/path/to/playwright/index.mjs \
FOCUS_CHROMIUM_EXECUTABLE=/abs/path/to/chrome \
FOCUS_BROWSER_OUTPUT=/tmp/focus-annotations \
node tests/reading_annotations_browser.mjs
```

## 附：原型检查脚本思路（可复用到对比测试）

原型验证时用过的断言：选中文本用 TreeWalker 找到引文、`document.createRange()` 设置后等待 350ms；吸附开后对每段计算卡片矩形两两不相交、小段笔记区 top 与正文 bottom、最后卡片 bottom 比较；灯泡 `getComputedStyle().visibility`；删除后 toast“撤销”恢复数量；保存后 150ms 检查 `document.getAnimations()` 是否有 target 为卡片的动画。

## Comments

2026-10-23：正式脚本 `tests/reading_annotations_browser.mjs` 在真实 Chrome 完成 A1/A2/A3/A4/A5/A6/A7/A8/A9/A10/A12/A13/A14/A17；desktop/mobile/reduced 三 context 均无 pageerror、console error、HTTP ≥400。A11/A15/A16 由既定单元/Host 故障注入覆盖。13 的具体矩阵、原型对照、合成截图和脱敏库副本汇总见 [交付记录](../delivery.md)。

回归适配遵循当前 UI 合同：Mist 无新会话按钮时使用公开 API 并保留 SSE/刷新/前沿断言；资料与任务区隐藏保留 DOM 时检查 aria-hidden/inert。生产构建输出同源 KaTeX 字体，保持 Host CSP 不变。测试选择手势补齐 pointerUp→mouseUp，业务断言和默认 timeout 不变。

## Answer

实现与所需自动化验收完成。`pnpm reader:typecheck`、`pnpm reader:test`（192 UI + 168 standalone）、`pnpm reader:build`、三个旧浏览器回归通过；Python 全量 510 项通过、1 项 opt-in SDK 跳过（功能实现根分支证据，无后端产品变更后未重复）。真实库副本的原/译文跨公式标注、讨论显示位置、刷新、吸附切换和清除通过，仅提交脱敏计数；原库不改动。

物理中文输入法 **NOT_RUN**：当前环境未做人机系统组字手测，DOM composition 单元通过不等同于物理 IME。交付记录明确保留该验证缺口及其他浏览器/物理触屏未验证范围。原型 SHA256 复核未变，工单、原型和关键合成证据均限定入库。
