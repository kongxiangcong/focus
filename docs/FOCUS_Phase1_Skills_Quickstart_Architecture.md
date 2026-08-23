# FOCUS 第一阶段：Skills 基线与 DSH 接入准备

> 状态：Current baseline
>
> 基线日期：2026-08-23
>
> FOCUS 基线：`kongxiangcong/focus@e8d8a2ad377459810e4b0749baa66cc3dc952bdb`
>
> 下一阶段：在不改变学习语义和本地数据权威的前提下接入 DeepSeek Harness

## 1. 文档目的

第一阶段固定当前 FOCUS v0.2 的产品语义、运行入口、持久化权威和 DSH 接入前置条件。它不是一套替代设计，也不把 FOCUS 改造成只记录阅读位置的分片翻译器。

当前闭环是：

```text
用户从 ask-paper 进入
→ 按意图选择 Scout / Study / Mastery
→ paper-map 建立与模式相称的来源模型
→ paper-study 教学、检查或补缺
→ paper-assess 进行即时或延迟闭卷验证
→ 状态内核提交来源、学习和证据变化
→ 新会话从 knowledge-base 恢复唯一下一动作
```

`paper-parser` 和 `paper2blog` 是独立的论文处理能力：前者生成可复用的解析证据包，后者从该证据包生成可追溯的中文技术博客。二者不代替学习证据，也不自行改变论文的学习状态。

当前用户说明见 [README](../README.md)，完整 v0.2 决策见 [risk-tiered architecture](../research/focus-v0.2-risk-tiered-architecture.md)。

## 2. 产品基线

### 2.1 FOCUS 是证据门控的论文学习工作流

FOCUS 把阅读投入和证明强度分开：

| 模式 | 目的 | 最小产物 | 最高默认结论 |
|---|---|---|---|
| `Scout` | 判断论文是否值得继续投入 | 来源身份、概览、关键主张、局限、研究相关性和去向决策 | `advance / park / reject` |
| `Study` | 建立研究可用的机制理解和批判能力 | 关键机制图、来源锚点、少量综合检查点和论文级 critique | `provisional` 或 `verified-now` |
| `Mastery` | 对少量核心论文建立可防御、可保持的理解 | 完整依赖计划、冻结评估、补缺和延迟复测 | `retained`，前提是满足跨会话七天门槛 |

新论文默认进入 Scout；明确要求学习、比较或批判时进入 Study；明确要求掌握、答辩、复现、教学或长期记忆时进入 Mastery。模式只能在保留既有产物和证据的前提下升级。

### 2.2 证据层级不能被 UI 动作替代

- `provisional`：来源锚定的即时检查通过，只证明当前可继续学习。
- `verified-now`：当前时期内完成无提示重构、迁移或冻结闭卷验证。
- `retained`：在另一个持久化会话中，且距 `verified-now` 至少七天，再次独立闭卷重构成功。
- `needs-remediation`、`skipped` 和 `stale`：分别保留误解、显式跳过和失效证据，不得被完成视图隐藏。

用户说“懂了”“继续”或点击界面按钮只构成自我报告或交互意图。只有符合评估契约的原始回答和判定才能改变证据层级。

### 2.3 Atlas 不属于本阶段运行链路

跨论文 Research Atlas 仍是设计边界，不是当前已实现产品。未来若接入，FOCUS 只向其投影已提交的论文修订；`paper.yaml`、论文局部 Claim、学习状态和掌握证据仍由 FOCUS 持有。Atlas 不创建第二个 Paper 身份，也不复制认知状态。

## 3. 当前能力与入口

### 3.1 普通用户入口

`ask-paper` 是唯一普通用户学习入口，负责：

1. 解析开始、继续、状态、答辩、补缺、复习或诊断意图；
2. 选择最便宜但足以满足意图的阅读模式；
3. 解析 Workspace 和论文；
4. 恢复待回答交互和持久状态；
5. 计算一个下一动作；
6. 将动作委派给一个语义模块；
7. 验证并提交结果；
8. 向用户只呈现目标、进度、为什么是下一步以及一个待办动作。

DSH 可以提供按钮、卡片和会话入口，但不能绕过 `ask-paper` 的路由语义，也不能把三个内部模块暴露成要求普通用户自行编排的生命周期。

### 3.2 内部语义模块

| 模块 | 所有职责 | 明确不拥有 |
|---|---|---|
| `paper-map` | 来源认领、解析真实性检查、Scout 输出、关键主张和 Study/Mastery 所需的最小论文模型 | 学习证据授予、认知投影 |
| `paper-study` | 一个机制教学动作、综合检查点、critique 或定向补缺 | 路由、锁、revision、跨会话恢复 |
| `paper-assess` | 即时闭卷、延迟保持、诊断、证据检查和 profile 投影 | 来源解析、论文地图创建 |

