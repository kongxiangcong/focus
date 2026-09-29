# FOCUS Skills 与 Python CLI 调试

本文仅供开发、诊断 Parser / Core 工作流。日常使用请按 [README](../README.md) 打开网页；不要在网页 Host 正写入同一 `knowledge-base/` 时，另开 CLI 修改该目录。

从仓库根目录执行。`.agents/skills/` 下的 `article-parser`、`focus-map`、`focus-read` 分别用于来源注册、阅读计划和阅读状态。脚本使用 Python 标准库；PDF 远端解析凭据从根目录 `.env` 的 `MINERU_API_TOKEN` 读取。

```bash
python -B -X utf8 .agents/skills/article-parser/scripts/article_parser.py parse-file ./paper.pdf \
  --workspace ./knowledge-base-debug --short-name Paper --topic "端侧 NPU" --topic-id edge-npu
```

记下返回的 `source_id`，继续检查 Plan 与当前段落：

```bash
python -B -X utf8 .agents/skills/focus-map/scripts/focus_map.py map \
  --workspace ./knowledge-base-debug --source-id SOURCE_ID
python -B -X utf8 .agents/skills/focus-read/scripts/focus_read.py current \
  --workspace ./knowledge-base-debug
```

将 `SOURCE_ID` 换成第一步返回的 `source_id`。若 `focus-map` 返回 `reading_plan_input_missing`，需按该 Skill 的 `SKILL.md` 从 Parser Bundle 生成 Plan 草案，再从 stdin 提交；直接运行脚本不会替代模型生成计划。每个 Skill 的完整参数和约束以相应 `SKILL.md` 为准。调试完后检查 `knowledge-base-debug/` 的数据，勿将论文、笔记或密钥提交到仓库。
