# FOCUS v0.2 Stage 6B：统一业务的可选 Agent Backend

Status: ready-for-agent

日期：2026-09-26。依据已确认 Q1–Q23、连通性检查补充、领域词汇及 ADR 0004、0007、0010、0012–0015、0017。主测试边界沿用 Q23 已确认的共同业务契约、真实 Runtime 与浏览器验证；本规格不是实现或验收声明。

## Problem Statement

读者可能拥有 Codex 会员，也可能只能使用 DeepSeek，但应使用同一套 FOCUS 功能、来源、讨论和阅读资产。当前设置选择并未统一覆盖后台 AI：阅读 Runtime 在启动时绑定，博客固定走 Codex，切换还会重置讨论入口。精确版本检查也会阻止用户自行升级 Runtime。

用户需要在设置页完成依赖、认证和连通性检查，明确刷新何时应用配置；遇到失败仍能保存合法成果、切换后接续未完成工作，不能因为 Backend 不同而承担两套业务流程。

## Solution

FOCUS 保持独立应用，Codex App Server 与官方 DeepSeek Harness SDK／Runtime 作为并列适配器。Backend 仅提供 Agent 能力；业务流程、Methods、工具权限、候选校验与 Core 发布只有一套。正式支持要求两种 Backend 覆盖全部已确认 AI 场景，不承诺模型正文相同。

用户在设置页选择 Backend 和已验证模型，检查依赖与认证，主动点击下方的连通性检查。Codex 共用个人 Codex 登录，未登录时提供浏览器授权。首次准备两套依赖，但不自动登录或调用模型；单套安装失败不阻止另一套可用路径。

保存配置不立即切换；空闲时刷新网页应用，Reload 就是刷新。尚未刷新仍可使用旧配置启动任务，右下角常驻差异提示，改回生效值则消失。任务运行时禁止改配置；此时刷新仅恢复页面，任务完成后再次刷新才应用。讨论、Notes、Plan、Cursor 和已完成成果不因切换而复制或重建。

## User Stories

