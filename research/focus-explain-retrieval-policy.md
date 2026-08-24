# `focus-explain` 检索与回答策略

> 状态：Phase 1 设计结论
>
> 调研范围：`research` Skill、当前 `CONTEXT.md`、Phase 1 架构草案
> 结论用途：约束 `focus-explain` 的内部检索纪律与面向用户的回答行为

## 结论

`focus-explain` 应采用“内部严谨研究，外部直接回答”的边界：模型可以检索论文全文和必要的外部资料，在内部优先读取拥有事实的一手来源并据此形成解释；面向用户时直接给出融合后的清晰回答，不强制逐条标注“论文内容/外部补充”，也不维护独立的来源账本。`research` Skill 要求的是研究工作的证据纪律和研究产物的引用，而不是所有对话回答都必须展示引用。来源：`C:\Users\72449\.agents\skills\research\SKILL.md:8-12`；[FOCUS domain language](../CONTEXT.md)

## 内部检索纪律

- 先在整篇 `paper.md` 中按标题、关键词、正文引用和相关结构定位段落、公式、表格、图片与 caption；按需读取相关内容，不在每轮机械加载全文。Phase 1 不为此建设向量数据库或 RAG。[Phase 1 `focus-explain`](../docs/FOCUS_Phase1_Skills_Quickstart_Architecture.md#14-focus-explain)
- 当论文自身不足以解释问题时，可以检索外部资料。外部检索沿用 `research` Skill 的方法：优先官方文档、规范、论文、源码或第一方 API，让事实性主张回到拥有该主张的一手来源。来源：`C:\Users\72449\.agents\skills\research\SKILL.md:8-11`
- 上述来源追踪是模型生成可靠解释的内部工作方法。Phase 1 不新增来源表、来源事件、检索索引或 Explanation Source 持久化字段；当前领域定义已明确，外部材料只在内部咨询，且可见回答不要求逐来源标注。[FOCUS domain language](../CONTEXT.md)

## 面向用户的回答

- 直接回答用户的问题：模型先阅读、比较和理解所取得的材料，再用最能解释清楚的方式组织回复。无需默认展示检索过程、来源分类或证据清单；用户明确要求出处时，再提供相应来源。
- 回答可以随着用户反馈更换表达、例子或继续下一步，但 `focus-explain` 始终不能推进、回退或重置 Reading Cursor。[Phase 1 `focus-explain`](../docs/FOCUS_Phase1_Skills_Quickstart_Architecture.md#14-focus-explain)；[FOCUS domain language](../CONTEXT.md)
- 如果现有论文内容与可取得的外部资料不足以支持一个可靠回答，应明确拒绝回答该问题，而不是猜测、编造或用无关内容填补。可以简短说明缺少什么；不得借此修改阅读游标或生成用户理解评价。[Phase 1 `focus-explain`](../docs/FOCUS_Phase1_Skills_Quickstart_Architecture.md#14-focus-explain)

## 不应从 `research` Skill 推导出的额外政策

- 不应推导出“每条回复必须带引用”或“必须区分论文观点与外部观点”；Skill 的逐项引用要求适用于研究发现文件，本文件即按该要求引用。
- 不应新增专门的隐私查询改写、逐次联网许可、来源持久化或检索审计协议；这些都不是 `research` Skill 的要求，也没有被当前 Phase 1 领域模型选中。
- 不应恢复解释进度状态机或 Chunk 关联。Explanation Session 仍只是一组持久化的用户问题与模型回复，不拥有 Reading Cursor，也不表达用户理解状态。[FOCUS domain language](../CONTEXT.md)

## 建议的最小执行顺序

```text
用户显式调用 focus-explain
→ 读取当前解释会话与问题
→ 搜索整篇论文的相关内容
→ 必要时研究一手外部资料
→ 判断证据是否足够
→ 足够：直接解释并保存可见问答
→ 不足：明确拒绝回答并保存可见问答
```

该流程只影响 Explanation Session；解释前后 Reading Cursor 必须保持不变，这是 Phase 1 的明确验收边界。[Phase 1 完成标准](../docs/FOCUS_Phase1_Skills_Quickstart_Architecture.md#18-phase-1-完成标准)
