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
function setup(start = initial) {
  let listener: ((r: ReturnType<typeof readerSuccess<ReadingWindow>>) => void) | undefined;
  const host: ReaderHost = {
    getReadingWindow: vi.fn(async () => readerSuccess(start)),
    getSourceDocument: vi.fn(async () => readerSuccess({ sourceId: "paper", bundleVersion: "v1", title: "Paper", markdown: "# Paper\n\nFirst evidence.\n\nSecond evidence.", lineCount: 5 })),
    subscribe: callback => { listener = callback; return () => { listener = undefined; }; },
    sendMessage: vi.fn(async () => readerSuccess({ ...initial, revision: 2 })),
    continueReading: vi.fn(async () => readerSuccess(initial)),
  };
  render(<ConversationReader host={host} />);
  return { host, emit: (value: ReadingWindow) => act(() => listener?.(readerSuccess(value))) };
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
  await screen.findByRole("button", { name: "返回回答证据 1" });
  expect(scrolling).not.toHaveBeenCalled();
  expect(screen.queryByLabelText("原文证据")).not.toBeInTheDocument();
});
