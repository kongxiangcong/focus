// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { readerSuccess, type ReaderChunk, type ReaderHost, type ReaderHostResult, type ReadingWindow, type ValidatedAnswerEvidence } from "@focus/reader-contracts";
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

async function setup(missingSecondTarget = false, reading = snapshot) {
  let resolvePdf!: (document: { numPages: number; getPage: (page: number) => Promise<unknown> }) => void;
  let rejectPdf!: (error: Error) => void;
  getDocument.mockReturnValue({ promise: new Promise((resolve, reject) => { resolvePdf = resolve; rejectPdf = reject; }), destroy: async () => {} });
  const publish = new Set<(result: ReaderHostResult<ReadingWindow>) => void>();
  const host: ReaderHost = {
    getReadingWindow: async () => readerSuccess(reading),
    getSourceDocument: async () => readerSuccess({
      sourceId: "paper", title: "Paper", bundleVersion: "bundle", markdown: "First paragraph.\n\nSecond paragraph.", lineCount: 3,
      blocks: [{ blockId: "new-first", offsets: [0, 16] }, { blockId: "new-second", offsets: [18, 35] }],
      pdf: {
        pdfHash: "original", version: "layout",
        blocks: [
          { blockId: "first", page: 1, sourceLines: [1, 1], bbox: [0.1, 0.1, 0.4, 0.2] },
          ...(!missingSecondTarget ? [{ blockId: "second", page: 2, sourceLines: [3, 3] as const, bbox: [0.1, 0.1, 0.4, 0.2] as const }] : []),
        ],
      },
      translation: { status: "ready", chunks: [
        { id: "translated-first", text: "第一段译文。", blockIds: ["first"], sourceLines: [1, 1] },
        ...(!missingSecondTarget ? [{ id: "translated-second", text: "第二段译文。", blockIds: ["second"], sourceLines: [3, 3] as const }] : []),
      ] },
    }),
    sourceOriginalUrl: () => "/paper.pdf", selectDiscussionSource: async () => readerSuccess(reading),
    openSource: async () => readerSuccess(reading),
    continueReading: vi.fn(async () => readerSuccess(reading)), sendMessage: async () => readerSuccess(reading),
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
  await act(async () => { render(<WorkspaceApp host={host} />); });
  return {
    host,
    completePdf: () => resolvePdf({ numPages: 2, getPage: async pageNumber => ({ pageNumber, getViewport: () => ({ width: 100, height: 120 }) }) }),
    failPdf: () => rejectPdf(new Error("PDF failed")),
    reconnect: () => publish.forEach(listener => listener(readerSuccess({ ...reading, revision: 2 }))),
  };
}

it.each([
  ["wheel", (pane: HTMLElement) => fireEvent.wheel(pane, { deltaY: 120 })],
  ["touch", (pane: HTMLElement) => fireEvent.touchStart(pane)],
  ["scrollbar pointer", (pane: HTMLElement) => fireEvent.pointerDown(pane)],
  ["scrollbar native scroll", (pane: HTMLElement) => { pane.scrollTop = 60; fireEvent.scroll(pane); }],
  ["keyboard", (pane: HTMLElement) => fireEvent.keyDown(pane, { key: "PageDown" })],
])("cancels a waiting citation when the reader uses %s", async (_method, manuallyBrowse) => {
  const key = "focus.sourceBookmark:local:paper:0:bundle";
  const before = JSON.stringify({ line: 1, offset: 28 });
  localStorage.setItem(key, before);
  const session = await setup();
  const pane = await screen.findByLabelText("文章原文");
  const answer = screen.getByLabelText("文章对话");
  fireEvent.click(await within(answer).findByRole("button", { name: "1" }, { timeout: 5000 }));
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
  const session = await setup();
  const pane = await screen.findByLabelText("文章原文");
  const answer = within(screen.getByLabelText("文章对话"));
  fireEvent.click(await answer.findByRole("button", { name: "1" }, { timeout: 5000 }));
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
  const session = await setup();
  const pane = await screen.findByLabelText("文章原文");
  const answer = within(screen.getByLabelText("文章对话"));
  fireEvent.click(await answer.findByRole("button", { name: "1" }, { timeout: 5000 }));
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


it("does not replay an unavailable citation after the reader closes its card and reconnects", async () => {
  const session = await setup(true);
  const pane = await screen.findByLabelText("文章原文");
  const answer = within(screen.getByLabelText("文章对话"));
  fireEvent.click(await answer.findByRole("button", { name: "2" }, { timeout: 5000 }));
  const card = await screen.findByLabelText("原文证据");
  expect(within(card).getByText("Second paragraph.")).toBeVisible();
  expect(pane.scrollTop).toBe(0);
  fireEvent.click(within(card).getByRole("button", { name: "关闭证据" }));
  await act(async () => session.reconnect());
  expect(screen.queryByLabelText("原文证据")).not.toBeInTheDocument();
  expect(pane.scrollTop).toBe(0);
});

it("opens the answer before its source from a chunk bound to the current source blocks", async () => {
  const chunk: ReaderChunk = {
    sourceId: "paper", bundleVersion: "bundle", planId: "plan", chunkId: "chunk-1", index: 1, total: 2,
    sectionPath: ["Method"], sourceLines: [1, 1], sourceMarkdown: "First paragraph.", blockIds: ["new-first"],
    images: [], relevantGlossary: [], translation: "第一段译文。", presentationStatus: "presented",
  };
  const current: ReaderChunk = { ...chunk, chunkId: "chunk-2", index: 2, sourceLines: [3, 3], sourceMarkdown: "Second paragraph.", blockIds: ["new-second"] };
  const messages = snapshot.conversation.map(message => ({
    ...message, evidence: [first, { ...second, quote: { ...second.quote, prefix: "unmatched context" } }],
  }));
  const reading: ReadingWindow = { ...snapshot, status: "reading", current, history: [chunk], conversation: messages, readingStarted: true,
    timeline: [{ kind: "reading", chunk }, { kind: "reading", chunk: current }, { kind: "message", messageId: "answer" }] };
  const bookmark = "focus.sourceBookmark:local:paper:0:bundle";
  const before = JSON.stringify({ line: 1, offset: 28 });
  localStorage.setItem(bookmark, before);
  HTMLElement.prototype.scrollIntoView = vi.fn();
  const session = await setup(false, reading);
  await act(async () => session.completePdf());
  await within(screen.getByLabelText("文章对话")).findByRole("button", { name: "1" }, { timeout: 10000 });
  const mode = screen.getByRole("combobox", { name: "阅读方式" });
  fireEvent.change(mode, { target: { value: "chunks" } });
  const stream = screen.getByRole("main", { name: "阅读与对话" });
  const disclosure = await within(stream).findByRole("button", { name: "对话证据 · 1 条" }, { timeout: 10000 });
  expect(within(stream).getAllByRole("button", { name: /对话证据/ })).toHaveLength(1);
  expect(stream.textContent).not.toContain("[[e:");
  fireEvent.click(disclosure);
  fireEvent.click(within(stream).getByRole("button", { name: /First paragraph/ }));
  const answer = within(screen.getByLabelText("文章对话"));
  const number = await answer.findByRole("button", { name: "1" });
  await waitFor(() => {
    expect(number).toHaveFocus();
    expect(number).toHaveAttribute("data-answer-target", "true");
  });
  expect(screen.queryByLabelText("原文证据")).not.toBeInTheDocument();
  expect(mode).toHaveValue("chat");
  fireEvent.click(number);
  expect(await screen.findByLabelText("原文证据")).toBeVisible();
  expect(localStorage.getItem(bookmark)).toBe(before);
  expect(session.host.continueReading).not.toHaveBeenCalled();
});