1. As a 读者, I want 选择 Codex 或 DeepSeek, so that 能使用适合自己的账号与服务。
2. As a 读者, I want 两种 Backend 提供相同 FOCUS 功能, so that 不必学习两套流程。
3. As a 读者, I want 在设置页统一选择默认 Backend, so that 问答和后台生成不会暗中用不同服务。
4. As a 读者, I want 配置按本机应用用户保存, so that 切换 Knowledge Base 后不重复配置。
5. As a 读者, I want 首次自动准备两套依赖, so that 无需安装开发工具或克隆仓库。
6. As a 读者, I want 安装结果分别显示并可重试, so that 单套失败不会阻塞另一套。
7. As a 读者, I want 安装阶段不自动登录或调用模型, so that 服务选择由我决定。
8. As a Codex 用户, I want 复用个人 Codex 登录, so that 无需维护第二份认证。
9. As a Codex 用户, I want 未登录时在设置页打开授权浏览器, so that 无需复制令牌或使用 API Key。
10. As a Codex 用户, I want 登录失败或过期有明确提示, so that 可以重新授权。
11. As a 读者, I want 环境 API Key 不覆盖 Codex 登录, so that 认证与计费路径符合选择。
12. As a 读者, I want 选择已验证的默认模型, so that 不必填写任意模型名称。
13. As a 读者, I want 看到 Runtime 实际路径, so that 知道外部升级应作用于哪份安装。
14. As a 读者, I want 指定 Runtime 优先、其次复用本机安装, so that 不会隐式使用另一份旧副本。
15. As a 读者, I want Runtime 不受版本号门槛限制, so that 升级后可以直接尝试运行。
16. As a 读者, I want 实际启动失败显示原因, so that 能自行修复而非被自动降级。
17. As a 读者, I want 主动检查设置页所选 Backend 的连通性, so that 生效前可验证真实请求。
18. As a 读者, I want 连通检查不切换当前 Backend, so that 检查不会影响业务任务。
19. As a 读者, I want 检查显示进行中、成功或失败, so that 知道配置是否完成真实往返。
20. As a 读者, I want 配置变化后旧检查结果失效, so that 不把另一配置的成功当成当前结果。
21. As a 读者, I want 仅在设置页修改 Backend, so that 阅读界面不出现快捷切换。
22. As a 读者, I want 任务运行时禁止修改配置, so that 运行不会混用不同 Backend。
23. As a 读者, I want 保存后刷新网页才生效, so that 切换时机明确。
24. As a 读者, I want 刷新前继续用旧配置工作, so that 不必立即中断操作。
25. As a 读者, I want 配置差异提示常驻右下角, so that 不忘记刷新。
26. As a 读者, I want 改回原配置时提示消失, so that 不被无效刷新要求打扰。
27. As a 读者, I want 运行中刷新保留任务且暂不应用配置, so that 刷新不会取消工作。
28. As a 读者, I want 一个页面应用后其他页面同步, so that 同一 Host 不存在多套生效配置。
29. As a 读者, I want Backend 切换后继续同一 Source 的讨论, so that 不丢失讨论背景。
30. As a 读者, I want 长讨论保留全文并统一压缩模型上下文, so that 接续不受原生会话格式限制。
31. As a 读者, I want 摘要不自动变成 Notes, so that 只有明确请求才保存主动笔记。
32. As a 读者, I want 打开来源不启动模型且可恢复最近讨论或新建讨论, so that 阅读与模型执行分开。
33. As a 读者, I want 两种 Backend 都能生成完整 Plan 和 Reading Preparation, so that 精读能力一致。
34. As a 读者, I want 两种 Backend 都能生成含引用和图片的 Blog Output, so that 切换不降低功能范围。
35. As a 读者, I want 问答、显式 Notes、阅读推进和进度记录共用 Core, so that 只有一份阅读状态。
36. As a 读者, I want 停止批次并切换后重试剩余工作, so that 不重做已完成文档。
37. As a 读者, I want 取消或崩溃后的迟到结果不能提交, so that 旧执行不覆盖新状态。
38. As a 读者, I want 知识库主页 Bundle 卡片提供清除本篇讨论与笔记, so that 管理操作集中在主页。
39. As a 读者, I want 阅读界面不出现清除／删除 Notes 按钮, so that 不在阅读中误操作。
40. As a 读者, I want 清除前明确范围并确认不可撤销, so that 知道全部讨论、摘要、Notes 及恢复副本都会删除。
41. As a 读者, I want 清除保留 Plan、Cursor、博客和 Reading Progress Entries, so that 不重置阅读成果。
42. As a 读者, I want Source 有活动任务时不可清除, so that 不出现删除后迟到恢复内容。
43. As a 读者, I want 详细后台日志终态后只保留七天, so that 日志不会无限累积。
44. As a 读者, I want 失败不自动切换另一付费服务, so that 服务使用符合我的选择。
45. As a 读者, I want Windows x64 干净安装可以完整使用, so that 无需开发环境。
46. As a 后续 Linux 用户, I want FOCUS 不因平台名称拒绝运行, so that 可以自行尝试使用。

## Implementation Decisions

### 唯一业务权威与适配边界

- 延用 Backend 的会话、回合、事件、工具请求、打断和关闭接口；DeepSeek 官方 SDK 的协议差异在适配器内翻译。不增加另一套 Host 编排业务，不为某 Backend 复制业务功能。
- Application 拥有 Run／Step／attempt 与提交资格；Core 唯一发布 Source、Bundle、Blog、Plan、Notes 与 Cursor。SDK 会话不作为业务断点。每个 AI attempt 只有一个模型—工具循环。
- 将启动时固定的阅读 Runtime、固定 Codex 博客路径及其他 AI 入口接到同一生效配置；解析服务保持既有 Parser 路径。复用候选接口和校验器，可信 Host 写候选，Core 守卫提交。
- 审批、用户输入、流式终态与取消复用既有公共交互。按任务限制工具，实测可见与可执行工具；禁止仅以 minimal profile 名称当作隔离证明。缺能力明确阻止，不绕过校验或增加业务分叉。

### 设置、认证与 Runtime

