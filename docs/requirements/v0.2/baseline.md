# 当前基线与差距

核查日期：2026-09-21；本地 HEAD：`1de307f51c9bd674b8c7efc053e57e5e5b777276`。这是源码和离线测试快照，未启动新 Host、调用远端模型／MinerU、迁移私人数据或验证 DSH。

开始时存在未跟踪的 `.focus-runtime/` 和总计划文件；本轮仅新增需求文档，保留二者。真实 workspace 的资料数量、内容和可迁移性没有在本轮盘点。

## 可复用实现与具体缺口

| 当前证据 | 可复用内容 | v0.2 差距及承接阶段 |
| --- | --- | --- |
| [SourceLibrary](../../../.agents/core/source_library.py)、[ADR 0003](../../adr/0003-use-one-source-library-for-ordered-topic-reading.md) | 单份 Source、多专题引用、稳定身份、原件复用 | Inbox 和 Bundle 版本化提交尚需落地；阶段 1、5（管理） |
| [HostService](../../../host/service.py) 的 `library_upload`／`_verify_library_task` | PDF、HTML、Markdown 路由，上传产物核验、重试复用 | 成功仍依赖 Plan 和全文准备；阶段 1 移除新入库链上的该门槛 |
| [Core](../../../.agents/core/reading_workspace.py)、[CoreBridge](../../../host/core_bridge.py) | 原文范围读取、搜索、缓存、游标回执 | `read_source_range` 已可显式指定 Source；搜索仍依赖当前 Source，`append_note` 强制当前 Plan／Chunk；阶段 3 才形成独立备注 |
| [article-blog](../../../methods/article-blog/SKILL.md) 及其方法副本 | PDF 证据地图、写作准则、渲染／校验脚本，与阅读资产隔离 | 明确拒绝 HTML；不是已贯通的网页博客 Application；阶段 2、5（输入格式） |
| [ADR 0010](../../adr/0010-prepare-reading-before-opening.md)、[prepared-reading 测试](../../../tests/test_prepared_reading.py) | 逐 Chunk 保存、缺失恢复、中文不重复翻译、重读保留资产 | 当前必须全 Plan 就绪才能打开／继续；阶段 4 改为目标 Chunk 按需准备 |
| [后端契约](../../../host/backends/base.py)、[ADR 0007](../../adr/0007-selectable-agent-backends.md) | Session、事件、工具、停止、空闲切换与会话隔离 | Codex 是参考候选，须重新预检查；WorkBuddy 当前仍显式不可用；阶段 0、7 |
| [ADR 0004](../../adr/0004-host-agnostic-reader-seam.md)、[HostService](../../../host/service.py) | ReaderHost、HTTP／SSE、Core 权威、现有单写者保护 | 尚无总计划目标 Application／RuntimePort／DSH 原生交付证据；阶段 1 增量抽取，2D 验证 |

Markdown 是当前明确的本地导入能力，可作离线回归材料；不能据此替代 v0.2 必需的 PDF／HTML 真实解析出口。首阶段建议 PDF，是为了复用已存在的解析及 article-blog 衔接；仍需阶段 0 验证参考环境可用性。

## 必须显式处理的既有决策

| 现行约定 | 与 v0.2 的差异 | 收敛时点 |
| --- | --- | --- |
| ADR 0003：直接调用 Parser 即授权；ADR 0008／0009：上传后立即处理并规划 | Inbox 放入文件本身不授权外发，需绑定明确确认；新入库不创建 Plan | 阶段 1 区分直接工具调用与新版 Inbox 入口的授权边界 |
| ADR 0010：全 Plan 译文准备好才成功／阅读 | 仅进入精读才规划，目标 Chunk 按需翻译 | 阶段 1 替代上传部分；阶段 4 替代打开／推进部分 |
| 原 CONTEXT／ADR 0001：Notes 属于按 Chunk 隔离的 Record；Blog Output 限 Paper | Source 级独立 Reading Notes；博客支持统一来源 | 阶段 3 grill 已以 ADR-0015 和术语修订区分主动 Source 笔记与被动进度记录，尚非实施声明；博客输入范围由阶段 2、5 处理 |
| ADR 0002／0003 的旧非目标限制版本／收据等资产机制 | 总计划需要 Bundle 版本、业务 Run／Step、attempt 和提交校验 | 阶段 1 仅对所需一致性机制明确替代，避免泛化成事件平台 |
| ADR 0008 删除整个 Source；部分旧重读说明已被 ADR 0010 替代 | 保留当前有效的“重读保留备注”行为，并讨论管理和迁移后的关联完整性 | 阶段 4、5（管理与迁移）；不恢复旧清空备注路径 |

本轮不修改 CONTEXT 或已 accepted 的 ADR；实施阶段通过新决策明确替代范围。总计划优先决定新流程，旧 ADR 用于解释当前代码和识别迁移影响。

## 本轮验证

- Python：`.venv/Scripts/python.exe -B -X utf8 -m unittest discover -s tests -q`，135 项，进程退出码 1，报告 2 failures、2 errors。三个不同测试受影响：技能数量断言；CodeBuddy 缺失 SDK 测试未抛期望错误且清理临时目录报占用；prepared-reading CLI 子进程输出 UTF-8 解码失败。原因未进一步诊断，不能宣称全绿或简单归因于环境。
- UI：进程级设置 `NODE_OPTIONS=--no-experimental-webstorage` 后运行 `pnpm reader:test`，38 项通过（Reader 28、Standalone 10），退出码 0。本轮未重跑 typecheck／build，也未做新浏览器验收。
- 历史 [专题库验收](../../FOCUS_Topic_Library_Acceptance.md) 和 [任务进度验收](../../FOCUS_Task_Progress_Acceptance.md) 提供样例 Host／浏览器证据，也明确未重新完成真实 MinerU 链路；历史计数不能替代以上当前测试。
- 本轮未复验真实服务、图像能力、PDF／HTML 远端解析和 DSH 安装；这些分别进入阶段 0／1／2／5（输入格式）／2D 的验收门槛。

## Grill 第一轮后的调整（2026-09-21）

用户确认 CodeBuddy 不再需要：已从 `tests/test_agent_backends.py` 删除 CodeBuddyAdapterTests、CodeBuddyHostTests 及专用 SDK 替身，保留有效的注册、WorkBuddy 边界与代理测试。运行 `.venv/Scripts/python.exe -B -X utf8 -m unittest discover -s tests -p test_agent_backends.py -q`：10 项通过。未重跑全套；上面的 135 项结果继续作为修改前的历史基线，不代表当前测试数量或当前全套结果。

技能相关旧失败暂存，待本轮开发结束重新运行并刷新；不再对应有效需求的无关失败测试届时删除并说明依据。UTF-8 解码问题仍未归因。详细决定见 [阶段 0 第一轮记录](stage-0-baseline.md)。
