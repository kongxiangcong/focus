# 08: PDF 从统一 IR 生成可引用正文

**What to build:** 新入库的 PDF 由统一来源 IR 生成正文，读者可从回答中的引文回到原文对象。

**Blocked by:** 07 用真实论文验收 Batch B

**Status:** resolved

- [x] 正常入库产出 v1 IR，涵盖来源与版本、章节层级、有序块、规范文本、原文范围、页面和几何区域。
- [x] 从同一 IR 重复序列化得到一致的 LF Markdown。使用该正文读取和签发引文，证据卡原句与发布正文一致。
- [x] 通过正常阅读入口复验 PDF 框、已知页及中文译文回退；旧 Bundle 继续可读。

## Comments

已合入 `3245d0c`。正常 PDF Inbox 和 CLI 发布 v1 IR。实际 MinerU Standard 产物复验了逐字签发及 PDF 框、页定位和译文回退。 审查补充见 `5a49256`。
