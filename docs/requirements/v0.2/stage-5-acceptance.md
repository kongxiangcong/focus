# 阶段 5 票 06 验收记录

日期：2026-09-26。基点：FOCUS `d6ab8b48faef02785022da5bc7c06c2446326f9c`。本轮在隔离 `.scratch/focus-v02-stage5/live-20260926/knowledge-base` 执行，不导入旧知识库。

结论：票 06 的既定功能验收出口通过，Stage 2D 前置已解除，票 06 resolved。此结论限定于下述样例、版本和分层证据；全仓 Python 回归仍有 38 项既存失败，不能将本轮称为全仓测试全绿。未发布到外网、未提交或推送 Git。

## 环境与前置

- 阶段 2D 已取得真实 DeepSeek V4.1 Flash 候选、公共校验、Core 提交、HTML 打开及成功/取消归档证据，见 [2D 验收记录](stage-2d-acceptance.md)。插件共享服务依赖修正为 peers，版本 `0.2.0-stage2d.24`；DSH 固定基准未修改。
- 独立版通过正式 `python -m host` 启动，不加载 DSH。项目 `.venv` 中 `openai-codex==0.154.0`；实际 `model/list` 返回默认 `gpt-6-astra`，本轮显式选用该模型。
- PDF 使用真实 hosted MinerU `vlm`，带图/无图 HTML 使用真实本地 `local-html-v1`；凭据仅在本机被忽略的 `.env` 与进程环境中读取。
- 输入：真实《Attention Is All You Need》PDF、用户已保存的“AI Agent 真懂芯片架构吗？Microsoft Research 的实验结论有点微妙”HTML（1 张正文图片）、[Python 官方 Functional Programming HOWTO](https://docs.python.org/3/howto/functional.html) 完整无图 HTML。另加入明确的缺失图片 fixture 验证单项失败，不能将它计为真实来源成功。
- 无图备选 W3C `Cool URIs don't change` 在预检因正文边界无法唯一识别而被拒绝，未修改页面结构以绕过校验，未将该文计为成功。

## 本轮发现与修复

单独重试已停止批次中的一项时，`workIds` 缩小，未执行的其他已确认材料被错误投影为 failed。HTTP 回归先复现 `['completed', 'failed']`，随后修正为按单项持久状态与错误事实显示 queued；继续批次后两项均完成。修复不改变调度范围或重复执行材料。

浏览器工具选择文件后未触发 React 的 change 处理，本轮对工具已经选择的原生 FileList 补发 change 事件，再由页面按钮确认和上传。未注入文件内容、绕过 HTTP/Host 或伪造业务状态。

真实中文文章的全 Plan 准备另复现 `Only reference lists may be excluded`：Core 未识别“参考来源”标题，Runtime 提示又要求排除标题前空行，与 Core 的按标题归属校验冲突。新增真实标题形态回归先失败，随后扩充精确参考标题集合，并让 Runtime 从参考标题开始排除、将前置空行保留于上一块；无参考文献时明确返回空排除集合。未放宽正文、图片或附录覆盖检查。Host 重启后，浏览器“恢复准备”复用已保存全文上下文，真实模型重新规划并检查成功。

## 自动化证据

- 阶段 5 原有专项：32 tests / 104.422 秒通过，覆盖真实 HTTP/Application/Core、空启动、故障暂停、取消、恢复、管理与删除；远端 Parser/Runtime 为受控替身。
- 上述修复：新增 HTTP 回归 1 项先失败、后通过；批次及恢复联合 14 tests / 48.503 秒通过。
- 阅读修复：新增中文参考标题回归先失败；Stage 4 阅读模块 28 tests / 28.468 秒通过，覆盖参考排除与后续附录保留、准备、导航和讨论契约。
- 前端：Reader UI 31 + Standalone 29 = 60 tests 通过。类型检查与生产构建已于本日通过；存在原有 chunk-size 警告。
- 全仓 Python：322 tests / 264.982 秒，8 failures / 30 errors；全仓未通过。38 个失败名称全部出现在已有隔离基线 `3c8debd` 的日志，未据此宣称它们已解决。该全仓运行在新增排队投影回归前开始；之后的修复由上述 14 项回归覆盖。
- 原始日志与失败名称对照保存在 `.scratch/focus-v02-stage5/live-20260926/`。最初按模块名执行 Stage 5 测试时因 tests 目录导入路径错误出现 5 个加载错误；改用仓库既定 discovery 入口后上述 32 项通过，加载错误不计为产品失败。

## 真实流程

- 空知识库页面显示 0 个来源；浏览器选择 4 个文件、单 Topic、一次开始确认后串行处理。
- PDF 经真实 MinerU 发布，远端 batch ID `270c0ec9-3f95-4933-b16c-e78baa56c1b2`。浏览器在博客运行时停止整批，页面为 paused，当前博客 cancelled；重启后保持暂停，没有自动外发。单项显式重试只恢复博客，所有 Parser Bundle 文件 SHA-256 不变。
- PDF 博客真实生成并 Core 提交，内嵌页面打开，3 张引用图片实际加载，8 个 KaTeX 节点。Value Analysis 不适用，原因可见；实现相关结论保留未执行核查警告。
- PDF 来源问答真实完成并引用第 3.5 节；显式“记下来”后笔记 0→1，阅读位置仍为 0/0，没有隐式准备或推进。
- 已恢复整批。缺失图片 HTML 失败后，下一份真实带图 HTML 仍正常入库并开始博客，证明本地解析失败未终止后续调度。

- 带图文章与无图文档均完成本地解析、博客、HTML、真实来源问答和显式备注，三份 Source 均经 Bundle 校验，各有 1 条 Source Note。问答/备注阶段均保持未规划的 0/0 状态；没有隐式推进。带图文章 1 张正文图片在博客中实际解码；无图文档 0 张图片合法发布。
- 带图文章 Value Analysis 与 Reading Blog 均完成，HTML 更新时间 `2026-09-26T16:26:09+08:00`；无图文档 HTML 完成时间 `2026-09-26T16:29:42+08:00`，Value Analysis 正确不适用。成功不是仅凭模型完成事件判定：已检查 Core 正式产物、元数据、Bundle、哈希及浏览器显示。
- 带图文章显式“进入精读”，先准备全文上下文，再形成 `plan-001` 的 5 个 chunk，所有正文为 `source_ready`；这是中文原文阅读，不冒充外文翻译验收。整 Plan check `passed=true`、coverage 覆盖 5 块，保留 2 块 source_issues。ready 前不选择 Plan/移动 Cursor；浏览器“打开阅读”选中 chunk-001，“继续”推进 chunk-002，reading_revision=2，笔记 1 条、阅读记录 1 条。PDF 和英文无图文档未做全文翻译准备，本票的真实完整 Plan 场景使用带图中文文章。
- 浏览器创建临时 Topic，将正在阅读的 Source 附加至第二个 Topic，纠正 Source Title，重命名 Topic、删除该 Topic，再在原 Topic 中上移 Source。Source ID 不变；删除 Topic 不删除来源。管理前后 Cursor、Notes、Bundle 和所有正式 Blog 文件哈希均相同。既有 shortName 仍用于卡片短标题，原题元数据与阅读器材料标题已显示纠正值。
- 浏览器查看无图 Source 的删除影响摘要并永久删除（仅本轮隔离测试资产）。批次分项显示“来源已删除 / 原处理授权已失效”，不再给出原件/正文入口；文件目录与 Notes/Blog 一同删除，清理状态 pending_cleanup=false。历史聊天 6 条保留且 sourceDeleted=true、reference=null，浏览器实际显示“来源已删除”。原件、正文、博客 HTTP 均拒绝访问（现有 API 返回 400 invalid-request；分别为 Source 不存在或 Blog 未发布）。其他来源继续保持 chunk-002 及笔记。
- 最后再次重启独立 Host：新增资产、Plan、Cursor、Notes、管理结果和删除结果持久化。两次审计仅新增了一条重启前显式“打开阅读”的请求回执，阅读 revision 与进度不变。自动化 `StartupTests.test_default_start_is_fresh_and_restart_preserves_new_knowledge_base` 在 old_exists=false/true 两种临时环境实际启动正式 Host，验证默认 knowledge-base、保留新资产且不读取旧 workspace；此项是进程/HTTP 证据，不冒充两个真实浏览器运行。
- 混合批次最终为 partial：3 个真实成功项和 1 个预期缺图失败项。完成后的无图 Source 再用于删除验收；不将 partial 伪装成四项全成功。公共外部服务故障暂停与迟到结果拒绝由本轮专项 HTTP 测试覆盖，本轮未人为破坏真实供应商凭据制造公共故障。

## 质量边界与证据索引

- 带图文章实现检索实际失败，按既定契约降级为仅来源阅读；PDF/无图文档实现检索存在未运行、未核查范围。页面保留警告，不声称外部实现已运行验证。
- 整 Plan 检查保留原文论断强度、百分比聚合口径和未注明单位的疑点，未将其当译文错误擅改。结构校验、来源锚点及浏览器显示通过不等于语义深度或所有原文事实已自动证实；按规格不增加人工质量审批。
- 原始日志、输入 SHA-256、重试前后 Bundle 哈希、三份完成产物与笔记审计位于 `.scratch/focus-v02-stage5/live-20260926/`：`inputs.json`、`stopped-state.json`、`before-management.json`、`after-continue.json`、`after-management.json`、`after-delete.json`、`after-final-restart.json`、`management-checks.json`、`final-checks.json`、`full-suite-comparison.json`。
- 浏览器截图：`pdf-blog.png`、`pdf-note.png`、`image-article-blog.png`、`image-article-note.png`、`noimage-blog.png`、`noimage-note.png`、`reading-continued.png`、`delete-impact.png`、`management-reading-preserved.png`。完整模型聊天仍归 Host，不复制到 Core 验收资产。
- 全仓 Python 未通过；38 项名称均与既存基线对应，尚未逐项修复。报告明确保留此工程回归风险，不以本票专项通过消除它，也不把失败计数当作新增变更已造成回归。
