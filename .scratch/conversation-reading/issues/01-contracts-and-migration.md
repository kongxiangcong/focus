# 01 契约、术语与迁移边界

Status: ready-for-agent
Type: task
Blocked by: 无（用户已授权）

## 目标与依据

spec §5、§8、§11；implementation §2–3。用户已于 2026-11-15 明确授权正式开发；按依赖顺序执行。

## 工作范围

- 定义 SourceDocument、ArticleOverview v2、AnswerEvidence、Reading View Bookmark、Source completion 的字段、身份与错误枚举。
- 补充旧 Host/旧消息/旧开场/旧 Cursor 兼容矩阵；明确无 Plan 的打开、清除/重置/新会话和回滚语义。
- 读取 domain-modeling 技能后更新 CONTEXT 和新 ADR，按范围更新设计索引；不得将全部旧 ADR 作废。

## 预计触及

Reader contracts、CONTEXT、docs/adr、设计索引。实际实施前检查现有状态和范围内 AGENTS。

## 完成条件

- 契约 JSON 样例包含纯文本、对象、外部、失效、历史版本五类。
- 旧记录可只读展示；新 UI 不能因 Cursor 缺失阻止阅读。
- Source-level completion 不伪造逐段阅读条目。

## 验证

文档审阅和契约 fixture；不请求真实模型。

## 非目标

不迁移无关来源，不清理用户资产，不以模拟 UI 验证替代真实证据校验。不扩展当前规格之外的学习功能。

## Comments

2026-11-15：已拆分，尚未开始正式开发。


2026-11-15：用户已授权按精简原型开始开发。
当前已新增公开领域类型、ADR 0034 和领域/设计入口说明；契约 fixture 与完整兼容矩阵仍待补齐，本工单尚未完成。

2026-11-15 已经接入正式契约和 ADR 0034。兼容行为见验收记录。正式接口使用原始 Markdown 行号，早期块清单草案已移除。 [正式验收记录](../production-acceptance.md)
