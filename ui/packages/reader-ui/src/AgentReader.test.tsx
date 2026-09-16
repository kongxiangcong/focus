import { act, fireEvent, render, screen, waitFor, cleanup } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ReaderHost, ReaderHostResult, ReadingWindow } from "@focus/reader-contracts";
import { readerSuccess } from "@focus/reader-contracts";
import { FocusReader } from "./FocusReader";

afterEach(cleanup);
const empty: ReadingWindow = { revision: 1, status: "empty", source: { sourceId: "", title: "选择论文", topicId: null }, current: null,
  history: [], conversation: [], agent: { run: null, catalog: { sources: [], topics: [] } } };
function setup() {
  let publish: (result: ReaderHostResult<ReadingWindow>) => void = () => {};
  const host: ReaderHost = {
    getReadingWindow: vi.fn(async () => readerSuccess(empty)),
    continueReading: vi.fn(async () => readerSuccess(empty)),
    sendMessage: vi.fn(async () => readerSuccess(empty)),
    stop: vi.fn(async () => readerSuccess(empty)),
    approve: vi.fn(async () => readerSuccess(empty)),
    subscribe: fn => { publish = fn; return () => {}; },
    upload: vi.fn(async () => readerSuccess({ attachmentId: "upload-1", name: "paper.pdf" })),
  };
  render(<FocusReader host={host} />);
  return { host, update: (value: ReadingWindow) => act(() => publish(readerSuccess(value))) };
}

describe("Agent Reader", () => {
  it("can start reading with no current paper and selected file", async () => {
    const { host } = setup();
    await screen.findByText("从一篇论文开始");
    fireEvent.change(screen.getByLabelText("选择论文文件"), { target: { files: [new File(["pdf"], "paper.pdf")] } });
    await screen.findByText("paper.pdf");
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "我要阅读这篇论文" } });
    fireEvent.click(screen.getByRole("button", { name: "发送" }));
    await waitFor(() => expect(host.sendMessage).toHaveBeenCalledWith({ receipt: null, content: "我要阅读这篇论文", attachmentIds: ["upload-1"] }, expect.any(AbortSignal)));
    expect(host.continueReading).not.toHaveBeenCalled();
  });

  it("streams messages, exposes stop/approval, and rejects older snapshots", async () => {
    const { host, update } = setup();
    await screen.findByText("从一篇论文开始");
    const running: ReadingWindow = { ...empty, revision: 3, conversation: [{ messageId: "m", chunkId: "", role: "assistant", content: "正在解析" }],
      agent: { ...empty.agent!, run: { runId: "run-1", status: "approval", error: null, activity: [],
        approvals: [{ id: "a", title: "命令审批", detail: "python demo.py", kind: "approval", questions: [], choices: ["accept", "decline"] }] } } };
    update(running);
    expect(await screen.findByText("正在解析")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "发送" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "拒绝" }));
    expect(host.approve).toHaveBeenCalledWith({ approvalId: "a", decision: "decline" });
    update({ ...empty, revision: 2 });
    expect(screen.getByText("正在解析")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "停止任务" }));
    expect(host.stop).toHaveBeenCalled();
  });
});