每次只委派一个语义动作。模块不直接操作路由文件、锁、事务或分账本；这些是状态内核的私有实现。

### 3.3 论文处理能力

| 能力 | 输入 | 输出 | 安全边界 |
|---|---|---|---|
| `paper-parser` | 用户明确授权上传的 PDF | `source.pdf`、`paper.md`、`images/`、`metadata.json`、`raw/mineru/`、`validation.json` | 只使用 MinerU 托管精准解析 API；Token 仅来自环境变量；结构通过不等于语义真实 |
| `paper2blog` | 已验证的 parser bundle | Evidence Map、`blog.md` 和本地 assets | 必须区分作者主张、论文证据和解释者推断；不写回学习证据 |

## 4. 当前实现边界

### 4.1 仓库结构

```text
focus/
├── .agents/skills/
│   ├── ask-paper/
│   │   ├── SKILL.md
│   │   ├── references/
│   │   └── scripts/
│   │       ├── focus_state.py
│   │       └── focus_core/
│   ├── paper-map/
│   ├── paper-study/
│   ├── paper-assess/
│   ├── paper-parser/
│   └── paper2blog/
├── research/
├── tests/
├── CONTEXT.md
├── README.md
└── paper_companion_skill_suit.md
```

当前仓库没有 `src/focus/` 应用包、`pyproject.toml`、专题目录、分片阅读计划或独立的 `paper-read`/`paper-explain` Skill。后续方案不得把这些尚未实现的对象描述成第一阶段既有能力。

### 4.2 状态服务接口

`.agents/skills/ask-paper/scripts/focus_state.py` 是当前确定性状态入口。公开给工作流的语义操作是：

```text
resolve
inspect
next
commit --route-id <id> --event <json-or-yaml>
cancel-route
migrate-paper
validate
rebuild-profile
repair-lock
```

`resolve`、`inspect` 和 `validate` 用于发现与诊断；`next` 计算一个动作；`commit` 提交模型或用户刚刚产生的语义结果。`route-id`、锁、事务记录和物理账本拆分是兼容内核的私有数据，不是 DSH、Skill 或用户需要编排的接口。

DSH 接入前可以在这个入口外增加稳定 JSON adapter，但不得另建一套能独立修改 `paper.yaml` 或 evidence 的状态服务。

## 5. 持久化权威

```text
knowledge-base/
├── workspace.yaml
├── reading-registry.yaml
├── cognitive-profile/
│   ├── evidence.jsonl
│   └── profile.yaml
└── research-corpus/<paper-directory>/
    ├── source.pdf
    ├── paper.md
    ├── images/
    ├── metadata.json
    ├── paper.yaml
    ├── ingest/
    ├── guide/
    ├── reading/
    ├── assessment/
    └── notes/
```

权威关系如下：

| 数据 | 权威 | 说明 |
|---|---|---|
| PDF、解析正文、图片和 source map | 对应不可变来源文件 | 来源变化必须保留旧版本并使受影响证据失效 |
| 论文路由和状态快照 | `paper.yaml` | 单篇论文的当前状态权威 |
| 用户原始回答和评估记录 | 追加式原始记录 | 不因投影或 UI 重建而改写 |
| 学习证据 | evidence ledger | 证据状态的事实来源 |
| `profile.yaml` | 可丢弃投影 | 可从 evidence 重建；损坏不得阻塞学习 |
| route、lock、revision 和 transaction | 状态服务私有控制数据 | 只用于并发、幂等和恢复 |

所有 `knowledge-base/` 内容均是本地论文资产和个人学习记录，保持 Git 忽略。DSH Session Log 未来只保存会话与呈现事实，不能取代上述权威。

## 6. 跨会话与恢复约束

1. 新会话先读取持久状态，不从聊天内容猜测当前节点。
2. 已存在待回答问题时，优先恢复该问题的所有者和原提示，不计算新的学习单元。
3. 任何等待用户的交互必须先持久化 owner、operation、prompt ID、目标节点、revision 和 artifact reference。
4. route 和文件锁不能跨用户等待或模型等待持有。
5. event ID 必须唯一，重复提交只接受相同 payload。
6. revision 冲突、来源哈希变化、未来 schema、无效引用和无法确认的锁所有者均明确阻塞。
7. `profile.yaml` 缺失或损坏时保留旧文件并自动重建；重建失败则展示 evidence 派生摘要，而不是中止学习。

## 7. DSH 接入前的最小准备

### P0：冻结语义基线

