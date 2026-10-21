# FOCUS 当前设计入口

本索引按当前分支已接受的决策组织设计文档（更新：2026-10-21）。它说明实施时查哪份规范，不宣称所有设计已完成或浏览器验收通过；验证状态看各验收记录。用户当前任务的明确变更优先于本文列出的旧条款。

## 按修改范围选择规范

| 范围 | 当前入口 | 适用及替代关系 |
|---|---|---|
| 工作台总体布局、设置、共用视觉基础 | [CDS 设计规范](FOCUS_UI_CDS2_DESIGN_SPEC.md) §4–§12 + [ADR 0025](../adr/0025-cds-focus-presentation.md) | 作为基础；以下专项决策在各自范围内覆盖它，旧颜色、动效和 Composer 规则不能直接套回 |
| 阅读镜头、按需图片、讨论吸附、阅读主题与动效 | [阅读重设计](FOCUS_READING_REDESIGN_SPEC.md) + [ADR 0026](../adr/0026-reading-lens-on-demand-figures.md) | 覆盖 ADR 0025 对应的阅读视觉、图片自动展开和相关动效条款；领域 Reading Cursor 不由镜头控制 |
| 阅读功能行、输入框、发送与收起 | [ADR 0028](../adr/0028-reading-dock-ghost-controls-and-inline-send.md) | 覆盖旧边框控件、Chin 下沿和分离的收起按钮；按此处的 ghost 控件与行内发送执行 |
| 知识库列表、卡片、来源详情面板 | [知识库重设计](FOCUS_LIBRARY_REDESIGN_SPEC.md) 方向 A + [ADR 0027](../adr/0027-library-list-and-details-panel.md) | 覆盖 CDS §5.2 的行内／卡片内详情展开 |
| 中文文章结构、导读及知识库预览 | [ADR 0030](../adr/0030-shared-chinese-article-overview.md) | 两入口共用派生资产；生成和预览与正式阅读进度分离 |
| 吸附笔记与直接记笔记 | [ADR 0031](../adr/0031-attached-notes-and-direct-note-entry.md) | 取代 ADR 0026 中 Discussion attachment；当前 spec 定义四挡行宽与抽屉平移，其余旧决定保留 |
| 宽度、亮度、小屏导航、完成后全文和导航提示 | [阅读控制补充](reading-controls-update.md) | 2026-10-21 用户明确修改，覆盖旧设置位置、亮度保留及已完成后的继续按钮条款 |
| 业务操作、数据与恢复 | [CONTEXT](../../CONTEXT.md) + [ADR 0018](../adr/0018-confirmed-reader-operation-semantics.md) 及相关领域 ADR | 视觉重设计本身不授权改写业务契约；ADR 0018 已补充完成后全文规则 |

实施数值统一从 [focus-tokens.css](../../ui/packages/reader-ui/src/focus-tokens.css) 读取。规范表达目标；现有 CSS 表达实现。二者冲突时先依据上述范围与明确的后续决策定位原因，不能用实现覆盖已接受目标，也不能恢复已被替代的规范值。新决策更新对应 ADR／补充说明及本索引，避免按文件名或日期猜测优先级。

## 验证记录与历史材料

- [阅读重设计验收](reading-redesign-acceptance.md)、[功能行验证](reading-dock-polish-validation.md)、[知识库验收](library-redesign-acceptance.md)、[文章结构验收](article-overview-acceptance.md)：各自范围的实施与证据记录，不是新的视觉权威。
- [focus-cds-ui.md](focus-cds-ui.md)：2026-10-18 迁移记录；其中的旧配色、段落、资料和 Composer 描述已由上述专项决策部分替代。
- [focus-reader-ui-spec.md](focus-reader-ui-spec.md)：历史统一流规范，已在文件内标明被 ADR 0008 替代；仍适用的渲染／领域能力由当前代码、CONTEXT 和相关 ADR 核对，不从中恢复历史外观。
- `focus-reader-current-session-prototype.md`、`focus-reader-design-verdict.md`、`FOCUS_LIBRARY_REDESIGN_PROMPTS.md`：原型、评议或执行提示材料；有已接受规范时按表中入口执行。
