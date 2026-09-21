# 01: 统一 article-parser，删除旧 paper-parser

What to build: 用户通过唯一 article-parser 入口将 PDF 解析为规范 Parser Bundle；复用现有解析能力，保留已有 HTML 能力，删除旧 paper-parser Skill 和废弃入口。解析不创建 Reading Plan，也不触发全文准备。

Blocked by: None (can start immediately)

Status: resolved

- [x] 重写统一 Skill，覆盖 Parse／Normalize／Metadata／Compose／Export；迁入可复用 PDF 实现，PDF 与已有 HTML 路径共用统一方法入口，不保留 paper-parser 改名兼容壳。
- [x] Host 解析路由与 Skill 装配、Core 的格式／解析器校验、产物标识和相关消费方同步适配新入口。博客输入检查能识别新 PDF Bundle；不在此实现新的博客编排或 article-blog 产品功能。
- [x] 通过新入口产出字节一致 PDF 原件、非空正文、有效图片引用和可解析元数据，Bundle 验证通过；未知信息不编造，Source 类型仍区分 Paper Source 与 Article Source，不因 Skill 统一而混淆来源类型。
- [x] Parser 候选生成、断点引用与正式安装有可复用的明确职责；直接 Skill 调用的正式注册仍经过 Core，后续 Application 能调用相同实现，不必让模型重新执行一套脚本编排。
- [x] 移除新入库方法中的规划／全文准备指令，完成结果没有 Plan，也不推进或改变现有阅读状态。
- [x] 更新与替换相关有效测试及文档；复用现有 Parser 案例验证 PDF、原件复用及已有 HTML 路径，不恢复废弃技能数量断言。旧私人 Bundle 的历史 provenance 和资产不批量改写，删除的是旧入口和实现残留，不是历史证据。

Verification: 以统一 Parser 的公开操作验证合法产物、原件复用与已有 HTML 基础行为，使用隔离目录。真实服务全流程验收归 03；此票不要求新增前端，也不声称新 Application 已完成。

Spec coverage: 统一 Parser 修正；T05 的 Parser 产物校验部分、T22 的方法规则部分。其余行为在后续票覆盖。

## Answer

唯一公开 `article-parser parse-file` 已按 PDF／HTML 格式调用同一入口，PDF 复用成熟 MinerU 传输和规范化实现；Core、Host、paper2blog 与文档均改认 `article-parser` provenance，旧 `paper-parser` Skill、脚本入口及数量断言已删除。公开操作仍由 Core 原子安装合法候选，不创建 Reading Plan 或全文准备。

验证：`PYTHONPATH=tests;.` 下相关 Python 回归 55 项通过，覆盖 PDF 原件字节一致、图片引用、断点恢复、重命名复用、HTML 既有行为、Blog 输入与阅读资产回归。真实 MinerU 留待 03。
