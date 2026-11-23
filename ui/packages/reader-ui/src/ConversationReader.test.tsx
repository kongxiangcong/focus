import "@testing-library/jest-dom/vitest";
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { readerSuccess, type ReaderHost, type ReadingDocument, type ReadingWindow, type SourceNote, type ValidatedAnswerEvidence } from "@focus/reader-contracts";
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

it("automatically locates at most one evidence per turn", async () => {
  const app = setup(); await send();
  app.emit(answer([first]));
  await waitFor(() => expect(scrolling).toHaveBeenCalledTimes(1));
  app.emit(answer([first, second], 4));
  await waitFor(() => expect(screen.getAllByRole("button", { name: "返回相关回答" })).toHaveLength(2));
  expect(scrolling).toHaveBeenCalledTimes(1);
  expect(app.host.continueReading).not.toHaveBeenCalled();
});

it("manual reading cancels pending automatic source navigation", async () => {
  const app = setup(); await send();
  fireEvent.wheel(screen.getByLabelText("文章原文"));
  scrolling.mockClear();
  app.emit(answer([first]));
  await screen.findByRole("button", { name: "返回相关回答" });
  expect(scrolling).not.toHaveBeenCalled();
  expect(screen.queryByLabelText("原文证据")).not.toBeInTheDocument();
});

it("restores saved answers without replaying an automatic jump", async () => {
  setup(answer([first]));
  await screen.findByRole("button", { name: "返回相关回答" }, { timeout: 5000 });
  expect(scrolling).not.toHaveBeenCalled();
  expect(screen.queryByLabelText("原文证据")).not.toBeInTheDocument();
});

