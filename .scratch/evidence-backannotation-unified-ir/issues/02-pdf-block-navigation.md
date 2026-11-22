# 02: 在原文 PDF 定位可靠块或页面

**What to build:** 读者点选现有按行签发的证据，可查看完整对象，或直接跳到可靠页码。

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

- [ ] 通过正常入库读取既有及带前缀的 MinerU middle、content_list、content_list_v2 归档。Batch B 继续使用现有正文生成流程。
- [ ] 从回答打开真实跨栏与旋转页，所有可靠框与对象对齐。仅按明确坐标契约归一化；坐标越界、缺乏基准或未知时，有可靠页码则跳页，同页多个页级标记可区分。
- [ ] 校验来源、bundleVersion 与 layoutVersion。版面摘要覆盖 IR 版本、PDF、正文、页尺寸、旋转、有序块与几何。仅改变几何即可使旧框及旧页码失效，原引文仍可读。
- [ ] 按页尺寸占位并按需加载。从已渲染页点击远端证据，无需先加载全部页面即可定位。
