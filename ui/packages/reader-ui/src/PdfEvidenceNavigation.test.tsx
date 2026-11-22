import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { readerSuccess, type ReaderHost, type ReadingDocument, type ReadingWindow } from "@focus/reader-contracts";
import { ConversationReader } from "./ConversationReader";

vi.mock("pdfjs-dist", () => ({
  GlobalWorkerOptions: {},
  getDocument: () => ({
    promise: Promise.resolve({
      numPages: 12,
      getPage: (number: number) => number === 1 ? Promise.resolve({
        pageNumber: 1,
        getViewport: () => ({ width: 600, height: 800, scale: 1, rotation: 0 }),
        render: () => ({ promise: Promise.resolve(), cancel() {} }),
        streamTextContent: () => null,
      }) : new Promise(() => {}),
    }),
    destroy: () => Promise.resolve(),
  }),
  TextLayer: class {
    render() { return Promise.resolve(); }
    cancel() {}
  },
}));

afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });

it("opens all boxes of a far PDF block before the destination page renders", async () => {
  vi.stubGlobal("IntersectionObserver", class {
    constructor(private readonly callback: IntersectionObserverCallback) {}
    observe(node: HTMLElement) {
      if (node.dataset.pdfPage === "1") {
        this.callback([{ isIntersecting: true } as IntersectionObserverEntry], this as unknown as IntersectionObserver);
      }
    }
    disconnect() {}
  });
  vi.stubGlobal("ResizeObserver", class { observe() {} disconnect() {} });
  vi.spyOn(HTMLElement.prototype, "clientHeight", "get").mockReturnValue(900);
  vi.spyOn(HTMLElement.prototype, "scrollHeight", "get").mockReturnValue(12000);
  vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockImplementation(function (this: HTMLElement) {
    if (this.closest('[data-pdf-page="12"]')) return new DOMRect(0, 9000, 600, 800);
    return new DOMRect(0, 0, 600, 900);
  });
  const scroll = vi.fn();
  HTMLElement.prototype.scrollTo = scroll;
  const evidence = {
    sourceId: "paper", bundleVersion: "body", layoutVersion: "layout", blockIds: ["11-0"],
    evidenceId: "a".repeat(24), messageId: "answer", discussionId: "discussion", answerRevision: "r1",
    displayNumber: 1, sourceLines: [1, 1] as const, quote: { exact: "Two columns.", prefix: "", suffix: "" },
    relation: "supports" as const,
  };
  const doc: ReadingDocument = {
    sourceId: "paper", bundleVersion: "body", title: "Paper", markdown: "Two columns.", lineCount: 1,
    pdf: {
      version: "layout", pdfHash: "hash",
      pages: Array.from({ length: 12 }, (_, index) => ({ page: index + 1, width: 600, height: 800, rotation: 0 })),
      blocks: [{
        blockId: "11-0", page: 12, sourceLines: [1, 1], bbox: [0.1, 0.2, 0.4, 0.3],
        bboxes: [[0.1, 0.2, 0.4, 0.3], [0.6, 0.2, 0.9, 0.3]],
      }],
    },
  };
  const window: ReadingWindow = {
    status: "empty", source: { sourceId: "paper", title: "Paper", topicId: null }, current: null, history: [],
    conversation: [{ role: "assistant", chunkId: "", messageId: "answer", sourceId: "paper", discussionId: "discussion",
      answerRevision: "r1", content: `Claim [[e:${evidence.evidenceId}]]`, evidence: [evidence] }],
    sessionId: "session", discussionId: "discussion", revision: 1,
  };
  const host: ReaderHost = {
    getReadingWindow: async () => readerSuccess(window),
    getSourceDocument: async () => readerSuccess(doc),
    sourceOriginalUrl: () => "/original.pdf",
    subscribe: () => () => {},
    sendMessage: async () => readerSuccess(window),
    continueReading: async () => readerSuccess(window),
  };
  render(<ConversationReader host={host} />);
  await screen.findByLabelText("原版 PDF 第 1 页", undefined, { timeout: 5000 });
  const destination = screen.getByLabelText("第 12 页");
  expect(destination).toHaveStyle({ aspectRatio: "600/800" });
  expect(screen.queryByLabelText("原版 PDF 第 12 页")).toBeNull();

  const answer = screen.getByLabelText("文章对话");
  fireEvent.click(answer.querySelector<HTMLElement>("[data-citation]")!);
  const card = await screen.findByLabelText("原文证据");
  expect(within(card).getByText("Two columns.")).toBeVisible();
  expect(within(card).getByRole("button", { name: "下一处（1/2）" })).toBeVisible();
  await waitFor(() => expect(scroll).toHaveBeenLastCalledWith({ top: 8712, behavior: "instant" }));
  const regions = Array.from(destination.querySelectorAll("[data-active=true]"));
  expect(regions).toHaveLength(2);
  expect(regions[0]).toHaveStyle({ left: "10%", top: "20%" });
  expect(regions[1]).toHaveStyle({ left: "60%", top: "20%" });
});
