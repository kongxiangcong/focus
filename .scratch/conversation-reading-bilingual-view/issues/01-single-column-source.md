# 01: 单栏原文与打开原件

Status: resolved

**What to build:** 读者在对话区用同一套单栏排版阅读已准备好的 PDF、HTML 和 Markdown，核对版面时从当前阅读位置打开原件。

**Blocked by:** None (can start immediately)

[父规格 · 用户故事 7、19](../spec.md#user-stories)

- [x] 在正式工作台依次打开三种格式，标题、正文、图表、公式、附录与参考文献依原文顺序出现。字号和主题适用于三种格式。
- [x] 在 1440px 和 390px 下都能阅读和选文。宽表、代码和公式在块内滚动，页面宽度保持在视口内。
- [x] 有原件时工具栏只有一处「打开原件 ↗」。在可靠页码第 8 页打开直达第 8 页，手动读到第 12 页后再打开直达第 12 页。
- [x] PDF 页码未知时打开文件，HTML 原件按自身地址打开。缺少原件时隐藏该动作。

## Comments

正式工作台在 1440px 和 390px 验证 PDF、HTML、Markdown 单栏排版、选文、主题、字号与块内滚动。PDF 原件链接验证第 8 页、第 12 页及未知页码的 URL，并读取 Host 返回的原件。[浏览器用例](../../../tests/single_column_source_browser.py)
