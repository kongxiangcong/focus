# FOCUS Reading Workspace

FOCUS 是一个以来源原文为锚点的私人阅读工作台。它保存可跨会话恢复的阅读位置和精简阅读资产，但不复制宿主对话，也不评价读者的理解、掌握或能力。

## Language

**Topic**:
按阅读意图组织 Reading Source ID 的命名有序集合；顺序就是 Topic Reading 顺序；同时作为来源的专题标签。一份来源可属于多个专题，不拥有或复制来源资产。
_Avoid_: Course, physical asset owner, knowledge domain

**Source Library**:
Workspace 内唯一的 `sources/` 权威集合；每份 Reading Source 及其 Parser Bundle、Reading Plans、Records 与 Notes 只保存一次。
_Avoid_: Topic-owned sources, object store, duplicate source tree

**Reading Source**:
一份已在 Workspace 本地注册、可稳定阅读的来源及其可复用源资产；类型只区分 Paper Source 与 Article Source。
_Avoid_: Learning object, assessment subject, knowledge item

**Paper Source**:
以 PDF 提供并由 MinerU 文档模型解析的学术作品。
_Avoid_: Article Source, generic document

**Article Source**:
以 URL、单文件 HTML 或 Markdown 提供的文章或博客，不按发布平台细分。
_Avoid_: Zhihu Source, WeChat Source, Paper Source

**Source Title**:
Reading Source 由发布者或文档给出的完整原题；不混入 Source ID、Source 类型、发布日期或目录消歧信息。
_Avoid_: Source ID, storage name, title with type suffix

**Source Short Name**:
Reading Source 注册时确定的简短、可读且稳定的工作名；优先采用作品公认简称，否则概括其核心对象或主张，确定后不随摘要或展示文案变化。
_Avoid_: Source Title, generated summary, mutable alias

**Source ID**:
Reading Source 注册时分配的稳定引用和目录键；以 Source Short Name 加 `-paper` 或 `-article` 构成，不作为展示标题，只有同名同类型冲突时才追加消歧信息。
_Avoid_: Source Title, source hash, mutable display name

**Source Identity**:
用于识别相同规范 URL 或相同 Paper 原件并复用已注册 Reading Source 的稳定输入身份；它独立于 MinerU Parser Task ID 与 Source ID。
_Avoid_: Source ID, directory name, display title

**Parser Bundle**:
由来源解析或 Markdown 导入得到的规范来源表示、Markdown、引用图片、最小元数据与结构验证结果。
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
workspace/state.json 中保存当前 Reading Source、可选当前 Topic，以及每份 Source 当前 Plan/Chunk 引用及是否已开始阅读的极小持久化对象。
_Avoid_: Session state, event log, per-Topic progress matrix

**Reading Cursor**:
Cursor State 中当前选择的 Reading Chunk 引用；null 表示当前 Plan 已经经过最后一个 Chunk。
_Avoid_: Learning progress, understanding state, mastery state

**Hot Cursor Receipt**:
同一连续宿主会话复用的最近一次 Source、Plan 和 Chunk 返回值；持久化权威仍是 Cursor State。
_Avoid_: Lock, revision, second state authority

**Continue Reading**:
读者明确要求向后阅读时，将 Reading Cursor 推进一个 Chunk 的唯一操作。
_Avoid_: Bare continue, confirmed, understood, mastered, passed

**Topic Reading**:
沿 Topic manifest 的 Source ID 顺序选择首个未完成 Source，并复用每份 Source 自己的 Reading Plan、Cursor、Records 与 Notes；跨 Source 的 Continue Reading 不创建 Topic 进度副本。
_Avoid_: Topic-owned plan, duplicated progress, tag browsing

**Reading Record**:
按 Chunk 隔离的可变阅读资产，仅包含可选的纯中文翻译和精简 Reading Notes；中文来源不保存重复翻译。
_Avoid_: Chat history, plan row, learner record

**Reading Note**:
脱离原始对话仍可理解的有限句子总结或关键词，类型只取 thought、emphasis、question、clarification，来源只取 user 或 dialogue。
_Avoid_: Transcript, discussion log, assessment result, cognitive evidence

**Source Anchor**:
Reading Chunk 或 Reading Note 回到 Parser Bundle 原文的行范围及可选短引文。
_Avoid_: Content hash, duplicated source text

**Topic Synthesis**:
用户显式请求后，从 Topic 内带 Source Anchor 的 Reading Notes 与选定原文范围生成的简洁 claims 集合；它保存在 Topic 下但只是可重新生成的派生产物。
_Avoid_: Source authority, automatic summary, copied Parser Bundle, knowledge graph

**Relevant Glossary**:
当前 Chunk 原文实际出现的 Plan Glossary 子集。
_Avoid_: Full glossary projection, global vocabulary

**Private Reading Data**:
留在本地 Workspace 的 Cursor State、翻译、Reading Notes 和其他读者特定资产。
_Avoid_: Public fixture, reusable project asset, user profile

**Reading Status**:
来源的待规划、待阅读、阅读中或已完成状态；规划与开始阅读是不同事件，完成表示已经读过最后一个 Chunk。
_Avoid_: Understanding score, per-Topic progress copy
