---
status: accepted
---

# Reading Lens and on-demand figures

2026-10-20: Reading figures open only on explicit demand. Paragraph thumbnails open the native image viewer; “在资料栏固定” opens the Source gallery and selects that figure. This replaces ADR 0019/0023 automatic figure selection and drawer opening/closing driven by pictureContext. Continuing or reviewing a paragraph leaves the user's gallery selection and open state intact. Source changes clear that presentation state; image Source identity and URL normalization remain unchanged.

In Mist, making room means translating the entire reading column without changing its width or line wrapping. If the available space cannot contain both drawer and unchanged column, the drawer overlays the text. Reading anchors preserve the vertical reading position.

Reading Lens represents visual attention, never the persistent Reading Cursor. Discussion attachment is an explicit local presentation preference, paused when space is insufficient or materials are open. Neither writes to Host state. The redesign specification replaces ADR 0025 colour and motion choices with one product-owned token source, interruptible motion and reduced-motion fallbacks. Host calls, drafts, notes, progress and recovery semantics remain unchanged.

Discussion attachment 部分由 [ADR 0031](0031-attached-notes-and-direct-note-entry.md) 取代（2026-10-21）；原文保留，其余决定继续有效。
