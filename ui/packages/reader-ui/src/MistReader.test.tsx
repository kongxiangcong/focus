import "@testing-library/jest-dom/vitest";
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { readerSuccess, type ReaderHost, type ReadingWindow } from "@focus/reader-contracts";
import { FocusReader } from "./FocusReader";

afterEach(cleanup);
beforeEach(() => {
  HTMLElement.prototype.scrollIntoView = vi.fn();
  HTMLElement.prototype.scrollTo = vi.fn();
  HTMLDialogElement.prototype.showModal = function () { this.setAttribute("open", ""); };
  HTMLDialogElement.prototype.close = function () { this.removeAttribute("open"); };
});
const current = { sourceId: "demo-paper", planId: "plan-001", chunkId: "chunk-001", index: 1, total: 2,
  sectionPath: ["Method"], sourceLines: [1, 4] as const, sourceMarkdown: "![Figure](images/image-001.png)\n\nOriginal paragraph.",
  translation: null, images: [], relevantGlossary: [], presentationStatus: "source-ready" as const };
const first: ReadingWindow = { status: "reading", sessionId: "s1", source: { sourceId: "demo-paper", title: "Demo", topicId: null }, current, history: [], conversation: [] };
function setup() {
  const next = { ...current, chunkId: "chunk-002", index: 2, sectionPath: ["Results"] };
  const second: ReadingWindow = { ...first, current: next, history: [current] };
  const host: ReaderHost = {
    getReadingWindow: vi.fn(async () => readerSuccess(first)),
    continueReading: vi.fn(async () => readerSuccess(second)),
    sendMessage: vi.fn(async () => readerSuccess(second)),
  };
  render(<FocusReader host={host} appearance="mist" />);
  return host;
}
it("disables unread navigation, advances once, and reviews history without moving the Cursor", async () => {
  const host = setup();
  const nav = await screen.findByRole("navigation", { name: "段落目录" });
  await waitFor(() => expect(within(nav).getByRole("button", { name: /02/ })).toBeDisabled());
  fireEvent.click(screen.getByRole("button", { name: "继续" }));
  await screen.findByRole("heading", { name: "Results" });
  expect(host.continueReading).toHaveBeenCalledTimes(1);
  fireEvent.click(within(nav).getByRole("button", { name: /01.*Method/ }));
  expect(host.continueReading).toHaveBeenCalledTimes(1);
  fireEvent.change(screen.getByRole("textbox"), { target: { value: "这段是什么意思？" } });
  fireEvent.click(screen.getByRole("button", { name: "发送 ↑" }));
  await waitFor(() => expect(host.sendMessage).toHaveBeenCalledWith(expect.objectContaining({ receipt: expect.objectContaining({ chunkId: "chunk-001" }) })));
  expect(host.continueReading).toHaveBeenCalledTimes(1);
});
it("renders bundle images and preserves the draft when collapsing the composer", async () => {
  setup();
  const image = await screen.findByRole("img", { name: "Figure" });
  expect(image).toHaveAttribute("src", "/reader/assets/demo-paper/images/image-001.png");
  fireEvent.change(screen.getByRole("textbox"), { target: { value: "草稿" } });
  fireEvent.click(screen.getByRole("button", { name: "收起" }));
  expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "展开" }));
  expect(screen.getByRole("textbox")).toHaveValue("草稿");
});
it("keeps upload and attachment actions out of the Mist reading workspace", async () => {
  const host: ReaderHost = {
    getReadingWindow: vi.fn(async () => readerSuccess(first)),
    continueReading: vi.fn(async () => readerSuccess(first)),
    sendMessage: vi.fn(async () => readerSuccess(first)),
    upload: vi.fn(),
  };
  render(<FocusReader host={host} appearance="mist" />);
  await screen.findByRole("heading", { name: "Method" });
  expect(screen.queryByRole("button", { name: /附件|上传/ })).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "材料" }));
  expect(screen.queryByRole("button", { name: /附件|上传/ })).not.toBeInTheDocument();
  expect(host.upload).not.toHaveBeenCalled();
});
it("streams one assistant card into the central timeline and keeps only prompts in Companion", async () => {
  let emit!: Parameters<NonNullable<ReaderHost["subscribe"]>>[0];
  const unsubscribe = vi.fn();
  const prompt = { messageId: "u1", chunkId: current.chunkId, role: "user" as const, content: "解释共享存储" };
  const answer = { messageId: "a1", chunkId: current.chunkId, role: "assistant" as const, content: "先确定 **生命周期**。" };
  const pending: ReadingWindow = { ...first, revision: 2, conversation: [prompt], timeline: [{ kind: "reading", chunk: current }, { kind: "message", messageId: "u1" }] };
  const host: ReaderHost = {
    getReadingWindow: vi.fn(async () => readerSuccess({ ...first, revision: 1 })),
    continueReading: vi.fn(async () => readerSuccess(first)),
    sendMessage: vi.fn(async () => readerSuccess(pending)),
    subscribe: callback => { emit = callback; return unsubscribe; },
  };
  const app = render(<FocusReader host={host} appearance="mist" />);
  await screen.findByRole("heading", { name: "Method" });
  fireEvent.change(screen.getByRole("textbox"), { target: { value: prompt.content } });
  fireEvent.click(screen.getByRole("button", { name: "发送 ↑" }));
  const companion = screen.getByRole("complementary", { name: "阅读助手" });
  await within(screen.getByRole("navigation", { name: "历史提问" })).findByRole("button", { name: prompt.content });
  // Partial timeline deliberately omits the streaming message reference.
  act(() => emit(readerSuccess({ ...pending, revision: 3, conversation: [prompt, answer] })));
  const stream = screen.getByRole("main", { name: "阅读与对话" });
  expect(within(stream).getByText("生命周期").tagName).toBe("STRONG");
  expect(within(companion).queryByText("生命周期")).not.toBeInTheDocument();
  expect(stream.querySelectorAll(".focus-reader__chunk")).toHaveLength(2);
  expect([...stream.querySelectorAll("article")].map(el => el.getAttribute("data-role"))).toEqual([null, "user", "assistant"]);
  act(() => emit(readerSuccess({ ...pending, revision: 4, conversation: [prompt, { ...answer, content: "完成后的唯一回复" }] })));
  expect(within(stream).getAllByText("完成后的唯一回复")).toHaveLength(1);
  act(() => emit(readerSuccess({ ...pending, revision: 3, conversation: [prompt, answer] })));
  expect(within(stream).queryByText("生命周期")).not.toBeInTheDocument();
  expect(host.continueReading).not.toHaveBeenCalled();
  app.unmount(); expect(unsubscribe).toHaveBeenCalledOnce();
});
it("shows immediate feedback and locks task-changing actions through startup and streaming", async () => {
  let emit!: Parameters<NonNullable<ReaderHost["subscribe"]>>[0];
  let resolve!: (value: ReturnType<typeof readerSuccess<ReadingWindow>>) => void;
  const running: ReadingWindow = { ...first, agent: {
    catalog: { sources: [], topics: [] },
    run: { runId: "run1", status: "running", error: null, approvals: [], activity: [],
      progress: { label: "连接助手", startedAt: Date.now(), updatedAt: Date.now() } },
  } };
  const host: ReaderHost = {
    getReadingWindow: vi.fn(async () => readerSuccess(first)),
    continueReading: vi.fn(() => new Promise<ReturnType<typeof readerSuccess<ReadingWindow>>>(r => { resolve = r; })),
    sendMessage: vi.fn(), newSession: vi.fn(),
    stop: vi.fn(async () => readerSuccess({ ...running, agent: { ...running.agent!, run: { ...running.agent!.run!, status: "stopping" as const } } })),
    subscribe: callback => { emit = callback; return () => {}; },
  };
  render(<FocusReader host={host} appearance="mist" />);
  await screen.findByRole("heading", { name: "Method" });
  fireEvent.change(screen.getByRole("textbox"), { target: { value: "保留草稿" } });
  fireEvent.click(screen.getByRole("button", { name: "继续" }));
  expect(screen.getByRole("status")).toHaveTextContent("正在打开下一段");
  expect(screen.getByRole("textbox")).toBeDisabled();
  expect(screen.getByRole("button", { name: "新会话" })).toBeDisabled();
  fireEvent.click(screen.getByRole("button", { name: "打开中" }));
  expect(host.continueReading).toHaveBeenCalledTimes(1);
  await act(async () => resolve(readerSuccess(running)));
  expect(screen.getByRole("status")).toHaveTextContent("连接助手");
  expect(screen.getByRole("textbox")).toBeDisabled();
  fireEvent.click(screen.getByRole("button", { name: "收起" }));
  expect(screen.getByRole("status")).toBeVisible();
  fireEvent.click(screen.getByRole("button", { name: "停止" }));
  await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("正在停止"));
  expect(host.stop).toHaveBeenCalledOnce();
  act(() => emit(readerSuccess({ ...running, agent: { ...running.agent!, run: { ...running.agent!.run!, status: "interrupted" } } })));
  fireEvent.click(screen.getByRole("button", { name: "展开" }));
  expect(screen.getByRole("textbox")).toBeEnabled();
  expect(screen.getByRole("textbox")).toHaveValue("保留草稿");
  expect(host.sendMessage).not.toHaveBeenCalled();
  expect(host.newSession).not.toHaveBeenCalled();
});
