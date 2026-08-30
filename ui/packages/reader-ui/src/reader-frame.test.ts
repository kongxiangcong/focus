import { type ReadingWindow } from "@focus/reader-contracts";
import { describe, expect, it } from "vitest";

import { projectReaderFrame } from "./reader-frame";

const current = {
  sourceId: "source",
  planId: "plan",
  chunkId: "chunk-001",
  index: 1,
  total: 2,
  sectionPath: ["Source", "One"],
  sourceLines: [1, 2] as const,
  sourceMarkdown: "One",
  translation: null,
  images: [],
  relevantGlossary: [],
  presentationStatus: "source-ready" as const,
};

const settled: ReadingWindow = {
  status: "reading",
  source: { sourceId: "source", title: "Source", topicId: null },
  current,
  history: [],
  conversation: [],
};

describe("projectReaderFrame", () => {
  it("projects the target host history without synthesizing a second history", () => {
    const target: ReadingWindow = {
      ...settled,
      current: { ...current, chunkId: "chunk-002", index: 2 },
      history: [{ ...current, sourceMarkdown: "Host-corrected One" }],
    };

    const frame = projectReaderFrame(settled, { target, active: false });

    expect(frame.history).toBe(target.history);
    expect(frame.history[0]?.sourceMarkdown).toBe("Host-corrected One");
    expect(frame.settlingChunkId).toBe("chunk-001");
    expect(frame.enteringCurrent).toBe(true);
  });
});
