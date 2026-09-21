# 专题知识库：目录与本地工作流

`focus/workspace/` 是默认私人文件数据库，由 `--workspace` / `FOCUS_WORKSPACE` 指定时使用那个目录，网页与技能必须指向同一个绝对路径。目录已被 Git 忽略；对话保存在其外的 Host 数据库。

```text
workspace/
  state.json
  sources/<source-id>/
    source.yaml
    parser-bundle/{source.pdf|source.html|source.md,content.md,images/,metadata.json,validation.json}
    reading/plans/plan-NNN/{chunks.jsonl,glossary.tsv,records/}
  topics/<topic-id>/topic.yaml
```

来源根目录是完整 bundle，parser-bundle 是其规范原文部分。专题 manifest 的有序 `sources` 是成员关系唯一权威；卡片 tags 从这里反向投影。跨专题复用来源 ID，不复制目录。

## Inbox 入库与本地导入

网页阶段 1 只接收单篇 PDF：先选择或新建目标专题并放入持久 Inbox；这一步不外发。用户核对文件、专题、MinerU/Codex 服务和“仅入库”范围后明确确认，Host 才调用共享 Application。相同原件复用唯一 Source，只补 Topic 关系。完成结果可查看原件、正文和引用图片，但没有 Reading Plan、全文翻译或博客。

直接使用 `article-parser` Skill 仍支持 PDF 与单文件 HTML；Markdown 已是文本，使用以下本地导入，不提交到 MinerU。这些开发者入口与网页 Inbox 的确认边界不同。

在仓库 `.agents/` 目录执行（替换为真实绝对路径）：

```powershell
python -B -X utf8 -m core.library_import markdown <article.md> --workspace <workspace> --short-name <简称> --language zh --topic <专题> --uploader 孔祥聪
python -B -X utf8 -m core.library_import describe --workspace <workspace> --source-id <id> --published-at 2026-09 --venue <期刊或会议>
```

Markdown 接受 UTF-8 非空文本，保留字节相同原件。单文件上传不包含相邻图片，缺失的本地图片引用会明确失败，不生成残缺 bundle。英文文本选择 `--language en`。完整标题保留；简称必须有来源依据。年月保留 YYYY、YYYY-MM 或 YYYY-MM-DD 原有精度；不知道的期刊或时间留空。

解析/导入只注册来源。只有用户随后点击阅读或重新规划，才调用 focus-map 建立／复用 Plan 并准备阅读；入库成功不依赖 Plan。失败输入、远端引用和有效候选保留在 Inbox 断点中；继续处理只补未完成步骤。

本地通过 SourceLibrary.attach 或现有 parser reuse 命令添加第二专题；网页把相同 PDF 放入 Inbox 并选择另一专题时复用同一 Source，不重新解析，也不改变既有阅读位置。

## 阅读生命周期

state.json 的每份来源保存 current_plan_id、current_chunk_id，以及可选 reading_started。新计划为 false；显式 focus-read current 或网页阅读成功后为 true；continue 推进 Cursor 并标记已开始。只查状态、列表、历史或提问不会推进 Cursor。

黄色为有计划未开始；蓝色为已开始未完成；绿色为 Plan 存在且 Cursor=null。没有 Plan 单独显示待规划。旧数据缺少标记时保守按已推进段数推断，下一次显式阅读写入标记，不批量猜测历史。

重读保留 Parser Bundle、旧计划与缓存翻译，沿用现有明确确认后清空笔记的规则，重置选择并创建下一编号计划。规划成功后留在知识库，变黄；失败保持待规划并可重试。

阅读页只选已保存材料；底部输入框提问，右边缘短横线定位当前会话的历史提问，悬停/键盘聚焦显示内容。Host 会话存储方式不变。

## 2026-09-18：准备后阅读（替代上文旧流程）

所有来源均先分 Chunk；中文论文和文章不翻译，外文／混合 Chunk 保存中文译文。
Plan 可选 language=zh/en/mixed；旧 Plan 继承 bundle 语言。语言由规划时对正文的判断确定，
不是按文件扩展名判断。中文夹技术术语仍可标为 zh。

重新规划／首次打开未规划 Source：分段和术语表 → preparation 查询 → 逐个 prepare_chunk／
prepare_translation → ready=true。中文条目也计入已就绪段数，但没有复制的译文。
任务中断后重新打开材料，保留已有译文，只补缺失项。准备不计入阅读进度；Inbox 入库不触发本段流程。

打开已准备材料／下一段只读 Core 和缓存，不启动 Agent。旧计划缺译文时先点击阅读补齐。
从头阅读保留 Plan、译文和 Notes，回到第一段；重新规划保留旧资产并创建新 Plan，不清空笔记。
详见 ADR 0010。正式阅读默认显示中文内容，外文原文仅在主动切换时显示。
