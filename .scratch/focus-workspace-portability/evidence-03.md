# 03 验收证据

日期：2026-10-06。起点：`0138446c6d67329f4a4ef4f4b001442d0681dcfa`，当前分支 `main`。01 和 02 各自在完成票内验收、状态和证据后推进下一票；最终审查产生的跨票修复在本票复验。

## 实现

- 初始化和设置复用同一 Backend 面板。默认 Codex／默认模型，跳过、页面挂载、改选及保存均不发起安装、授权、推理或模型发现。工作区绑定和初始化配置一次原子保存；两个 Backend 的偏好跨库独立保存，返回默认清除手选覆盖。
- 显式检查或首次 AI 使用才准备所选依赖。默认优先使用已安装 SDK 的配套 Runtime，明确失效路径报错而不换路径。基础 requirements 不强制安装两个可选 SDK。
- 最小连接请求不带业务工具和私人来源。首次环境检查使用 Host 发布的默认模型；连接成功后才发现模型，支持独立清单重试。Codex 从实际选定 Runtime 读取，DeepSeek 从供应商目录并按当前 Anthropic Messages 路径能力过滤。
- 检查回执绑定 Backend、实际 Runtime 和认证环境版本、所检模型；更换配置、改选、失败重检和关闭页面使旧结果失效。没有硬编码列表或跨 Backend 清单替代。
- “保存并应用”只在空闲时生效，不强制推理。失败保留原配置，未知响应按 operationId 查询权威状态。切库 POST 同样检查代际，旧页草稿不能再次切库或覆盖机器偏好。
- 新格式工作区在业务写入前预检。损坏 JSON、讨论必需字段和数据库被拒绝且原数据字节不变；原始 MinerU 数组证据保留。SQLite 在临时副本读取 DB＋WAL，兼容未 checkpoint 的崩溃恢复。Core 删除回执的清理范围与所属 Source 绑定，预检和恢复共用规则。

## 确定性与 Host／进程

- `final-task-accepted.txt`：129 项通过，覆盖真实 Application／Core 存储、新格式 CLI、工作区绑定与复制、两后端偏好、默认清除、跳过零动作、最小检查与清单分离、实际 Runtime／认证改变失效、应用失败回滚、忙碌拒绝、Source Notes 幂等、准备和解析。
- 最后删除范围复验 `final-delete-scope.txt`：29 项通过，包含坏回执的六种路径拒绝且资产字节不变、待清理文件解锁后恢复、工作区崩溃接管、旧 Core／Store 实例写入拒绝、活跃 retention 写者保持锁定、合法 MinerU 数组重开、损坏 session 原地拒绝和上传相对引用。
- 运行中的库先取得 OS 排他资格再稳定读取；无锁坏目录在建立锁和业务存储前拒绝。新旧业务 writer 资格由实例租约判定，不复用旧机器 actor 字符串。
- 实际 `python -m host` 在无保存位置时没有业务库；新建后重启直接打开；强制杀进程后的 WAL 接管通过。02 的实际项目复制、中文／空格路径、不同 cwd、缺少可选 Runtime、完整资产和暂停批次剩余步骤证据仍有效。

## 前端与浏览器

- `pnpm reader:typecheck`、`pnpm reader:build` 通过；全前端 115 项通过（reader-ui 46，standalone 69）。本机 Node 25 使用进程级 `NODE_OPTIONS=--no-experimental-webstorage`，避免实验性全局 localStorage 与 jsdom 冲突，不修改项目或系统配置。
- 当前构建＋实际 Chrome：Backend 初始化／设置 12 项，工作区绑定 10 项及失效位置重定位，阅读／Notes／历史前沿／Blog 10 项均通过，页面错误为零。
- 浏览器包括默认零动作、主动授权／取消／确认的协议、检查失败仍默认进入、连接通过但清单失败及独立重试、手选模型不自动验证、独立偏好、一次保存应用、两页配置同步、旧实例业务及切库请求拒绝、中文整库复制导入、窄屏与当前 Mist 交互。
- 目录选择器取消、远端推理、清单与首次授权返回采用受控替身；Host、实际文件系统、Core 存储、Chrome 和页面交互真实。没有把替身协议宣称为真实供应商登录或内容验收。

## 真实 Runtime、内容与恢复

可复核的精简结果：[evidence-03-runtime.json](evidence-03-runtime.json)。运行入口：`tests/workspace_real_journey.py`，没有业务 Runtime 替身；材料是明确标注为分析模型、非硬件实测的合成英文来源。

