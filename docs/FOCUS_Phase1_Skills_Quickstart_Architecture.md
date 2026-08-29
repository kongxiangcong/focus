# FOCUS Phase 1 Source Library 与 Topic Reading

> 状态：Implemented prototype
> 范围：本地 Skills、确定性核心、私人 Workspace
> 非范围：DSH adapter、多写者、数据库索引、兼容迁移

## 1. 公开接口

| Skill | 职责 |
|---|---|
| paper-parser | 调用即授权本次 MinerU PDF 上传；解析、注册或复用 Paper Source |
| article-parser | 调用即授权本次 MinerU URL 获取或 HTML 上传；解析、注册或复用 Article Source |
| paper2blog | 从 Paper Parser Bundle 生成独立 Blog Output |
| focus-map | 通过 stdin 接收私有草案，创建、复用或显式重建 Source-owned Reading Plan |
| focus-read | 阅读 Source 或有序 Topic，检索、记录、推进并显式生成 Topic Synthesis |

Parser 失败直接返回 typed error。Article URL 被访问控制、登录、限流或动态页面阻止时，不尝试第二条抓取路径，只提示用户另行保存一个 `.html` 后重新调用。

## 2. 权威存储

~~~text
workspace/
├── state.json
├── sources/<source-id>/
│   ├── source.yaml
│   ├── parser-bundle/
│   ├── blog/
│   └── reading/plans/<plan-id>/
│       ├── chunks.jsonl
│       ├── glossary.tsv
│       └── records/<chunk-id>.json
└── topics/<topic-id>/
    ├── topic.yaml
    └── synthesis/synthesis-NNN.json
~~~

`sources/` 是唯一 Source Library。`source.yaml` 保存 exact title、stable short_name、Source Identity、Source ID、kind 及可选 published_at/source_url，不保存 Topics。`topic.yaml.sources` 是唯一 membership 权威，列表顺序就是 Topic Reading 顺序。

Source ID 在 MinerU 完成并解析出 title 后才分配：`<short-name>-paper` 或 `<short-name>-article`。Short Name 保留可读空格与有意义标点；真实冲突优先插入可靠年份，再使用 `-2-`、`-3-`。MinerU Task ID 永远不是 Source ID。

## 3. Plan、Record 与 Cursor

`focus-map` 的 JSON 草案只通过 stdin 运输。正式 Plan 始终位于 Source 内；成功和失败都不保留 draft、receipt 或临时 staging。普通调用复用当前 Plan 和 Cursor；显式 reinitialize 安装下一个 `plan-NNN`，保留旧 Plan/Records，失败时回滚选择。

`chunks.jsonl` 只保存 Chunk identity/order、section path、Source Anchor 与 images。`records/<chunk-id>.json` 只保存可选中文翻译与有限 Reading Notes。宿主会话保存原始对话，Workspace 不复制 transcript。

`state.json` 只包含：

~~~json
{
  "current_source_id": "DeepStack-paper",
  "current_topic_id": "game-ai",
  "sources": {
    "DeepStack-paper": {"current_plan_id": "plan-001", "current_chunk_id": "chunk-018"}
  }
}
~~~

只有 Continue Reading 移动 Cursor。Topic Reading 选择 Topic 中第一个未完成 Source；完成其最后一个 Chunk 后进入下一个未完成 Source。完成状态属于 Source，因此在另一个 Topic 中默认跳过；重读必须显式 reinitialize。

## 4. Topic 检索与综合

Topic 搜索按 manifest 限定 Source 集合并返回有界 snippets。模型只读取选定 Source ranges。显式 Topic Synthesis draft 只能引用：

- 带 Source Anchor 的 Topic Reading Notes；
- 用户为本次综合选定的 Topic Source ranges。

每条 claim 至少包含一个 Source ID 与 Source Anchor。持久化综合只保存 claims/anchors，不复制 Source text、Parser Bundle、Reading Records 或对话；读取和新增 Source 不自动改写综合。

## 5. 边界与验收

- 整个 `workspace/`、真实 PDF/HTML、Parser 结果、Token 与 `.env` 保持 Git 忽略。
- WeChat 与 Zhihu 都是 Article Source；没有 publisher adapter。
- Phase 1 没有 inbox、SQLite/FTS、embeddings、vector DB、knowledge graph、locks、revision、event log、receipt 或 compatibility path。
- fixture/offline 测试通过同一公共 seam 使用 fake MinerU adapter；真实 acceptance 单独报告外部服务结果。
- 完整测试必须覆盖 Source 原子注册/复用/回滚、单向 Topic membership、post-parse naming、Plan rollback、跨 Source Topic Reading、有界搜索、anchored Synthesis 以及仓库边界。
