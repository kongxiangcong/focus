import "@testing-library/jest-dom/vitest";

import {
  readerFailure,
  readerSuccess,
  type ReaderHost,
  type ReadingWindow,
} from "@focus/reader-contracts";
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { FocusReader } from "./FocusReader";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const firstWindow: ReadingWindow = {
  status: "reading",
  source: { sourceId: "fixture-paper", title: "Fixture Paper", topicId: null },
  current: {
    sourceId: "fixture-paper",
    planId: "plan-001",
    chunkId: "chunk-001",
    index: 1,
    total: 2,
    sectionPath: ["Fixture Paper", "Method"],
    sourceLines: [1, 4],
    sourceMarkdown: "The first chunk.",
    translation: null,
    images: [],
    relevantGlossary: [],
    presentationStatus: "source-ready",
  },
  history: [],
  conversation: [],
};

const secondWindow: ReadingWindow = {
  ...firstWindow,
  current: {
    ...firstWindow.current!,
    chunkId: "chunk-002",
    index: 2,
    sourceMarkdown: "The second chunk.",
  },
  history: [firstWindow.current!],
};

beforeEach(() => {
  HTMLDialogElement.prototype.showModal = function () { this.setAttribute("open", ""); };
  HTMLDialogElement.prototype.close = function () { this.removeAttribute("open"); };
  HTMLElement.prototype.scrollIntoView = vi.fn();
});
function setup(value = firstWindow) {
  const host: ReaderHost = {
    getReadingWindow: vi.fn().mockResolvedValue(readerSuccess(value)),
    continueReading: vi.fn().mockResolvedValue(readerSuccess(secondWindow)),
    sendMessage: vi.fn().mockResolvedValue(readerSuccess(value)),
  };
  render(<FocusReader host={host} />); return host;
}
describe("FocusReader unified flow", () => {
  it("focuses the reading card when opening or advancing past an older conversation", async () => {
    const conversation = [{ messageId: "old", chunkId: "", role: "assistant" as const, content: "Earlier source discussion." }];
    const host = setup({ ...firstWindow, conversation });
    await screen.findByText("The first chunk.");
    expect(screen.getByText("The first chunk.").closest(".focus-output")).toHaveAttribute("data-current-output", "true");
    vi.mocked(host.continueReading).mockResolvedValue(readerSuccess({ ...secondWindow, conversation }));
    fireEvent.click(screen.getByRole("button", { name: "下一段 →" }));
    await screen.findByText("The second chunk.");
    expect(screen.getByText("The second chunk.").closest(".focus-output")).toHaveAttribute("data-current-output", "true");
  });
  it("only advances from the explicit action and locks duplicate requests", async () => {
    const host = setup();
    await screen.findByText("The first chunk.");
    fireEvent.keyDown(screen.getByRole("main"), { key: " ", code: "Space" });
    expect(host.continueReading).not.toHaveBeenCalled();
    let resolve!: (v: ReturnType<typeof readerSuccess<ReadingWindow>>) => void;
    vi.mocked(host.continueReading).mockReturnValue(new Promise(r => { resolve = r; }));
    const next = screen.getByRole("button", { name: "下一段 →" });
    fireEvent.click(next); fireEvent.click(next);
    expect(host.continueReading).toHaveBeenCalledTimes(1);
    await act(async () => resolve(readerSuccess(secondWindow)));
    expect(screen.queryByText("The first chunk.")).not.toBeInTheDocument();
    expect(screen.getByText("The second chunk.")).toBeInTheDocument();
  });
  it("references a historical paragraph independently of the cursor", async () => {
    const host = setup(secondWindow);
    await screen.findByText("The second chunk.");
    fireEvent.click(screen.getByRole("button", { name: "目录" }));
    fireEvent.click(screen.getByRole("button", { name: "第 1 段 · Method" }));
    fireEvent.click(screen.getByRole("button", { name: "引用提问" }));
    expect(screen.getByText(/引用第 1 段/)).toBeInTheDocument();
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "解释这段" } });
    fireEvent.click(screen.getByRole("button", { name: "发送 ↑" }));
    await waitFor(() => expect(host.sendMessage).toHaveBeenCalledWith(expect.objectContaining({ receipt: expect.objectContaining({ chunkId: "chunk-001" }) })));
    expect(host.continueReading).not.toHaveBeenCalled();
  });
  it("keeps drafts editable in flight and retries the exact failed operation", async () => {
    const host = setup(); await screen.findByText("The first chunk.");
    vi.mocked(host.sendMessage).mockResolvedValueOnce(readerFailure("unavailable", "发送未确认", true));
    const input = screen.getByRole("textbox");
    fireEvent.change(input, { target: { value: "问题一" } });
    fireEvent.click(screen.getByRole("button", { name: "发送 ↑" }));
    await screen.findByText("发送未确认");
    expect(input).toHaveValue("问题一"); expect(input).toBeEnabled();
    fireEvent.change(input, { target: { value: "问题二草稿" } });
    fireEvent.click(screen.getByRole("button", { name: "重试发送" }));
    await waitFor(() => expect(host.sendMessage).toHaveBeenCalledTimes(2));
    expect(vi.mocked(host.sendMessage).mock.calls[0][0]).toEqual(vi.mocked(host.sendMessage).mock.calls[1][0]);
    expect(input).toHaveValue("问题二草稿");
    expect(host.getReadingWindow).toHaveBeenCalledTimes(1);
  });
  it("reconnects an unavailable initial host without a fake resend", async () => {
    const host: ReaderHost = { getReadingWindow: vi.fn().mockResolvedValueOnce(readerFailure("unavailable", "断线", true)).mockResolvedValue(readerSuccess(firstWindow)), continueReading: vi.fn(), sendMessage: vi.fn() };
    render(<FocusReader host={host} />); await screen.findByText("断线");
    fireEvent.click(screen.getByRole("button", { name: "重新连接" }));
    await screen.findByText("The first chunk."); expect(host.sendMessage).not.toHaveBeenCalled();
  });
  it("toggles source/translation without duplicating text or losing the draft", async () => {
    setup({ ...firstWindow, current: { ...firstWindow.current!, translation: "中文译文" } });
    await screen.findByText("中文译文"); expect(screen.queryByText("The first chunk.")).not.toBeInTheDocument();
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "待发送" } });
    fireEvent.click(screen.getByRole("button", { name: "查看原文" }));
    expect(screen.getByText("The first chunk.")).toBeInTheDocument();
    expect(screen.queryByText("中文译文")).not.toBeInTheDocument();
    expect(screen.getByRole("textbox")).toHaveValue("待发送");
  });
  it("renders technical markdown in the main flow with safe links and no raw HTML", async () => {
    setup({ ...firstWindow, conversation: [{ messageId: "md", chunkId: "chunk-001", role: "assistant", content: "## 解释\n\n| A | B |\n| - | - |\n| 1 | 2 |\n\n```py\nprint(1)\n```\n\n$x^2$\n\n<script>alert(1)</script>\n\n[unsafe](javascript:alert(1))" }] });
    expect(await screen.findByRole("heading", { name: "解释" })).toBeInTheDocument();
    expect(screen.getByRole("table")).toBeInTheDocument();
    expect(document.querySelector(".katex")).not.toBeNull();
    expect(document.querySelector("main script")).toBeNull();
    expect(screen.getByText("unsafe").getAttribute("href") ?? "").not.toContain("javascript:");
    expect(screen.queryByRole("complementary")).not.toBeInTheDocument();
  });
  it("renders PDF parser tables with merged cells while stripping unsafe HTML", async () => {
    setup({ ...firstWindow, current: { ...firstWindow.current!, translation:
      '<table><tr><th colspan="2">PDF 表格</th></tr><tr><td rowspan="2">模型</td><td>$x^2$</td></tr><tr><td>28.4</td></tr></table>\n\n<script>alert(1)</script><img src="x" onerror="alert(1)" />' } });
    const table = await screen.findByRole("table");
    expect(table.querySelector("th")).toHaveAttribute("colspan", "2");
    expect(table.querySelector('td[rowspan="2"]')).toHaveTextContent("模型");
    expect(table.querySelector(".katex")).not.toBeNull();
    expect(document.querySelector("main script, main [onerror]")).toBeNull();
  });
  it("keeps completed reading visible and allows questions", async () => {
    const host = setup({ ...secondWindow, status: "completed", current: null, history: [firstWindow.current!, secondWindow.current!] });
    await screen.findByRole("button", { name: "查看已读段落" });
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "总结全文" } });
    fireEvent.click(screen.getByRole("button", { name: "发送 ↑" }));
    await waitFor(() => expect(host.sendMessage).toHaveBeenCalledWith(expect.objectContaining({ receipt: null })));
    expect(screen.queryByRole("button", { name: "下一段 →" })).not.toBeInTheDocument();
  });
  it("keeps failed progress collapsed and retries without another Continue", async () => {
    const entry = { progress_id: "progress-1", trigger_request_id: "progress-1", source_id: "fixture-paper",
      bundle: "bundle-1", plan_id: "plan-001", chunk_id: "chunk-001", reading_pass: 1,
      operation: "continue" as const, status: "failed" as const, revision: 1,
      fact: "已读本段", topic: null, user_understanding: null, deleted: false, error: "生成失败，可补记" };
    const value = { ...secondWindow, readingProgress: [entry] };
    const host = setup(value);
    host.retryReadingProgress = vi.fn().mockResolvedValue(readerSuccess({ ...value,
      readingProgress: [{ ...entry, status: "saved", topic: "别名地址的作用" }] }));
    await screen.findByText("The second chunk.");
    expect(screen.getByText(/生成未完成，已读位置不受影响/)).not.toBeVisible();
    fireEvent.click(screen.getByText("阅读记录 · 1"));
    expect(screen.getByText(/生成未完成，已读位置不受影响/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "补记" }));
    await screen.findByText(/别名地址的作用/);
    expect(host.continueReading).not.toHaveBeenCalled();
  });
});