- 应用用户级设置保存在业务 Knowledge Base 之外；Host 区分已保存配置与当前生效配置，浏览器只投影视图。任一页面应用后全部页面同步。切换保留全部业务资产和讨论。
- Backend、模型、Runtime 路径与认证状态分别表示。配置修改及应用与任务准入由 Host 统一协调，不能只禁用 UI 按钮而放过并发请求或批次调度。保存时有任务运行则拒绝。
- 空闲刷新应用保存值；有活动任务或仍在调度的批次时刷新不应用、不取消，显示“任务运行中，完成后请刷新以应用配置”，结束后须再刷新。尚未刷新可继续用旧配置启动工作。
- 差异提示为“配置更改，需要刷新页面”，常驻右下角；依据最终保存值与生效值比较，改回则立即消失。Reload 与手动刷新完全同义，无须重启 Host。
- 首次为两个 Backend 准备依赖，复用已有安装，独立报告和重试失败。只安装，不自动登录／模型请求；未配置 DeepSeek 不阻止可用 Codex，反之亦然。
- Runtime 解析顺序：显式指定、本机已有安装、缺失时安装补齐。显示最终路径；选定路径实际失败时报告，不悄悄尝试另一份。移除 FOCUS 的精确版本要求、白名单与区间门槛；不提供升级入口、降级或自动回退。记录验收时实际版本不产生产品版本限制。
- Codex 共用个人认证，由实际 Runtime 查询账号并管理浏览器 OAuth；FOCUS 不接管令牌刷新，不读取个人聊天，不修改个人模型或工具配置。移除环境 API Key 自动覆盖路径。首次认证未完成、取消或失效均显示真实状态，不将打开浏览器算作成功。
- DeepSeek 凭据由 Host 管理，使用 FOCUS 管理的运行配置，不隐式借用个人 DSH profile；不进入业务资产、浏览器持久化或诊断明文。配置／密钥具体存储实现必须符合该边界。

### 连通性检查

- 选择 Backend 后其下方显示检查入口。使用当前设置选项的配置快照，可检查尚未应用的 Backend；不保存、不应用、不刷新配置，不改变业务 Backend，不取消差异提示。
- 通过所选 SDK／Runtime 完成一个最小模型请求；不附带私人 Source 或讨论、不开放业务写入工具、不追加讨论或资产。仅安装、登录记录或网络可达不等于成功。
- 显示未检查、检查中、成功、失败及脱敏原因。结果关联配置快照，改变相关配置使旧结果失效，迟到结果不覆盖新选择。检查有界结束并释放资源；不强制每次业务执行前手动检查，不自动换 Backend 重试。
- 检查失败与实际业务失败各自报告；连通成功不证明工具、图像、检索或完整业务已通过。

### 统一讨论与恢复

- FOCUS Discussion 固定绑定 Source，有自己的持久身份与历史；不以 Backend 或 Runtime session ID 分组。打开 Source 可恢复最近讨论或显式新建，打开本身不启动模型。
- 保留完整可见历史，统一提供近期对话、早期摘要和必要来源上下文；摘要不是 Notes。切回旧 Backend 不恢复另一条历史分支，不把原生 resume key 跨 Backend 使用。
- 保存讨论与 Runtime 事件分离；旧会话、旧 attempt 和已清除讨论的迟到事件不可重新写回。上下文失效后从合法 FOCUS 上下文重建，不能靠原生会话恢复已删除内容。
- 停止批次、改设置并刷新后，显式恢复／重试用当前配置创建新 attempt；合法成果与已完成步骤复用。刷新不自动重放或恢复批次。单项取消、整批停止及公共故障处理沿用既有 Application 规则。

### 清除与日志

- 清除／删除 Notes 按钮只在知识库主页 Bundle 卡片。Source 有活动任务时禁止清除；确认框说明范围、保留项及不可撤销，Host／Core 再次验证条件。
- 清除该 Source 全部讨论、摘要、Reading Notes 和 Notes 恢复副本，失效关联运行上下文；保留 Source／Bundle、Plan、Cursor、Blog Output 与 Reading Progress Entries。重复请求不得扩大范围，部分失败必须可见且能收敛，不能先显示成功再留旧上下文可恢复。
- 此 Source 级不可撤销操作是对既有单条 Notes 编辑撤销规则的明确限定：普通编辑的恢复机制不能恢复整篇清除内容。
- FOCUS 管理的后台详细执行日志从终态起保留七天，超期自动清理；业务状态、必要提交回执与合法资产保留。SDK 原生日志的停止、释放、归档与删除分别取证，不声明 close 等于删除，不清理个人无关日志。

## Testing Decisions

