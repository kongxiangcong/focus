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

## 上传与本地导入

网页填写专题、用户（默认孔祥聪），选择文件再确认。PDF 走 paper-parser，HTML 走 article-parser；两者保留既有 MinerU 路径。Markdown 已是文本，使用以下本地导入，不提交到 MinerU。

在仓库 `.agents/` 目录执行（替换为真实绝对路径）：

```powershell
python -B -X utf8 -m core.library_import markdown <article.md> --workspace <workspace> --short-name <简称> --language zh --topic <专题> --uploader 孔祥聪
python -B -X utf8 -m core.library_import describe --workspace <workspace> --source-id <id> --published-at 2026-09 --venue <期刊或会议>
```

Markdown 接受 UTF-8 非空文本，保留字节相同原件。单文件上传不包含相邻图片，缺失的本地图片引用会明确失败，不生成残缺 bundle。英文文本选择 `--language en`。完整标题保留；简称必须有来源依据。年月保留 YYYY、YYYY-MM 或 YYYY-MM-DD 原有精度；不知道的期刊或时间留空。

解析/导入只注册来源；知识库完整工作流随后调用 focus-map 规划或复用。上传与重读只规划，不自动 focus-read。Host 校验原件、bundle 和所选 Plan 才报告任务成功。失败输入暂存在 uploads/，成功后清理；重新上传同一原件复用已安装来源，补做规划，追加专题而不重置进度。

本地通过 SourceLibrary.attach 或现有 parser reuse 命令添加第二专题；网页重复上传相同原件并选择另一专题得到同样结果。

## 阅读生命周期

state.json 的每份来源保存 current_plan_id、current_chunk_id，以及可选 reading_started。新计划为 false；显式 focus-read current 或网页阅读成功后为 true；continue 推进 Cursor 并标记已开始。只查状态、列表、历史或提问不会推进 Cursor。

黄色为有计划未开始；蓝色为已开始未完成；绿色为 Plan 存在且 Cursor=null。没有 Plan 单独显示待规划。旧数据缺少标记时保守按已推进段数推断，下一次显式阅读写入标记，不批量猜测历史。

重读保留 Parser Bundle、旧计划与缓存翻译，沿用现有明确确认后清空笔记的规则，重置选择并创建下一编号计划。规划成功后留在知识库，变黄；失败保持待规划并可重试。

阅读页只选已保存材料；底部输入框提问，右边缘短横线定位当前会话的历史提问，悬停/键盘聚焦显示内容。Host 会话存储方式不变。
