# 阶段 2 入库后生成博客：验收记录

日期：2026-09-24。此记录区分确定性、Host、浏览器、真实 Runtime 与内容证据，并在最后分别列出通过、失败与未测。

**结论先行：阶段 2 不构成完整验收。** spec「真实证据与完成门槛」第 4 条要求真实 Runtime 层证据（授权参考论文 DeepStack，`2604.04750v2.pdf` 经真实 Runtime 完整生成博客与价值分析），本机当前没有任何可用外部模型后端，该层未执行；spec 明确规定「缺少真实 Runtime 层证据时，不得宣布阶段 2 完整验收通过」。用户 2026-09-24 决定：真实 Runtime 层直接标为未测，不生成 DeepStack 博客产物，不以任何代写产物冒充 Runtime 调用。

## 确定性层（主边界）

主边界为共享 Application 的博客生成接口：真实 Core ＋ 真实隔离持久目录 ＋ 可控 Runtime／网络适配器，断言落在最终资产与业务状态，不 mock Core 证明提交成功。

- 票 02，`tests/test_blog_application.py`（12 项）：手动触发生成并提交 `blog.md`；未授权报 `blog_not_authorized`；生成中状态与 `state.json` 不变；Runtime 自述完成但候选无效时不发布（`blog_candidate_invalid`）；同 request_id 重放、重复点击、模拟重启都返回已有结果；失败与取消后 `parser-bundle/` 逐字节不变；第二写入方在外发前被拒（`writer_conflict`）；生成后不产生 Plan／全文翻译／Notes／Cursor。
- 票 03，`tests/test_blog_dual_artifacts.py`（17 项）：架构类论文产出 `blog.md`＋`value-analysis.md`＋evidence；非架构类不生成价值分析且在 metadata 记录不适用与理由；有网时记录官方仓库核查与核查层级，无网时零外部调用降级为「仅论文阅读」且不判失败；一篇成功一篇失败只重跑失败篇；证据笔记与用户 Reading Notes 分开保存。
- 票 03 校验器单元边界（直接注入非法候选）：图片无法解码或不来自 Bundle 判失败并点名文件；编号引用与章节锚点不可解析判失败并定位；深度／证据缺口只写警告，输出中不存在「质量通过」字样。
- 票 04，`tests/test_blog_html.py`（12 项）：自包含双页产出、不适用三态第二页、页脚警告区、渲染失败保 md 与旧 HTML、「重新生成 HTML」只重渲染、文章重生成跟随重渲染；校验器第④项 6 项单元边界（外链样式表／外链图片／单页／默认第二页／公式无渲染器／缺理由）。

## Host 层

票 05，`tests/test_blog_host.py`（9 项，全通过）：

- 手动触发在同一 Host 上生成并发布 `blog.md`＋`value-analysis.md`＋`index.html`，三子状态均为 completed，Runtime 调用顺序为 classify → reading_blog → value_analysis。
- 运行中第二个生成请求被拒；生成期间 `library_sources()` 与 `snapshot()` 仍可用（阅读不被阻塞）。
- 按粒度重试：`html` 重试只重渲染，`blog.md` 字节不变、被破坏的旧 HTML 被替换；未知 artifact 抛错；Runtime 抛异常时不发布、记 `error_id=blog_runtime_failed`、无 `index.html`、`parser-bundle/content.md` 完好。
- 非架构类论文：`value_analysis` 为 `not_applicable`，HTML 含 `not-applicable` 与判定理由。
- 入库勾选：确认后 Bundle 发布即自动接续生成，且 `blog:<item_id>` 授权**只消费一次**（不是长期授权）；未勾选时 Runtime 零调用、无 blog 目录。
- 查看器：`blog_open` 返回真实路径、`/library/sources/{id}/blog/html`、`text/html`。

（本层期间修正一处契约不一致：Host 的 `blog_errors` 原用 `errorId`，与 Core 的 `error_id` 及 HTTP 适配层的 snake→camel 约定不符，已统一为 `error_id`，由 TS 适配层归一为 `errorId`。）

## 浏览器层

