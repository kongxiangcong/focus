# 阅读批注与小段笔记交付

Brief: [实施规格](spec.md)、[验收工单 13](issues/13-acceptance.md)、[ADR 0033](../../docs/adr/0033-reading-annotations-and-chunk-notes.md)。

Changes since brief: 资料栏清除增加可选 `noteClearVersion`，使仅清除笔记也能准确废弃草稿；不通过“空笔记列表”推断清除。其余按规格执行。原型 SHA256 为 `f813a3f77d84cea1d8da00f4a0ebcc1153180e424c55e70b09b0f3004b064b85`，未修改原型。

Files/routes delivered: Core `source_highlights.py` / `source_notes.py` 与 Host 标注接口；reader-contracts、HTTP/fixture adapters；reader-ui 的可标注文本、投影、`annotations/`、`SourceNotesPanel`、`FocusReader` 及 `focus-tokens.css`；`/reading` 与资料栏笔记页。自动化入口为 `tests/reading_annotations_browser.mjs`，并适配原有 attachment / discussion / confirmed UX 浏览器回归。standalone 构建把字体输出为同源资源，保留既有 Host CSP 与鉴权。

## Implemented behavior

选中同一块内的原文或译文 → 显示“重点 / 备注 / 引用提问” → 重点为黄色渐变且字重 700，备注在原句下方编辑、保存后显示红色虚线和灯泡。跨块选择只提供引用提问。重点与句子备注分别持久化，相同区间合成一个标注。

打开笔记吸附 → 句子备注变为跟随原句的卡片，灯泡隐藏；碰撞卡片下推，小段笔记位于正文与最后卡片之后。关闭吸附 → 灯泡恢复，小段笔记折叠成“小段笔记 · N”。窄屏或侧栏不足 200px 时卡片堆叠到正文下方。句子备注不重复进入小段笔记列表。

讨论中绑定段落保存笔记 → 使用 `placement` 展示在对应段，保留证据锚点与显示位置的区别；无引用时保存为整篇笔记。直接“记小段笔记”不调用模型。资料栏按句子、小段、整篇分组，失效原句保留内容与状态提示。

Recovery and retained state: 写入乐观显示，失败保留草稿并以同一请求号重试；修订冲突不冒充成功。组合删除只重试失败的一半，可撤销成功删除。Bundle 失效提供存为整篇笔记。清除/重置废弃待定写与草稿，单纯新会话保留标注。减少动效时直接得到最终状态。

## Validation

2026-10-23，Windows、真实 Google Chrome（Playwright 驱动）。新浏览器脚本使用 canonical 合成夹具与 FixtureReaderHost；讨论和 confirmed UX 使用隔离 Python Host 与受控 Runtime。以下 PASS 不代表外部模型效果。

