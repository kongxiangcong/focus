# FOCUS Reading Workspace

FOCUS 是一个专题驱动的论文阅读工作台。它组织论文资产、建立逐片段精读计划、缓存中文翻译、保存用户备注，并允许把复杂问题放进可恢复的独立解释会话。

FOCUS 记录“当前读到哪里”和“用户做了什么”，不判断用户是否理解，不生成能力等级、薄弱项、画像、测试或掌握结论。

## 当前状态

2026-08-24 已完成新产品架构决策，并建立 Reading Workspace 实现基线：

- [Phase 1 Skills 原型设计](docs/FOCUS_Phase1_Skills_Quickstart_Architecture.md)
- [Phase 2 DSH 迁移边界](docs/FOCUS_Phase2_DSH_Migration_and_Deployment.md)
- [领域语言](CONTEXT.md)

Paper Companion v0.2 已由 `paper-companion-v0.2` Git tag 保存；旧学习 Skills、状态内核和学习测试已退出活动主线。`paper-parser` 已接入 Reading Workspace：它在逐篇授权后生成无哈希 Parser Bundle，通过结构校验后才注册 Topic、Paper 和初始指针，并支持按非敏感 `batch_id` 恢复异步任务。`paper2blog` 已按显式 Paper ID 创建隔离 Blog；`focus-map` 已能校验并原子安装首个 Reading Plan；`focus-guide` 已支持稳定 Chunk 展示、显式 Notes、术语修正、重译与单步推进；`focus-explain` 已支持独立解释会话的创建、追加、选择和跨进程恢复。这些路径已通过受控 fixture 验证，尚未把一次真实 MinerU 调用或真实论文全流程声明为验收完成。

## 目标体验

Phase 1 的显式阅读 Skill：

- `focus-map`：已实现，为已注册 Paper 创建或复用稳定 Reading Plan；
- `focus-guide`：已实现当前 Chunk 的稳定翻译、三类 Notes、行内讨论、术语修正、重译、Continue Reading、完成与跨进程恢复；
- `focus-explain`：已实现独立解释问答的持久化与恢复、全文结构检索、必要外部一手资料研究纪律及可靠拒答。

两个论文处理 Skill 继续保留：

- `paper-parser`：经逐篇授权调用 MinerU 托管精准解析 API，直接在 Workspace Paper 目录生成无哈希 Parser Bundle，并在结构校验后完成注册；
- `paper2blog`：从已注册 Paper 的 Parser Bundle 生成同级独立 Blog，不读取或修改 Reading 与 Explanation 数据。

不设置统一公共路由 Skill。`focus-guide` 中的“继续”表示继续阅读，`focus-explain` 中的“继续”表示继续解释；两者不能由隐藏路由混用。

## 核心规则

- 只有 Continue Reading 能移动 Reading Cursor；
- 简短追问留在 `focus-guide`，形成中性 Discussion Note；
- 只有用户显式调用 `focus-explain` 才创建 Explanation Session；
- Explanation Session 只保存 `role` 与 `content`，不保存 Chunk、时间、来源或用户评价；
- 翻译按 Chunk 缓存，用户可显式重新翻译；
- Notes 分为 `reader`、`discussion` 和 `emphasis`；
- 重新初始化创建新 Plan 目录，旧翻译和 Notes 原样保留；
- Blog、Parser Bundle 与 Reading 数据互不拥有；
- Phase 1 假设每篇 Paper 只有一个写入者，不建设锁、revision 或事务框架；
- Paper、Plan、Chunk 和 Parser Bundle 均不使用内容哈希。

## 目标 Workspace

```text
workspace/
├── pointers.yaml
├── topics/<topic_id>/topic.yaml
└── papers/<paper_id>/
    ├── paper.yaml
    ├── parser-bundle/
    ├── blog/
    └── reading/
        ├── plans/<plan_id>/
        │   ├── chunks.jsonl
        │   └── glossary.tsv
        └── explanations/<explanation_id>.jsonl
```

`workspace/` 包含论文、翻译、Notes、解释问答和阅读位置，属于用户私有数据。实施时将整体 Git 忽略；公开仓库只保留代码、Skills、文档和不含真实用户内容的合成 fixtures。

## Parser 云端边界

目标实现仍只使用 MinerU 托管精准解析 API。上传 PDF 前必须取得用户对该论文的明确授权。Token 只从 `MINERU_API_TOKEN` 环境变量或被 Git 忽略的 `.env` 读取，不得进入聊天、命令行、日志或产物。

解析任务是异步的；上传或创建任务不等于成功。超时可以使用非敏感 `batch_id` 恢复。解析器不计算或持久化内容哈希；源 PDF 副本使用直接字节比较验证。

## Explanation 检索

`focus-explain` 先搜索完整论文，按需读取相关段落、公式、表格、图片和 caption；必要时研究外部一手资料。模型形成自己的理解后直接回答用户，不强制逐条展示来源或检索过程。无法形成可靠解释时明确拒绝，不猜测。

## 后续实施边界

当前实现基线已完成历史保全、旧运行时退役、Paper Parser 注册、隔离 Blog Output、首个 Reading Plan、完整 Guided Reading 操作，以及 Explanation Session 持久化与恢复切片。后续实施任务将：

1. 实现 Reading Plan 重新初始化与旧工作保全；
2. 使用真实论文完成 Phase 1 十一项验收。

当前 README 不声称这些后续运行时已经存在。
