// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { readerSuccess, type ReaderHost, type ReaderHostResult, type ReadingWindow, type ValidatedAnswerEvidence } from "@focus/reader-contracts";
import { WorkspaceApp } from "./WorkspaceApp";

const { getDocument } = vi.hoisted(() => ({ getDocument: vi.fn() }));
vi.mock("../../../packages/reader-ui/node_modules/pdfjs-dist/build/pdf.mjs", () => ({ GlobalWorkerOptions: {}, getDocument }));

const first: ValidatedAnswerEvidence = {
  evidenceId: "a".repeat(24), sourceId: "paper", discussionId: "discussion", messageId: "answer", answerRevision: "answer-v1",
  bundleVersion: "bundle", displayNumber: 1, relation: "supports", sourceLines: [1, 1], layoutVersion: "layout", blockIds: ["first"],
  quote: { exact: "First paragraph.", prefix: "", suffix: "" },
};
const second: ValidatedAnswerEvidence = {
  ...first, evidenceId: "b".repeat(24), displayNumber: 2, sourceLines: [3, 3], blockIds: ["second"],
  quote: { exact: "Second paragraph.", prefix: "", suffix: "" },
};
const snapshot: ReadingWindow = {
  status: "empty", source: { sourceId: "paper", title: "Paper", topicId: null }, current: null, history: [],
  sessionId: "session", discussionId: "discussion", sourceBundleVersion: "bundle", revision: 1,
  conversation: [{
    role: "assistant", messageId: "answer", chunkId: "", sourceId: "paper", discussionId: "discussion", answerRevision: "answer-v1",
    content: `A [[e:${first.evidenceId}]] and B [[e:${second.evidenceId}]]`, evidence: [first, second],
  }],
};

beforeEach(() => {
  history.replaceState(null, "", "/reading");
  localStorage.clear();
  getDocument.mockReset();
  HTMLDialogElement.prototype.showModal = function () { this.setAttribute("open", ""); };
  HTMLDialogElement.prototype.close = function () { this.removeAttribute("open"); };
  vi.stubGlobal("IntersectionObserver", class { observe() {} disconnect() {} });
  vi.stubGlobal("ResizeObserver", class { observe() {} disconnect() {} });
  vi.stubGlobal("matchMedia", (query: string) => ({
    matches: query === "(prefers-reduced-motion: reduce)", addEventListener() {}, removeEventListener() {},
  }));
});
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });

function setup() {
  let resolvePdf!: (document: { numPages: number; getPage: (page: number) => Promise<unknown> }) => void;
  let rejectPdf!: (error: Error) => void;
  getDocument.mockReturnValue({ promise: new Promise((resolve, reject) => { resolvePdf = resolve; rejectPdf = reject; }), destroy: async () => {} });
  const publish = new Set<(result: ReaderHostResult<ReadingWindow>) => void>();
  const host: ReaderHost = {
    getReadingWindow: async () => readerSuccess(snapshot),
    getSourceDocument: async () => readerSuccess({
      sourceId: "paper", title: "Paper", bundleVersion: "bundle", markdown: "First paragraph.\n\nSecond paragraph.", lineCount: 3,
      pdf: {
        pdfHash: "original", version: "layout",
        blocks: [
          { blockId: "first", page: 1, sourceLines: [1, 1], bbox: [0.1, 0.1, 0.4, 0.2] },
          { blockId: "second", page: 2, sourceLines: [3, 3], bbox: [0.1, 0.1, 0.4, 0.2] },
        ],
      },
      translation: { status: "ready", chunks: [
        { id: "translated-first", text: "第一段译文。", blockIds: ["first"], sourceLines: [1, 1] },
        { id: "translated-second", text: "第二段译文。", blockIds: ["second"], sourceLines: [3, 3] },
      ] },
    }),
    sourceOriginalUrl: () => "/paper.pdf", selectDiscussionSource: async () => readerSuccess(snapshot),
    openSource: async () => readerSuccess(snapshot),
    continueReading: vi.fn(async () => readerSuccess(snapshot)), sendMessage: async () => readerSuccess(snapshot),
    subscribe: listener => { publish.add(listener); return () => { publish.delete(listener); }; },
  };
  HTMLElement.prototype.scrollTo = function (options?: ScrollToOptions | number, y?: number) {
    this.scrollTop = typeof options === "number" ? y ?? 0 : options?.top ?? 0;
  };
  vi.spyOn(HTMLElement.prototype, "clientHeight", "get").mockReturnValue(400);
  vi.spyOn(HTMLElement.prototype, "scrollHeight", "get").mockReturnValue(2000);
  vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockImplementation(function (this: HTMLElement) {
    const y = this.dataset.sourceLine === "3" ? 900 : this.dataset.sourceLine === "1" ? 700 : 0;
    return { x: 0, y, top: y, bottom: y + 400, left: 0, right: 100, width: 100, height: 400, toJSON() {} };
  });
  render(<WorkspaceApp host={host} />);
  return {
    host,
    completePdf: () => resolvePdf({ numPages: 2, getPage: async pageNumber => ({ pageNumber, getViewport: () => ({ width: 100, height: 120 }) }) }),
    failPdf: () => rejectPdf(new Error("PDF failed")),
    reconnect: () => publish.forEach(listener => listener(readerSuccess({ ...snapshot, revision: 2 }))),
  };
}

