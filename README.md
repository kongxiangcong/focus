# FOCUS

FOCUS 是一个本地、私有、以来源原文为锚点的极简阅读工作台。它把长期资产收敛为固定 Reading Plan、极小 Cursor State 和按 Chunk 隔离的 Reading Record；用户在一个自然会话中阅读、追问、检索、记录与继续，不需要切换交互模式。

## 怎么使用

FOCUS 主要通过 Codex Skills 使用。一次完整流程只有四步：注册 Source、创建 Reading Plan、开始阅读、按需综合 Topic。

1. 用 `paper-parser` 或 `article-parser` 注册来源。调用 Parser 本身即授权本次 MinerU 获取或上传，不会再要求二次确认。
2. 用 `focus-map` 为返回的 Source ID 创建 Reading Plan。重复调用会复用现有 Plan，只有明确要求重建时才会 reinitialize。
3. 用 `focus-read` 阅读单个 Source，或按 Topic manifest 中的 Source ID 顺序连续阅读。
4. 只有明确请求时，才用 `focus-read` 生成带 Source ID 与原文行号锚点的 Topic Synthesis。

最小对话示例：

~~~text
用户：用 $paper-parser 解析 D:\papers\DeepStack.pdf，short name 用 DeepStack，加入 Topic“AI Systems”（topic id: ai-systems）。
用户：用 $focus-map 为 DeepStack-paper 创建阅读计划。
用户：用 $focus-read 按 Topic ai-systems 开始阅读。
用户：继续阅读。
用户：基于这个 Topic 已保存的 Reading Notes 和相关原文范围，生成带来源锚点的综合。
~~~

Parser 成功后会返回稳定的 `source_id`，例如 `DeepStack-paper`。完整原标题保存在 `title`，稳定工作名保存在 `short_name`；Topic 只保存有序 Source ID，不复制 Source 资产。同一规范 URL 或同一 PDF 再次注册时会复用已有 Source。

### 准备环境

- 使用 Python 运行仓库内脚本；脚本仅依赖 Python 标准库。
- 在环境变量 `MINERU_API_TOKEN` 或仓库根目录被 Git 忽略的 `.env` 中配置 MinerU Token。
- 从仓库根目录运行命令，私有数据默认写入被 Git 忽略的 `workspace/`。
- 不要提交 PDF、HTML、Parser Bundle、Reading Records、Topic Synthesis、`.env` 或 Token。

PowerShell：

~~~powershell
Set-Location D:\dsh-proj\focus
$workspace = Join-Path $PWD "workspace"
~~~

### 命令行最小例子

下面的例子注册一篇 Paper，同时创建 `ai-systems` Topic 并把 Source 放入其有序列表：

~~~powershell
$paper = python -B -X utf8 .agents/skills/paper-parser/scripts/mineru_precision.py parse `
  D:\papers\DeepStack.pdf `
  --workspace $workspace `
  --short-name "DeepStack" `
  --topic "AI Systems" `
  --topic-id ai-systems |
  ConvertFrom-Json

$sourceId = $paper.source_id
~~~

Article 使用同一注册语义：

~~~powershell
python -B -X utf8 .agents/skills/article-parser/scripts/article_parser.py parse-url `
  "https://example.com/article" `
  --workspace $workspace `
  --short-name "核心对象与主张" `
  --topic "AI Systems" `
  --topic-id ai-systems
~~~

如果 URL 因登录、限流或访问控制无法解析，手工保存为单个 HTML 文件，再把 `parse-url` 改为 `parse-file <article.html>`；FOCUS 不会绕过访问限制或切换抓取路径。

创建或复用 Source 自己的 Reading Plan：

~~~powershell
python -B -X utf8 .agents/skills/focus-map/scripts/focus_map.py map `
  --workspace $workspace `
  --source-id $sourceId
~~~

第一次调用若返回 `reading_plan_input_missing`，由 `focus-map` 读取 canonical `parser-bundle/content.md`，生成最小 Plan JSON，并在同一回合通过 stdin 再次调用；草案不落盘。直接使用 Skill 时这一步由 Codex 完成。

按 Topic 顺序选择第一个未完成 Source，并显示当前 Chunk：

~~~powershell
$cursor = python -B -X utf8 .agents/skills/focus-read/scripts/focus_read.py topic `
  ai-systems --workspace $workspace |
  ConvertFrom-Json

python -B -X utf8 .agents/skills/focus-read/scripts/focus_read.py current `
  --workspace $workspace
~~~

只有用户明确要求继续阅读时才推进 Cursor；使用上一步返回的 receipt 可以防止重复推进：

~~~powershell
python -B -X utf8 .agents/skills/focus-read/scripts/focus_read.py continue `
  --workspace $workspace `
  --expected-plan-id $cursor.plan_id `
  --expected-chunk-id $cursor.chunk_id
~~~

Topic Synthesis 先做有界检索并核对选中的原文范围，再把 claims 草案通过 stdin 交给 `synthesize-topic`。每条 claim 的 anchor 必须与 Reading Note 或 `topic-range` 选中的范围一致：

~~~powershell
python -B -X utf8 .agents/skills/focus-read/scripts/focus_read.py topic-search `
  ai-systems --workspace $workspace --query "stacked memory" --limit 5

