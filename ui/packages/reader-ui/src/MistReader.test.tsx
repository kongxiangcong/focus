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
  await screen.findByRole("heading", { name: "Method" });
  fireEvent.click(screen.getByRole("button", { name: "当前阅读位置" }));
  expect(within(screen.getByRole("navigation", { name: "已读段落" })).getByRole("button", { name: /第 2 段/ })).toBeDisabled();
  fireEvent.click(screen.getByRole("button", { name: "关闭" }));
  fireEvent.click(screen.getByRole("button", { name: "继续" }));
  await screen.findByRole("heading", { name: "Results" });
  expect(host.continueReading).toHaveBeenCalledTimes(1);
  fireEvent.click(screen.getByRole("button", { name: "当前阅读位置" }));
  fireEvent.click(within(screen.getByRole("navigation", { name: "已读段落" })).getByRole("button", { name: /第 1 段.*Method/ }));
  expect(host.continueReading).toHaveBeenCalledTimes(1);
  fireEvent.change(screen.getByRole("textbox"), { target: { value: "这段是什么意思？" } });
  fireEvent.click(screen.getByRole("button", { name: "发送" }));
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
  fireEvent.click(screen.getByRole("button", { name: "提问" }));
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
  expect(screen.queryByRole("button", { name: "材料" })).not.toBeInTheDocument();
  expect(host.upload).not.toHaveBeenCalled();
});
it("renders rich Markdown and the referenced source figure in the assistant output", async () => {
  const figure = { src: "/reader/assets/demo-paper/images/image-001.png", caption: "图 1 LP5X-PIM 架构" };
  const answer = { messageId: "a1", chunkId: current.chunkId, sourceId: current.sourceId, role: "assistant" as const,
    content: "## 2.1 硬件建模\n\n**内存控制器：**处理请求，==逐周期检查==时序（图 1）。" };
  const window: ReadingWindow = { ...first, figures: [figure], conversation: [answer] };
  const host: ReaderHost = { getReadingWindow: vi.fn(async () => readerSuccess(window)), continueReading: vi.fn(), sendMessage: vi.fn() };
  render(<FocusReader host={host} appearance="mist" />);
  const output = (await screen.findByText("内存控制器：")).closest("article")!;
  expect(within(output).getByRole("heading", { name: "2.1 硬件建模" })).toBeVisible();
  expect(within(output).getByText("内存控制器：").tagName).toBe("STRONG");
  expect(within(output).getByText("逐周期检查").tagName).toBe("MARK");
  expect(within(output).getByRole("img")).toHaveAttribute("src", figure.src);
  fireEvent.click(within(output).getByRole("button", { name: "放大图 1" }));
  expect(screen.getByRole("dialog", { name: "图片放大" }).querySelector("img")).toHaveAttribute("src", figure.src);
});
it("renders an explicit Markdown image in an answer without duplicating the figure", async () => {
  const illustrated = { ...current, images: [{ src: "/reader/assets/demo-paper/images/image-001.png", caption: "图 1 架构" }] };
  const answer = { messageId: "a2", chunkId: current.chunkId, sourceId: current.sourceId, role: "assistant" as const,
    content: "图 1：![架构](images/image-001.png)" };
  const host: ReaderHost = { getReadingWindow: vi.fn(async () => readerSuccess({ ...first, current: illustrated, conversation: [answer] })), continueReading: vi.fn(), sendMessage: vi.fn() };
  render(<FocusReader host={host} appearance="mist" />);
  const output = (await screen.findByText("图 1：")).closest("article")!;
  expect(within(output).getAllByRole("img")).toHaveLength(1);
  expect(within(output).getAllByRole("button", { name: "查看图 1" })).toHaveLength(1);
});
it("only resolves figure references to bound images from the same source", async () => {
  const illustrated = { ...current, images: [
    { src: "/reader/assets/demo-paper/images/fig1.png", caption: "Figure 1. System" },
    { src: "/reader/assets/demo-paper/images/fig10.png", caption: "Figure 10. Other" },
  ] };
  const answer = { messageId: "a3", chunkId: current.chunkId, sourceId: "another-paper", role: "assistant" as const, content: "见图 1。" };
  const host: ReaderHost = { getReadingWindow: vi.fn(async () => readerSuccess({ ...first, current: illustrated, conversation: [answer] })), continueReading: vi.fn(), sendMessage: vi.fn() };
  render(<FocusReader host={host} appearance="mist" />);
  const output = (await screen.findByText("见图 1。")).closest("article")!;
  expect(within(output).queryByRole("img")).not.toBeInTheDocument();
});
it("streams one assistant card into the central timeline and keeps only prompts in Companion", async () => {
  let emit!: Parameters<NonNullable<ReaderHost["subscribe"]>>[0];
  const unsubscribe = vi.fn();
  const prompt = { messageId: "u1", chunkId: current.chunkId, role: "user" as const, content: "解释共享存储" };
  const answer = { messageId: "a1", chunkId: current.chunkId, role: "assistant" as const, content: "先确定 **生命周期**。" };
  const pending: ReadingWindow = { ...first, revision: 2, conversation: [prompt], timeline: [{ kind: "reading" as const, chunk: current }, { kind: "message", messageId: "u1" }] };
  const host: ReaderHost = {
    getReadingWindow: vi.fn(async () => readerSuccess({ ...first, revision: 1 })),
    continueReading: vi.fn(async () => readerSuccess(first)),
    sendMessage: vi.fn(async () => readerSuccess(pending)),
    subscribe: callback => { emit = callback; return unsubscribe; },
  };
  const app = render(<FocusReader host={host} appearance="mist" />);
  await screen.findByRole("heading", { name: "Method" });
  fireEvent.change(screen.getByRole("textbox"), { target: { value: prompt.content } });
  fireEvent.click(screen.getByRole("button", { name: "发送" }));
  const companion = screen.getByRole("complementary", { name: "阅读助手" });
  await within(screen.getByRole("main", { name: "阅读与对话" })).findByText(prompt.content);
  expect(screen.queryByRole("navigation", { name: "历史提问" })).not.toBeInTheDocument();
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
  expect(screen.queryByRole("button", { name: "新会话" })).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "打开中…" }));
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
  fireEvent.click(screen.getByRole("button", { name: "提问" }));
  expect(screen.getByRole("textbox")).toBeEnabled();
  expect(screen.getByRole("textbox")).toHaveValue("保留草稿");
  expect(host.sendMessage).not.toHaveBeenCalled();
  expect(host.newSession).not.toHaveBeenCalled();
});

