import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
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
const chunk = { sourceId: "demo-paper", planId: "plan-001", chunkId: "chunk-001", index: 1, total: 2,
  sectionPath: ["Paper", "Method"], sourceLines: [1, 4] as const, sourceMarkdown: "First body paragraph.",
  translation: null, images: [], relevantGlossary: [], presentationStatus: "source-ready" as const };
const second = { ...chunk, chunkId: "chunk-002", index: 2, sectionPath: ["Paper", "Results"], sourceMarkdown: "Second body paragraph." };
const intro: ReadingWindow = {
  status: "empty", source: { sourceId: "demo-paper", title: "测试文章", topicId: null },
  current: null, navigationCurrent: chunk, history: [], conversation: [], readingRevision: 0,
  readingStarted: false, structureIntro: true, sessionFresh: true,
  outline: [{ chunkId: chunk.chunkId, index: 1, sectionPath: chunk.sectionPath, nodeId: "method" },
    { chunkId: second.chunkId, index: 2, sectionPath: second.sectionPath, nodeId: "results" }],
  structure: [{ id: "paper", parentId: null, title: "全文", description: "从方法到验证。", sourceLines: [1, 8] },
    { id: "method", parentId: "paper", title: "方法", description: "介绍解决问题的方法。", sourceLines: [1, 4] },
    { id: "results", parentId: "paper", title: "结果", description: "验证方法的效果。", sourceLines: [5, 8] }],
};
const body: ReadingWindow = { ...intro, status: "reading", current: chunk, readingStarted: true,
  structureIntro: false, sessionFresh: false, readingRevision: 1 };

it("shows the structure before body text and explicitly starts without advancing", async () => {
  const host: ReaderHost = { getReadingWindow: vi.fn(async () => readerSuccess(intro)),
    continueReading: vi.fn(async () => readerSuccess(body)), sendMessage: vi.fn() };
  render(<FocusReader host={host} appearance="mist" />);
  await screen.findByRole("region", { name: "文章结构" });
  expect(screen.queryByText("First body paragraph.")).not.toBeInTheDocument();
  expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /结果/ })).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "进入正文" }));
  await screen.findByText("First body paragraph.");
  expect(host.continueReading).toHaveBeenCalledWith(expect.objectContaining({ beginBody: true,
    receipt: expect.objectContaining({ chunkId: "chunk-001", readingRevision: 0 }) }));
  const location = screen.getByLabelText("当前阅读位置");
  expect(location).toHaveTextContent("1 / 2全文 › 方法");
  const controls = screen.getByRole("navigation", { name: "阅读功能控制区" });
  expect(controls).toContainElement(location);
  expect(within(screen.getByRole("main", { name: "阅读与对话" })).queryByLabelText("当前阅读位置")).not.toBeInTheDocument();
  expect([...controls.children].map(el => el.textContent)).toEqual([
    "资料", "1 / 2全文 › 方法", "宽幅", "吸附讨论", "新会话", "全屏", "收起", "继续 · 第 2 段",
  ]);
  fireEvent.click(screen.getByRole("button", { name: "收起" }));
  expect([...controls.children].map(el => el.textContent)).toEqual([
    "资料", "1 / 2全文 › 方法", "宽幅", "吸附讨论", "新会话", "全屏", "提问", "继续 · 第 2 段",
  ]);
});

it("returns to structure and reviews read sections without changing the frontier or draft", async () => {
  const advanced: ReadingWindow = { ...body, current: second, navigationCurrent: second, history: [chunk], readingRevision: 2 };
  const host: ReaderHost = { getReadingWindow: vi.fn(async () => readerSuccess(advanced)),
    continueReading: vi.fn(), sendMessage: vi.fn() };
  render(<FocusReader host={host} appearance="mist" />);
  await screen.findByText("Second body paragraph.");
  fireEvent.change(screen.getByRole("textbox"), { target: { value: "保留草稿" } });
  fireEvent.click(screen.getByRole("button", { name: "当前阅读位置" }));
  fireEvent.click(screen.getByRole("button", { name: "文章结构总览" }));
  const tree = screen.getByRole("region", { name: "文章结构" });
  expect(within(tree).getByText("结果").closest("li")).toHaveAttribute("data-current", "true");
  fireEvent.click(within(tree).getByRole("button", { name: /方法/ }));
  await waitFor(() => expect(screen.getByLabelText("当前阅读位置")).toHaveTextContent("全文 › 方法"));
  expect(screen.getByRole("textbox")).toHaveValue("保留草稿");
  expect(host.continueReading).not.toHaveBeenCalled();
  expect(screen.getByText(/正式位置未改变/)).toBeInTheDocument();
});

it("does not force an introduction in a fresh discussion after reading has begun", async () => {
  const host: ReaderHost = { getReadingWindow: vi.fn(async () => readerSuccess({ ...body, current: null, sessionFresh: true })),
    continueReading: vi.fn(), sendMessage: vi.fn() };
  render(<FocusReader host={host} appearance="mist" />);
  await screen.findByRole("button", { name: "当前阅读位置" });
  expect(screen.queryByRole("button", { name: "进入正文" })).not.toBeInTheDocument();
});

it("opens the overview from the locator and Escape restores the locator focus", async () => {
  const host: ReaderHost = { getReadingWindow: vi.fn(async () => readerSuccess(body)), continueReading: vi.fn(), sendMessage: vi.fn() };
  render(<FocusReader host={host} appearance="mist" />);
  const locator = await screen.findByRole("button", { name: "当前阅读位置" });
  fireEvent.click(locator);
  fireEvent.click(screen.getByRole("button", { name: "文章结构总览" }));
  expect(screen.getByRole("region", { name: "文章结构" })).toBeVisible();
  fireEvent.keyDown(document.querySelector(".focus-reader")!, { key: "Escape" });
  expect(screen.queryByRole("region", { name: "文章结构" })).not.toBeInTheDocument();
  expect(locator).toHaveFocus();
  expect(host.continueReading).not.toHaveBeenCalled();
});
