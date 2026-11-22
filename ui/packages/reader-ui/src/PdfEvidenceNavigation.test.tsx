import "@testing-library/jest-dom/vitest";
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { readerSuccess, type ReaderHost, type ReadingDocument, type ReadingWindow, type ValidatedAnswerEvidence } from "@focus/reader-contracts";
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

async function renderPaper(document: ReadingDocument, evidence: ValidatedAnswerEvidence) {
  const view: ReadingWindow = {
    status: "empty", source: { sourceId: "paper", title: "Paper", topicId: null }, current: null, history: [],
    conversation: [{ role: "assistant", chunkId: "", messageId: "answer", sourceId: "paper", discussionId: "discussion",
      answerRevision: "r1", content: `Claim [[e:${evidence.evidenceId}]]`, evidence: [evidence] }],
    sessionId: "session", discussionId: "discussion", revision: 1,
  };
  const host: ReaderHost = {
    getReadingWindow: async () => readerSuccess(view),
    getSourceDocument: async () => readerSuccess(document),
    sourceOriginalUrl: () => "/original.pdf",
    subscribe: () => () => {},
    sendMessage: async () => readerSuccess(view),
    continueReading: async () => readerSuccess(view),
  };
  await act(async () => { render(<ConversationReader host={host} />); });
}

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
  await renderPaper(doc, evidence);
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

it("synchronizes manual view changes using the linked PDF block and translated paragraph", async () => {
  vi.stubGlobal("IntersectionObserver", class { observe() {} disconnect() {} });
  vi.spyOn(HTMLElement.prototype, "clientHeight", "get").mockReturnValue(100);
  vi.spyOn(HTMLElement.prototype, "scrollHeight", "get").mockReturnValue(2000);
  vi.spyOn(HTMLElement.prototype, "getClientRects").mockReturnValue([new DOMRect()] as unknown as DOMRectList);
  vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockImplementation(function (this: HTMLElement) {
    const y = this.matches("[data-block-id]") ? 32 : this.matches("[data-translation-chunk]") ? 500 : 0;
    const scrollTop = y ? this.closest<HTMLElement>(".source-original")!.scrollTop : 0;
    return new DOMRect(0, y - scrollTop, 100, y ? 80 : 100);
  });
  HTMLElement.prototype.scrollTo = function (this: HTMLElement, options?: ScrollToOptions | number) {
    if (typeof options === "object") this.scrollTop = options.top ?? 0;
  };
  localStorage.clear();
  const bookmarkKey = "focus.sourceBookmark:local:paper:0:body";
  localStorage.setItem(bookmarkKey, '{"line":90,"offset":12}');
  const doc: ReadingDocument = {
    sourceId: "paper", bundleVersion: "body", title: "Paper", markdown: "The heading\n\nSupported quote.", lineCount: 3,
    pdf: { version: "layout", pdfHash: "hash", blocks: [{ blockId: "current", page: 1, sourceLines: [1, 3], bbox: [0.1, 0.2, 0.4, 0.3] }] },
    translation: { status: "ready", chunks: [{ id: "translated", text: "对应的中文段落。", blockIds: ["current"], sourceLines: [3, 3] }] },
  };
  const evidence: ValidatedAnswerEvidence = {
    sourceId: "paper", bundleVersion: "body", layoutVersion: "layout", blockIds: ["current"], renderGranularity: "block",
    evidenceId: "a".repeat(24), messageId: "answer", discussionId: "discussion", answerRevision: "r1",
    displayNumber: 1, sourceLines: [3, 3], quote: { exact: "Supported quote.", prefix: "", suffix: "" }, relation: "supports",
  };
  await renderPaper(doc, evidence);
  await screen.findByLabelText("第 1 页", {}, { timeout: 8500 });
  const source = screen.getByLabelText("文章原文");
  fireEvent.click(screen.getByRole("button", { name: "中文译文" }));
  expect(screen.getByText("对应的中文段落。")).toBeVisible();
  expect(source.scrollTop).toBe(468);

  fireEvent.click(screen.getByLabelText("文章对话").querySelector<HTMLElement>("[data-citation]")!);
  expect(screen.getByRole("button", { name: "中文译文" })).toHaveAttribute("aria-pressed", "true");
  expect(screen.getByLabelText("原文证据")).toHaveTextContent("译块定位Supported quote.");
  expect(source.scrollTop).toBe(468);

  fireEvent.click(screen.getByRole("button", { name: "原版 PDF" }));
  await screen.findByLabelText("第 1 页", {}, { timeout: 8500 });
  await waitFor(() => expect(source.scrollTop).toBe(0), { timeout: 8500 });
  expect(localStorage.getItem(bookmarkKey)).toBe('{"line":90,"offset":12}');
});

it("jumps to a verified page when the citation has no reliable box", async () => {
  vi.stubGlobal("IntersectionObserver", class { observe() {} disconnect() {} });
  vi.spyOn(HTMLElement.prototype, "clientHeight", "get").mockReturnValue(900);
  vi.spyOn(HTMLElement.prototype, "scrollHeight", "get").mockReturnValue(12000);
  vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockImplementation(function (this: HTMLElement) {
    return new DOMRect(0, this.closest('[data-pdf-page="12"]') ? 9000 : 0, 600, 900);
  });
  const scroll = vi.fn();
  HTMLElement.prototype.scrollTo = scroll;
  const doc: ReadingDocument = {
    sourceId: "paper", bundleVersion: "body", title: "Paper", markdown: "A page-only quotation.", lineCount: 1,
    pdf: { version: "layout", pdfHash: "hash", blocks: [] },
    translation: { status: "ready", chunks: [{ id: "translation", text: "另有译文。", blockIds: [], sourceLines: [1, 1] }] },
  };
  await renderPaper(doc, {
    sourceId: "paper", bundleVersion: "body", layoutVersion: "layout", renderGranularity: "block",
    evidenceId: "a".repeat(24), messageId: "answer", discussionId: "discussion", answerRevision: "r1",
    displayNumber: 1, sourceLines: [1, 1], quote: { exact: "A page-only quotation.", prefix: "", suffix: "" }, relation: "supports",
    pdfRegions: [{ pageIndex: 11, pageNumber: 12, bboxes: [], granularity: "page" }],
  });
  const page = await screen.findByLabelText("第 12 页", {}, { timeout: 8500 });
  fireEvent.click(screen.getByLabelText("文章对话").querySelector<HTMLElement>("[data-citation]")!);
  expect(await screen.findByLabelText("原文证据", {}, { timeout: 8500 })).toHaveTextContent("第 12 页 · 页定位");
  expect(screen.getByRole("button", { name: "原版 PDF" })).toHaveAttribute("aria-pressed", "true");
  expect(within(page).getByRole("button", { name: "返回回答证据 1" })).toBeVisible();
  await waitFor(() => expect(scroll).toHaveBeenLastCalledWith({ top: 8712, behavior: "instant" }), { timeout: 8500 });
});