| Scenario | Status | Evidence basis | Evidence / environment / reason |
|---|---|---|---|
| A1 单块/跨块选区气泡 | PASS | Chrome 合成浏览器 | `reading_annotations_browser.mjs`；单块三个操作、跨块仅引用 |
| A2 重点样式与刷新 | PASS | Chrome 合成浏览器 | [metrics](evidence/product/metrics.json)：字重 700、linear-gradient，刷新后仍在 |
| A3 句下编辑、多行保存、查看 | PASS | Chrome 合成浏览器 | 编辑框距最后片段底部 0–20px；Shift+Enter 换行、Enter 保存、灯泡查看 |
| A4 修改、组合删除、取消重点与撤销 | PASS | Chrome 合成浏览器 | Host 两类记录删除与撤销数量一致；取消重点保留备注 |
| A5 吸附几何、小段笔记与 placement | PASS | Chrome 实际布局 | 1600×1000、1280×800、1024×768：卡片不重叠，未位移卡片距首行 ≤8px，段末区低于正文/卡片 |
| A6 句下编辑后飞入卡片 | PASS | Chrome WAAPI + 截图 | [150ms 中间帧](evidence/product/anno-save-flight-1600x1000-light.png)，实际卡片动画存在，动画结束后卡片就位 |
| A7 关闭吸附与折叠 | PASS | Chrome 合成浏览器 | 900ms 后飞行层为空、灯泡可见、计数与 aria-expanded 正确 |
| A8 讨论保存反馈 | PASS | Chrome 合成浏览器 | 引用 c3 保存显示“第 3 段”；明确无引用保存显示“已存为整篇笔记” |
| A9 直接小段笔记与 Bundle 恢复 | PASS | Chrome 合成浏览器 | createSourceNote 带 chunk；注入 bundle_changed 后提供存为整篇 |
| A10 原文/译文层隔离 | PASS | Chrome 合成浏览器 | 为 c3 补测试译文；两层标注互不显示 |
| A11 Plan 重建重定位与位置失效 | PASS | 单元/组件 | `annotation-projection.test.ts` 引文上下文重定位与 lost；`SourceNotesPanel.test.tsx` 失效提示、禁止错跳及已加载失效内容编辑 |
| A12 减少动效 | PASS | Chrome reducedMotion context | 开关及删除后 `document.getAnimations().length === 0`，最终状态正确 |
| A13 手机堆叠与触点 | PASS | Chrome 390×844 touch context | [移动截图](evidence/product/anno-stacked-390x844-light.png)；正文→卡片→段末笔记，无横向溢出；灯泡中心四向 ±21px 均命中 |
| A14 深色 | PASS | Chrome 截图 + 人工目视 | [深色截图](evidence/product/anno-attached-1600x1000-dark.png)：文字、黄底加粗、红虚线与卡片可辨；未见重叠 |
| A15 清除/重置与新会话 | PASS | Host/Core 单元 + 库副本 HTTP | `test_reading_highlights_host.py::test_fresh_session_retains_annotations_but_clear_and_reset_erase_them_and_receipts`；库副本清除后刷新零标注 |
| A16 写失败、草稿与局部重试 | PASS | 故障注入单元/组件 | `useAnnotationActions.test.tsx` 同请求重试、只重试删除失败一半、请求恢复；`Annotations.test.tsx` 草稿及保存中继续输入 |
| A17 资料栏句子备注与去重 | PASS | Chrome 合成浏览器 | [metrics.materials](evidence/product/metrics.json)：SourceNote.sentence 存在，“句子备注”原句/内容可见，无小段列表重复 |
| 控制台与 HTTP | PASS | 三 Chrome contexts + 两隔离 Host 浏览器 | 全程无 pageerror、console error、HTTP ≥400；不屏蔽错误。direct Host 的缺省 Workbench binding 由显式 fixture route 提供 |

### 回归与构建

- `pnpm reader:typecheck`：contracts / reader-ui / standalone 均通过。
- `pnpm reader:test`：reader-ui 192、standalone 168 项通过。首次高负载运行有一条选区等待失败；完整单 worker 两套均通过。补齐测试 helper 的 pointerUp→mouseUp 实际手势后重跑默认命令通过；业务断言与 timeout 未降低。
- `pnpm reader:build`：通过；小型 KaTeX 字体输出为同源文件，隔离 Host 生产资源浏览器回归无 CSP console 错误。仍有既有 bundle-size 提示。
- Python 全量 discover：510 项（1 项真实 DeepSeek SDK opt-in 测试跳过），其余通过（根分支同功能实现，611.089s；13 只改浏览器 fixture 支持代码，未改后端产品逻辑）。
- `reading_attachment_browser.mjs`：side / split / stacked、390–1600、普通/全屏、阅读锚点、dock、偏好与减少动效通过。
- `reading_discussion_browser.mjs`：原文选区引用、引用跳转/悬停、段落回看、笔记保存与只读跳转、控制台门禁通过。
- `confirmed_ux_browser.mjs`：10 组旧流程通过，覆盖准备/正文/回看/前沿、新会话 SSE 与刷新、完成终态、资料抽屉、重读确认、知识库任务区与顶层模态。Mist 已移除的新会话按钮改由公开 Host API 驱动，仍断言 UI 与持久状态；未恢复旧 UI。

可重复命令和结果摘要见 [validation-summary.json](evidence/product/validation-summary.json)。原始运行日志保存在本地 `tmp/test-runs/annotations/acceptance13-*.log`，不将私人库内容纳入提交。

### 原型对照与手测范围

对照 [原型吸附](evidence/attached-1440.png)、[关闭吸附](evidence/detached-1440.png)、[保存中间帧](evidence/save-flight-1440.png) 与产品 [吸附](evidence/product/anno-attached-1600x1000-light.png)、[关闭吸附](evidence/product/anno-detached-1600x1000-light.png)、[飞入](evidence/product/anno-save-flight-1600x1000-light.png)。产品保留现有应用导航、阅读镜头和 dock；批注的黄底/红虚线/卡片/段末分离与原型一致。按规格差异落实独立重点记录、文案“小段笔记”、字重 700、第三个引用按钮。

实际 Knowledge Base **副本**：PASS。隔离 Host 使用受控 CandidateRuntime，无外部模型调用。原文和译文分别创建跨公式的重点/备注，公式未被标注包裹；讨论“记一下”有 placement 无伪造 anchor；刷新保留 2 条重点与 3 条笔记，吸附开/关/再开均正常；清除后数据库数量归零、generation 前进，刷新无标注/灯泡/卡片。只提交 [脱敏汇总](evidence/product/real-copy-summary.json)，不提交实际正文、私有截图或库路径；原库未改动。

