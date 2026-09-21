# 阶段 1 实施任务

依据：[已确认 spec](spec.md)。用户于 2026-09-21 批准 4 票方案：先统一 Parser 和后端，再接前端；原 9 票方案未发布。

| 任务 | 依赖 | 交付 | 状态 |
| --- | --- | --- | --- |
| [01 统一 article-parser，删除旧 paper-parser](issues/01-unify-article-parser.md) | 无 | 唯一解析入口与规范 Bundle，保留已有 HTML 能力 | ready-for-agent |
| [02 完成共享后端入库主流程](issues/02-shared-ingestion-workflow.md) | 01 | 脱离浏览器的确认、发布、复用与 Topic 关联 | ready-for-agent |
| [03 完成后端续接与真实运行验证](issues/03-resume-and-real-backend.md) | 02 | 沿进展续接、取消与真实 Parser／Runtime 运行 | ready-for-agent |
| [04 接入独立网页的最小入库体验](issues/04-web-ingestion-experience.md) | 03 | 网页操作闭环与一次必要整体回归 | ready-for-agent |

当前可开始：01。`ready-for-agent` 表示票已清楚定义，不免除依赖条件，也不表示已实施。各票独立记录验收，任务表仅作导航。

按用户要求，前三票以后端公开行为作为可演示出口，不要求每票新增 UI。必要重构放入最早相关票，异常处理和验证合并在业务票内；不额外创建框架、防御或单独验收票。详细测试以 spec 的 Application 主边界为准，票中的 T 编号用于覆盖追踪，不要求逐项建立重复测试。

本目录为本地 Markdown tracker；spec、任务索引及这 4 张票已显式纳入版本管理，其他被忽略的试验数据不提交。实施不写旧私人工作区，正式迁移不在这 4 张票范围内。