it.each([
  ["wheel", (pane: HTMLElement) => fireEvent.wheel(pane, { deltaY: 120 })],
  ["touch", (pane: HTMLElement) => fireEvent.touchStart(pane)],
  ["scrollbar", (pane: HTMLElement) => fireEvent.pointerDown(pane)],
  ["keyboard", (pane: HTMLElement) => fireEvent.keyDown(pane, { key: "PageDown" })],
])("cancels a waiting citation when the reader uses %s", async (_method, manuallyBrowse) => {
  const key = "focus.sourceBookmark:local:paper:0:bundle";
  const before = JSON.stringify({ line: 1, offset: 28 });
  localStorage.setItem(key, before);
  const session = setup();
  const pane = await screen.findByLabelText("文章原文");
  const answer = screen.getByLabelText("文章对话");
  fireEvent.click(await within(answer).findByRole("button", { name: "1" }));
  await waitFor(() => expect(getDocument).toHaveBeenCalled());
  manuallyBrowse(pane);
  pane.scrollTop = 250;
  await act(async () => session.completePdf());
  await waitFor(() => expect(pane.querySelector('[data-pdf-page="2"]')).toBeInTheDocument());
  expect(screen.queryByLabelText("原文证据")).not.toBeInTheDocument();
  expect(pane.scrollTop).toBe(250);
  expect(localStorage.getItem(key)).toBe(before);
});


it("lands on the latest citation once and preserves the manual bookmark through reconnect and display switches", async () => {
  const key = "focus.sourceBookmark:local:paper:0:bundle";
  const before = JSON.stringify({ line: 1, offset: 28 });
  localStorage.setItem(key, before);
  const session = setup();
  const pane = await screen.findByLabelText("文章原文");
  const answer = within(screen.getByLabelText("文章对话"));
  fireEvent.click(await answer.findByRole("button", { name: "1" }));
  fireEvent.click(answer.getByRole("button", { name: "2" }));
  await act(async () => session.completePdf());
  const card = await screen.findByLabelText("原文证据");
  expect(within(card).getByText("Second paragraph.")).toBeVisible();
  expect(pane.scrollTop).toBe(772);
  fireEvent.scroll(pane);
  await act(async () => session.reconnect());
  expect(pane.scrollTop).toBe(772);

  fireEvent.click(screen.getByRole("button", { name: "中文译文" }));
  fireEvent.scroll(pane);
  fireEvent.click(screen.getByRole("button", { name: "对话全屏" }));
  fireEvent.click(screen.getByRole("button", { name: "关闭全屏模式" }));
  fireEvent.change(screen.getByRole("combobox", { name: "阅读方式" }), { target: { value: "chunks" } });
  fireEvent.change(screen.getByRole("combobox", { name: "阅读方式" }), { target: { value: "chat" } });
  expect(screen.queryByLabelText("原文证据")).not.toBeInTheDocument();
  expect(localStorage.getItem(key)).toBe(before);
  expect(session.host.continueReading).not.toHaveBeenCalled();
});

it.each(["success", "failure"] as const)("a pending PDF %s cannot replace the later citation in the translation", async result => {
  const session = setup();
  const pane = await screen.findByLabelText("文章原文");
  const answer = within(screen.getByLabelText("文章对话"));
  fireEvent.click(await answer.findByRole("button", { name: "1" }));
  await waitFor(() => expect(getDocument).toHaveBeenCalled());
  fireEvent.click(screen.getByRole("button", { name: "中文译文" }));
  fireEvent.click(answer.getByRole("button", { name: "2" }));
  const card = await screen.findByLabelText("原文证据");
  expect(within(card).getByText("Second paragraph.")).toBeVisible();
  const position = pane.scrollTop;
  await act(async () => result === "success" ? session.completePdf() : session.failPdf());
  expect(within(card).getByText("Second paragraph.")).toBeVisible();
  expect(pane.scrollTop).toBe(position);
  expect(screen.queryByText("PDF 加载失败", { exact: false })).not.toBeInTheDocument();
});
