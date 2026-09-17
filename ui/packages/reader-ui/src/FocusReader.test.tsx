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
    presentationStatus: "translation-required",
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
    expect(screen.getByText("The first chunk.")).toBeInTheDocument();
    expect(screen.getByText("The second chunk.")).toBeInTheDocument();
  });
  it("references a historical paragraph independently of the cursor", async () => {
    const host = setup(secondWindow);
    await screen.findByText("The second chunk.");
    fireEvent.click(screen.getAllByRole("button", { name: "引用提问" })[0]);
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
    expect(screen.getByText("unsafe").getAttribute("href")).not.toContain("javascript:");
    expect(screen.queryByRole("complementary")).not.toBeInTheDocument();
  });
  it("keeps completed reading visible and allows questions", async () => {
    const host = setup({ ...secondWindow, status: "completed", current: null, history: [firstWindow.current!, secondWindow.current!] });
    await screen.findByText("The second chunk.");
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "总结全文" } });
    fireEvent.click(screen.getByRole("button", { name: "发送 ↑" }));
    await waitFor(() => expect(host.sendMessage).toHaveBeenCalledWith(expect.objectContaining({ receipt: null })));
    expect(screen.queryByRole("button", { name: "下一段 →" })).not.toBeInTheDocument();
  });
});