- 主缝隙为 ReaderHost／Host 公共操作及视图，穿过真实 Application、Core 和持久层，只替换外部 Runtime 或必要外部 Parser。用户已在 Q23 同意这条边界；不新增逐层模拟的大量脆弱测试。
- 好测试断言可观察状态、资产、事件终态与失败恢复；不锁私有方法调用顺序、对象布局或实现细节。低影响文案使用浏览器检查即可。
- 复用现有 Backend 协议替身、HTTP ReaderHost adapter、来源讨论／Notes、阅读准备、博客候选和 Stage 5 批次恢复测试模式。沿用临时知识库与真实 Core 校验；替身通过不代表真实 Runtime 通过。
- 设置矩阵：空闲保存／刷新、保存后用旧配置启动、运行中刷新、结束后再次刷新、改回旧值、多页面同时保存／刷新／启动、多个业务 worker 与批次调度的忙时拒绝。观察 Host 唯一生效配置，无部分切换。
- Runtime 矩阵：显式路径优先、已装复用、缺失安装、部分安装失败、非历史版本也尝试启动、实际协议失败可见、无隐式可执行文件回退。认证检查覆盖共享个人登录、OAuth 成功／取消／失败／失效、Key 不覆盖且无凭据泄露。
- 连通矩阵：两个 Backend 的真实最小请求、未登录、网络错误、额度不足、Runtime 错误、配置变动和迟到结果；检查对资产和当前 Backend 无副作用。
- 业务矩阵：两种 Backend 分别生成 Plan、全文准备、博客与适用 Value Analysis，执行 Source 问答、显式 Notes、Chunk 精读／推进、进度记录；核验来源隔离、图片／引用、结构校验、幂等和权限拒绝。
- 讨论矩阵：Source A/B 隔离、长历史压缩、切换往返连续性、重启恢复、合法 Notes／Cursor 不变、原生会话键隔离；不要求生成措辞相同。
- 恢复矩阵：取消前后提交竞争、流中断、Runtime 崩溃、Host 重启、整批停止后切换再重试、已完成三篇不重做、失效 attempt 迟到不能发布。
- 清除矩阵：入口仅在主页、取消确认不删除、忙时拒绝、全部目标删除、恢复副本不可撤销、关联上下文失效、保留项内容不变、失败可见与重启收敛。日志使用可控时钟验证七天阈值且不触碰资产与个人日志。
- 最终在 Windows x64 干净环境实际安装并分别运行两个 Runtime；真实 PDF、带图 HTML、无图 HTML 和混合批次复用阶段 5 业务样例，浏览器实际完成所有关键动作。已有阶段 5／2D 证据是参照，不替代 6B 接入证据。
- 分开记录确定性、Host、浏览器、真实 Runtime／内容证据；记录当次版本而不建立版本门槛。既存回归失败与未验证项如实列出，不以聊天或连通检查通过宣布发布完成。

## Out of Scope

- 功能实施、计费探针或真实登录不由本次写 spec 自动启动。
- DSH 原生工作台、插件／worker 宿主接管、跨机器部署、删除既有 DSH 代码、旧资产迁移。
- 运行中热切换、逐 Source／步骤路由、后台自动更换付费服务、跨 Runtime 原生会话无损迁移。
- Runtime 版本白名单、强制升级／降级、自动兼容修复、保证任意未来版本兼容。
- Linux 适配和验收本阶段不负责，但不按平台名称主动拒绝运行。
- 以连通成功替代完整能力验收、人工内容审批、宣称两种模型内容质量等价。

## Further Notes

- 前置基线为阶段 1–5 已确认业务及阶段 3／4 的 Notes／阅读语义。阶段 6 已跳过，阶段 2D 的旧集成不作为 SDK 可用证明。正式发布核对阶段 5 稳定出口，不能只按状态标签推断通过。
- 当前代码的聊天切换、阅读启动绑定、博客 Codex 路径、workspace 级设置、环境 Key 登录和精确 Runtime 版本检查均需改变；保持用户已有未提交修改，不覆盖其他阶段工作。
- 官方 SDK 指定外部 Runtime 的方式、完整工具限制、图像／检索、上下文和原生清理能力仍需实测。遇到缺口记录阻塞证据，不暗中换技术路线、放宽验收或让用户决定可查明的技术事实。
- 所有已确认产品规则保持成立。SDK 不足属于未完成技术工作；ready-for-agent 表示规格可执行，不表示能力已被验证。
