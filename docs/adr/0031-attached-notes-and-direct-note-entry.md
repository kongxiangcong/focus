---
status: accepted
---

# Attached Notes and direct Reading Note entry

2026-10-21：按 reader-usability-audit/spec.md §1 D1、D2、D5 和 §3.4/§3.6，取代 ADR 0026 的 Discussion attachment 部分。其余现行布局与输入决定保持。

Reading Note 仍属于 Source，不属于 Reading Chunk、Reading Plan 或 FOCUS Discussion。用户可直接手写，也可从讨论回答预填后确认保存；直接创建不经过 AI，不进入讨论历史、不推进 Reading Cursor 或生成 Reading Progress Entry。

Attached Notes 只按相同 Parser Bundle 版本及 Source Anchor 行范围重叠投影到当前已加载的 Reading Chunk。每条笔记最多投影一次，优先最大重叠行数，平局取最小段序号。无锚点、旧 Bundle、未加载的笔记仍在资料的笔记页可见。旧版本锚点不能被悄悄重新绑定。

空间足够时原文与旁注并列，保持原文换行不变；不足时在同一阅读段内按正文 3/4、笔记 1/4 并列分栏（2026-10-21 用户后续修订，替代原文后方内联）。关闭吸附只改变展示，仍可直接记笔记。讨论消息始终留在阅读流。功能区开关显示“笔记”，普通窗口与全屏均可打开；按阅读区可用宽度自动选择布局。笔记栏保留“就这段讨论”，只展开输入框并引用该段，不推进 Reading Cursor。吸附偏好属于本地展示状态，不写 Host。

直接创建通过 `POST /library/sources/<sourceId>/notes`，包含稳定 requestId、content、kind（thought/conclusion/question）、origin（user/dialogue）及可选 Plan/Chunk 引用和原文 quote。Host 校验当前讨论来源及 Plan provenance，构建 Source Anchor；Plan Bundle 已变更时返回 note_bundle_changed，用户可选择改存无锚点的整篇笔记。请求由 SourceNotes.save 原子保存，重复请求保持幂等；编辑、删除、撤销和冲突语义复用现有 SourceNotes。

ReaderChunk 的 bundleVersion 是 Plan provenance 的投影；不创建第二份笔记存储。所有入口复用 NoteEditor 与现有 drafts 机制，草稿按 Source/Discussion/Chunk 隔离；关闭、切换来源和刷新不丢失草稿。记笔记不依赖讨论任务是否运行。

资料抽屉不压缩正文，Reading Lens 与 Reading Cursor 继续分离。Host 鉴权、instance 校验、清除讨论与笔记及重新阅读的既有语义保持。

## 验证

直接创建合同、幂等、版本冲突、投影、输入法、草稿、布局和真实 Knowledge Base 副本验收分别由工单 06–11 提供；本 ADR 记录已批准决定，不宣称功能已实现。