| 层级 | Codex | DeepSeek |
| --- | --- | --- |
| 依赖解析 | 已有 SDK 配套 Codex 0.154 Runtime | 已有 DeepSeek Harness Runtime |
| 实际认证 | 已有 ChatGPT 登录复用 | Host 从项目配置读取密钥，实际供应商接受 |
| 默认最小请求 | gpt-6-astra 通过 | deepseek-v4-flash 通过 |
| 真实目录 | gpt-6-astra、gpt-5.6-sol、gpt-5.6-terra、gpt-5.6-luna、gpt-5.5 | deepseek-flash、deepseek-v4-pro |
| 明确手选及重检 | gpt-5.6-sol 通过 | deepseek-flash 通过 |
| 阅读准备与打开 | 3／3 翻译 ready；实际打开有译文 | 3／3 翻译 ready；实际打开有译文 |
| 讨论与 Notes | completed，明确意图提交一条笔记 | completed，明确意图提交一条笔记 |
| Blog | 价值分析、带读博客、HTML 全部 completed | 价值分析、带读博客、HTML 全部 completed |
| 退出、整库复制、新机器配置导入 | 隐藏原目录后恢复；身份、历史讨论、Notes 保持 | 同左 |
| 剩余阅读及恢复后问题 | 下一 chunk 推进，原讨论身份保留，实际续问 completed | 同左 |

- Codex 发布默认仍为 gpt-6-astra。其第一次完整旅程出现翻译超时，保留失败记录；最终从实际目录明确选择 gpt-5.6-sol 完成旅程，不是程序静默换模型。默认最小请求另行通过，不宣称默认模型的完整旅程已通过。
- 旧全局 CLI 0.130 无法解析本机已有 service_tier 配置；最终使用已有 SDK 的兼容 Runtime，未改个人 Codex 配置、登录或凭据。初始与最终真实结果分别保留在 tmp/workspace-portability。
- 初次合成材料过短导致 Blog 不适用，初版脚本过宽的成功判定已修正为必须完成 Notes、Blog 和剩余阅读。最终材料明确适用性能建模，两后端实际完整产物状态和恢复均通过；不宣称硬件测量或全部模型已验证。
- **未测**：真实首次账号授权、现场下载／安装缺失 Runtime；使用已有认证和已有依赖。首次授权／取消／过期与安装失败重试由确定性协议验收，Chrome 的首次授权交互使用受控返回。规格明确允许将未执行的真实登录／安装场景单列未测。

## 全量基线与最终审查

- 冻结后的最终完整 Python 测试：435 项，327.773 秒，11 failures、30 errors。41 个失败／子测试身份全部在起点隔离基线中出现，新增失败身份为零；不宣称仓库全绿。完整对照：[evidence-03-baseline.json](evidence-03-baseline.json)。最终日志 `tmp/workspace-portability/final-full-python-frozen.txt`。
- 起点隔离基线 402 项，14 failures、36 errors。隔离副本路径增加了 Windows 路径长度，且方法目录／Git 夹具边界环境不同；9 个基线独有失败不作为本轮修复宣称。对照按精确测试／子测试身份，不宣称每个同名失败的原因完全相同。
- 仍失败的旧阅读 CLI／聊天导航、原版本引用／提示词、旧 reread／check_backend、Blog HTML 及仓库边界契约另列于 JSON。没有为了使这些旧契约全绿重新开放已退休业务接口。与本任务相关的新增格式／锁／上传／配置／恢复失败已修复并按实际公共入口复验。
- 115 项前端全套、类型检查、构建以及 `git diff --cached --check` 均通过。六个原有未提交文档 SHA256 保持不变，未暂存；凭据、个人 Runtime 配置、生成缓存及 tmp 日志未纳入任务提交。

## Standards

规范轴已报告的 Backend 旧验证回执、合法 MinerU 数组误拒均已修复；复审未发现新的已记载规范硬违反。没有把判断性代码气味当作阻断。

## Spec

规格轴的旧切库请求、损坏数据写前拒绝、CLI 格式准入、合法数组、讨论 session 字段、删除回执清理范围均已修复。最后只读复核确认全部关闭，未发现新的具体缺陷。上传引用、retention 等待、Store 实例保护、SQLite WAL 和保存反馈问题也已回归。

最终审查：Standards 未解决 0；Spec 未解决 0；两轴均无未解决的最高优先级问题。
