---
status: accepted
---

# 专题知识库与 Mist 阅读基础

2026-09-17 本次用户需求替代 ADR 0008 的 Companion 布局与仅解析上传行为。
workspace/ 作为项目内唯一文件数据库，网页投影 sources 与 topics。专题既是阅读集合也是标签；多对多关系仅由专题 manifest 保存，来源资产只存一份。

保留既有目录能避免迁移和双写；把 bundle 复制到每个专题会使原文、笔记和进度产生多个权威版本，因此不采用。扩展来源描述信息和同一 state.json 中的开始阅读标记，区分规划与阅读；不新建数据库服务。

上传完成须解析和规划成功；PDF、HTML 使用现有 hosted MinerU 路径，Markdown 使用明确标记的本地文本导入。重读重新规划但不自动阅读。阅读界面保留中央原文与对话流，输入框放底部，历史提问用右边缘短横线导航。

实施与验收见 `.scratch/library-foundation/spec.md`；稳定目录与本地命令见 `docs/library-workflow.md`。
