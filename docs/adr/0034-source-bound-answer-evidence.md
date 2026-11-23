---
status: accepted
---

# Source-bound answer evidence and unified reading

[ADR 0035](0035-close-reading-completion-and-reset.md) 将来源完成统一到精读计划。

2026-11-15: the user approved the simplified conversation-reading prototype and authorized implementation. Full original text and continuous Source discussion become the intended reading surface; the opening combines Chinese structure and guide without a preparation gate. Implemented in the local production reader and Host; no remote deployment is implied. Validation is recorded in `.scratch/conversation-reading/production-acceptance.md`.

Answer Evidence belongs to a specific discussion message revision, bound to Source and Parser Bundle version. It is not a Reading Highlight, Reading Note, Placement or proof that the model's claim is true. Host validation and display projection are distinct. Display projection must reject wrong versions, ambiguous quotations and missing ranges; it must never choose the nearest occurrence as evidence. Existing user annotation relocation remains unchanged.

Reading View Bookmark records manual browsing, separately from Reading Cursor. Citation navigation never advances progress. Source completion requires explicit user action and must not manufacture historical chunk records. Legacy messages without evidence remain readable without invented citations; old assets are read-compatible, not bulk rewritten on opening.

This decision replaces the intended presentation in ADR 0026/0033 (mixed discussion flow), ADR 0030 (separate generation and structure gate), and ADR 0018's sequential-only main flow when the new workspace is activated. Their ownership, explicit deletion, writer fencing and recovery requirements remain. The legacy reader remains available to adapters without the Source Document capability; existing navigation and preparation endpoints remain compatible.

UI contains original content, structure, guide and essential controls/status only; no promotional headings, helper slogans or prescribed next questions. Implementation and acceptance are tracked in `.scratch/conversation-reading/`.

Implementation uses canonical Markdown plus original line ranges as the document boundary. The existing sanitized Markdown/KaTeX pipeline retains a normalization-to-original line map. A Host `cite` result binds an exact quote to the current Source, Bundle, discussion, message and answer revision; its marker is rendered as a number. Exact visible-text projection is preferred. Complex objects or formatting that cannot be projected exactly use an explicitly labelled source-block location, never an invented exact span. External Markdown links are never projected into source text.

The v2 opening is one model candidate and one atomic Source/Bundle asset. A validated ready v1 overview is reused without rewriting it. Manual bookmarks are versioned, local display state with original-line anchors and offsets; completion is an explicit Core asset fenced by the Source clear generation. Neither touches the old Cursor.

## 2026-11-15 逐段精读保留修正

用户明确要求统一阅读入口内保留「逐段精读」和「对话」两个 tab。逐段精读复用原阅读器、Plan、译文、批注及 Cursor 推进流程。对话 tab 使用全文与回答证据联动。切换 tab 不视为读完或推进一段，已有准备好的计划直接恢复。首次尚未准备好的文章会启动原准备流程，完成后再次打开逐段精读。

原文中将逐段精读主流程视为被整体替代的条款由本项修正覆盖。旧逐段精读属于正式支持的阅读方式。

回归验证通过 17 项，包括从精读推进下一段、切到对话、再返回同一段。类型检查通过，构建结果见 tabs-build.log。
