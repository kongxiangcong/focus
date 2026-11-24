// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { readerSuccess, type ReaderChunk, type ReaderHost, type ReaderHostResult, type ReadingWindow, type ValidatedAnswerEvidence } from "@focus/reader-contracts";
import { WorkspaceApp } from "./WorkspaceApp";

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
  HTMLElement.prototype.scrollIntoView = vi.fn();
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
  const publish = new Set<(result: ReaderHostResult<ReadingWindow>) => void>();
  const host: ReaderHost = {
    getReadingWindow: async () => readerSuccess(reading),
    getSourceDocument: async () => readerSuccess({
      sourceId: "paper", title: "Paper", bundleVersion: "bundle", markdown: `First paragraph.\n\n${missingSecondTarget ? "A different paragraph." : "Second paragraph."}`, lineCount: 3,
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
    const line = this.closest<HTMLElement>("[data-source-line]")?.dataset.sourceLine;
    const anchor = this.closest<HTMLElement>(".source-original")?.scrollTop ?? 0;
    const top = line === "3" ? 900 - anchor : line === "1" ? 100 - anchor : 0;
    return new DOMRect(0, top, 100, line ? 20 : 400);
  });
  await act(async () => { render(<WorkspaceApp host={host} />); });
  return {
    host,
    reconnect: () => publish.forEach(listener => listener(readerSuccess({ ...reading, revision: 2 }))),
  };
}

it("keeps the latest citation after reconnect and resumes a bookmark set with a reading key", async () => {
  const session = await setup();
  const pane = await screen.findByLabelText("文章原文");
  const answer = within(screen.getByLabelText("文章对话"));
  const firstNumber = await answer.findByRole("button", { name: "1" });
  const secondNumber = answer.getByRole("button", { name: "2" });

  fireEvent.keyDown(pane, { key: "PageDown" });
  pane.scrollTop = 90;
  fireEvent.scroll(pane);
  const bookmark = "focus.sourceBookmark:local:paper:0:bundle";
  const before = JSON.stringify({ line: 1, offset: -10 });
  expect(localStorage.getItem(bookmark)).toBe(before);

  fireEvent.click(firstNumber);
  fireEvent.click(secondNumber);
  expect(within(pane).getByText("First paragraph.")).not.toHaveClass("is-active");
  expect(within(pane).getByText("Second paragraph.")).toHaveClass("is-active");
  expect(pane).toHaveProperty("scrollTop", 772);
  expect(screen.getByRole("link", { name: "打开原件 ↗" })).toHaveAttribute("href", "/paper.pdf?pdfHash=original#page=2");
  fireEvent.scroll(pane);
  await act(async () => session.reconnect());
  expect(pane).toHaveProperty("scrollTop", 772);
  expect(within(pane).getByText("Second paragraph.")).toHaveClass("is-active");
  fireEvent.click(within(pane).getByRole("button", { name: "返回回答证据 2" }));
  expect(secondNumber).toHaveFocus();
  expect(localStorage.getItem(bookmark)).toBe(before);
  expect(session.host.continueReading).not.toHaveBeenCalled();
});

it("keeps the prior verified location when a later citation is unavailable", async () => {
  const session = await setup(true);
  const pane = await screen.findByLabelText("文章原文");
  const answer = within(screen.getByLabelText("文章对话"));
  fireEvent.click(await answer.findByRole("button", { name: "1" }));
  const position = pane.scrollTop;
  fireEvent.click(answer.getByRole("button", { name: "2" }));
  await act(async () => session.reconnect());
  expect(within(pane).getByText("First paragraph.")).toHaveClass("is-active");
  expect(pane).toHaveProperty("scrollTop", position);
  expect(within(pane).queryByRole("button", { name: "返回回答证据 2" })).not.toBeInTheDocument();
  expect(screen.queryByLabelText("原文证据")).not.toBeInTheDocument();
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
  const session = await setup(false, reading);
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
  expect(within(screen.getByLabelText("文章原文")).getByText("First paragraph.")).toHaveClass("is-active");
  expect(localStorage.getItem(bookmark)).toBe(before);
  expect(session.host.continueReading).not.toHaveBeenCalled();
});
