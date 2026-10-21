import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { readerSuccess, type ReaderHost, type ReadingWindow, type SourceNote } from "@focus/reader-contracts";
import { FocusReader } from "./FocusReader";

beforeEach(() => {
  localStorage.clear(); sessionStorage.clear();
  HTMLElement.prototype.scrollIntoView = vi.fn();
  HTMLElement.prototype.scrollTo = vi.fn();
  HTMLDialogElement.prototype.showModal = function () { this.setAttribute("open", ""); };
  HTMLDialogElement.prototype.close = function () { this.removeAttribute("open"); };
});
afterEach(cleanup);
const chunk = { sourceId: "source", planId: "plan", chunkId: "first", index: 1, total: 3, bundleVersion: "v1",
  sectionPath: ["第一段"], sourceLines: [1, 10] as const, sourceMarkdown: "第一段原文", translation: null, images: [], relevantGlossary: [], presentationStatus: "source-ready" as const };
const second = { ...chunk, chunkId: "second", index: 2, sourceLines: [11, 20] as const, sourceMarkdown: "第二段原文" };
const note: SourceNote = { noteId: "n1", sourceId: "source", revision: 1, bundle: "v1", content: "第一段的**笔记**",
  kind: "thought", origin: "user", evidenceRole: "explanation", anchor: { sourceId: "source", bundle: "v1", sourceLines: [2, 4] },
  referenceStatus: "current", sourceUpdated: false, deleted: false, canUndo: false };
const view: ReadingWindow = { status: "reading", source: { sourceId: "source", title: "示例", topicId: null }, sessionId: "s1",
  current: second, navigationCurrent: second, history: [chunk], sourceNotes: [note, { ...note, noteId: "unanchored", anchor: null, content: "整篇笔记" }],
  conversation: [{ messageId: "m1", chunkId: "first", role: "assistant", content: "仍在阅读流中的讨论", reference: { sourceId: "source", planId: "plan", chunkId: "first" } }],
  timeline: [{ kind: "reading", chunk }, { kind: "reading", chunk: second }, { kind: "message", messageId: "m1" }] };
function setup() {
  const host: ReaderHost = { getReadingWindow: vi.fn(async () => readerSuccess(view)), continueReading: vi.fn(), sendMessage: vi.fn(async () => readerSuccess(view)) };
  const result = render(<FocusReader host={host} appearance="mist" fullscreen={false} />);
  return { host, ...result };
}

it("shows anchored notes without fullscreen or a minimum width and keeps discussion in order", async () => {
  localStorage.setItem("focus.attachDiscussion", "true");
  const { container } = setup();
  const first = await screen.findByRole("complementary", { name: "第 1 段笔记" });
  expect(first).toHaveTextContent("第一段的笔记");
  expect(first).not.toHaveTextContent("整篇笔记");
  expect(first).not.toHaveTextContent("仍在阅读流中的讨论");
  expect(screen.getByRole("complementary", { name: "第 2 段笔记" })).toHaveTextContent("本段还没有笔记");
  expect(container.querySelector(".focus-reader")).toHaveAttribute("data-notes-layout", "split");
  expect(container.querySelector('[data-lens-index="2"] .reading-group-discussion')).toHaveTextContent("仍在阅读流中的讨论");
  expect(localStorage.getItem("focus.attachDiscussion")).toBeNull();
});

it("toggles only note presentation, preserving source nodes, draft and host state", async () => {
  const { host } = setup();
  const source = await screen.findByText("第一段原文");
  fireEvent.change(screen.getByRole("textbox"), { target: { value: "保留草稿" } });
  const toggle = within(screen.getByRole("navigation", { name: "阅读功能控制区" })).getByRole("button", { name: "笔记" });
  fireEvent.click(toggle);
  expect(screen.queryByRole("complementary", { name: "第 1 段笔记" })).not.toBeInTheDocument();
  expect(screen.getByText("第一段原文")).toBe(source);
  expect(screen.getByRole("textbox")).toHaveValue("保留草稿");
  expect(localStorage.getItem("focus.attachNotes")).toBe("false");
  fireEvent.click(toggle);
  expect(screen.getByRole("complementary", { name: "第 1 段笔记" })).toBeVisible();
  expect(host.continueReading).not.toHaveBeenCalled();
  expect(host.sendMessage).not.toHaveBeenCalled();
});

it("discusses the chosen historical paragraph while preserving the current reading cursor", async () => {
  const { host } = setup();
  const notes = await screen.findByRole("complementary", { name: "第 1 段笔记" });
  fireEvent.click(screen.getByRole("button", { name: "收起" }));
  fireEvent.click(within(notes).getByRole("button", { name: "就这段讨论" }));
  expect(screen.getByRole("button", { name: /引用第 1 段/ })).toBeInTheDocument();
  await waitFor(() => expect(screen.getByRole("textbox")).toHaveFocus());
  fireEvent.change(screen.getByRole("textbox"), { target: { value: "这段如何理解？" } });
  fireEvent.click(screen.getByRole("button", { name: "发送" }));
  await waitFor(() => expect(host.sendMessage).toHaveBeenCalledWith(expect.objectContaining({
    receipt: expect.objectContaining({ chunkId: "first" }), content: "这段如何理解？",
  })));
  expect(host.continueReading).not.toHaveBeenCalled();
});

it("opens the matching note editor in materials while keeping paragraph notes available", async () => {
  const { host } = setup();
  const notes = await screen.findByRole("complementary", { name: "第 1 段笔记" });
  fireEvent.click(within(notes).getByRole("button", { name: "编辑" }));
  const editor = await screen.findByRole("textbox", { name: "编辑笔记" });
  expect(editor).toHaveValue(note.content);
  await waitFor(() => expect(editor).toHaveFocus());
  expect(notes).toBeVisible();
  expect(screen.getByRole("region", { name: "阅读资料侧栏" })).toBeVisible();
  expect(host.continueReading).not.toHaveBeenCalled();
});

it("places latest/review notices in the dock and removes the new-session action", async () => {
  const { container } = setup();
  await screen.findByText("第一段原文");
  const controls = screen.getByRole("navigation", { name: "阅读功能控制区" });
  const pane = screen.getByRole("main", { name: "阅读与对话" });
  Object.defineProperties(pane, { scrollHeight: { value: 2000 }, clientHeight: { value: 500 } });
  Object.defineProperty(pane.lastElementChild!.previousElementSibling!, "offsetTop", { value: 2000 });
  fireEvent.wheel(pane, { deltaY: -100 });
  pane.scrollTop = 150; fireEvent.scroll(pane);
  const latest = await screen.findByRole("button", { name: /^回到最新/ });
  expect(controls).toContainElement(latest);
  expect(container.querySelector(".focus-new-content")).toBeNull();
  expect(within(controls).queryByRole("button", { name: "新会话" })).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "关闭回到最新提示" }));
  expect(screen.queryByRole("button", { name: /^回到最新/ })).not.toBeInTheDocument();
});
