import "@testing-library/jest-dom/vitest";
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { readerSuccess, type ReaderHost, type ReadingWindow, type SourceNote, type ValidatedAnswerEvidence } from "@focus/reader-contracts";
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

it("scopes failed replies to their source and dismisses only the failed attempt", async () => {
  const run = { runId: "old-attempt", sourceId: "other-paper", status: "failed" as const, error: "问答未完成", approvals: [], activity: [] };
  const agent = { run, catalog: { sources: [], topics: [] } };
  const app = setup({ ...initial, agent });
  await screen.findByText("First evidence.");
  expect(screen.queryByText(run.error)).not.toBeInTheDocument();
  app.emit({ ...initial, revision: 2, agent: { ...agent, run: { ...run, sourceId: "paper" } } });
  expect(screen.getByRole("alert")).toHaveTextContent(run.error);
  fireEvent.click(within(screen.getByRole("alert")).getByRole("button", { name: "关闭" }));
  app.emit({ ...initial, revision: 3, agent: { ...agent, run: { ...run, sourceId: "paper" } } });
  expect(screen.queryByText(run.error)).not.toBeInTheDocument();
  app.emit({ ...initial, revision: 4, agent: { ...agent, run: { ...run, runId: "new-attempt", sourceId: "paper" } } });
  expect(screen.getByRole("alert")).toHaveTextContent(run.error);
});

it("keeps a note conflict through a healthy snapshot and clears it after saving the edit", async () => {
  const note: SourceNote = { noteId: "note", sourceId: "paper", revision: 1, content: "Old note",
    kind: "thought", origin: "user", evidenceRole: "explanation", bundle: "v1", anchor: null,
    referenceStatus: "current", sourceUpdated: false, deleted: false, canUndo: false };
  const current = { ...note, revision: 2, content: "Changed elsewhere" };
  const saved = { ...current, revision: 3, content: "Local edit" };
  const conflicted = { ...initial, revision: 2, sourceNotes: [current] };
  const changeSourceNote = vi.fn<NonNullable<ReaderHost["changeSourceNote"]>>()
    .mockResolvedValueOnce(readerSuccess({ ...conflicted, noteOperation: { sourceId: "paper", status: "conflict", current } }))
    .mockResolvedValueOnce(readerSuccess({ ...initial, revision: 4, sourceNotes: [saved] }));
  const app = setup({ ...initial, sourceNotes: [note] }, {
    createSourceNote: vi.fn(), changeSourceNote,
  });
  fireEvent.click(await screen.findByRole("button", { name: "笔记" }, { timeout: 10_000 }));
  fireEvent.click(screen.getByRole("button", { name: "编辑" }));
  const input = screen.getByRole("textbox", { name: "笔记内容" });
  fireEvent.change(input, { target: { value: saved.content } });
  fireEvent.click(screen.getByRole("button", { name: "保存笔记" }));
  const conflict = await screen.findByRole("alert");
  expect(conflict).toHaveTextContent("笔记已更新");
  app.emit({ ...conflicted, revision: 3 });
  expect(conflict).toBeVisible();
  expect(input).toHaveValue(saved.content);
  fireEvent.click(screen.getByRole("button", { name: "保存笔记" }));
  await waitFor(() => expect(screen.queryByRole("alert")).not.toBeInTheDocument());
  expect(changeSourceNote.mock.calls[1]?.[3]).toBe(current.revision);
});

it("highlights a fully visible quotation without moving the source or opening a panel", async () => {
  vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockImplementation(function (this: HTMLElement) {
    return this.matches("mark") ? new DOMRect(0, 150, 100, 20) : new DOMRect(0, 0, 100, 400);
  });
  setup(answer([first]));
  const conversation = within(await screen.findByLabelText("文章对话"));
  fireEvent.click(await conversation.findByRole("button", { name: "1" }), { detail: 1 });
  const source = within(screen.getByLabelText("文章原文"));
  expect(source.getByText("First evidence.")).toHaveClass("is-active");
  expect(scrolling).not.toHaveBeenCalled();
  expect(screen.queryByLabelText("原文证据")).not.toBeInTheDocument();
});

