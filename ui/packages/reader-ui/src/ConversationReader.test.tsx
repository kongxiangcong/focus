import "@testing-library/jest-dom/vitest";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { readerSuccess, type ReaderHost, type ReadingWindow, type ValidatedAnswerEvidence } from "@focus/reader-contracts";
import { ConversationReader } from "./ConversationReader";

const initial: ReadingWindow = { status: "empty", source: { sourceId: "paper", title: "Paper", topicId: null },
  current: null, history: [], conversation: [], sessionId: "session", discussionId: "discussion", revision: 1 };
const first: ValidatedAnswerEvidence = { sourceId: "paper", bundleVersion: "v1", evidenceId: "a".repeat(24),
  messageId: "answer", discussionId: "discussion", answerRevision: "r1", displayNumber: 1, sourceLines: [3, 3],
  quote: { exact: "First evidence.", prefix: "", suffix: "" }, relation: "supports" };
const second: ValidatedAnswerEvidence = { ...first, evidenceId: "b".repeat(24), displayNumber: 2, sourceLines: [5, 5],
  quote: { exact: "Second evidence.", prefix: "", suffix: "" } };
const scrolling = vi.fn();
beforeEach(() => {
  localStorage.clear(); scrolling.mockClear();
  HTMLElement.prototype.scrollTo = scrolling;
  HTMLElement.prototype.scrollIntoView = vi.fn();
  vi.spyOn(HTMLElement.prototype, "clientWidth", "get").mockReturnValue(1152);
  vi.spyOn(HTMLElement.prototype, "clientHeight", "get").mockReturnValue(400);
  vi.spyOn(HTMLElement.prototype, "scrollHeight", "get").mockReturnValue(2000);
  vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockImplementation(function (this: HTMLElement) {
    return { x: 0, y: 0, top: this.matches("mark") ? 900 : 0, bottom: this.matches("mark") ? 920 : 400,
      left: 0, right: 100, width: 100, height: 400, toJSON() {} };
  });
});
afterEach(() => { cleanup(); vi.restoreAllMocks(); });

function answer(evidence: readonly ValidatedAnswerEvidence[], revision = 3): ReadingWindow {
  return { ...initial, revision, conversation: [{ role: "assistant", chunkId: "", messageId: "answer", sourceId: "paper",
    discussionId: "discussion", answerRevision: "r1", content: evidence.map(e => `Claim [[e:${e.evidenceId}]]`).join("\n\n"), evidence }] };
}
function setup(start = initial, overrides: Partial<ReaderHost> = {}) {
  let listener: ((r: ReturnType<typeof readerSuccess<ReadingWindow>>) => void) | undefined;
  const host: ReaderHost = {
    getReadingWindow: vi.fn(async () => readerSuccess(start)),
    getSourceDocument: vi.fn(async () => readerSuccess({ sourceId: "paper", bundleVersion: "v1", title: "Paper", markdown: "# Paper\n\nFirst evidence.\n\nSecond evidence.", lineCount: 5 })),
    subscribe: callback => { listener = callback; return () => { listener = undefined; }; },
    sendMessage: vi.fn(async () => readerSuccess({ ...initial, revision: 2 })),
    continueReading: vi.fn(async () => readerSuccess(initial)),
    ...overrides,
  };
  const reader = render(<ConversationReader host={host} />);
  const display = (visible: boolean, fullscreen = false) => reader.rerender(<ConversationReader host={host} visible={visible} fullscreen={fullscreen} />);
  return { host, display, emit: (value: ReadingWindow) => act(() => listener?.(readerSuccess(value))) };
}
async function send() {
  await screen.findByText("First evidence.");
  fireEvent.change(screen.getByRole("textbox", { name: "输入消息" }), { target: { value: "Explain" } });
  fireEvent.click(screen.getByRole("button", { name: "发送" }));
  await waitFor(() => expect(screen.getByRole("textbox", { name: "输入消息" })).toHaveValue(""));
}

it("automatically locates at most one evidence per turn", async () => {
  const app = setup(); await send();
  app.emit(answer([first]));
  await waitFor(() => expect(scrolling).toHaveBeenCalledTimes(1));
  app.emit(answer([first, second], 4));
  await screen.findByRole("button", { name: "返回回答证据 2" });
  expect(scrolling).toHaveBeenCalledTimes(1);
  expect(app.host.continueReading).not.toHaveBeenCalled();
});

it("manual reading cancels pending automatic source navigation", async () => {
  const app = setup(); await send();
  fireEvent.wheel(screen.getByLabelText("文章原文"));
  scrolling.mockClear();
  app.emit(answer([first]));
  await screen.findByRole("button", { name: "返回回答证据 1" });
  expect(scrolling).not.toHaveBeenCalled();
  expect(screen.queryByLabelText("原文证据")).not.toBeInTheDocument();
});

it("restores saved answers without replaying an automatic jump", async () => {
  setup(answer([first]));
  await screen.findByRole("button", { name: "返回回答证据 1" }, { timeout: 5000 });
  expect(scrolling).not.toHaveBeenCalled();
  expect(screen.queryByLabelText("原文证据")).not.toBeInTheDocument();
});

it.each(["leave chat", "exit fullscreen"])("dismisses open evidence on %s", async transition => {
  const app = setup();
  if (transition === "exit fullscreen") app.display(true, true);
  await send();
  app.emit(answer([first]));
  fireEvent.click(await screen.findByRole("button", { name: "返回回答证据 1" }));
  expect(screen.getByLabelText("原文证据")).toBeInTheDocument();
  app.display(transition === "exit fullscreen");
  app.display(true);
  expect(screen.queryByLabelText("原文证据")).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "返回回答证据 1" }));
  expect(screen.getByLabelText("原文证据")).toBeInTheDocument();
});

