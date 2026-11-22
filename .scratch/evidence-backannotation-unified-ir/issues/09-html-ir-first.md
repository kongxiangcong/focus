# 09: HTML 入库保留可引用的 DOM 块

**What to build:** 正常导入 HTML 后，读者可以从回答中的证据追溯到对应原文块。

**Blocked by:** 08 PDF 从统一 IR 生成可引用正文

**Status:** resolved

- [x] 结构化 HTML 经正常入口产生统一 IR，保留 DOM 块锚点、阅读顺序与章节归属。
- [x] 同一 IR 重复生成一致的 LF 正文；通过工具读取并引用带链接或格式标记的段落，可从回答核对逐字引文与正确块。
- [x] 用含重复短句的不同块检验范围及上下文消歧；歧义仍在时拒签。

## Comments

已合入 `71e6b33`。同一归档 HTML 经 Inbox 和 CLI 生成逐字一致的 IR 与 LF 正文。HTTP 与 Host 工具验证 DOM 锚点、重复引文的范围消歧及精确上下文。
