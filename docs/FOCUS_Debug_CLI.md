# 解析流程与 Core 调试

本文仅供开发、诊断 Parser / Core 工作流。日常使用请按 [README](../README.md) 打开网页；不要在网页 Host 正写入同一 `knowledge-base/` 时，另开进程修改该目录。

## 解析来源

`.agents/skills/article-parser` 负责来源注册与 Parser Bundle 生成。脚本使用 Python 标准库；PDF 远端解析凭据从根目录 `.env` 的 `MINERU_API_TOKEN` 读取。

```bash
python -B -X utf8 .agents/skills/article-parser/scripts/article_parser.py parse-file ./paper.pdf \
  --workspace ./knowledge-base-debug --short-name Paper --topic "端侧 NPU" --topic-id edge-npu
```

记下返回的 `source_id`。

## 阅读计划与阅读状态

已删除的 `focus-map` / `focus-read` CLI 不再提供；阅读计划、Cursor 和 Source Notes 由 `core.WorkspaceCore` 直接驱动（网页 Host 走的也是同一个模块）。在仓库根目录执行：

```bash
python -B -X utf8 -c "import sys; sys.path.insert(0, '.agents'); from core import WorkspaceCore; import json; print(json.dumps(WorkspaceCore('./knowledge-base-debug').get_reading_state(), ensure_ascii=False, indent=2))"
```

需要新建或重建计划时调用 `WorkspaceCore.map_reading_plan(source_id, draft=...)`，草案结构见 `tests/test_reading_plan.py`。阅读推进、译文和笔记分别使用 `continue_reading`、`retranslate_current_chunk` 与 `append_note`；这些方法不会替你生成计划草案。

调试完后检查 `knowledge-base-debug/` 的数据，勿将论文、笔记或密钥提交到仓库。
