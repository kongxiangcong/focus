# 02: 统一 Backend 的阅读准备、博客与讨论

Status: ready-for-agent

2026-09-26 按用户要求合并原草稿 02、03、04，保留全部验收范围。本票已发布，尚未实施。

**What to build:** 用户使用任一 Backend，在同一套 FOCUS 中完成 Reading Plan、全文 Reading Preparation、完整 Blog Output、来源讨论、显式 Notes 及阅读推进。所有 AI 业务入口使用同一生效配置和共同 Application／Core；讨论历史与资产不按 Backend 分叉。

**Blocked by:** 01：依赖、认证与双 Backend 连通检查。

本票按阅读准备、博客、讨论三个内部验收段推进，但作为一张票完整交付；任一段未通过都不标记整票完成。三段共享 Backend 入口与公共业务契约，不为合并引入第二套调度或状态。

## Reading Plan 与全文准备

- [ ] 阅读上下文、Plan、翻译与检查使用共同生效配置和候选契约，不再在 Host 启动时永久绑定旧 Backend。
- [ ] 两种 Backend 通过同一 Application／Core 完成全文准备；中文、外文和混合来源遵守现有完整准备规则，准备本身不推进 Cursor。
- [ ] 任务仅取得所需输入和候选能力；不开放任意业务写入，候选结构、原文锚点与版本由共同校验器检查。
- [ ] 已合法 Plan／译文可复用；取消、失败、重启后从合法断点产生新 attempt，迟到结果不能提交或覆盖。
- [ ] 现有 UI 显示真实步骤与失败，缺能力在执行前明确阻止，不用 Codex 暗中补 DeepSeek。
- [ ] 通过公开阅读操作验证两种协议替身及真实 Core；分别运行真实 Runtime 的代表性 Plan／全文准备，并记录浏览器从准备到打开的闭环。
- [ ] 前置业务契约为既有阶段 4 初始化／准备；若基线失败先定位并记录，不在本票重新设计阅读流程。

## 完整 Blog Output

- [ ] 移除固定 Codex 博客运行路径，读取统一生效配置；BlogApplication、Methods、结果格式和校验器保持一套。
- [ ] 完成 Reading Blog、适用时的 Value Analysis 和合并单文件 HTML；图片与引用来自合法来源，无法满足结构条件则不发布。
- [ ] 官方实现检索等业务所需能力通过受限工具完成并留下证据；只有正文生成成功不算博客闭环。
- [ ] 可信 Host 写结构化候选，Core 守卫发布；schema 失败、网络错误、取消和失效 attempt 不破坏已发布资产。
- [ ] 用户在现有来源／处理界面看到生成、失败、取消、重试和成果；不新增 Backend 专属业务界面。
- [ ] 公开业务契约覆盖两个 Runtime 替身；分别完成真实 Runtime 与浏览器博客流程，不以阶段 2D 旧证据替代。
- [ ] 本票不改 Parser 为 Agent Backend，不把入库成功和博客成功合成一个状态。

## 来源讨论与阅读上下文

- [ ] FOCUS 自己持久化 Source 绑定的 Discussion 身份与历史；打开 Source 不启动模型，可恢复最近讨论或新建，不按 Backend 拆分。
- [ ] 保留全部可见历史，统一近期消息、早期摘要和必要来源上下文；压缩不生成 Reading Notes，不复制 Runtime 私有日志为讨论。
- [ ] 新 Runtime 从共同上下文继续，不跨 Backend 传原生 resume key；切回旧 Backend 不返回历史分支，重启后仍能恢复同一讨论。
- [ ] 问答、显式 Notes、Chunk 精读、推进及 Reading Progress Entries 接入统一 Backend；Core 继续唯一决定 Cursor，Notes 仅由明确请求写入。
- [ ] SDK 工具请求、审批、用户输入、流式结束与取消映射到既有公共交互；验证工具越界拒绝、Source 隔离和旧事件不串入新讨论。
- [ ] 公开 Host 操作证明两个适配器依次接续同一讨论，历史和合法资产不变；设置页刷新触发生效由票 03 验收。
- [ ] 分别记录真实 Runtime 的多轮问答／显式 Notes／阅读推进和浏览器证据。使用既有阶段 3／4 公共能力，不复制业务状态。

## Evidence

验收遵循父 spec 的最高公共测试边界。分别记录三个内部验收段在确定性／Host、真实 Runtime 和浏览器层的通过、失败、未测试及阻塞事实；不将替身证据提升为真实 Runtime 或浏览器通过。设置页刷新生效与全路径一致切换由票 03 集成验收。
