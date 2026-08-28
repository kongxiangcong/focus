# FOCUS Phase 1 极简阅读工作台

> 状态：Implemented prototype
> 范围：本地 Skills、确定性核心与私人 Workspace
> 非范围：DSH 适配、部署、迁移兼容和多写者支持

## 1. 目标

Phase 1 提供一个最小闭环：

~~~text
Parser Bundle
-> focus-map 创建固定 Reading Plan
-> focus-read 恢复 Cursor State 并展示当前 Chunk
-> 在同一宿主会话中自由阅读、追问和检索
-> 按需保存精简 Reading Notes
-> 读者明确要求后推进一个 Chunk
-> 新会话恢复同一 Paper、Plan 和 Chunk
~~~

宿主会话是原始用户—模型对话的权威。FOCUS 不保存第二份聊天历史，不要求用户声明交互模式，也不推断理解、掌握、薄弱项或能力。

## 2. 公开接口

活动 Skill 只有：

| Skill | 职责 |
|---|---|
| paper-parser | 经明确授权解析 PDF，生成并注册 Parser Bundle |
| paper2blog | 从 Parser Bundle 生成独立 Blog Output |
| focus-map | 创建、复用或显式重建 Reading Plan |
| focus-read | 展示、翻译、答疑、检索、记录与推进 |

focus-map 是一次初始化能力。focus-read 是唯一阅读入口；模型回答本身不需要调用领域命令。

## 3. 持久化权威

~~~text
workspace/
├── state.json
├── topics/<topic_id>/topic.yaml
└── papers/<paper_id>/
    ├── paper.yaml
    ├── parser-bundle/
    │   ├── source.pdf
    │   ├── paper.md
    │   ├── images/
    │   ├── metadata.json
    │   └── validation.json
    ├── blog/
    └── reading/plans/<plan_id>/
        ├── chunks.jsonl
        ├── glossary.tsv
        └── records/
            ├── chunk-001.json
            └── chunk-002.json
~~~

state.json：

~~~json
{"current_paper_id":"flexsa","papers":{"flexsa":{"current_plan_id":"plan-001","current_chunk_id":"chunk-018"}}}
~~~

它只保存当前 Paper 与每篇 Paper 的当前 Plan/Chunk。完成阅读时保留 current_plan_id，将 current_chunk_id 写为 null。不存在逐 Chunk 状态表。

chunks.jsonl 每行只保存固定结构：

~~~json
{"chunk_id":"chunk-018","index":18,"section_path":["Method","Address Mapping"],"source_lines":[420,447],"images":["images/image-012.png"]}
~~~

records/chunk-018.json 保存可变资产：

~~~json
{
  "chunk_id": "chunk-018",
  "translation": "……",
  "notes": [
    {
      "kind": "clarification",
      "origin": "dialogue",
      "content": "编译器保留 relocation 信息，最终地址由加载阶段确定。",
      "anchor": {"source_lines": [431, 434], "quote": "alias address"}
    }
  ]
}
~~~

追加 Note 或重译只替换一个 Record；chunks.jsonl 不改变。显式重建安装完整新 Plan 后才切换 Cursor，旧 Plan 与 Records 原样保留。

## 4. Reading Notes

Note kind 只取：

- thought：用户形成的思考、连接或判断；
- emphasis：用户明确标记为重要的内容；
- question：值得后续追踪且尚无可靠结论的问题；
- clarification：经过追问后形成的稳定澄清。

origin 只取 user 或 dialogue。anchor 可选；缺省时由所属 Chunk 提供原文范围。

Reading Record 只保存有限句子的总结或关键词。低信息确认、重复解释、闲聊、旁支任务、模型自行选择的重点和对用户认知状态的推测都不写入。同一完整 Note 重复提交不会再次追加。

## 5. Prompt 投影

持久化数据量与模型上下文量分离：

~~~text
get_reading_state
-> paper_id + plan_id + chunk_id + index + total + section_path

get_current_chunk
-> source_lines + source_text + translation + images + relevant_glossary
~~~

普通状态与 Chunk 展示不返回 Notes、其他 Chunks、完整 Glossary 或历史聊天。只有显式回顾时 list_notes 才读取指定 Chunk Notes。

论文检索使用两步：

~~~text
search_paper(query, limit)
-> section_path + source_lines + short snippet

read_source_range(start, end)
-> selected source_text + bound images
~~~

搜索先定位，模型再读取必要范围；搜索与读取都不移动 Cursor。

## 6. 写入规则

内部命令：

~~~text
get_reading_state
get_current_chunk
continue_reading(expected_plan_id, expected_chunk_id, pending_notes=[])
append_note(expected_plan_id, expected_chunk_id, kind, origin, content, anchor?)
list_notes(plan_id, chunk_id, kinds?, limit?)
search_paper(query, limit)
read_source_range(start, end)
update_glossary(expected_plan_id, source, translation)
retranslate_current_chunk(expected_plan_id, expected_chunk_id, translation)
switch_paper(paper_id)
~~~

只有 continue_reading 推进 Cursor。它先校验 expected receipt，再合并 pending_notes，最后覆盖 state.json。重复旧 receipt 不会再次推进；Record 已保存而 Cursor 写入失败时，重试依靠完整 Note 去重。

推进不预生成下一 Chunk 翻译。推进成功后按需读取下一 Chunk；未缓存时由独立 retranslate 流程写入。

## 7. 解释与方案表达

focus-read 先判断用户真正缺少的概念或关系，只引入完成当前问题所需的最小词汇。实现相关回答区分当前代码、文档意图、推断和未知；证据不足时明确说明。

解释优先使用一个保持机制完整的最小贯通示例。只有三项以上关系难以用短文说明时才使用一个紧凑图。长回答末尾直接回答用户的显式问题，达到可用程度后停止，不自动扩展成教程、路线图或额外产物。

## 8. 边界

- Parser Bundle 成功生成后按约定不可变。
- Blog Output 不读取或修改 state.json、Reading Plans、Glossary 或 Reading Records。
- 整个 workspace/ 被 Git 忽略。
- Token 只来自环境变量或被忽略的 .env。
- Phase 1 不增加数据库、锁、revision、事件账本、会话日志、兼容层、向量库或部署抽象。
- 当前原型按单写者使用；写冲突只通过 expected receipt 防止旧会话污染新 Cursor。

## 9. 验收

完整测试必须证明：

1. Plan 有序、连续、原文锚定，重建保留旧 Plan 与 Records；
2. state.json 是唯一持久化 Cursor 权威；
3. 连续追问、检索与旁支任务不移动 Cursor；
4. 明确继续只推进一个 Chunk，旧 receipt 重试不跳段；
5. Record 写入失败时 Cursor 不动，Cursor 写入失败后的重试不重复 Note；
6. 翻译和 Notes 变化不修改 chunks.jsonl；
7. 历史 Notes 增长不放大默认状态与 Chunk 投影；
8. Glossary 只返回当前 Chunk 命中项；
9. 搜索只返回有限 snippet，range 读取按需展开；
10. 活动仓库只有四个公开 Skills，没有平行阅读状态或聊天归档。
