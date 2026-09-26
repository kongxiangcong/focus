# FOCUS Reading Workspace

FOCUS 是一个以来源原文为锚点的私人阅读工作台。它保存可跨会话恢复的阅读位置和精简阅读资产，但不复制宿主对话，也不评价读者的理解、掌握或能力。

## Language

**Knowledge Base**:
FOCUS 保存来源、专题及私人阅读资产的本地知识库，是跨会话恢复阅读与处理进展的唯一业务数据集合。
_Avoid_: Host chat history, duplicate asset store

**Topic**:
按阅读意图组织 Reading Source ID 的命名有序集合；顺序就是 Topic Reading 顺序；同时作为来源的专题标签。一份来源可属于多个专题，不拥有或复制来源资产。
知识库按 Topic 展示，同一来源在不同专题中的展示指向同一份来源资产。
名称去首尾空白并忽略大小写后相同的 Topic 是同一个专题。
_Avoid_: Course, physical asset owner, knowledge domain

**Source Library**:
Knowledge Base 内唯一的来源权威集合；每份 Reading Source 及其 Parser Bundle、Reading Plans、Records 与 Notes 只保存一次。
_Avoid_: Topic-owned sources, object store, duplicate source tree

**Reading Source**:
一份已在 Knowledge Base 本地注册、可稳定阅读的来源及其可复用源资产；类型只区分 Paper Source 与 Article Source。
_Avoid_: Learning object, assessment subject, knowledge item

**Inbox Item**:
一份待入库材料及其处理目标、确认和可恢复进展；它本身不是已注册 Reading Source。相同原件已有未完成入库任务时，重复添加指回原任务。
_Avoid_: Reading Source, duplicate parsing task

**Ingestion**:
将来源原件及通过校验的 Parser Bundle 发布到 Source Library 的过程；不以图片存在、AI 审核、Reading Plan 或博客完成为前提。文档发布与所请求的 Topic 关联分别报告结果。
_Avoid_: Reading Preparation, AI quality certification, Topic attachment

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
用于识别相同规范 URL、相同 Paper 原件或没有 URL 的相同 HTML 原件并复用已注册 Reading Source 的稳定输入身份；它独立于 MinerU Parser Task ID 与 Source ID。
相同 PDF 内容即为相同 Paper 原件，改名或加入另一 Topic 不产生新 Source 或 Parser Bundle。
_Avoid_: Source ID, directory name, display title

**Parser Bundle**:
由来源解析或 Markdown 导入得到的规范来源表示、Markdown、引用图片、最小元数据与结构验证结果。
_Avoid_: Temporary extraction, duplicate source tree, Reading Plan

**Blog Output**:
从 Reading Source 的 Parser Bundle 派生的解释性产物集合，包含必需的 Reading Blog、适用时生成的 Value Analysis 及合并单文件 HTML；它不拥有或修改阅读数据。
_Avoid_: Reading Plan, Reading Record, source bundle

**Reading Blog**:
Blog Output 中按 `reading-blog-guide.md`（带读博客方法）生成的技术细读长文（`blog.md`）；以问题组织材料、解释方法成立的原因。
_Avoid_: full translation, section-by-section summary, paper2blog（历史资产名）

**Value Analysis**:
Blog Output 中基于来源证据解释问题、输入输出、模块、运行例子以及贡献或工程设计边界的架构价值分析文。它仅在来源涉及硬件架构、DSE、编译器、仿真器或性能建模且有足够原文依据时生成，不按文件格式区分适用性，不适用时明确说明理由。
_Avoid_: review scorecard, abstract, reproduction report, unconditional companion of Reading Blog

**article-blog**:
从 Paper Source 或 Article Source 的 Parser Bundle 生成 Blog Output 的统一方法；取代历史名 paper2blog，不按来源类型分成不同方法。
_Avoid_: paper2blog, per-source-type blog method

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
Knowledge Base 中保存当前 Reading Source、可选当前 Topic，以及每份 Source 当前 Plan/Chunk 引用及是否已开始阅读的极小持久化对象。
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
按 Chunk 隔离的阅读资产，包含可选的纯中文翻译与阅读进度记录；中文来源不保存重复翻译，主动 Reading Notes 独立属于 Source。
_Avoid_: Chat history, plan row, learner record

**Reading Note**:
用户明确要求记录后保留的 Source 级精简笔记，脱离原始对话仍可理解，通常以例子和总结后的结论表达，也可包含理解链、澄清的概念或待解的问题；不依附某个 Topic 或 Reading Plan。
_Avoid_: Transcript, discussion log, assessment result, cognitive evidence

**Reading Progress Entry**:
每个 Reading Chunk 推进或完成本篇时系统简短保存的阅读进度记录，记载读过的段落、实际讨论的话题及用户明确表达的理解；与主动 Reading Note 分开，不表示系统对能力的评价，也不决定阅读位置。
_Avoid_: Reading Note, Reading Cursor, mastery evidence, transcript

**Source Anchor**:
Reading Chunk 或 Reading Note 回到对应版本 Parser Bundle 原文的行范围及可选短引文；来源更新不改变旧锚点指向。
_Avoid_: Content hash, duplicated source text

**Topic Synthesis**:
用户显式请求后，从 Topic 内带 Source Anchor 的 Reading Notes 与选定原文范围生成的简洁 claims 集合；它保存在 Topic 下但只是可重新生成的派生产物。
_Avoid_: Source authority, automatic summary, copied Parser Bundle, knowledge graph

**Relevant Glossary**:
当前 Chunk 原文实际出现的 Plan Glossary 子集。
_Avoid_: Full glossary projection, global vocabulary

**Private Reading Data**:
留在本地 Knowledge Base 的 Cursor State、翻译、Reading Notes 和其他读者特定资产。
_Avoid_: Public fixture, reusable project asset, user profile

**Reading Status**:
来源的待规划、待阅读、阅读中或已完成状态；规划与开始阅读是不同事件，完成表示读者在最后一个 Chunk 明确完成本篇，查看历史内容不改变完成状态。
_Avoid_: Understanding score, per-Topic progress copy

**Reading Review**:
对已读 Reading Chunk 的只读回看，可围绕所查看内容提问，但不改变 Reading Cursor 或完成状态，也不授权从该历史位置继续推进。
_Avoid_: Second cursor, unread preview, reread from start

**Reading Preparation**:
对一份 Reading Source 的固定 Reading Plan 准备完整可读内容：中文直接使用原文，外文／混合内容在全文语境下翻译并检查跨 Chunk 连贯性。
准备就绪不代表已开始或已读完，也不改变 Reading Cursor。
_Avoid_: Reading progress, second cursor, automatic explanation