it("shows only the verified original block in place when an older Host has no validated translation mapping", async () => {
  const sourceDocument = { sourceId: "paper", bundleVersion: "v1", title: "Paper", markdown: "# Paper\n\nFirst evidence.\n\nSecond evidence. Second evidence.", lineCount: 5,
    translation: { status: "ready", planId: "plan", chunks: [{ id: "chunk-1", sourceLines: [1, 5] as const, blockIds: [],
      text: "# 论文\n\n译文中的第二段。\n\n译文中的第一段。" }] } };
  setup(answer([first, second]), { getSourceDocument: async () => readerSuccess(sourceDocument) });
  const source = within(await screen.findByLabelText("文章原文"));
  const translated = await screen.findByRole("button", { name: "中文译文" });
  fireEvent.click(translated);
  expect(source.queryByText(first.quote.exact)).not.toBeInTheDocument();

  const chat = within(screen.getByLabelText("文章对话"));
  const citation = await chat.findByRole("button", { name: "1" });
  fireEvent.click(citation, { detail: 1 });
  expect(translated).toHaveAttribute("aria-pressed", "true");
  const originalBlock = source.getByRole("region", { name: "原文证据" });
  expect(within(originalBlock).getByText(first.quote.exact)).toHaveClass("is-active");
  expect(source.queryByText(/Second evidence/)).not.toBeInTheDocument();
  expect(source.getByText("译文中的第一段。").closest("[data-evidence-block]")).toBeNull();
  fireEvent.click(chat.getByRole("button", { name: "2" }));
  expect(within(originalBlock).getByText(first.quote.exact)).toHaveClass("is-active");
  expect(source.queryByText(/Second evidence/)).not.toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "原文", exact: true }));
  expect(source.getByText(first.quote.exact)).toHaveClass("is-active");
  expect(source.queryByRole("region", { name: "原文证据" })).not.toBeInTheDocument();
  fireEvent.click(translated);
  fireEvent.click(within(source.getByRole("region", { name: "原文证据" })).getByRole("button", { name: "返回回答证据 1" }));
  expect(citation).toHaveFocus();
});

