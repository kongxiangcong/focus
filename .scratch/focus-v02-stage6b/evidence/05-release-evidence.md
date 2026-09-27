# Stage 6B / 05 — 发布门槛核验（未通过）

日期：2026-09-27。审查基点：`da2844fccabbc653cbdd108ba68bcdcae8a7ed92`，当前分支 `main`。

**当前结论：票 05 未完成。** 用户已取消干净环境和首次登录测试；当前阻塞是实际业务候选失败及剩余未测项，不再等待环境或登录。已继续执行两套新知识库、六份真实材料的入库及博客生成，并修复 DeepSeek 候选输出截断问题。最新结果以 [当前环境真实验收](05-live-evidence.md) 为准。

## 用户调整后的当前范围（2026-09-27）

用户已明确取消干净环境和首次登录测试。下文原安装缺口和原审查结论作为历史记录保留；它们不再阻塞票 05，不等待虚拟机、独立发行包或首次登录操作。改在当前 Windows x64 环境复用已有认证继续双 Backend 真实业务及浏览器验收。被取消项目标为范围外，不能标为已通过。

以下第 1–5 节及 Review 为范围调整前的首轮记录；其中“本轮未执行”等表述仅描述首轮，不覆盖上述后续实测。

## 1. 当前基线与阶段 5 前置

- 工作区为 Windows 11 AMD64 开发环境，Python `3.13.14`；已安装 `openai-codex 0.154.0`、`deepseek-harness-sdk 0.1.5rc1`、`deepseek-harness-runtime-bin 0.1.5rc1`。这是包元数据记录，本轮未启动模型确认实际 Runtime 版本，不将其当新 Runtime 成功证据。
- 开始时有 14 个已有修改／未跟踪路径，记录于 [基线清单](05-release/baseline.json)。其中包含阶段 5 的批次排队投影修复、中文“参考来源”识别、Plan 参考范围提示及回归，以及未跟踪的 `docs/requirements/v0.2/stage-5-acceptance.md`。这些业务修复尚未包含于上述 HEAD；本轮工作区回归不能证明仅检出 HEAD 的发行物通过。
- 已读取阶段 5 原始 `inputs.json`、`after-final-restart.json`、`final-checks.json`、回归对照与验收说明，并重新校验实际磁盘文件。四份输入 SHA-256 全部一致；现存真实带图 HTML 和 PDF 的 Bundle 校验通过，33 个文件与最终快照哈希一致，Cursor 一致，无图文档保持已删除。[重新核验结果](05-release/stage5-audit.json)。这证明留存证据与资产相符，不证明 Stage 6B 已重新跑过它们。
- 03、04 的实现提交分别为 `9fc4f58`、`da2844f`。已读取公共 Host、Runtime、浏览器证据及原始紧凑报告，未单凭 `Status: done` 推断本票通过。

## 2. 实测安装缺口

在仓库跟踪文件及启动文档中未找到独立 Windows 发行包、安装器或打包入口。`README.md` 要求先执行 `python -m pip install`、`pnpm install`、`pnpm reader:build`、`python -m host`。`host/backend_setup.py` 的 Runtime 准备调用现有 `sys.executable -m pip`，不是 Python/应用自身的安装入口。

另有可复现的运行期 Node 依赖：`.agents/core/html_article.py` 调用 `node extract_article.cjs`。本轮在独立探针进程先用真实 `functional-programming.html` 成功提取 44,434 字正文；随后仅将该进程 PATH 改为 Windows System32，确认 Node 不可解析，再对相同输入提取，得到 `html_extractor_unavailable`，原因 `FileNotFoundError`，用户错误要求执行 `pnpm install`。未改变系统 PATH、个人设置、原件或知识库。[完整探针结果](05-release/dependency-probe.json)。

这是开发机依赖隔离证据，不是干净虚拟机安装证据。首次探针的记录器误用不存在的 `WorkspaceError.code`；修正为 `error_id` 后重跑，未修改产品来改变失败结果。

