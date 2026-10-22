---
status: accepted
---

# 阅读批注与小段笔记

2026-10-22：用户批准阅读批注原型；本决定采用实施规格 §2 的用户与实施决定。编号 0032 已用于 PDF parser 选择，本决定使用 0033。

## 背景

阅读时需要在句子旁保留重点和自己的备注，并将整段笔记与句子备注分开。现有讨论中“记一下”产生的笔记若没有证据锚点，就不会显示在引用段旁；强行补证据锚点又会错误声称原文支持。原型提供交互参照，以下决定记录数据归属与已批准差异。

## 决定

U1：阅读批注沿用户批准的原型方向实施，规格列明的差异优先于原型。

U2：针对整个 Reading Chunk 的笔记统一称“小段笔记”，替换原型中的“段全局笔记”及所有相关界面文案。

U3：重点以黄色高亮并将文字加粗至 `font-weight:700`，即使原型没有加粗也遵守这一决定。

U4：吸附栏只为句子备注生成卡片；只有重点的句子不生成卡片。

U5：无论吸附开关如何，备注编辑框始终出现在句子下方；吸附开启时提交后以动画移入右栏卡片位置。

U6：备注与小段笔记均以 Enter 保存、Shift+Enter 换行；输入法组字期间的 Enter 不提交。

U7：关闭吸附时，句子备注以句内灯泡显示，小段笔记折叠为段末“小段笔记 · N”；新保存的小段笔记自动展开。

D1：重点成为独立的 Source 级 Reading Highlight，只记录 Sentence Locator，没有文字内容。备注并入 Reading Note，带 `sentence`，以“句子 + 备注”保存：`content` 是备注文字，`sentence.quote.exact` 是原句。没有内容的重点不能满足 Reading Note 的非空内容契约；备注复用现有编辑、删除、撤销、清除和资料栏笔记机制。句子备注只能由用户在正文直接创建，类型固定为“想法”，编辑只改备注内容。

D2：Reading Highlight 存在同一 `sources/<id>/notes/notes.sqlite3` 的新表 `highlights`，复用请求幂等、撤销槽与清除流程；现有 `notes` 表新增 `sentence` 列，保持清除与重置可在同一事务中完成，不新增资产文件。

D3：Sentence Locator 由 Plan/Chunk、原文或译文显示层、UTF-16 字符区间和 exact/prefix/suffix 引文构成；配合 Parser Bundle 版本与 Chunk 行范围定位。重点在自身记录中保留版本和行范围，句子备注沿用笔记 `anchor` 的版本和行范围。字符区间供快速定位，引文供 Plan 重建或译文变化后重新定位，行范围供跨 Plan 投影。句子原句不能复用 `anchor.quote`：后者必须是 content.md 原文子串，而译文层与渲染文本不满足此条件；`sentence.quote` 是显示定位线索，不是来源证据。

D4：Reading Note 新增可选 Placement（`placement`），只表达显示位置，形状同 Source Anchor 但没有 quote。讨论绑定段落引用而模型未给 `anchor` 时，由 Host 填该段行范围；小段笔记按 `anchor ?? placement` 投影。这样遵守 source-discussion METHOD 不为类比或未解决问题伪造证据锚点的约束，修复“记一下”不显示。

D5：小段笔记是有 `anchor` 或 `placement` 且投影到该段的 Reading Note。“记小段笔记”直接调用带 Chunk 的现有 `createSourceNote`，不经过 AI。

D6：字符区间以 Chunk 渲染后 `.focus-markdown` 内按文档顺序拼接的可标注文本节点计算，排除数学公式、图和标注界面元素；DOM 选区与 hast 渲染使用相同规则并做一致性验证。

D7：一次标注必须处于同一个块级元素（`p/li/h1–h6/td/th/blockquote`）内；同一 Chunk 同一显示层的标注不允许部分重叠，以保持渲染与点击语义明确。

D8：写操作按请求号乐观显示待定状态，Host 成功后用正式记录替换；失败保留草稿并提供重试，不丢失输入。

D9：吸附偏好沿用 `localStorage["focus.attachNotes"]`，属于本地展示状态，不写 Host。

D10：同一句可同时是重点并带备注；一条 Reading Highlight 与一条句子备注区间完全相同时，界面合成一处标注（黄底加粗、红虚线、灯泡）。同一 Chunk 同一层内不允许部分重叠，同一区间最多一条重点和一条句子备注；“标注”只是显示概念，不产生第三种存储记录。

D11：句子备注不进入小段笔记列表，即使其 `anchor` 指向该段。它只通过句内灯泡或右栏卡片呈现；资料栏及任何纯文本消费 Reading Note 的位置均显示“「原句」+ 备注”，避免失去备注语境。

## 与现有决定的关系

本决定取代 [ADR 0031](0031-attached-notes-and-direct-note-entry.md) 中 sticky 笔记列表及关闭吸附后不显示段落笔记的展示部分，改为跟随句子的卡片与关闭吸附后的灯泡、段末折叠行；小段笔记投影来源扩展为 `anchor ?? placement`。直接记笔记仍不经 AI、不进入讨论历史、不推进 Reading Cursor、不生成 Reading Progress Entry，Reading Lens 与 Reading Cursor 分离，讨论消息保留在阅读流中。

遵循 [ADR 0015](0015-separate-explicit-notes-from-reading-progress.md) 的 Source 归属，Reading Highlight 与句子备注都属于 Source，不属于 Topic、Plan 或 Discussion。按 [ADR 0018](0018-confirmed-reader-operation-semantics.md)，Clear Source Discussion and Notes 与 Reset Source Reading 一并清除重点、句子备注及其恢复状态；Fresh Reading Session 保留它们。Host 鉴权与 instance 校验、原有 Cursor/进度语义不变；作者的 `==高亮==` 标记仍按原样式处理。

## 后果

存储增加 `highlights` 表，以及 `notes.placement`、`notes.sentence` 两列和兼容旧数据的迁移。UI 增加可标注文本与句内标注层、选区/标注气泡、编辑框、灯泡和跟随卡片；`AttachedNotes.tsx` 被新的吸附栏与小段笔记组件替换。视觉与动效数值按实施规格 §7 写入 `focus-tokens.css` 与组件样式；减少动效与窄屏堆叠按规格保留可操作的最终状态。

## 验证

实施依据为 [.scratch/reading-annotations/spec.md](../../.scratch/reading-annotations/spec.md) §2、§3、§11；浏览器矩阵、截图与交付记录由[工单 13](../../.scratch/reading-annotations/issues/13-acceptance.md) 提供。本 ADR 不宣称功能已实现。