it("saves the selected occurrence across chunks and leaves an overlapping highlight after deletion", async () => {
  const markdown = "同词以及**同词😀**\n然后继续。";
  const document = { sourceId: "paper", bundleVersion: "v1", title: "Paper", markdown, lineCount: 2,
    readingPlan: { planId: "plan", chunks: [{ chunkId: "c0", sourceOffsets: [0, 11] as const }, { chunkId: "c1", sourceOffsets: [12, 17] as const }] } };
  const highlight = { highlightId: "highlight", sourceId: "paper", revision: 1, bundle: "v1", sourceLines: [1, 2] as const,
    deleted: false, canUndo: false, sourceUpdated: false, planId: "plan", chunkId: "c0", layer: "source" as const,
    range: { start: 4, end: 6 }, quote: { exact: "同词", prefix: "同词以及", suffix: "😀\n然后继续。" } };
  const start = { ...initial, sourceHighlights: [highlight] };
  const selection = { layer: "source" as const, planId: "plan", bundleVersion: "v1",
    ranges: [{ start: 6, end: 9 }, { start: 11, end: 14 }] };
  const note: SourceNote = { noteId: "one-note", sourceId: "paper", revision: 1, content: "我的笔记",
    kind: "thought", origin: "user", evidenceRole: "explanation", bundle: "v1", anchor: null,
    referenceStatus: "current", sourceUpdated: false, deleted: false, canUndo: false,
    selection: { ...selection, chunkIds: ["c0", "c1"] } };
  const createSourceNote = vi.fn<NonNullable<ReaderHost["createSourceNote"]>>().mockResolvedValue(readerSuccess({ ...start, revision: 2, sourceNotes: [note] }));
  setup(start, {
    getSourceDocument: async () => readerSuccess(document),
    createSourceNote,
    changeSourceNote: async () => readerSuccess({ ...start, revision: 3, sourceNotes: [] }),
  });
  const pane = await screen.findByLabelText("文章原文");
  await waitFor(() => expect(pane.querySelector("strong")).toHaveTextContent("同词😀"));
  const paragraph = pane.querySelector("p")!;
  function selectAcrossChunks() {
    const range = window.document.createRange();
    range.setStart(paragraph.querySelector("strong")!, 0);
    range.setEnd(paragraph.lastChild!, 3);
    window.getSelection()!.removeAllRanges();
    window.getSelection()!.addRange(range);
    fireEvent(window.document, new Event("selectionchange"));
  }
  selectAcrossChunks();
  fireEvent.click(screen.getByRole("button", { name: "记笔记" }));
  fireEvent.click(screen.getByRole("button", { name: "关闭笔记" }));
  expect(createSourceNote).not.toHaveBeenCalled();
  expect(pane.querySelector(".reader-anno--shared-note")).toBeNull();

  selectAcrossChunks();
  fireEvent.click(screen.getByRole("button", { name: "记笔记" }));
  fireEvent.change(screen.getByRole("textbox", { name: "笔记内容" }), { target: { value: note.content } });
  fireEvent.click(screen.getByRole("button", { name: "保存笔记" }));
  await screen.findByText(note.content);
  expect(createSourceNote).toHaveBeenCalledWith(expect.objectContaining({ selection }));
  expect(pane.textContent).toContain("同词以及同词😀\n然后继续。");
  expect([...pane.querySelectorAll(".reader-anno--shared-note")].map(mark => mark.textContent).join("")).toBe("同词😀\n然后");
  fireEvent.click(screen.getByRole("button", { name: "删除" }));
  await waitFor(() => expect(pane.querySelector(".reader-anno--shared-note")).toBeNull());
  expect([...pane.querySelectorAll(".reader-anno--hl")].map(mark => mark.textContent).join("")).toBe("同词");
});

