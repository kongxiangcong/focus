import "@testing-library/jest-dom/vitest";
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
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

it("opens the saved PDF and projects a citation into the shared translated chunk", async () => {
  const cited = { ...first, layoutVersion: "old-layout", blockIds: ["0-1"] };
  setup(answer([cited]), {
    sourceOriginalUrl: () => "/paper.pdf",
    getSourceDocument: async () => readerSuccess({
      sourceId: "paper", bundleVersion: "v1", title: "Paper", markdown: "# Paper\n\nFirst evidence.", lineCount: 3,
      pdf: { version: "new-layout", pdfHash: "abc", blocks: [] },
      translation: { status: "ready", chunks: [{ id: "chunk-1", text: "已检查的译文。", blockIds: [], sourceLines: [1, 3] }] },
    }),
  });
  expect(await screen.findByRole("button", { name: "原版 PDF" })).toHaveAttribute("aria-pressed", "true");
  fireEvent.click(window.document.querySelector<HTMLElement>("[data-citation]")!);
  expect(await screen.findByText(/版面位置暂不可用/)).toBeVisible();
  fireEvent.click(screen.getByRole("button", { name: "中文译文" }));
  expect(screen.getByText("已检查的译文。")).toBeVisible();
  fireEvent.click(screen.getByRole("button", { name: "返回回答证据 1" }));
  await waitFor(() => expect(window.document.querySelector("[data-citation]")).toHaveFocus());
});

it("returns from a block to its only linked answer even when a newer answer is selected", async () => {
  const cited = { ...first, renderGranularity: "block" as const };
  const start = answer([cited]);
  setup({ ...start, conversation: [...start.conversation, {
    ...start.conversation[0], messageId: "uncited-answer", answerRevision: "r2", content: "There's nothing to verify here.", evidence: [],
  }] });
  const source = await screen.findByLabelText("文章原文");
  fireEvent.click(await within(source).findByRole("button", { name: "返回回答证据 1" }));
  await waitFor(() => expect(within(screen.getByLabelText("文章对话")).getByRole("button", { name: "1" })).toHaveFocus());
  expect(screen.queryByLabelText("选择回答")).not.toBeInTheDocument();
});

it("offers answer excerpts for a shared block and returns an active number to its exact origin", async () => {
  const cited = { ...first, renderGranularity: "block" as const };
  const other = { ...cited, evidenceId: "c".repeat(24), messageId: "second-answer", answerRevision: "r2" };
  const start = answer([cited]);
  setup({ ...start, conversation: [
    { ...start.conversation[0], content: `The original result held [[e:${cited.evidenceId}]].` },
    { ...start.conversation[0], messageId: other.messageId, answerRevision: other.answerRevision,
      content: `The replication differed [[e:${other.evidenceId}]].`, evidence: [other] },
  ] });
  const source = within(await screen.findByLabelText("文章原文"));
  const conversation = within(screen.getByLabelText("文章对话"));
  const [firstNumber, secondNumber] = await conversation.findAllByRole("button", { name: "1" });
  fireEvent.click(await source.findByRole("button", { name: "查看 2 条相关回答" }));
  const chooser = within(screen.getByRole("dialog", { name: "选择回答" }));
  expect(chooser.getByRole("button", { name: /The replication differed/ })).toBeVisible();
  fireEvent.click(chooser.getByRole("button", { name: /The original result held/ }));
  expect(firstNumber).toHaveFocus();

  fireEvent.click(secondNumber);
  fireEvent.click(await source.findByRole("button", { name: "返回回答证据 1" }));
  expect(secondNumber).toHaveFocus();
  expect(screen.queryByRole("dialog", { name: "选择回答" })).not.toBeInTheDocument();
});
