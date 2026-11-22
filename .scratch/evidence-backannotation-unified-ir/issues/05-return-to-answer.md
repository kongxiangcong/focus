# 05: 从证据块返回对应回答

**What to build:** 读者可从来源块回到相关回答，并在多条回答共用一块时选择目标。

**Blocked by:** None (can start immediately)

**Status:** resolved

- [x] 通用标记只关联一条回答时，点击直接返回对应消息及编号。
- [x] 同块关联多条回答时列出可区分的回答摘录；点选后命中所选消息及证据编号。
- [x] 从第二条回答跳来后，点击当前高亮编号直接回到该回答的出发位置。

## Comments

已合入 `c9bfc20`。定向界面测试及真实 PDF 验收覆盖单条直接返回、多条按回答摘录选择和精确回到出发编号。参见 [Batch B 验收](../batch-b-acceptance.md)。