it("T3/T6 appends chunks chronologically and sends a pre-navigation draft with its original receipt", async () => {
  const next = { ...current, chunkId: "chunk-002", index: 2, sectionPath: ["Results"] };
  const second: ReadingWindow = { ...first, readingRevision: 2, current: next, history: [current],
    timeline: [{ kind: "reading" as const, chunk: current, eventId: "r1" }, { kind: "reading" as const, chunk: next, eventId: "r2" }] };
  const host: ReaderHost = { getReadingWindow: vi.fn(async () => readerSuccess({ ...first, readingRevision: 1,
    timeline: [{ kind: "reading" as const, chunk: current, eventId: "r1" }] })),
    continueReading: vi.fn(async () => readerSuccess(second)), sendMessage: vi.fn(async () => readerSuccess(second)) };
  render(<FocusReader host={host} appearance="mist" />);
  await screen.findByRole("heading", { name: "Method" });
  fireEvent.change(screen.getByRole("textbox"), { target: { value: "第一段的草稿" } });
  fireEvent.click(screen.getByRole("button", { name: "继续" }));
  await screen.findByRole("heading", { name: "Results" });
  expect(screen.getByRole("heading", { name: "Method" })).toBeInTheDocument();
  expect([...document.querySelectorAll(".focus-output")].map(el => el.getAttribute("data-event-id"))).toEqual(["r1", "r2"]);
  fireEvent.click(screen.getByRole("button", { name: "发送" }));
  await waitFor(() => expect(host.sendMessage).toHaveBeenCalledWith(expect.objectContaining({ receipt: expect.objectContaining({ chunkId: "chunk-001", planId: current.planId }) })));
});