可复核脚本：[audit_prerequisites.py](05-release/audit_prerequisites.py)。在仓库根目录执行 `.venv/Scripts/python.exe -B -X utf8 .scratch/focus-v02-stage6b/evidence/05-release/audit_prerequisites.py`，读取本机保留的 `.scratch/focus-v02-stage5/live-20260926/inputs.json`、`inputs/`、`after-final-restart.json`、`knowledge-base/`，输出比较结果；不改写这些资产。缺少原始本地材料时无法复跑，紧凑 JSON 不能代替原始材料。脚本不调用模型或供应商服务。

**原阻塞项（用户已取消对应测试）：** 尚无已提供的独立发行物和干净安装环境；应用启动及 HTML 解析仍依赖开发环境。不能把设置页可准备两种 Runtime 等同于无需 Python／Node 的完整安装。已向用户询问已有发行物／干净虚拟机位置；未收到位置前不声称它们不存在于仓库之外。

## 3. 本轮自动化结果

- Python 全量：366 tests / 365.266 秒，**8 failures / 31 errors，未通过**。与票 04 的最终日志逐个失败身份对比，无新增失败；原 Windows `state.json` PermissionError 对应的 `test_discussion_from_previous_pass_is_not_reused` 本次通过，仅记为未复现，不声称修复。
- 相比票 03 的 38 个失败身份，另有 `test_replan_preserves_previous_assets`，仍因已不存在的 `host.service.check_backend` 测试替换点报错；它已在票 04 报告中记录，本轮未改变该测试或增加兼容层。其余失败未被本票修复。
- 同一次全量中：Backend setup 11、Stage 6B configuration 7、workflows 16、clear/retention 8，共 42 tests 全通过；Stage 4 reading 28、Stage 5 batch/recovery/ingestion/management/deletion 33 全通过。外部服务受控替身的结果仅计确定性／公共 Host 证据。
- 前端 typecheck、64 tests（reader-ui 30 + standalone 34）、生产 build 通过；构建保留超过 500 kB 的 chunk-size 警告。
- [紧凑回归清单](05-release/regression-summary.json) 包含失败身份、逐项对照、模块计数、原始日志 SHA-256。原始 `python-full.txt`、`typecheck.txt`、`ui-tests.txt`、`build.txt` 留在本地 `05-release/`，未提交。没有改写旧失败预期来获得通过。

命令（仓库根目录）：

```powershell
.venv/Scripts/python.exe -B -X utf8 -m unittest discover -s tests -v
pnpm reader:typecheck
pnpm reader:test
pnpm reader:build
```

## 4. 分层覆盖与缺口

