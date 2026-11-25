import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { readerSuccess, type ReaderHost, type ReadingWindow, type ValidatedAnswerEvidence } from "@focus/reader-contracts";
import { ConversationReader } from "./ConversationReader";

const evidence: ValidatedAnswerEvidence = {
  evidenceId: "a".repeat(24), sourceId: "paper", bundleVersion: "bundle",
  messageId: "answer", answerRevision: "r1", discussionId: "discussion", displayNumber: 1,
  layoutVersion: "old-layout", pdfRegions: [{ pageIndex: 11, pageNumber: 12, bboxes: [], granularity: "page" }],
  sourceLines: [5, 5], quote: { exact: "x^2", prefix: "\\[", suffix: "\\]" },
  renderGranularity: "block", relation: "supports",
};
const window: ReadingWindow = {
  status: "empty", source: { sourceId: "paper", title: "Paper", topicId: null },
  current: null, history: [], sessionId: "session", discussionId: "discussion",
  conversation: [{ messageId: "answer", chunkId: "", role: "assistant", answerRevision: "r1",
    content: `The example follows [[e:${evidence.evidenceId}]].`, evidence: [evidence] }],
};

beforeEach(() => {
  localStorage.clear();
  HTMLElement.prototype.scrollIntoView = vi.fn();
  HTMLElement.prototype.scrollTo = function (options?: ScrollToOptions | number) {
    this.scrollTop = typeof options === "object" ? options.top ?? 0 : 0;
  };
  vi.spyOn(HTMLElement.prototype, "clientHeight", "get").mockReturnValue(400);
  vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockImplementation(function (this: HTMLElement) {
    const top = this.dataset.sourceLine === "5" ? 700 : 0;
    return new DOMRect(0, top, 400, top ? 50 : 400);
  });
});
afterEach(() => { cleanup(); vi.restoreAllMocks(); });

it.each([12, undefined])("locates a verified formula in the source and uses reliable PDF page metadata (%s)", async page => {
  const host: ReaderHost = {
    getReadingWindow: async () => readerSuccess(window),
    getSourceDocument: async () => readerSuccess({
      sourceId: "paper", title: "Paper", bundleVersion: "bundle", lineCount: 7,
      markdown: "# Method\n\nRead the formulation.\n\n\\[x^2\\]\n\nThe result follows.",
      original: { format: "pdf" },
      pdf: { version: "current-layout", pdfHash: "hash",
        blocks: page ? [{ blockId: "formula", page, sourceLines: [5, 5], bbox: null }] : [] },
    }),
    sourceOriginalUrl: () => "/original.pdf",
    sendMessage: async () => readerSuccess(window),
    continueReading: async () => readerSuccess(window),
  };
  render(<ConversationReader host={host} />);
  const conversation = within(await screen.findByLabelText("文章对话"));
  const citation = await conversation.findByRole("button", { name: "1" });
  fireEvent.click(citation);
  const source = screen.getByLabelText("文章原文");
  expect(source.querySelector("[data-evidence-block].is-active .katex")).toBeInTheDocument();
  expect(source).toHaveProperty("scrollTop", 572);
  expect(screen.getByRole("link", { name: "打开原件 ↗" })).toHaveAttribute("href", `/original.pdf?pdfHash=hash${page ? `#page=${page}` : ""}`);
  fireEvent.click(within(source).getByRole("button", { name: "返回回答证据 1" }));
  expect(citation).toHaveFocus();
});