python -B -X utf8 .agents/skills/focus-read/scripts/focus_read.py topic-range `
  ai-systems DeepStack-paper --workspace $workspace --start 120 --end 138

$draft = @{
  selected_ranges = @(
    @{ source_id = "DeepStack-paper"; source_lines = @(120, 138) }
  )
  claims = @(
    @{
      text = "这里填写由选定原文支持的简洁 claim。"
      anchors = @(
        @{ source_id = "DeepStack-paper"; source_lines = @(120, 138) }
      )
    }
  )
} | ConvertTo-Json -Depth 6

$draft | python -B -X utf8 .agents/skills/focus-read/scripts/focus_read.py synthesize-topic `
  ai-systems --workspace $workspace
~~~

示例中的 Source ID、查询词和行号需要替换为 Parser 返回值与 `topic-search`/`topic-range` 的真实结果。Synthesis 是显式生成的派生产物，不会自动改写，也不会复制 Parser Bundle、Reading Records 或对话。

## 公开 Skills

- paper-parser：选定 PDF 并调用即授权本次 MinerU 上传，解析后注册或复用 canonical Paper Source。
- article-parser：提供 URL 或选定单文件 HTML 并调用即授权本次 MinerU 获取/上传，注册或复用 Article Source；不绕过访问控制或适配发布平台。
- paper2blog：从 Parser Bundle 生成独立 Blog Output，不读取或修改私人阅读数据。
- focus-map：为已注册 Reading Source 创建、复用或显式重建固定 Reading Plan。
- focus-read：展示当前 Chunk；按 Topic 有序跨 Source 阅读；执行有界 Source/Topic 搜索、Notes、Cursor 推进与显式 Source-anchored Topic Synthesis。

## 阅读闭环

~~~text
Source Library
  -> Topic manifest: 有序 Source ID 引用
  -> focus-map: 固定 chunks.jsonl 与 glossary.tsv
  -> focus-read: state.json 恢复当前 Chunk
  -> 自由阅读、追问、检索
  -> records/<chunk_id>.json 保存纯翻译和精简 Notes
  -> 明确继续阅读时推进一个 Chunk 或下一个 Topic Source
  -> 显式综合时写入带 Source Anchor 的 claims
~~~

只有 continue_reading 能移动 Reading Cursor。解释、确认、换例子、来源检索、外部检索和旁支任务都不会移动 Cursor。

## Workspace

~~~text
workspace/
├── state.json
├── topics/<topic_id>/
│   ├── topic.yaml
│   └── synthesis/synthesis-NNN.json
└── sources/<source_id>/
    ├── source.yaml
    ├── parser-bundle/
    ├── blog/
    └── reading/plans/<plan_id>/
        ├── chunks.jsonl
        ├── glossary.tsv
        └── records/<chunk_id>.json
~~~

state.json 只保存当前 Reading Source、可选 current_topic_id 及每份 Source 的 current_plan_id/current_chunk_id。Topic 只按顺序引用 Source ID；Source 可以不属于 Topic，也可以被多个 Topic 引用。chunks.jsonl 只保存固定身份、顺序和原文锚点。Reading Record 只保存当前 Chunk 的可选纯中文翻译与 thought、emphasis、question、clarification Notes。

原始用户—模型对话由宿主会话保存。Notes 只保留有限句子的稳定总结或关键词，不复制对话，不评价用户理解、掌握或能力。普通状态恢复和 Chunk 展示不返回历史 Notes；Glossary 只投影当前原文实际命中的术语。

## 开发与验证

### Host-agnostic Focus Reader

独立 Reader 壳位于 `ui/`。`reader-ui` 只依赖 `ReaderHost` Interface；Standalone Fixture/HTTP Adapter 与后续 DSH Adapter 都位于这个 Seam 的宿主侧，不会把运输协议或宿主状态带进 Reader Module。

~~~powershell
pnpm install
pnpm reader:dev
pnpm reader:typecheck
pnpm reader:test
pnpm reader:build
~~~

未设置 `VITE_FOCUS_READER_BASE_URL` 时，Standalone 使用不读取私人 Workspace 的合成 Fixture Adapter。当前只实现结构骨架和最小语义界面；多方案视觉 prototype、正式 Markdown 渲染、动画、粒子和设计系统属于下一独立 feature。

Skills 的脚本都从各自目录解析。Windows 下使用：

~~~powershell
python -B -X utf8 scripts/<script>.py ...
~~~

运行完整验证：

~~~powershell
python -B -X utf8 -m unittest discover -s tests -v
~~~

整个 workspace/ 必须保持 Git 忽略。PDF、Parser Bundle、Blog Output、翻译、Notes、state.json、.env、Token 和签名 URL 都不能进入公开仓库。
