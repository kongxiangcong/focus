import type { ReaderChunk, ReaderSource } from "@focus/reader-contracts";

export const fixtureSource: ReaderSource = {
  sourceId: "quiet-systems-paper",
  title: "Quiet Systems: Designing for Sustained Attention",
  topicId: null,
};

export const fixtureChunks: readonly ReaderChunk[] = [
  {
    sourceId: fixtureSource.sourceId,
    planId: "plan-001",
    chunkId: "chunk-001",
    index: 1,
    total: 3,
    sectionPath: ["Quiet Systems", "Attention"],
    sourceLines: [1, 8],
    sourceMarkdown:
      "## Attention as a limited channel\n\nA reading interface should preserve context without allowing history to compete with the active passage.",
    translation: "阅读界面应当保留上下文，但不能让历史内容与当前段落争夺注意力。",
    images: [],
    relevantGlossary: [{ source: "active passage", translation: "当前段落" }],
    presentationStatus: "presented",
  },
  {
    sourceId: fixtureSource.sourceId,
    planId: "plan-001",
    chunkId: "chunk-002",
    index: 2,
    total: 3,
    sectionPath: ["Quiet Systems", "Continuity"],
    sourceLines: [9, 17],
    sourceMarkdown:
      "## Continuity over replacement\n\nWhen the cursor advances, the previous passage remains spatially legible while the next passage becomes the semantic focus.",
    translation: "游标推进时，旧段落仍保留空间连续性，新段落则成为语义焦点。",
    images: [],
    relevantGlossary: [{ source: "semantic focus", translation: "语义焦点" }],
    presentationStatus: "presented",
  },
  {
    sourceId: fixtureSource.sourceId,
    planId: "plan-001",
    chunkId: "chunk-003",
    index: 3,
    total: 3,
    sectionPath: ["Quiet Systems", "Host independence"],
    sourceLines: [18, 26],
    sourceMarkdown:
      "## The host is replaceable\n\nThe reader depends on a narrow projection and command interface. The host remains responsible for authoritative state and conversation persistence.",
    translation: "Reader 只依赖窄小的投影和命令接口；权威状态与对话持久化仍由宿主负责。",
    images: [],
    relevantGlossary: [{ source: "authoritative state", translation: "权威状态" }],
    presentationStatus: "presented",
  },
];
