# 阅读批注与小段笔记

## Notes

实施依据：[spec.md](spec.md) 与 [issues/](issues/)，交互参照 [prototype.html](prototype.html)。

## Decisions-so-far

- [01 领域与决策文档](issues/01-domain-docs.md#answer)：CONTEXT 定义重点、句子备注、显示位置及清除语义；ADR 0033 记录 U1–U7、D1–D11（0032 已占用）。文档自查通过，尚不宣称功能实现。

- [02 重点与句子备注存储](issues/02-core-highlights-sentence-notes.md#answer)：SourceHighlights 与句子备注共用笔记数据库及清除围栏，旧 schema 兼容迁移；45 项 Core/Host 合成测试通过，请求回执故障注入验证原子回滚，不作为真实 Runtime 验收。

- [07 视觉基础](issues/07-visual-foundation.md#answer)：批注浅深色 token、原型组件样式及两种减少动效规则落地；4 项静态检查与 standalone 生产构建通过。计算样式和截图留待工单 13。

- [03 讨论笔记显示位置](issues/03-dialogue-note-placement.md#answer)：Host 引用无证据锚点时保存 placement，笔记迁移/重放/编辑撤销/版本失效行为通过；65 项回归与真实库副本的受控 Runtime HTTP 验收通过，不宣称外部模型效果。

- [04 Host 标注接口](issues/04-host-highlights-sentence-api.md#answer)：重点 HTTP 创建/删除/撤销/请求查询、句子备注、快照与错误码落地；43 项规定测试和 39 项笔记/讨论回归通过，兼容旧请求 digest，并清除残留操作快照。均为隔离合成 Host/Core 证据。

## Fog

功能与浏览器验收以 [13](issues/13-acceptance.md) 为准。