describe("HTTP browser without crypto.randomUUID", () => {
  beforeEach(() => {
    const getRandomValues = globalThis.crypto.getRandomValues.bind(globalThis.crypto);
    vi.stubGlobal("crypto", { getRandomValues });
  });
  it("starts Continue without the secure-context UUID API", async () => {
    const host = setup();
    await screen.findByText("The first chunk.");
    fireEvent.click(screen.getByRole("button", { name: "下一段 →" }));
    await waitFor(() => expect(host.continueReading).toHaveBeenCalledOnce());
  });
  it("sends a prompt on Enter without the secure-context UUID API", async () => {
    const host = setup();
    await screen.findByText("The first chunk.");
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "解释这段" } });
    fireEvent.keyDown(screen.getByRole("textbox"), { key: "Enter" });
    await waitFor(() => expect(host.sendMessage).toHaveBeenCalledWith(expect.objectContaining({ content: "解释这段", requestId: expect.stringMatching(/^[a-f0-9-]{36}$/) })));
  });
});

it("surfaces request preparation errors and unlocks the composer", async () => {
  vi.stubGlobal("crypto", { getRandomValues: () => { throw new Error("随机数不可用"); } });
  const host = setup();
  await screen.findByText("The first chunk.");
  fireEvent.change(screen.getByRole("textbox"), { target: { value: "解释这段" } });
  fireEvent.keyDown(screen.getByRole("textbox"), { key: "Enter" });
  expect(await screen.findByRole("alert")).toHaveTextContent("随机数不可用");
  expect(screen.getByRole("textbox")).toBeEnabled();
  expect(screen.getByRole("textbox")).toHaveValue("解释这段");
  expect(host.sendMessage).not.toHaveBeenCalled();
});