it("dismisses open evidence when leaving chat", async () => {
  const app = setup();
  await send();
  app.emit(answer([first]));
  const citation = await screen.findByRole("button", { name: "1" });
  fireEvent.click(citation);
  expect(screen.getByLabelText("原文证据")).toBeInTheDocument();
  app.display(false);
  app.display(true);
  expect(screen.queryByLabelText("原文证据")).not.toBeInTheDocument();
  fireEvent.click(citation);
  expect(screen.getByLabelText("原文证据")).toBeInTheDocument();
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
  expect(screen.getByLabelText("原文证据")).toBeInTheDocument();
  app.display(true);
  fireEvent.click(within(screen.getByLabelText("原文证据")).getByRole("button", { name: /证据 1/ }));
  expect(citation).toHaveFocus();
});
it("does not replay evidence when a reply arrives after leaving chat", async () => {
  const app = setup(); await send();
  app.display(false);
  app.emit(answer([first]));
  app.display(true);
  await screen.findByRole("button", { name: "返回相关回答" });
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

it.each([
  { layoutVersion: "old-layout", page: 1, outcome: "ready" },
  { layoutVersion: "new-layout", page: 0, outcome: "ready" },
  { layoutVersion: "new-layout", page: 0, outcome: "cancelled" },
  { layoutVersion: "old-layout", page: 1, outcome: "failed" },
] as const)("settles a waiting translation citation with $layoutVersion, page $page, $outcome", async ({ layoutVersion, page, outcome }) => {
  const cited = { ...first, layoutVersion, blockIds: ["current"], renderGranularity: "block" as const };
  const start = answer([cited]);
  const preparation = { source_id: "paper", status: "running" as const, step: "translation",
    total: 1, completed: 0, ready: false, error: null, plan_id: "plan" };
  let translation: ReadingDocument["translation"] = { status: "running", chunks: [] };
  const app = setup({ ...start, preparations: { paper: preparation } }, {
    sourceOriginalUrl: () => "/paper.pdf",
    getSourceDocument: async () => readerSuccess({
      sourceId: "paper", bundleVersion: "v1", title: "Paper", markdown: "# Paper\n\nFirst evidence.", lineCount: 3,
      pdf: { version: "new-layout", pdfHash: "abc", blocks: [{ blockId: "current", page, sourceLines: [3, 3], bbox: null }] },
      translation,
    }),
  });
  await screen.findByRole("button", { name: "中文译文 · 准备中" }, { timeout: 8500 });
  fireEvent.click(window.document.querySelector<HTMLElement>("[data-citation]")!);
  expect(screen.queryByLabelText("原文证据")).not.toBeInTheDocument();
  if (outcome === "cancelled") fireEvent.wheel(screen.getByLabelText("文章原文"));
  const status = outcome === "failed" ? "failed" : "ready";
  translation = { status, chunks: status === "ready" ?
    [{ id: "chunk-1", text: "已准备好的译文。", blockIds: ["current"], sourceLines: [3, 3] }] : [] };
  app.emit({ ...start, revision: 4, preparations: { paper: { ...preparation, status, ready: status === "ready" } } });
  if (outcome === "ready") {
    expect(await screen.findByText("已准备好的译文。", {}, { timeout: 8500 })).toBeVisible();
    expect(await screen.findByLabelText("原文证据")).toHaveTextContent("First evidence.");
  } else if (outcome === "cancelled") {
    await screen.findByRole("button", { name: "中文译文" }, { timeout: 8500 });
    expect(screen.getByRole("button", { name: "原版 PDF" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.queryByLabelText("原文证据")).not.toBeInTheDocument();
  } else {
    expect(await screen.findByLabelText("原文证据", {}, { timeout: 8500 })).toHaveTextContent("First evidence.");
    expect(screen.getByRole("button", { name: "原版 PDF" })).toHaveAttribute("aria-pressed", "true");
  }
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

it("returns from a block to its only linked answer even when a newer answer is selected", async () => {
  const cited = { ...first, renderGranularity: "block" as const };
  const start = answer([cited]);
  setup({ ...start, conversation: [...start.conversation, {
    ...start.conversation[0], messageId: "uncited-answer", answerRevision: "r2", content: "There's nothing to verify here.", evidence: [],
  }] });
  const source = await screen.findByLabelText("文章原文");
  fireEvent.click(await within(source).findByRole("button", { name: "返回相关回答" }));
  await waitFor(() => expect(screen.getByText("Claim", { exact: false }).closest(".source-message")).toHaveFocus());
  expect(screen.queryByLabelText("选择回答")).not.toBeInTheDocument();
});

it("offers answer excerpts for a shared block and returns an active number to its exact origin", async () => {
  const cited = { ...first, renderGranularity: "block" as const };
  const other = { ...cited, evidenceId: "c".repeat(24), messageId: "second-answer", answerRevision: "r2" };
  const start = answer([cited]);
  setup({ ...start, conversation: [
    { ...start.conversation[0], content: `The original result held [[e:${cited.evidenceId}]].` },
    { ...start.conversation[0], messageId: other.messageId, answerRevision: other.answerRevision,
      content: `The replication differed [[e:${other.evidenceId}]].\n\nThe same source supports that conclusion [[e:${other.evidenceId}]].`, evidence: [other] },
  ] });
  const source = within(await screen.findByLabelText("文章原文"));
  const conversation = within(screen.getByLabelText("文章对话"));
  const [firstNumber, , secondNumber] = await conversation.findAllByRole("button", { name: "1" });
  fireEvent.click(await source.findByRole("button", { name: "查看 2 条相关回答" }));
  const chooser = within(screen.getByRole("dialog", { name: "选择回答" }));
  expect(chooser.getByRole("button", { name: /The replication differed/ })).toBeVisible();
  fireEvent.click(chooser.getByRole("button", { name: /The original result held/ }));
  expect(firstNumber.closest(".source-message")).toHaveFocus();

  fireEvent.click(secondNumber);
  fireEvent.click(await source.findByRole("button", { name: "返回回答证据 1" }));
  expect(secondNumber).toHaveFocus();
  expect(screen.queryByRole("dialog", { name: "选择回答" })).not.toBeInTheDocument();
});