it("T4 respects manual scrolling while streaming without an extra latest-content badge", async () => {
  let emit!: Parameters<NonNullable<ReaderHost["subscribe"]>>[0];
  const host: ReaderHost = { getReadingWindow: vi.fn(async () => readerSuccess(first)), continueReading: vi.fn(), sendMessage: vi.fn(),
    subscribe: callback => { emit = callback; return () => {}; } };
  render(<FocusReader host={host} appearance="mist" />);
  await screen.findByRole("heading", { name: "Method" });
  const pane = screen.getByRole("main", { name: "阅读与对话" });
  const scroll = vi.fn(); pane.scrollTo = scroll;
  fireEvent.wheel(pane);
  scroll.mockClear();
  act(() => emit(readerSuccess({ ...first, revision: 2, conversation: [{ messageId: "stream", chunkId: current.chunkId, role: "assistant", content: "partial" }] })));
  expect(scroll).not.toHaveBeenCalled();
  expect(screen.queryByRole("button", { name: "查看新内容" })).not.toBeInTheDocument();
  expect(screen.getByText("partial")).toBeInTheDocument();
});

it("T7/T8 a fresh session is blank and uses the persisted frontier for Continue", async () => {
  const blank: ReadingWindow = { ...first, current: null, navigationCurrent: current, sessionFresh: true,
    readingRevision: 8, readingStarted: true, history: [], timeline: [] };
  const host: ReaderHost = { getReadingWindow: vi.fn(async () => readerSuccess(blank)), continueReading: vi.fn(async () => readerSuccess(first)), sendMessage: vi.fn() };
  render(<FocusReader host={host} appearance="mist" />);
  await screen.findByRole("button", { name: "继续" });
  expect(document.querySelectorAll(".focus-output")).toHaveLength(0);
  fireEvent.click(screen.getByRole("button", { name: "继续" }));
  await waitFor(() => expect(host.continueReading).toHaveBeenCalledWith(expect.objectContaining({ receipt: expect.objectContaining({ chunkId: current.chunkId, readingRevision: 8 }) })));
});

it("places image/notes toggle and fullscreen in the Mist function row", async () => {
  const host: ReaderHost = { getReadingWindow: vi.fn(async () => readerSuccess(first)),
    continueReading: vi.fn(), sendMessage: vi.fn() };
  const toggle = vi.fn();
  render(<FocusReader host={host} appearance="mist" fullscreen={false} onFullscreenChange={toggle} />);
  await screen.findByRole("heading", { name: "Method" });
  const actions = screen.getByRole("navigation", { name: "阅读功能控制区" });
  expect(within(actions).queryByRole("button", { name: "新会话" })).not.toBeInTheDocument();
  expect(actions).toHaveTextContent("继续");
  expect(within(actions).queryByRole("button", { name: "收起资料" })).not.toBeInTheDocument();
  expect(actions).toHaveTextContent("资料");
  fireEvent.click(within(actions).getByRole("button", { name: "资料" }));
  expect(within(actions).getByRole("button", { name: "收起资料" })).toHaveAttribute("aria-expanded", "true");
  fireEvent.click(screen.getByRole("button", { name: "全屏" }));
  expect(toggle).toHaveBeenCalledWith(true);
});

it("keeps one disclosure in the function row and preserves draft and focus", async () => {
  const host: ReaderHost = { getReadingWindow: vi.fn(async () => readerSuccess(first)),
    continueReading: vi.fn(), sendMessage: vi.fn() };
  render(<FocusReader host={host} appearance="mist" />);
  const textbox = await screen.findByRole("textbox", { name: "输入问题或阅读需求" });
  const row = textbox.closest(".focus-composer-row");
  expect(row).not.toBeNull();
  const collapse = screen.getByRole("button", { name: "收起" });
  const actions = screen.getByRole("navigation", { name: "阅读功能控制区" });
  expect(collapse.closest(".mist-reading-actions")).toBe(actions);
  expect(collapse).toHaveAttribute("aria-expanded", "true");
  expect(within(row as HTMLElement).queryByRole("button", { name: "收起" })).toBeNull();
  fireEvent.change(textbox, { target: { value: "暂存的问题" } });
  fireEvent.click(collapse);
  expect(row?.parentElement).toHaveAttribute("data-collapsed", "true");
  expect(row?.parentElement).toHaveAttribute("inert");
  expect(row?.parentElement).toHaveAttribute("aria-hidden", "true");
  const expand = screen.getByRole("button", { name: "提问" });
  expect(expand).toBe(collapse);
  expect(expand).toHaveAttribute("aria-expanded", "false");
  expect(expand.textContent).toBe("提问");
  expect(expand.querySelector(".mist-composer-toggle__draft")).toHaveAttribute("aria-hidden", "true");
  await waitFor(() => expect(expand).toHaveFocus());
  // jsdom does not run grid transitions; actual zero height is checked in Playwright.
  expect(document.querySelector(".focus-bottom")).toHaveAttribute("data-empty", "true");
  expect(screen.queryByRole("button", { name: "收起" })).not.toBeInTheDocument();
  fireEvent.click(expand);
  expect(textbox).toHaveValue("暂存的问题");
  expect(row?.parentElement).toHaveAttribute("data-collapsed", "false");
  expect(row?.parentElement).not.toHaveAttribute("inert");
  await waitFor(() => expect(textbox).toHaveFocus());
});

