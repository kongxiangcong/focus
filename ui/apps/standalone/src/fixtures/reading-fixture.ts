import type { ReaderChunk, ReaderSource } from "@focus/reader-contracts";

export const fixtureSource: ReaderSource = {
  sourceId: "quiet-systems-article",
  title: "安静系统：为持续注意力而设计",
  topicId: null,
};

export const fixtureChunks: readonly ReaderChunk[] = [
  {
    sourceId: fixtureSource.sourceId,
    planId: "plan-001",
    chunkId: "chunk-001",
    index: 1,
    total: 4,
    sectionPath: ["安静系统", "注意力"],
    sourceLines: [1, 8],
    sourceMarkdown:
      "阅读界面需要保留上下文，但历史内容不能与当前段落争夺注意力。当前段落应当拥有完整对比度，刚刚读过的内容则作为仍可回看的尾迹留在上方。",
    translation: null,
    images: [],
    relevantGlossary: [],
    presentationStatus: "source-ready",
  },
  {
    sourceId: fixtureSource.sourceId,
    planId: "plan-001",
    chunkId: "chunk-002",
    index: 2,
    total: 4,
    sectionPath: ["安静系统", "连续性"],
    sourceLines: [9, 17],
    sourceMarkdown:
      "当 Reading Cursor 推进时，上一段仍应保持空间上的连续，新段落再成为语义焦点。读者看到的是一次接力，而不是原文突然被另一块内容替换。",
    translation: null,
    images: [],
    relevantGlossary: [],
    presentationStatus: "source-ready",
  },
  {
    sourceId: fixtureSource.sourceId,
    planId: "plan-001",
    chunkId: "chunk-003",
    index: 3,
    total: 4,
    sectionPath: ["安静系统", "宿主独立"],
    sourceLines: [18, 26],
    sourceMarkdown:
      "Reader Module 只依赖窄小的 ReaderHost Interface。权威 Reading Cursor、对话持久化与来源数据仍由宿主负责，阅读界面不创建另一套状态权威。",
    translation: null,
    images: [],
    relevantGlossary: [],
    presentationStatus: "source-ready",
  },
  {
    sourceId: fixtureSource.sourceId,
    planId: "plan-001",
    chunkId: "chunk-004",
    index: 4,
    total: 4,
    sectionPath: ["安静系统", "私人阅读"],
    sourceLines: [27, 34],
    sourceMarkdown:
      "正式路径最终必须由真实 ReaderHost 投影用户选择的 Reading Source。Fixture Adapter 只负责开发与测试，不能代替真实 Workspace、重载恢复和操作链路的验收。",
    translation: null,
    images: [],
    relevantGlossary: [],
    presentationStatus: "source-ready",
  },
];