- 保留 `ask-paper`、Scout/Study/Mastery 和三层证据语义；
- 保留 `paper.yaml` 与 evidence 的权威关系；
- 记录当前 FOCUS commit 和状态 schema；
- 通过现有状态内核回归测试。

### P1：稳定机器接口

- 为 `resolve / inspect / next / commit / validate` 定义版本化 JSON request/response；
- stdout 只输出协议数据，诊断写入 stderr；
- 定义超时、进程退出、无效 JSON、revision 冲突和恢复错误；
- 对输入/输出中的绝对路径、Token 和用户回答制定最小披露规则。

### P2：形成无 DSH 的真实验收样本

至少用一篇真实论文验证：

- Scout 从认领到去向决策；
- Study 的关键机制、来源锚点和综合检查点；
- Mastery 的冻结验证与补缺路径；
- 新会话恢复待回答交互；
- profile 损坏后的 evidence 重建；
- parser bundle 到 `paper-map` 的解析真实性检查；
- `paper2blog` 不改变论文学习状态。

延迟七天的 `retained` 只能由真实跨会话时间证据验收，不能用同日夹具冒充完成。

### P3：定义 DSH 能力映射

| FOCUS 需要 | DSH 承载 | FOCUS 仍拥有 |
|---|---|---|
| 用户入口 | Web 页面、命令或会话 action | 意图分类和模式选择 |
| 一个下一动作 | Agent Preset 和模型轮次 | `next` 计算结果及其提交条件 |
| 待回答交互 | Session 呈现和恢复入口 | pending interaction 记录 |
| 状态/知识树 | Client 投影视图 | `paper.yaml` 和 evidence |
| 分支解释 | Session fork | 解释本身不是学习证据 |
| PDF 图片 | durable attachment 呈现 | 原始图片和来源关系 |

## 8. 测试基线

当前维护者回归命令：

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
python -B -X utf8 -m unittest discover -s tests -v
```

存在本地学习库时，再运行：

```powershell
python -B -X utf8 .agents\skills\ask-paper\scripts\focus_state.py validate --workspace knowledge-base
```

DSH 接入准备新增的 adapter 测试必须覆盖：协议版本、UTF-8、错误输出隔离、超时、幂等提交、revision 冲突、未来 schema、profile fail-soft 和日志脱敏。它们补充而不是替代当前状态回归测试。

## 9. 明确不做

- 不停用 `ask-paper`；
- 不把 `paper-map`、`paper-study`、`paper-assess` 改成普通用户需要手工串联的入口；
- 不用“理解并继续”直接授予 `provisional`、`verified-now` 或 `retained`；
- 不引入另一套 `reading/plan.yaml`、`chunks.jsonl`、`progress.yaml` 或事件账本与当前学习状态并行；
- 不把 DSH Session Log 设为论文状态或学习证据权威；
- 不把 `profile.yaml` 反向升级成路由输入；
- 不自动上传 PDF，不把 MinerU Token 写入 Session、命令行或产物；
- 不把设计中的 Research Atlas 描述成已实现能力；
- 不迁移到 TypeScript 后再保留一套可写 Python 兼容核心。

## 10. 第一阶段完成标准

第一阶段可作为 DSH 迁移基线，当且仅当：

1. 文档、Skills 和状态内核对 Scout/Study/Mastery 的定义一致；
2. `ask-paper` 仍是唯一普通用户学习入口；
3. 三个语义模块一次只处理一个由状态服务导出的动作；
4. `paper.yaml`、原始回答、evidence 和 profile 的权威关系明确；
5. 所有等待用户的动作均可跨新会话恢复；
6. route、锁和事务不跨用户等待；
7. parser 的云端授权、Token 和真实性检查边界保持；
8. `paper2blog` 与学习状态相互独立；
9. 现有回归测试通过；
10. DSH adapter 只调用状态服务，不直接写本地学习文件。

## 11. 基线来源

- [README](../README.md)：当前产品入口、模式、状态和持久化说明；
- [CONTEXT](../CONTEXT.md)：FOCUS 领域术语；
- [ask-paper Skill](../.agents/skills/ask-paper/SKILL.md)：普通用户入口和语义路由；
- [artifact contracts](../.agents/skills/ask-paper/references/artifact-contracts.md)：文件权威、事件和投影；
- [state machine](../.agents/skills/ask-paper/references/state-machine.md)：恢复、证据和状态转移；
- [paper-parser Skill](../.agents/skills/paper-parser/SKILL.md)：MinerU 解析边界；
- [paper2blog Skill](../.agents/skills/paper2blog/SKILL.md)：论文解释导出边界；
- [FOCUS v0.2 architecture](../research/focus-v0.2-risk-tiered-architecture.md)：风险分级工作流决策。
