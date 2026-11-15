# 统一阅读与对话 · 评审入口

日期：2026-11-15
状态：正式阅读界面与证据联动已接入并通过本地验收。

- [完整需求规格](spec.md)：入口、联合开场、全文与讨论、证据契约、联动状态机、UI/动效、兼容与 A01–A17 验收矩阵。
- [实施计划](implementation.md)：模块边界、数据结构、迁移/回滚、依赖顺序与真实垂直切片。
- [原型验收记录](acceptance.md)：本轮实际验证和未覆盖项。
- [正式界面验收记录](production-acceptance.md)：浏览器、自动化与真实 Codex 验证。
- [交互原型](http://127.0.0.1:5191/prototypes/conversation-reading/)：当前本机预览，合成样文与预设回答，无真实模型请求。
- [原型使用说明](../../ui/apps/standalone/src/prototypes/conversation-reading/README.md)。

## 独立工单

1. [契约、术语与迁移](issues/01-contracts-and-migration.md)
2. [全文原文与显示映射](issues/02-source-document-and-mapping.md)
3. [联合开场与自动准备](issues/03-unified-opening.md)
4. [回答证据生成、校验与事件](issues/04-validated-answer-evidence.md)
5. [统一入口与双栏布局](issues/05-unified-reading-layout.md)
6. [证据联动、浮卡与动效](issues/06-evidence-interaction-and-motion.md)
7. [持续对话、选文和外部来源](issues/07-conversation-and-context.md)
8. [现场恢复、完成与兼容](issues/08-restoration-and-compatibility.md)
9. [整体验收与发布](issues/09-acceptance-and-release.md)

各工单底部记录最终实现及验收范围。正式入口与原型路径独立。

`.scratch/` 按仓库规则被 Git 忽略，本目录文件已保存于本机；后续若需要提交，应显式纳入版本管理。
