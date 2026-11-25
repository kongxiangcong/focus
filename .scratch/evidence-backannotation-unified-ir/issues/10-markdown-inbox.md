# 10: Markdown 从 Inbox 入库并签发证据

**What to build:** 通过现有 Inbox 流程导入 Markdown 后，读者可对新文章提问并核对跨段证据。

**Blocked by:** 08 PDF 从统一 IR 生成可引用正文

**Status:** resolved

- [x] Markdown 经过正常入库状态机发布为可打开的 Reading Source，包含有序块、章节及原文范围。
- [x] 同一 IR 确定性生成 LF 正文，使用真实换行的连续跨段引文可签发；跳过中间块的引用被拒绝。
- [x] 关闭再打开文章，已保存的回答、引文和来源位置仍可核对。

## Comments

已合入 `75bb23e`。Markdown 经普通 Inbox 发布 v1 IR，HTTP 验证连续跨段引用、跳段拒签、旧来源复用及重启恢复。独立工作台上传测试通过。 审查补充见 `5a49256`。
