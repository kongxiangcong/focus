# 02: 手动切换 PDF 与译文时恢复阅读位置

Status: resolved
Blocked by: None (can start immediately)

**What to build:** 读者对照两种视图时优先看到同一段内容。缺少映射时，目标视图恢复本次阅读的位置。

- [x] PDF 到译文、译文到 PDF 各测一次可靠映射。即使目标视图曾停在别处，也应命中对应内容。
- [x] 在译文读到「实验方法」后，去 PDF 找一张无译文映射的表，再手动切回译文，恢复「实验方法」。反向切换同样恢复 PDF 上次位置。
- [x] 本次打开该来源后首次访问目标视图且无映射时，从目标视图开头展示。用无待处理跳转的场景独立验收。
- [x] 在正式 Host 的浏览器阅读入口完成上述操作，通过现有 HTTP/Core 接口核对导航前后的 Reading Cursor 与已读段数保持一致。

## Comments

正式 Host 验证双向可靠映射、目标视图已访问和首次访问两种回退、延迟 PDF 重新加载，以及同页无映射表格和同一来源块跨页的往返。旋转 PDF 样本另验证实际页和段落的对应位置。公开接口确认 Reading Cursor 和已读段数一致。 [浏览器用例](../../../tests/reading_paper_position_browser.mjs)
