# 05: 中文证据与历史来源回退

Status: resolved

**What to build:** 读者在中文段落看到对应的回答证据，切回原文可核对签发该证据的原句。

**Blocked by:** [03 双语切换与位置恢复](03-bilingual-position.md)、[04 从回答直接定位原文证据](04-source-evidence-navigation.md)

[父规格 · 用户故事 8、10–12、15](../spec.md#user-stories)

- [x] 从中文视图点回答编号，高亮由同一原文位置映射出的译段。在证据仍可见时切换语言，两侧对应同一条证据。手动滚远再切换，视口停在眼前段落。
- [x] 使用只能验证到一组译段的历史材料，核对整组高亮；只有段数相同而无法验证对应时，在该处显示可核对的原文块。
- [x] 无 Source IR 时采用规范 Markdown 与原文行范围。使用旧 Host、只读旧 Bundle 及歧义引文样例验证安全回退，证据身份与精读进度保持稳定。

## Comments

验证中文译段和历史段组的定位、切换时保留证据、无可靠映射时显示可核对的原文，以及缺失、歧义或版本不符时保守处理。[双语浏览器用例](../../../tests/bilingual_position_browser.py) · [历史 Host 用例](../../../tests/test_source_reading_http.py)