it("T15 restores the original source draft and never sends it to another source", async () => {
  let emit: ((value: ReturnType<typeof readerSuccess<ReadingWindow>>) => void) | undefined;
  const first = { ...firstWindow, sessionId: "s1", discussionId: "d1", revision: 1 };
  const host: ReaderHost = {
    getReadingWindow: vi.fn().mockResolvedValue(readerSuccess(first)),
    continueReading: vi.fn().mockResolvedValue(readerSuccess(first)),
    subscribe: callback => { emit = callback; return () => {}; },
    sendMessage: vi.fn().mockResolvedValue(readerSuccess(first)),
  };
  render(<FocusReader host={host} />);
  await screen.findByText("The first chunk.");
  fireEvent.change(screen.getByRole("textbox"), { target: { value: "材料一的草稿" } });
  const other = { ...first, source: { ...first.source, sourceId: "other-paper" }, current: { ...first.current!, sourceId: "other-paper" }, discussionId: "d2", revision: 2 };
  act(() => emit!(readerSuccess(other)));
  expect(screen.getByRole("textbox")).toHaveValue("");
  expect(host.sendMessage).not.toHaveBeenCalled();
  act(() => emit!(readerSuccess({ ...first, revision: 3 })));
  expect(screen.getByRole("textbox")).toHaveValue("材料一的草稿");
  fireEvent.click(screen.getByRole("button", { name: "发送 ↑" }));
  await waitFor(() => expect(host.sendMessage).toHaveBeenCalledWith(expect.objectContaining({ receipt: expect.objectContaining({ sourceId: "fixture-paper", chunkId: "chunk-001" }) })));
});
