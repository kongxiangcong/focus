# FOCUS Reading Workspace

FOCUS 是一个以来源原文为锚点的私人阅读工作台。它保存可跨会话恢复的阅读位置和精简阅读资产，但不复制宿主对话，也不评价读者的理解、掌握或能力。

## Language

**Topic**:
组织相关 Reading Sources 的命名集合，不拥有或复制来源资产。
_Avoid_: Course, learning path, knowledge domain

**Reading Source**:
一份已在 Workspace 本地注册、可稳定阅读的来源及其可复用源资产；类型只区分 Paper Source 与 Article Source。
_Avoid_: Learning object, assessment subject, knowledge item

**Paper Source**:
以 PDF 提供并由 MinerU 文档模型解析的学术作品。
_Avoid_: Article Source, generic document

**Article Source**:
以公开 URL 或用户手动保存的单文件 HTML 提供并由 MinerU-HTML 解析的中文文章或博客，不按发布平台细分。
_Avoid_: Zhihu Source, WeChat Source, Paper Source

**Source ID**:
Reading Source 注册时分配的稳定可读 slug；仅在冲突时追加数字后缀，不依赖内容哈希。
_Avoid_: Full title, source hash, mutable display name

**Parser Bundle**:
由 Paper Parser 或 Article Parser 直接生成在 Reading Source 目录中的规范来源表示、Markdown、引用图片、最小元数据与结构验证结果。
_Avoid_: Temporary extraction, duplicate source tree, Reading Plan

**Blog Output**:
从 Paper Source 的 Parser Bundle 派生并与其同级保存的解释文章；它不拥有或修改阅读数据。
_Avoid_: Reading Plan, Reading Record, source bundle

**Reading Plan**:
对一份 Reading Source 的固定、有序、原文锚定的 Reading Chunks 定义。
_Avoid_: Curriculum, mastery plan, knowledge map

**Plan Glossary**:
属于一个 Reading Plan 的原文术语到中文译法表。
_Avoid_: Knowledge graph, global terminology authority

**Reading Chunk**:
Reading Plan 中一个稳定、连续、可整体展示的原文单元。
_Avoid_: Lesson, checkpoint, mastery node

**Cursor State**:
workspace/state.json 中保存当前 Reading Source 及每份 Source 当前 Plan/Chunk 引用的极小持久化对象。
_Avoid_: Session state, event log, progress matrix

**Reading Cursor**:
Cursor State 中当前选择的 Reading Chunk 引用；null 表示当前 Plan 已经经过最后一个 Chunk。
_Avoid_: Learning progress, understanding state, mastery state

**Hot Cursor Receipt**:
同一连续宿主会话复用的最近一次 Source、Plan 和 Chunk 返回值；持久化权威仍是 Cursor State。
_Avoid_: Lock, revision, second state authority

**Continue Reading**:
读者明确要求向后阅读时，将 Reading Cursor 推进一个 Chunk 的唯一操作。
_Avoid_: Bare continue, confirmed, understood, mastered, passed

**Reading Record**:
按 Chunk 隔离的可变阅读资产，仅包含可选的纯中文翻译和精简 Reading Notes；中文来源不保存重复翻译。
_Avoid_: Chat history, plan row, learner record

**Reading Note**:
脱离原始对话仍可理解的有限句子总结或关键词，类型只取 thought、emphasis、question、clarification，来源只取 user 或 dialogue。
_Avoid_: Transcript, discussion log, assessment result, cognitive evidence

**Source Anchor**:
Reading Chunk 或 Reading Note 回到 Parser Bundle 原文的行范围及可选短引文。
_Avoid_: Content hash, duplicated source text

**Relevant Glossary**:
当前 Chunk 原文实际出现的 Plan Glossary 子集。
_Avoid_: Full glossary projection, global vocabulary

**Private Reading Data**:
留在本地 Workspace 的 Cursor State、翻译、Reading Notes 和其他读者特定资产。
_Avoid_: Public fixture, reusable project asset, user profile