it("closes the left-side drawer with Escape and keeps the function entry in place", async () => {
  const host: ReaderHost = { getReadingWindow: vi.fn(async () => readerSuccess(first)),
    continueReading: vi.fn(), sendMessage: vi.fn() };
  render(<FocusReader host={host} appearance="mist" />);
  await screen.findByRole("heading", { name: "Method" });
  const controls = screen.getByRole("navigation", { name: "阅读功能控制区" });
  if (within(controls).queryByRole("button", { name: "收起资料" })) {
    fireEvent.click(within(controls).getByRole("button", { name: "收起资料" }));
  }
  fireEvent.click(within(controls).getByRole("button", { name: "资料" }));
  expect(screen.getByRole("region", { name: "阅读资料侧栏" })).toHaveAttribute("data-side-placement", "left");
  fireEvent.keyDown(document.querySelector(".focus-reader")!, { key: "Escape" });
  expect(screen.queryByRole("region", { name: "阅读资料侧栏" })).not.toBeInTheDocument();
  expect(within(controls).getByRole("button", { name: "资料" })).toBeInTheDocument();
});

it("keeps quote jumps and answer review local, and saves through the existing message request", async () => {
  const receipt = { sourceId: current.sourceId, planId: current.planId, chunkId: current.chunkId };
  const withAnswer: ReadingWindow = { ...first, conversation: [
    { messageId: "question", role: "user", chunkId: current.chunkId, reference: receipt, content: "这句是什么意思？" },
    { messageId: "answer", role: "assistant", chunkId: current.chunkId, reference: receipt, content: "这是原文的解释。" },
  ] };
  const host: ReaderHost = { getReadingWindow: vi.fn(async () => readerSuccess(withAnswer)), continueReading: vi.fn(),
    reviewChunk: vi.fn(), sendMessage: vi.fn(async () => readerSuccess(withAnswer)) };
  render(<FocusReader host={host} appearance="mist" />);
  await screen.findByText("这是原文的解释。");
  fireEvent.click(document.querySelector<HTMLButtonElement>(".reader-quote-bar")!);
  fireEvent.click(screen.getByRole("button", { name: "回看第 1 段" }));
  expect(host.reviewChunk).not.toHaveBeenCalled();
  expect(host.continueReading).not.toHaveBeenCalled();
  fireEvent.change(screen.getByRole("textbox"), { target: { value: "保留的草稿" } });
  fireEvent.click(screen.getByRole("button", { name: "存为笔记" }));
  await waitFor(() => expect(host.sendMessage).toHaveBeenCalledWith({ sessionId: "s1", receipt,
    content: "请把下面的回答记下来：\n\n这是原文的解释。", attachmentIds: [], sourceId: current.sourceId, requestId: expect.any(String) }));
  expect(screen.getByRole("textbox")).toHaveValue("保留的草稿");
  expect(document.querySelector(".mist-history-rail")).toBeNull();
});

it("uses decorative function-row icons and a clean fullscreen accessible name", async () => {
  const host: ReaderHost = { getReadingWindow: vi.fn(async () => readerSuccess(first)),
    continueReading: vi.fn(), sendMessage: vi.fn() };
  const { rerender } = render(<FocusReader host={host} appearance="mist" />);
  await screen.findByRole("heading", { name: "Method" });
  const controls = screen.getByRole("navigation", { name: "阅读功能控制区" });
  const icons = controls.querySelectorAll("button > svg");
  expect(icons.length).toBeGreaterThan(0);
  icons.forEach(icon => { expect(icon).toHaveAttribute("aria-hidden", "true"); expect(icon).toHaveAttribute("focusable", "false"); expect(icon.textContent).toBe(""); });
  rerender(<FocusReader host={host} appearance="mist" fullscreen />);
  const exit = within(controls).getByRole("button", { name: "退出全屏" });
  expect(exit).toHaveTextContent("退出全屏");
  expect(exit.textContent).not.toContain("×");
});