it("automatically locates at most one evidence per turn", async () => {
  const app = setup(); await send();
  app.emit(answer([first]));
  await waitFor(() => expect(scrolling).toHaveBeenCalledTimes(1));
  app.emit(answer([first, second], 4));
  await waitFor(() => expect(screen.getAllByRole("button", { name: /返回回答证据/ })).toHaveLength(2));
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

it("does not replay a source jump when returning to the conversation", async () => {
  const app = setup(answer([first]));
  const conversation = within(await screen.findByLabelText("文章对话"));
  const citation = await conversation.findByRole("button", { name: "1" });
  fireEvent.click(citation);
  const source = within(screen.getByLabelText("文章原文"));
  expect(source.getByText("First evidence.")).toHaveClass("is-active");
  scrolling.mockClear();
  app.display(false);
  app.display(true);
  expect(scrolling).not.toHaveBeenCalled();
  expect(source.getByRole("button", { name: "返回回答证据 1" })).toBeInTheDocument();
});

it("keeps the evidence and return-to-answer focus when exiting fullscreen", async () => {
  const app = setup(answer([first]));
  app.display(true, true);
  const citation = await waitFor(() => {
    const button = window.document.querySelector<HTMLButtonElement>("[data-citation]");
    expect(button).toBeInTheDocument();
    return button!;
  }, { timeout: 10_000 });
  fireEvent.click(citation);
  expect(screen.getByText("First evidence.")).toHaveClass("is-active");
  app.display(true);
  fireEvent.click(screen.getByRole("button", { name: "返回回答证据 1" }));
  expect(citation).toHaveFocus();
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
  { scenario: "a changed bundle", evidence: { ...first, bundleVersion: "older" } },
  { scenario: "a missing context match", evidence: { ...first, quote: { ...first.quote, suffix: " different context" } } },
  { scenario: "a missing range", evidence: { ...first, sourceLines: [] as unknown as ValidatedAnswerEvidence["sourceLines"] } },
  { scenario: "an absent legacy range", evidence: { ...first, sourceLines: undefined as unknown as ValidatedAnswerEvidence["sourceLines"] } },
  { scenario: "a malformed legacy range", evidence: { ...first, sourceLines: {} as unknown as ValidatedAnswerEvidence["sourceLines"] } },
])("leaves the reading position and previous highlight intact after $scenario", async ({ evidence }) => {
  setup(answer([second, evidence]));
  const conversation = within(await screen.findByLabelText("文章对话"));
  fireEvent.click(await conversation.findByRole("button", { name: "2" }));
  const source = screen.getByLabelText("文章原文");
  source.scrollTop = 120;
  scrolling.mockClear();
  fireEvent.click(conversation.getByRole("button", { name: "1" }));
  expect(source).toHaveProperty("scrollTop", 120);
  expect(scrolling).not.toHaveBeenCalled();
  expect(within(source).getByText("Second evidence.")).toHaveClass("is-active");
  expect(within(source).queryByRole("button", { name: "返回回答证据 1" })).not.toBeInTheDocument();
  expect(screen.queryByLabelText("原文证据")).not.toBeInTheDocument();
});

it("returns from a block to its only linked answer even when a newer answer is selected", async () => {
  const cited = { ...first, renderGranularity: "block" as const };
  const start = answer([cited]);
  setup({ ...start, conversation: [...start.conversation, {
    ...start.conversation[0], messageId: "uncited-answer", answerRevision: "r2", content: "There's nothing to verify here.", evidence: [],
  }] });
  const source = await screen.findByLabelText("文章原文");
  fireEvent.click(await within(source).findByRole("button", { name: "返回回答证据 1" }));
  expect(within(screen.getByLabelText("文章对话")).getByRole("button", { name: "1" })).toHaveFocus();
  expect(screen.queryByLabelText("选择回答")).not.toBeInTheDocument();
});

it("returns from a shared source block to the selected answer and the exact originating button", async () => {
  const cited = { ...first, renderGranularity: "block" as const };
  const other = { ...cited, evidenceId: "c".repeat(24), messageId: "second-answer", answerRevision: "r2", displayNumber: 2 };
  const start = answer([cited]);
  setup({ ...start, conversation: [
    { ...start.conversation[0], content: `The original result held [[e:${cited.evidenceId}]].` },
    { ...start.conversation[0], messageId: other.messageId, answerRevision: other.answerRevision,
      content: `The replication differed [[e:${other.evidenceId}]].\n\nThe same source supports that conclusion [[e:${other.evidenceId}]].`, evidence: [other] },
  ] });
  const source = within(await screen.findByLabelText("文章原文"));
  const conversation = within(screen.getByLabelText("文章对话"));
  const firstNumber = await conversation.findByRole("button", { name: "1" });
  const [firstOccurrence, secondOccurrence] = conversation.getAllByRole("button", { name: "2" });
  fireEvent.click(await source.findByRole("button", { name: "返回回答证据 2" }));
  expect(firstOccurrence).toHaveFocus();

  fireEvent.click(conversation.getByText(/The original result held/));
  fireEvent.click(source.getByRole("button", { name: "返回回答证据 1" }));
  expect(firstNumber).toHaveFocus();

  fireEvent.click(secondOccurrence);
  fireEvent.click(source.getByRole("button", { name: "返回回答证据 2" }));
  expect(secondOccurrence).toHaveFocus();
  expect(screen.queryByRole("dialog", { name: "选择回答" })).not.toBeInTheDocument();
});
