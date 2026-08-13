# FOCUS Paper Companion

FOCUS Paper Companion 是一套项目内学习工作流。它不把“读完论文”当作学习结果，而是把理解拆成一组有依赖关系、可观察、可验证的中间状态：先掌握动作，再让结果水到渠成。

当前 v0.2 先服务论文学习，核心变化是按投入强度分级，而不是让所有论文默认进入完整答辩。

仓库发布的是工作流主体：1 个入口 Skill、3 个内部语义模块、隐藏的确定性状态内核、回归测试以及设计文档。论文原文、解析产物和个人学习记录均保留在本地，不进入版本控制。

## 快速开始

环境要求：已安装 Git、Python 3.11+，并使用支持项目级 `.agents/skills/` 的 Codex。

```powershell
git clone https://github.com/kongxiangcong/focus.git
cd focus
```

把要学习的 PDF 放进项目根目录后，在该项目中用自然语言告诉 Codex：

- `开始学习 A04_FlexSA.pdf`
- `继续学习 FlexSA`
- `我已经懂 systolic array，直接验证我能不能跳过`
- `查看这篇论文的知识树和我的进度`
- `开始闭卷答辩`
- `我刚才哪里理解错了？`

正常学习不需要运行命令，也不需要管理文件。新论文默认先做低成本 Scout；只有用户明确要学习或掌握时才升级。系统每次只给出一个下一步。

## 三种阅读模式

- **Scout**：筛选是否值得投入。只产出来源、概览、关键主张、局限、研究相关性和 `advance / park / reject`，不建完整知识 DAG、不答辩、不创建认知画像。
- **Study**：形成研究可用的理解。只建关键机制图、来源锚点、少量综合检查点和论文级 critique，可到 `provisional` 或 `verified-now`，不要求所有 supporting node 闭卷通过。
- **Mastery**：仅用于少量核心论文。启用完整依赖计划、冻结答辩、补缺、认知证据和延迟复测。

未明确强度时默认 Scout；“学习、精读、比较、批判”进入 Study；“掌握、答辩、复现、教学、长期记住”进入 Mastery。升级会复用已有产物，不删除旧证据。

首次认领论文时，工作流会在本地创建 `knowledge-base/`。PDF、解析正文、图片、状态和学习证据已由 `.gitignore` 排除；请勿手动强制提交这些内容。

## 它怎样工作

1. **解析论文**：先检查 PDF 是否已有可靠文本层；默认在本地解析版面、正文、表格、公式与图示，只有失效区域才进入 OCR。
2. **建立知识树**：从论文主张反推先修概念、机制、证据和边界，建立“树状浏览 + DAG 依赖”学习地图。
3. **一次掌握一个节点**：每轮只推进一个可验证动作，不用聊天长度代表学习进度。
4. **用证据关节点**：即时检查只记为 `provisional`；同日闭卷或迁移记为 `verified-now`；至少 7 天后、跨会话的独立闭卷重构才记为 `retained`。
5. **持续更新认知画像**：用户回答写入追加式证据账本，画像可随时从证据重建，而不是靠长对话记忆。
6. **跨会话继续**：新任务会读取同一知识库，恢复当前节点、未回答问题、薄弱概念和唯一下一步。

## 节点状态

- `planned`：已进入学习计划，尚未开始。
- `learning`：正在学习或等待当前检查点。
- `provisional`：即时检查已通过，可继续后续依赖，但还不能算最终掌握。
- `verified-now`：已通过即时迁移或冻结闭卷，证明当前可独立重构，但尚未证明长期保持。
- `retained`：在不同会话且至少 7 天后通过延迟闭卷重构。
- `needs-remediation`：发现具体误解，需要修复后再验证。
- `skipped`：用户明确跳过，缺口仍保留。
- `stale`：来源或计划变化后，旧证据需要重新确认。

“我懂了”只记录自我报告，不会自动关闭节点。已有基础可以走快速验证路径，但仍须完成无提示重构、边界辨析和迁移。

旧库中的 `mastered` 在迁移时按 `verified-now` 解释，绝不自动升级为 `retained`。

## 一个入口、三个语义模块

- `ask-paper`：唯一普通用户入口；选择模式、恢复状态并给出一个下一动作。
- `paper-map`：来源认领、解析真实性检查、Scout 筛选，以及 Study/Mastery 所需的最小论文模型。
- `paper-study`：关键机制教学、综合检查点、critique 和定向补缺。
- `paper-assess`：即时闭卷、延迟保持、诊断、证据检查和 profile 投影。

这些 Skill 共享一个确定性状态内核。模型负责解释、提问和可审计的语义判断；脚本只负责来源、状态、revision、幂等、原子写入和恢复。route、helper、锁和事务是当前内核的私有兼容细节，不属于 v0.2 Skill 接口。

## 仓库结构

```text
.
├── .agents/skills/                 # ask-paper + 3 个 v0.2 语义模块
│   └── ask-paper/scripts/
│       ├── focus_state.py          # 状态维护入口
│       └── focus_core/             # 确定性状态内核
├── research/                       # 解析器选型与维护证据
├── tests/                          # 状态内核回归测试
├── paper_companion_skill_suit.md   # 完整设计与契约
└── README.md
```

## PDF 解析原则

默认路径是本地 Docling：保留无损结构化 JSON、规范化 Markdown、来源映射、提取图片和质量报告。结构成功不等于真实可读；质量门还检查章节/页面覆盖、figure/table/equation inventory、双栏阅读顺序和抽样 claim-to-span 支持性。像 FlexSA 这样已有文本层的双栏论文不会做整页 OCR。MinerU 是首选质量回退；任何云端解析都必须先获得用户对上传该 PDF 的明确同意。

当前默认路径不需要注册 API。Mathpix 等托管方案仅在本地质量门失败、且用户明确授权上传时才考虑。

## 持久化边界

学习状态位于 `knowledge-base/`：

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

`paper.yaml` 是单篇论文的状态快照；原始回答与 evidence 是权威；`profile.yaml` 只是 UI 投影，不参与路由。投影缺失或损坏时系统自动保留旧文件并重建；失败时降级显示 evidence，不要求用户授权。运行控制记录保存在 `knowledge-base/.paper-companion/`，正常用户无需查看。

这些运行时内容属于本地学习档案，不是可复用程序源码。备份或同步时应自行选择受控的私有位置，并留意其中可能包含论文版权内容和个人学习记录。

## 维护者验证

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
python -B -X utf8 -m unittest discover -s tests -v
```

已有本地学习库时，还可以验证其结构：

```powershell
python -B -X utf8 .agents\skills\ask-paper\scripts\focus_state.py validate --workspace knowledge-base
```

当前规范见 [FOCUS v0.2 risk-tiered architecture](research/focus-v0.2-risk-tiered-architecture.md)；v0.1 内核历史契约见 [paper_companion_skill_suit.md](paper_companion_skill_suit.md)，OCR 取舍与证据见 [research/ocr-tool-evaluation.md](research/ocr-tool-evaluation.md)。

## 当前边界

- 当前仅支持论文学习；博客、教程和一般知识文档尚未接入。
- 默认本地解析路径使用 Docling；MinerU 等后端仍需按环境单独资格化。
- 云端解析必须由用户明确授权，工作流不会默认上传论文。
- `verified-now` 不等于长期保持；只有满足跨会话和 7 天延迟门的 `retained` 才表示保持证据。
- 当前状态内核仍保留 v0.1 route/分账本实现作为兼容层；v0.2 的公开工作流不暴露这些概念，后续只在真实维护收益成立时替换内部实现。
