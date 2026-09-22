# 阶段 1 实施任务

依据：[已确认 spec](spec.md)。用户于 2026-09-21 批准 4 票方案：先统一 Parser 和后端，再接前端；原 9 票方案未发布。

| 任务 | 依赖 | 交付 | 状态 |
| --- | --- | --- | --- |
| [01 统一 article-parser，删除旧 paper-parser](issues/01-unify-article-parser.md) | 无 | 唯一解析入口与规范 Bundle，保留已有 HTML 能力 | resolved |
| [02 完成共享后端入库主流程](issues/02-shared-ingestion-workflow.md) | 01 | 脱离浏览器的确认、发布、复用与 Topic 关联 | resolved |
| [03 完成后端续接与真实运行验证](issues/03-resume-and-real-backend.md) | 02 | 沿进展续接、取消与真实 Parser／Runtime 运行 | resolved |
| [04 接入独立网页的最小入库体验](issues/04-web-ingestion-experience.md) | 03 | 网页操作闭环与一次必要整体回归 | resolved |
| [05 无图、无 AI 审核的单篇入库](issues/05-ingest-without-ai-review.md) | 无 | 合法无图来源可发布，默认入库不依赖 Codex | resolved |
| [06 重复添加找回未完成 Inbox 任务](issues/06-reuse-unfinished-inbox.md) | 无 | 重复添加定位原任务，保留目标与进展且不重复解析 | ready-for-agent |
| [07 受理不明时明确提示后重新提交](issues/07-explicit-resubmission.md) | 06 | 明确风险选择后的重提、幂等与迟到结果保护 | ready-for-agent |

01–04 已按依赖顺序完成并通过各自票内验证；阶段 1 综合证据见 `docs/requirements/v0.2/stage-1-acceptance.md`。各票独立记录验收，任务表仅作导航。

2026-09-22：用户已确认 grill Q1–Q4，[spec](spec.md) 已按 to-spec 整理，并批准 05–07 三票方案，现已发布至本地 Markdown tracker。05 已完成并通过票内验证，06、07 为 `ready-for-agent`；07 必须等待 06 完成，与 05 无硬依赖。三票各自包含必要的后端、网页接入和验证；不另拆重构或验收票。原四票的完成记录不代表这些补充要求已实现。

原 01–04 按用户要求先后端再前端；本轮 05–07 在已有网页上分别完成可验证的业务切面。必要重构放入最早相关票，异常处理和验证合并在业务票内；不额外创建框架、防御或单独验收票。详细测试以 spec 的 Application 主边界为准，票中的 T 编号用于覆盖追踪，不要求逐项建立重复测试。

本目录为本地 Markdown tracker；spec、任务索引和原 4 张票已纳入版本管理。新增 05–07 已写入本地文件，仍受现有 scratch 忽略规则影响，本轮未暂存、提交或推送；后续版本交付仅显式纳入所需票据，其他试验数据继续保持本地。实施不写旧私人工作区，正式迁移不在这些票的范围内。