物理中文输入法：**NOT_RUN**，当前自动化环境未进行真实输入法硬件/系统组字手测。DOM composition 单元测试通过，仅证明事件契约。Firefox、Safari、物理触屏设备及外部模型回答质量未在本次验证。

## Remaining work

所需自动化验收已通过；物理中文输入法仍需人在目标机器检查“组字中 Enter 不提交，完成组字后 Enter 保存”。真实触屏与其他浏览器为后续验证范围。独立双轴审查后的修复复核与最终工作树清理由集成任务统一完成。

## Independent review fixes

独立审查范围为 `883c456` → `7e08b5c`。两轴分别保留：Standards 发现 3 项（2 项规则违反、1 项设计判断），Spec 发现 2 项；各轴最高为 P2。以下修复来自隔离的 `codex/annotations-review-fixes` 分支，未调整产品契约或删除失败断言。

| Axis / finding | Resolution | Public regression |
|---|---|---|
| Standards P2：持久化允许重复与部分重叠 | `SourceNotes._check_annotation_overlap` 在既有 `BEGIN IMMEDIATE` 内同时检查两张 active 表；相同区间只允许一条重点与一条备注，其他交集拒绝。创建与撤销恢复共用检查，请求重放优先；拒绝不消耗撤销槽或修订号 | `test_annotation_overlap.py`：独立请求、双实例与独立进程竞争、跨实体、包含/部分重叠、边界相接、恢复冲突及同请求重试；原 undo 测试的第二独立样本改用不重叠区间，保留原恢复断言 |
| Standards P3：几何 token 未使用 | `AnnotationRail` 与 `useRailLayout` 从计算样式读取 narrow-rail / card-gap / card-offset，纯 packing 显式接收数值 | `AnnotationRail.test.tsx`：覆盖自定义 300px 阈值、24px 间距及 12px 偏移 |
| Standards P3（设计判断）：归属判断重复 | `reading-owner.ts` 统一 Source/Bundle 资格、精确 Plan/Chunk 优先、最大行交集、小段序优先和重复段最后一次出现；三个入口共用 | 原 annotation/note projection 测试保留；`SourceNotesPanel.test.tsx` 增加最后一次精确出现回归，已加载失效备注仍可编辑 |
| Spec P2：跨段键盘选区保留旧气泡 | `useAnnotations.readSelection` 对越界、无效偏移及无效段落关闭旧选区气泡，保留编辑器入口的草稿保护 | `Annotations.test.tsx`：先建立可操作选区，再 Shift+Arrow 延伸到另一 Chunk，旧重点/备注操作消失；原非空编辑器保护测试保留 |
| Spec P3：普通内容 repack 禁用 M13 | `useRailLayout` 只在首次布局及布局模式变化时加 `.no-anim`；内容修订和删除保留 CSS transform 过渡 | `AnnotationRail.test.tsx`：备注变高、删除前卡后，后卡移动且无 `.no-anim`；模式切换仍抑制过渡 |

跨 HTTP 边界的拒绝使用 409 与稳定 `highlight_overlap` / `note_sentence_overlap` 错误码；HTTP adapter 保留这些码。新备注拒绝不会冒充保存或把他人的备注绑定成当前编辑对象，用户草稿仍保留并提示重新选择。`test_reading_highlights_host.py` 检查创建/恢复拒绝后持久数据不变；actions 与完整 reader UI 测试覆盖草稿和回调语义。

修复后验证：受影响 Python 六套共 61 项通过（48.626s），含独立进程竞争；完整 reader-ui 199 项通过；standalone 完整单 worker 169 项通过。standalone 首次并行运行有一条既有 WorkspaceApp 元数据编辑测试 5 秒超时，未改变断言/超时，完整单 worker 重跑通过。contracts / reader-ui / standalone 三套 tsc 与生产构建（422 modules）通过；既有 bundle-size 提示保留。

`tests/reading_annotations_browser.mjs` 对隔离修复分支重跑全部 14 个 Chrome 场景通过，desktop / mobile / reduced-motion 三个 context 的 `errors` 为空。本地日志 `tmp/test-runs/annotations/review-fixes-browser.log`，指标 `tmp/test-runs/annotations/review-fixes-browser/metrics.json`；仅使用合成数据。物理中文输入法的 NOT_RUN 状态不变。原始两轴发现及集成复核由集成任务另记，修复本身不宣称新的独立审查已经通过。
