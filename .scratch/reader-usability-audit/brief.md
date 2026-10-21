# 实施简报

- Goal：按 spec §1–§6 修复阅读界面 P1–P11，维护 Source 级 Reading Notes。
- Route：Integrate；visual_policy: preserve；Substantial。仅 spec 指定的视觉与 Host 合同变化。
- Authority：上传 spec，优先于旧宽度/讨论吸附决策；其余 ADR 0023/0026/0028 保留。
- Surfaces：生产 /reading 的 Mist、非 Mist 不崩溃；四视口×浅深色。
- Contracts：spec §5；§3.6 授权直接创建笔记，不引入 AI 调用或推进 Cursor。
- Ownership：focus-tokens.css 与 typography.ts；现有 Host、drafts、Markdown renderer。
- Reference：PR #24 feat/article-structure-guide @ 9f183cd；不采用外部主题。
- Acceptance：11 张实时工单；每张红/绿、typecheck/test、相关 build/browser/Python；最终干净构建。
- Open items：当前仓库未附真实 Knowledge Base；正在定位验证环境，合成 fixture 不替代真实数据验收。
