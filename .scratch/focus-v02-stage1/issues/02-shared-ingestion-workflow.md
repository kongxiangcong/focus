# 02: 完成共享后端入库主流程

What to build: 不依赖浏览器，通过同一 Application 完成 PDF 暂存、确认、解析、Core 发布及 Topic 关联；重复文档复用唯一 Bundle，已发布文档可查看原件和正文，无需 Plan。

Blocked by: 01 — 统一 article-parser，删除旧 paper-parser

Status: resolved

- [x] 将必要上传编排收敛到共享 Application，增量抽取所需 Core／Parser 能力；Host 保持薄装配，现有调用迁入同一实现，不新增第二业务路径。以真实 Core、隔离目录及可控 Parser／Runtime 验证公开操作。
- [x] 暂存 PDF、选择／最小创建 Topic 后可恢复待确认状态；未确认零外发。确认绑定原件、目标、服务和本次仅入库的范围，输入变化拒绝旧确认。
- [x] 新 PDF 经统一 Parser、Core 校验发布后可查询状态并访问原件、正文、图片；无 Plan 也成功，不调用博客、规划或全文准备。模型完成消息不能代替合法产物提交。
- [x] 同原件改名或加入其他 Topic 仍复用同一 Source／Bundle，不重新解析；Topic 关系只保留一处权威，同标题不同原件不误合并。复用不修改原有 Plan、Cursor、Records、Notes。
- [x] Bundle 发布和 Topic 关联分别记录结果；关联失败保留并可访问已发布 Source，返回关联待恢复，不回滚有效文档或要求重新解析。后续续接动作由 03 完成。
- [x] 从首次正式写入起校验预期版本、请求 ID 与有效独占写入方；重复请求返回已有结果，版本冲突保留候选且不覆盖，第二写入方被拒绝。建立本业务所需 Run／Step／attempt 与结果持久化，供 03 续接使用，不另建通用引擎。
- [x] 替换“无 Plan 不得上传成功”的过期行为断言，保留有效阅读回归。必要认证、资源访问与凭据处理沿用既有有效约束，不把新写入路径暴露为无保护入口。

Verification: 从 Application 主接口演示新文档成功、重复文档跨 Topic 复用、无效候选拒绝与提交冲突；只测试可观察行为。必要 Host 适配可更新，但此票不建设新网页，不开启尚未完成续接／取消约束的真实工作流。

Spec coverage: T01–T08、T19–T23 的后端主路径；T09 的分步结果，T14 的持久提交基础。恢复、进程边界和浏览器证据由 03／04 完成。

## Answer

新增持久化 `IngestionApplication` 作为单篇 Inbox／确认／入库的唯一编排边界，并由 `IngestionCore` 执行候选校验、预期版本、请求幂等和独占写入方约束。MinerU 只生成候选；Source 发布与 Topic 关联分成两个 Core 提交。Host 新增薄方法调用同一 Application，不再需要模型复制 Parser 脚本序列。

验证：Application 7 项通过，覆盖未确认零外发、刷新恢复、确认失效、合法无 Plan 发布、跨 Topic 原件复用、无效候选、关联失败保留 Source、版本冲突候选保留、第二写入方拒绝、Host 薄接入；连同 Parser／Host／进度相关回归共 36 项通过。续接、取消和真实服务留待 03。