| 验收项 | 已有证据及边界 | 本票结论／剩余工作 |
| --- | --- | --- |
| 阶段 5 稳定出口／发布基线 | 本轮核验原件、Bundle、哈希、Cursor；工作区仍含未提交业务修复 | 前置已核对；可复现发行基线尚未建立 |
| 干净安装、双依赖、部分失败重试 | 01 有受控 Host 安装失败测试及开发机连通；本轮证实缺 Node 时 HTML 解析失败 | 干净环境安装范围外；当前环境双依赖与失败重试仍保留 |
| Codex 共享登录及 OAuth | 01 有真实个人 ChatGPT 登录复用、设置页连通；未登录 OAuth 只有受控协议测试 | 首次登录实测范围外；已有登录复用与真实连通仍保留 |
| 两 Backend × PDF／带图 HTML／无图 HTML 全业务 | 02 有复用 DeepStack Bundle 的双 Runtime Blog；Plan／全文译文／问答／Notes／推进主要为 synthetic fixture；03 为合成中文无图批次 | 不能填充真实三类来源的双 Backend 全流程矩阵；本轮未执行 |
| 适用 Value Analysis 与内容警告 | 02 有双 Runtime DeepStack Reading Blog／Value Analysis／HTML，保留 paper_reading 及检索缺口；不适用时应记录理由 | 本轮真实三类来源的适用／不适用分支未测试，结构通过不等于内容认可，不增加人工审批 |
| Topic／Source 管理 | 阶段 5 有创建／重命名／排序／多 Topic 关联／删除及资产保留证据 | 本轮两个 Backend 的管理回归未测试，需在当前环境核验 |
| 连通错误与配置竞争 | 01 有真实成功／Runtime 失败，以及受控认证／供应商错误／迟到结果测试；03 有保存与激活的公共准入测试 | 本轮未登录／网络／额度／协议故障、配置变动、迟到结果的完整连通矩阵未测试 |
| 混合批次失败／取消／整批停止／公共故障／重启／换 Backend | 03 有真实 Runtime 合成批次 DeepSeek→Codex，前三篇 33 文件不变；公共契约覆盖更多故障 | 未完成真实三类来源混合批次发布验收 |
| 浏览器设置、改回、多页面、忙时刷新、讨论、清除 | 03、04 有实际浏览器状态转换和结果；并非单张静态截图 | 历史子票证据，本轮当前环境未复跑 |
| 日志七天清理与资产／个人日志保护 | 04 有可控时钟、崩溃恢复、下一任务、清除保留项的公共测试及受管 Runtime 临时目录证据 | 本轮当前环境未测试；原生 SDK 永久删除仍为 not_verified，不把 close 或目录移除算删除证明 |
| 取消、崩溃、迟到 attempt、越界、Source 隔离、结构／图片／引用 | 共同 Host/Core 测试及 02–04 子票证据；严格 JSON 拒绝、显式重试与内容 warning 分开 | 当前自动化结果见第 3 节；不升格为本轮真实双 Runtime 故障验收 |
| 非历史版本及实际协议失败、无静默换路径 | 01／03 已有默认 Codex 路径失败且未回退；显式选择另一份后成功 | 未完成本票非历史 Runtime 版本实跑；安装版本列表不是该证据 |
| Linux 无新增平台硬拒绝 | 本轮没有产品修改，不新增平台判断 | 未执行 Linux 验收，不宣称支持验证通过 |

历史索引：[01](01-runtime-gate.md)、[02](02-workflows.md)、[03](03-refresh-batch-switch.md)、[04](04-clear-retention.md)。Stage 2D／旧 Codex 路径证据没有记为本票成功。

## 5. 恢复验收的顺序

1. 将阶段 5 所依赖的现有业务修复纳入明确、可复现的发布基线；当前未提交修改保持原样，本票不代为纳入提交。
2. 使用当前 Windows x64 环境和已有认证，记录实际 Runtime 路径／版本，验证依赖、连通及部分失败重试；不执行干净环境与首次登录测试。
3. 在当前环境为 Codex、DeepSeek 分别建立新知识库，用真实 PDF／带图 HTML／无图 HTML 完成全部业务和混合恢复矩阵；使用实际浏览器执行关键动作，保存输入、版本、动作、终态、正式产物和保留哈希。
4. 独立列出失败、未测及内容警告；两 Backend 所有完整出口通过后才关闭票 05。已有全仓失败须逐项处理或明确保留结论，不能写成全绿。

## Review

### Standards

初审指出探针缺可复现过程，已补 `audit_prerequisites.py` 与完整本地输入／快照路径，并执行重跑。最终复审核对四份日志哈希、39 个失败身份、14 个已有文件哈希均一致；0 项剩余发现。

### Spec

初审指出缺口表遗漏 Value Analysis、Topic／Source 管理、连通失败矩阵、日志保留，已分别补入。最终复审确认矩阵、测试计数、探针重跑与未完成状态一致；0 项剩余报告发现。此结论仅针对证据报告，不构成票 05 验收通过。

发布门槛失败是本报告的结果，不因报告已提交而转为发布通过。14 个原有修改／未跟踪文件的 SHA-256 与开始时一致。