it("keeps inline send with a screen-reader keyboard hint and ignores composing Enter", async () => {
  const host = setup();
  const textbox = await screen.findByRole("textbox", { name: "输入问题或阅读需求" });
  const send = screen.getByRole("button", { name: "发送" });
  expect(textbox.closest("form.focus-composer")).toBe(send.closest("form.focus-composer"));
  expect(textbox).toHaveAttribute("rows", "1");
  expect(document.querySelector(".focus-composer__chin")).toBeNull();
  expect(document.querySelector(".composer-key-hint")).toBeNull();
  expect(document.querySelector(".focus-composer__tools")).toBeNull();
  expect(document.getElementById(textbox.getAttribute("aria-describedby")!)).toHaveTextContent("Enter 发送");
  fireEvent.change(textbox, { target: { value: "正在输入的问题" } });
  fireEvent.keyDown(textbox, { key: "Enter", isComposing: true });
  fireEvent.keyDown(textbox, { key: "Enter", keyCode: 229 });
  fireEvent.keyDown(textbox, { key: "Enter", shiftKey: true });
  expect(host.sendMessage).not.toHaveBeenCalled();
  fireEvent.keyDown(textbox, { key: "Enter" });
  await waitFor(() => expect(host.sendMessage).toHaveBeenCalledTimes(1));
});

it("selects character measures with arrows, restores focus and persists without advancing", async () => {
  localStorage.clear(); const host = setup();
  await screen.findByRole("heading", { name: "Method" });
  fireEvent.click(screen.getByRole("button", { name: "行宽" }));
  expect(screen.getByRole("radio", { name: "标准" })).toHaveAttribute("aria-checked", "true");
  fireEvent.keyDown(screen.getByRole("radio", { name: "标准" }), { key: "ArrowRight" });
  expect(screen.getByRole("radio", { name: "宽" })).toHaveFocus();
  expect(localStorage.getItem("focus.readingMeasure")).toBe("wide");
  expect(document.querySelector<HTMLElement>(".focus-reader")!.style.getPropertyValue("--reader-column")).toBe("calc(50 * var(--reader-reading-size))");
  fireEvent.keyDown(screen.getByRole("radio", { name: "宽" }), { key: "Escape" });
  expect(screen.queryByRole("radiogroup")).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "行宽" })).toHaveFocus();
  cleanup(); render(<FocusReader host={host} appearance="mist" />);
  fireEvent.click(screen.getByRole("button", { name: "行宽" }));
  expect(screen.getByRole("radio", { name: "宽" })).toHaveAttribute("aria-checked", "true");
  expect(host.continueReading).not.toHaveBeenCalled();localStorage.clear();
});

it("shows the completed document without a Continue button", async () => {
  const last = { ...current, chunkId: "chunk-002", index: 2, sourceMarkdown: "Final paragraph." };
  const completed: ReadingWindow = { ...first, status: "completed", current: null, history: [current, last],
    timeline: [{ kind: "reading", chunk: current }, { kind: "reading", chunk: last }] };
  const host: ReaderHost = { getReadingWindow: vi.fn(async () => readerSuccess(completed)),
    continueReading: vi.fn(), sendMessage: vi.fn() };
  render(<FocusReader host={host} appearance="mist" />);
  await screen.findByText("Final paragraph.");
  expect(screen.getByText("Original paragraph.")).toBeInTheDocument();
  expect(document.querySelector(".focus-reader__continue")).toBeNull();
  expect(host.continueReading).not.toHaveBeenCalled();
});


it("does not show latest navigation on the first body page", async () => {
  setup();
  await screen.findByRole("heading", { name: "Method" });
  const pane = document.querySelector<HTMLElement>(".focus-stream")!;
  fireEvent.wheel(pane, { deltaY: -100 });
  fireEvent.touchStart(pane);
  expect(screen.queryByRole("button", { name: /回到最新/ })).not.toBeInTheDocument();
});
