# 阅读批注与小段笔记

## Notes

实施依据：[spec.md](spec.md) 与 [issues/](issues/)，交互参照 [prototype.html](prototype.html)。

## Decisions-so-far

- [01 领域与决策文档](issues/01-domain-docs.md#answer)：CONTEXT 定义重点、句子备注、显示位置及清除语义；ADR 0033 记录 U1–U7、D1–D11（0032 已占用）。文档自查通过，尚不宣称功能实现。

- [02 重点与句子备注存储](issues/02-core-highlights-sentence-notes.md#answer)：SourceHighlights 与句子备注共用笔记数据库及清除围栏，旧 schema 兼容迁移；45 项 Core/Host 合成测试通过，请求回执故障注入验证原子回滚，不作为真实 Runtime 验收。

- [07 视觉基础](issues/07-visual-foundation.md#answer)：批注浅深色 token、原型组件样式及两种减少动效规则落地；4 项静态检查与 standalone 生产构建通过。Chrome 1600/390 宽度的控制样式检查通过，修正通用按钮级联与灯泡伪元素命中尺寸（31/43px）；证据见 [07-control-styles.json](evidence/07-control-styles.json)，完整功能与截图矩阵留待工单 13。

- [03 讨论笔记显示位置](issues/03-dialogue-note-placement.md#answer)：Host 引用无证据锚点时保存 placement，笔记迁移/重放/编辑撤销/版本失效行为通过；65 项回归与真实库副本的受控 Runtime HTTP 验收通过，不宣称外部模型效果。

- [04 Host 标注接口](issues/04-host-highlights-sentence-api.md#answer)：重点 HTTP 创建/删除/撤销/请求查询、句子备注、快照与错误码落地；43 项规定测试和 39 项笔记/讨论回归通过，兼容旧请求 digest，并清除残留操作快照。均为隔离合成 Host/Core 证据。

- [05 合同与适配器](issues/05-contracts-adapters.md#answer)：可选标注合同、HTTP/fixture 幂等读写及演示 JSON 落地，9 项适配器和 4 项 CSS 检查及三个 TypeScript 项目检查通过；依赖可标注文本的 seedMarks 辅助函数移至 06，避免循环依赖。

- [06 可标注文本与投影](issues/06-text-offsets-rendering.md#answer)：DOM/HAST 共用 UTF-16 定位、首帧标注渲染与重定位合并、演示 seedMarks 已完成；47 项文本/Markdown/图片/投影测试及 UI/standalone 类型检查与构建通过。ReadingChunk 稳定上报 marks/lost/layer/text，供 08 接入。

- [12 资料栏与清除](issues/12-materials-and-clear.md#answer)：资料栏分组显示句子备注与小段/整篇笔记，编辑回调和清除版本围栏已接入；22 项 UI、4 项 fixture、7 项 Host 检查及三项目类型检查、构建与隔离 Chrome 检查通过。

- [08 批注交互](issues/08-selection-bubble-editor.md#answer)：选区/标注气泡、句下备注编辑与查看、乐观写重试/撤销、持久草稿与清除围栏完成；61 项 UI 测试、类型检查及真实 Chrome A1/A2/A3 与编辑框几何通过。物理 IME 手测仍为 NOT_RUN，留在 13 验证缺口。

- [10 关闭吸附与保存反馈](issues/10-detached-mode.md#answer)：fold 复用共享笔记 CRUD 并保持可访问折叠；讨论保存按投影提示且仅“查看”跳转，明确 null 的无引用回答保存为整篇。73 项 UI 回归、类型检查及真实 Chrome A7/A8/A9 与既有批注预检通过；并修复保存中继续输入导致重复句子备注的边界，提供 11 的 M8 几何事件。

- [09 吸附栏与小段笔记](issues/09-attached-rail.md#answer)：跟随卡片、碰撞下推、段末小段笔记区、堆叠布局及共享 CRUD 已完成；真实 Chrome A5 三视口与 390–1600 宽度附件回归、三项目类型检查和构建通过，最终共享 list/fold 回归 8 项通过。旧 AttachedNotes 展示已替换。

- [11 批注动效](issues/11-motion.md#answer)：保存飞入、吸附开关 FLIP/卡片飞行、删除视觉保留及减少动效/堆叠降级完成；51 项动效/样式测试、UI/standalone 类型检查与构建通过。根分支严格 Chrome 复验通过 A1/A2/A3/A4/A5/A6/A7/A8/A9/A10/A12/A13/A14/A17，三 context 零 pageerror/consoleerror/HTTP 错误，证据待 13 整理。

- [13 浏览器验收与交付](issues/13-acceptance.md#answer)：14 个正式 Chrome 场景及三个旧浏览器回归、360 项 UI/standalone 单元、类型检查与构建通过；A11/A15/A16 单元与 Host 证据、真实库副本脱敏结果、5 张产品截图及原型参照归档于 [delivery.md](delivery.md)。物理 IME 未运行，不以 DOM composition 代替。

## Fog

13 已完成实现及自动化验收，物理中文输入法仍为 NOT_RUN；详见 [交付记录](delivery.md)。独立代码审查与工作树清理由集成任务统一处理。

功能与浏览器验收以 [13](issues/13-acceptance.md) 为准。