- 方法包的渲染脚本产出 `index.html`：653,516 字符、2 个 `role="tabpanel"`、5 处 `data-tex`、1 张 base64 内嵌图、KaTeX 运行时已内联；`check_html` 的 errors 与 warnings 均为空。
- 经真实 Host 路由 `/library/sources/Fixture-paper/blog/html` 提供：HTTP 200、`Content-Type: text/html; charset=utf-8`、`Content-Security-Policy: default-src 'none'; img-src data:; style-src 'unsafe-inline'; font-src data:; script-src 'unsafe-inline'; frame-ancestors 'self'`。HTTP 正文与磁盘文件 sha256 一致（`efd6cdc0…`）。
- 本机真实 Chrome（`C:\Program Files\Google\Chrome\Application\chrome.exe`，无头）实际加载该 URL：dump-dom 得到 660,086 字符 DOM，含 2 个 tabpanel／2 个 tab、**5 个已渲染 `.katex` 节点**、10 个 katex-mathml/html 节点、1 个 `data:image/` 图片、**0 处外部资源引用**；截图 118,033 字节。
- 同一文档用 jsdom 执行真实点击：点击「论文价值分析」后 `panel-1[data-active=true]`、`panel-0[data-active=false]`，`aria-selected` 随之翻转；点回「带读博客」复原；两页分别渲染 4／1 个公式，脚本错误 0。
- 证据文件：`.scratch/focus-v02-stage2/t20-browser-report.json`、`t20-dom.html`、`t20-viewer.png`、`t20-tab-switch.json`。

**注意：本层验证的是渲染结果与查看器能否真正打开互联网页，所用 `index.html` 由方法包对夹具正文产出，不等于真实 Runtime 的写作产物。**

## 真实 Runtime 层（未测）

本机逐个探测，三个候选后端均不可用：

| 后端 | 结果 |
| --- | --- |
| `codex exec`（host/blog_runtime.py 的后端） | 180s 超时未返回，`subprocess.TimeoutExpired` |
| `claude` CLI | 被路由到 Kimi Code，API 403「Your current subscription does not have access to Kimi Code right now」 |
| 直连 `ANTHROPIC_BASE_URL`（`https://api.kimi.com/coding/`） | 同样 403，同一订阅限制 |
| `gemini` CLI | 缺 `GEMINI_API_KEY` |

证据文件：`.scratch/focus-v02-stage2/cli-backend-probe.json`、`gemini-probe.json`。

因此：DeepStack 论文未经真实 Runtime 生成，确定性证据链之外的「方法深度、图表证据、引用可追溯」在真实论文上没有样本可供抽查。DeepStack Bundle 仍停在票 01 的 `prepare` 骨架状态（`blog/` 下只有 evidence 模板与 assets 副本，`blog.md`／`value-analysis.md`／`index.html` 均未生成），按用户决定不推进。

## 内容层（未做）

内容层抽查要求针对真实 Runtime 的写作产物核对核心机制、公式与图表解读。没有真实 Runtime 产物，本层不做，也不以夹具正文冒充。

## 基线层

- Python 全套：`python -m unittest discover -s tests`（PYTHONPATH 含 `.agents` 与 `tests`）**225 项通过**，含本阶段新增 4 个模块（`test_blog_application` 12、`test_blog_dual_artifacts` 17、`test_blog_html` 12、`test_blog_host` 9）。证据：`python-baseline-discover.txt`。
- UI：`ui/apps/standalone` vitest **24 项通过**（3 个测试文件），含票 05 新增 5 项。证据：`ui-baseline.txt`。

跑法提示（本机环境相关，非产品问题）：必须用 `discover -s tests` 且把 `tests` 本身放进 PYTHONPATH，否则少数模块里的 `import test_focus_read` 无法解析；另外把全部 Python 测试塞进单进程会触发本机沙箱的批量删除守卫（`shutil.rmtree` 超过 50 个条目需确认），那 95 个 error 是守卫造成的假失败，不是产品缺陷——先前按.`tests.test_x` 逐模块的跑法同样会命中导入差异。

## 失败清单

**通过**：上述 Python 225 项、UI 24 项；票 01–04 全部验收框；票 05 前 5 个验收框。当前无失败用例。

**失败**：无。（本轮修掉的 3 项属于新测试自身的问题：等待逻辑过早返回、错误键名与 Core 约定不符、入库夹具缺图导致 `parser_bundle_invalid`。）

**未测**：

1. 真实 Runtime 层——DeepStack 论文经真实 Runtime 生成完整博客与价值分析（票 05 最后一个验收框，本机无可用后端）。
2. 内容层抽查——依赖上一项产物。
3. 浏览器完整流程——勾选入库 → 自动生成 → 打开查看 → 制造失败 → 按粒度重生成。`agent-browser` 未安装，本机无 Playwright／Puppeteer；该链路每一步的可断言部分已由 UI vitest 与 `tests/test_blog_host.py` 覆盖，但缺真实浏览器点击证据。
4. file:// 双击打开 index.html（spec 中标注为附带收益自查项，未执行）。

## 剩余边界

- `host/blog_runtime.py` 的 `CodexBlogRuntime` **从未在真实 Codex 上跑通过**：它的接口实现、超时与取消路径只被刻意构造的替身 Runtime 验证过（体现在 blog failed 语义测试里），真实调用行为待后端可用后实测。
- 票 05 状态保持 `blocked`，只有补齐上述第 1、3 项后才应置为 resolved；届时本文件需重新刷新。
- 本阶段未 commit、未 push，等待用户决定。
