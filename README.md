# FOCUS Paper Companion

FOCUS Paper Companion 是一套项目内学习工作流。它不把“读完论文”当作学习结果，而是把理解拆成一组有依赖关系、可观察、可验证的中间状态：先掌握动作，再让结果水到渠成。

当前版本先服务论文学习，后续可把同一套状态与证据模型迁移到博客、教程和一般知识文档。

仓库发布的是工作流主体：6 个协作 Skill、确定性状态内核、测试以及设计文档。论文原文、解析产物和个人学习记录均保留在本地，不进入版本控制。

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

正常学习不需要运行命令，也不需要管理文件。系统每次只给出一个下一步：一段讲解、一个检查点、一道答辩题，或一个明确的修复决定。

首次认领论文时，工作流会在本地创建 `knowledge-base/`。PDF、解析正文、图片、状态和学习证据已由 `.gitignore` 排除；请勿手动强制提交这些内容。

## 它怎样工作

1. **解析论文**：先检查 PDF 是否已有可靠文本层；默认在本地解析版面、正文、表格、公式与图示，只有失效区域才进入 OCR。
2. **建立知识树**：从论文主张反推先修概念、机制、证据和边界，建立“树状浏览 + DAG 依赖”学习地图。
3. **一次掌握一个节点**：每轮只推进一个可验证动作，不用聊天长度代表学习进度。
4. **用证据关节点**：刚学完后的完整复述只记为 `provisional`；跨情境迁移或冻结的闭卷证明才记为 `mastered`。
5. **持续更新认知画像**：用户回答写入追加式证据账本，画像可随时从证据重建，而不是靠长对话记忆。
6. **跨会话继续**：新任务会读取同一知识库，恢复当前节点、未回答问题、薄弱概念和唯一下一步。

## 节点状态

- `planned`：已进入学习计划，尚未开始。
- `learning`：正在学习或等待当前检查点。
- `provisional`：即时检查已通过，可继续后续依赖，但还不能算最终掌握。
- `mastered`：已通过迁移或闭卷证据。
- `needs-remediation`：发现具体误解，需要修复后再验证。
- `skipped`：用户明确跳过，缺口仍保留。
- `stale`：来源或计划变化后，旧证据需要重新确认。

“我懂了”只记录自我报告，不会自动关闭节点。已有基础可以走快速验证路径，但仍须完成无提示重构、边界辨析和迁移。

## 六个协作 Skill

- `ask-paper`：唯一普通用户入口；恢复状态并选择一个下一动作。
- `paper-ingest`：认领来源，生成可追溯的结构化解析结果并执行质量门。
- `paper-guide`：建立论文模型、主张图、知识地图和依赖计划。
- `paper-reader`：讲解一个节点并运行即时检查点。
- `paper-grill`：冻结范围，进行闭卷答辩、诊断和定向补救。
- `cognitive-profile`：从证据账本重建跨论文认知画像。

这些 Skill 共享一个确定性状态内核。模型负责解释、提问和判定语义质量；脚本负责校验状态、依赖、幂等、原子写入和恢复。

## 仓库结构

```text
.
├── .agents/skills/                 # 6 个项目级 Skill
│   └── ask-paper/scripts/
│       ├── focus_state.py          # 状态维护入口
│       └── focus_core/             # 确定性状态内核
├── research/                       # 解析器选型与维护证据
├── tests/                          # 状态内核回归测试
├── paper_companion_skill_suit.md   # 完整设计与契约
└── README.md
```

## PDF 解析原则

默认路径是本地 Docling：保留无损结构化 JSON、规范化 Markdown、来源映射、提取图片和质量报告。像 FlexSA 这样已有文本层的双栏论文不会做整页 OCR；系统保留原生文本，并针对版面、公式和图示做结构恢复。MinerU 是首选质量回退；任何云端解析都必须先获得用户对上传该 PDF 的明确同意。

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

`paper.yaml` 是单篇论文的状态快照；`evidence.jsonl` 是认知画像的权威证据；`profile.yaml` 是可重建投影。运行中的路由、锁和恢复日志保存在 `knowledge-base/.paper-companion/`，正常用户无需查看。

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

完整设计与契约见 [paper_companion_skill_suit.md](paper_companion_skill_suit.md)，OCR 取舍与证据见 [research/ocr-tool-evaluation.md](research/ocr-tool-evaluation.md)。

## 当前边界

- 当前仅支持论文学习；博客、教程和一般知识文档尚未接入。
- 默认本地解析路径使用 Docling；MinerU 等后端仍需按环境单独资格化。
- 云端解析必须由用户明确授权，工作流不会默认上传论文。
- `mastered` 代表通过迁移或闭卷证据，不等同于看完、听懂或即时复述。
