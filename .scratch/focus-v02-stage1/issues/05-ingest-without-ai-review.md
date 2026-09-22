# 05: 无图、无 AI 审核的单篇入库

What to build: 用户明确确认单篇 PDF 后，由程序校验 Parser Bundle 并经 Core 发布，无图论文和 Codex 不可用都不阻止合法入库。网页处理说明与实际服务调用一致，用户可打开无 Plan 的来源原件和正文。

Blocked by: None (can start immediately)

Status: resolved

- [x] 默认入库不执行 AI 审核，不要求标题匹配或观察到图片等 Runtime 返回值作为发布条件；Codex 未配置、不可用或已配置时均不产生默认审核调用。
- [x] 原本无图的 PDF 在原件一致、正文非空、元数据合法及引用完整等校验通过后，可以发布唯一 Source 并完成目标 Topic 关联。正文引用的图片缺失、越界或不可访问仍拒绝发布。
- [x] Application、Host 和网页确认说明只声明默认入库实际使用的服务，服务配置绑定与执行一致。单独变更 Codex 配置不使该流程的确认失效；原件、目标、Parser 配置或处理范围改变仍执行既有重新确认规则。
- [x] 来源原件、正文及存在的引用图片可查看，不生成 Plan、翻译或博客，也不改变已有 Source 的阅读资产。Core 仍是唯一发布入口，保留确认、版本、请求与有效写入方校验。
- [x] 独立 Runtime 能力验证与入库验收分开保留；调整仅为旧强制审核服务的入库断言，不删除仍有效的 Runtime 能力和工具约束测试。
- [x] 通过 Application 公开操作配真实 Core 与可控 Parser 验证有图／无图成功、缺失引用失败和零 Runtime 调用；以少量 Host／网页测试证明确认说明、真实入口和来源访问接通。运行相关回归、受影响的 UI 类型／构建检查并记录结果。

Verification: 沿用已确认的 Application 主边界，在隔离数据中验收，断言最终资产、服务外发次数和可访问结果。先完成本票必需的局部重构，不另建兼容流程或框架；不为证明重复添加而重复调用真实解析服务。

Spec coverage: 本轮 Q1、Q4；T03、T05、T05a、T05b、T22、T26，以及必要的 T02／T24 接入回归。

Scope: 本票是从用户确认到来源查看的完整切面，不依赖 06 或 07；不扩展 AI 质量审核产品。

## Comments

2026-09-22：用户批准三票补充方案；原 01–04 的完成记录不代表本票通过。保留现有未提交工作，不重置或覆盖无关修改。

## Answer

默认入库链路收敛为"Parser 生成候选 → Core 校验发布"，AI 审核整体移出该链路：`IngestionApplication` 不再持有或接受 Runtime（`runtime` 形参被拒绝），`INGESTION_SERVICES` 只声明 `mineru`，`host/__main__.py` 不再装配 `CodexIngestionRuntime`，Host `inbox_confirm` 只提交 `['mineru']`，网页确认文案只列 MinerU 并明确"不做 AI 内容审核"。`CodexIngestionRuntime` 保留为独立 Runtime 能力，只在自身边界（`tests/test_ingestion_runtime.py`）验证，与入库验收分离。图片从 Bundle 必需项改为可选：无 `images/` 目录可发布，正文引用的本地图片仍逐一对盘校验（缺失、越界、不可访问即拒绝，且 `images/` 内文件必须被引用、按序命名）。

验证（Application 主边界 + 真实 Core + 可控 Parser）：
- 有图成功：`FigureParser`（真实图片 + 引用）发布成功、Bundle 保图片、无 Plan、零 Runtime 调用。
- 无图成功：`FigurelessParser` 发布并关联 Topic；缺失／越界引用由 `DanglingImageParser` 拒绝，无新正式资产。
- 零 Runtime 调用：测试在确认＋处理全程 patch `subprocess.Popen` 断言无外部 Codex 进程；Codex 已配置／不可用两种 Host 装配下均完成入库（T26）。
- 配置无关性：确认后单独变更 `codex_bin`／模型不使确认失效；Parser 模型漂移、原件／目标变更仍按既有规则要求重新确认。
- Host／网页：真实 HTTP 入口（staging→confirm→process→轮询完成）可访问原件、正文与 `/library/sources/{id}/images/...` 引用图片；WorkspaceApp 测试断言确认说明只列 MinerU、不含 Codex、声明不做 AI 审核。
- 回归：Python 全套 152 项通过（含新增 3 项）；UI 类型检查 3 包通过、vitest 43 项通过、生产构建通过（仅既有 >500 kB 单块非阻断警告）。

不做的事：未扩展 AI 质量审核产品，未新增兼容流程或第二发布入口；Core 的确认、版本、请求幂等与独占写入方校验保持不变。

边界说明：`host/__main__.py` 启动时的 `check_backend` 是助手后端（阅读对话）装配检查，属既有产品约束，与本票入库切面无关；入库链路自身（Application／HostService）不依赖 Codex 可用性，已由测试证明。工作区中重复添加找回原任务（06 票范围）等未提交改动为既有工作，按票内指示原样保留，不在本票验收。