it("does not replay evidence when a reply arrives after leaving chat", async () => {
  const app = setup(); await send();
  app.display(false);
  app.emit(answer([first]));
  app.display(true);
  await screen.findByRole("button", { name: "返回回答证据 1" });
  expect(screen.queryByLabelText("原文证据")).not.toBeInTheDocument();
  expect(scrolling).not.toHaveBeenCalled();
});

it.each([
  { scenario: "the evidence layout has changed", layoutVersion: "old-layout", page: 1 },
  { scenario: "no PDF page is known", layoutVersion: "new-layout", page: 0 },
])("opens the corresponding translated paragraph when $scenario", async ({ layoutVersion, page }) => {
  const cited = { ...first, layoutVersion, blockIds: [page ? "0-1" : "new-5"], renderGranularity: "block" as const,
    quote: { ...first.quote, suffix: "\n\nNext paragraph." } };
  setup(answer([cited]), {
    sourceOriginalUrl: () => "/paper.pdf",
    getSourceDocument: async () => readerSuccess({
      sourceId: "paper", bundleVersion: "v1", title: "Paper", markdown: "# Paper\r\n\r\nFirst evidence.\r\n\r\nNext paragraph.", lineCount: 5,
      pdf: { version: "new-layout", pdfHash: "abc", blocks: [{ blockId: "new-5", page, sourceLines: [3, 3], bbox: null }] },
      translation: { status: "ready", chunks: [{ id: "chunk-1", text: "已检查的译文。", blockIds: ["new-5"], sourceLines: [3, 3] }] },
    }),
  });
  expect(await screen.findByRole("button", { name: "原版 PDF" }, { timeout: 8500 })).toHaveAttribute("aria-pressed", "true");
  fireEvent.click(window.document.querySelector<HTMLElement>("[data-citation]")!);
  expect(await screen.findByText("已检查的译文。", {}, { timeout: 5000 })).toBeVisible();
  expect(screen.getByRole("button", { name: "中文译文" })).toHaveAttribute("aria-pressed", "true");
  fireEvent.click(screen.getByRole("button", { name: "返回回答证据 1" }));
  await waitFor(() => expect(window.document.querySelector("[data-citation]")).toHaveFocus());
});

it.each([
  { scenario: "a changed bundle", bundleVersion: "older", suffix: "" },
  { scenario: "a missing context match", bundleVersion: "v1", suffix: " different context" },
])("keeps the translated reading position and displays the saved quote after $scenario", async ({ bundleVersion, suffix }) => {
  const cited = { ...first, bundleVersion, layoutVersion: "layout", blockIds: ["current"], renderGranularity: "block" as const,
    quote: { ...first.quote, suffix } };
  setup(answer([cited]), {
    sourceOriginalUrl: () => "/paper.pdf",
    getSourceDocument: async () => readerSuccess({
      sourceId: "paper", bundleVersion: "v1", title: "Paper", markdown: "# Paper\n\nFirst evidence.", lineCount: 3,
      pdf: { version: "layout", pdfHash: "abc", blocks: [{ blockId: "current", page: 1, sourceLines: [3, 3], bbox: null }] },
      translation: { status: "ready", chunks: [{ id: "chunk-1", text: "正在阅读的译文。", blockIds: ["current"], sourceLines: [3, 3] }] },
    }),
  });
  const translation = await screen.findByRole("button", { name: "中文译文" }, { timeout: 8500 });
  fireEvent.click(translation);
  const source = screen.getByLabelText("文章原文");
  source.scrollTop = 120;
  scrolling.mockClear();
  fireEvent.click(window.document.querySelector<HTMLElement>("[data-citation]")!);
  expect(await screen.findByLabelText("原文证据", {}, { timeout: 8500 })).toHaveTextContent("历史引文First evidence.");
  expect(screen.getByRole("button", { name: "中文译文" })).toHaveAttribute("aria-pressed", "true");
  expect(source).toHaveProperty("scrollTop", 120);
  expect(scrolling).not.toHaveBeenCalled();
  expect(screen.queryByRole("button", { name: "返回回答证据 1" })).toBeNull();
});

it("preserves the current translated paragraph when a verified quote has no matching chunk", async () => {
  setup(answer([{ ...first, layoutVersion: "layout", blockIds: ["current"], renderGranularity: "block" }]), {
    sourceOriginalUrl: () => "/paper.pdf",
    getSourceDocument: async () => readerSuccess({
      sourceId: "paper", bundleVersion: "v1", title: "Paper", markdown: "# Paper\n\nFirst evidence.", lineCount: 3,
      pdf: { version: "layout", pdfHash: "abc", blocks: [{ blockId: "current", page: 1, sourceLines: [3, 3], bbox: null }] },
      translation: { status: "ready", chunks: [{ id: "chunk-1", text: "文章标题。", blockIds: ["title"], sourceLines: [1, 1] }] },
    }),
  });
  const translation = await screen.findByRole("button", { name: "中文译文" }, { timeout: 8500 });
  fireEvent.click(translation);
  const source = screen.getByLabelText("文章原文");
  source.scrollTop = 120;
  scrolling.mockClear();
  fireEvent.click(window.document.querySelector<HTMLElement>("[data-citation]")!);
  expect(await screen.findByLabelText("原文证据", {}, { timeout: 8500 })).toHaveTextContent("译块位置暂不可用First evidence.");
  expect(screen.getByRole("button", { name: "中文译文" })).toHaveAttribute("aria-pressed", "true");
  expect(source).toHaveProperty("scrollTop", 120);
  expect(scrolling).not.toHaveBeenCalled();
});
