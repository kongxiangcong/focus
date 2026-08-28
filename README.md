# FOCUS

FOCUS 是一个本地、私有、以论文原文为锚点的极简阅读工作台。它把长期资产收敛为固定 Reading Plan、极小 Cursor State 和按 Chunk 隔离的 Reading Record；用户在一个自然会话中阅读、追问、检索、记录与继续，不需要切换交互模式。

## 公开 Skills

- paper-parser：经明确授权后使用 MinerU 托管精度 API 解析 PDF，并注册 Paper 与 Parser Bundle。
- paper2blog：从 Parser Bundle 生成独立 Blog Output，不读取或修改私人阅读数据。
- focus-map：为已注册 Paper 创建、复用或显式重建固定 Reading Plan。
- focus-read：展示与翻译当前 Chunk、连续答疑、按需检索论文、保存精简 Notes，以及推进 Reading Cursor。

## 阅读闭环

~~~text
Parser Bundle
  -> focus-map: 固定 chunks.jsonl 与 glossary.tsv
  -> focus-read: state.json 恢复当前 Chunk
  -> 自由阅读、追问、检索
  -> records/<chunk_id>.json 保存纯翻译和精简 Notes
  -> 明确继续阅读时推进一个 Chunk
~~~

只有 continue_reading 能移动 Reading Cursor。解释、确认、换例子、论文检索、外部检索和旁支任务都不会移动 Cursor。

## Workspace

~~~text
workspace/
├── state.json
├── topics/<topic_id>/topic.yaml
└── papers/<paper_id>/
    ├── paper.yaml
    ├── parser-bundle/
    ├── blog/
    └── reading/plans/<plan_id>/
        ├── chunks.jsonl
        ├── glossary.tsv
        └── records/<chunk_id>.json
~~~

state.json 只保存当前 Paper 及每篇 Paper 的 current_plan_id/current_chunk_id。chunks.jsonl 只保存固定身份、顺序和原文锚点。Reading Record 只保存当前 Chunk 的纯中文翻译与 thought、emphasis、question、clarification Notes。

原始用户—模型对话由宿主会话保存。Notes 只保留有限句子的稳定总结或关键词，不复制对话，不评价用户理解、掌握或能力。普通状态恢复和 Chunk 展示不返回历史 Notes；Glossary 只投影当前原文实际命中的术语。

## 本地运行

Skills 的脚本都从各自目录解析。Windows 下使用：

~~~powershell
python -B -X utf8 scripts/<script>.py ...
~~~

运行完整验证：

~~~powershell
python -B -X utf8 -m unittest discover -s tests -v
~~~

整个 workspace/ 必须保持 Git 忽略。PDF、Parser Bundle、Blog Output、翻译、Notes、state.json、.env、Token 和签名 URL 都不能进入公开仓库。
