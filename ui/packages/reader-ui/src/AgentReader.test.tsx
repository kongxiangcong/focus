import { act, fireEvent, render, screen, waitFor, cleanup } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ReaderHost, ReaderHostResult, ReadingWindow } from "@focus/reader-contracts";
import { readerSuccess, readerFailure } from "@focus/reader-contracts";
import { FocusReader } from "./FocusReader";

afterEach(cleanup);
beforeEach(() => { HTMLDialogElement.prototype.showModal = function () { this.setAttribute("open", ""); }; HTMLDialogElement.prototype.close = function () { this.removeAttribute("open"); }; });
const empty: ReadingWindow = { sessionId: "session-1", revision: 1, status: "empty", source: { sourceId: "", title: "选择论文", topicId: null }, current: null,
  history: [], conversation: [], agent: { run: null, catalog: { sources: [], topics: [] } } };
function setup() {
  let publish: (result: ReaderHostResult<ReadingWindow>) => void = () => {};
  const host: ReaderHost = {
    getReadingWindow: vi.fn(async () => readerSuccess(empty)),
    continueReading: vi.fn(async () => readerSuccess(empty)),
    sendMessage: vi.fn(async () => readerSuccess(empty)),
    newSession: vi.fn(async () => readerSuccess({ ...empty, sessionId: "session-2", sessionFresh: true, revision: 10 })),
    selectBackend: vi.fn(async () => readerSuccess({ ...empty, sessionId: "session-2", revision: 10,
      agent: { ...empty.agent!, backend: "workbuddy", backends: [{ id: "codex", label: "Codex" }, { id: "workbuddy", label: "WorkBuddy" }] } })),
    stop: vi.fn(async () => readerSuccess(empty)),
    approve: vi.fn(async () => readerSuccess(empty)),
    subscribe: fn => { publish = fn; return () => {}; },
    upload: vi.fn(async () => readerSuccess({ attachmentId: "upload-1", name: "paper.pdf" })),
  };
  render(<FocusReader host={host} />);
  return { host, update: (value: ReadingWindow) => act(() => publish(readerSuccess(value))) };
}
const running: ReadingWindow = { ...empty, revision: 3, conversation: [{ messageId: "m", chunkId: "", role: "assistant", content: "正在解析" }],
  agent: { ...empty.agent!, run: { runId: "run-1", status: "approval", error: null, activity: [],
    approvals: [{ id: "a", title: "命令审批", detail: "python demo.py", kind: "approval", questions: [], choices: ["accept", "decline"] }] } } };
describe("Agent Reader", () => {
  it("shows domestic WorkBuddy as unavailable without substituting CodeBuddy", async () => {
    const { host, update } = setup(); await screen.findByText("从一份材料开始");
    update({ ...empty, revision: 2, agent: { ...empty.agent!, backend: "codex", backends: [
      { id: "codex", label: "Codex" }, { id: "workbuddy", label: "WorkBuddy（国内，待接入）", unavailableReason: "需要开放平台授权" },
    ] } });
    expect(screen.getByRole("option", { name: "WorkBuddy（国内，待接入）" })).toBeDisabled();
    expect(host.selectBackend).not.toHaveBeenCalled();
  });
  it("switches agents through the host and retains the current selection on failure", async () => {
    const { host, update } = setup(); await screen.findByText("从一份材料开始");
    const agent = { ...empty.agent!, backend: "codex", backends: [{ id: "codex", label: "Codex" }, { id: "workbuddy", label: "WorkBuddy" }] };
    update({ ...empty, revision: 2, agent });
    vi.mocked(host.selectBackend!).mockResolvedValueOnce(readerFailure("unavailable", "SDK 未安装", false));
    fireEvent.change(screen.getByLabelText("选择 Agent"), { target: { value: "workbuddy" } });
    await screen.findByText("SDK 未安装");
    expect(screen.getByLabelText("选择 Agent")).toHaveValue("codex");
    fireEvent.click(screen.getByRole("button", { name: "重试切换 Agent" }));
    await waitFor(() => expect(screen.getByLabelText("选择 Agent")).toHaveValue("workbuddy"));
    expect(host.selectBackend).toHaveBeenCalledWith("workbuddy", "session-1");
    update({ ...running, sessionId: "session-2", revision: 11, agent: { ...agent, backend: "workbuddy", run: running.agent!.run } });
    expect(screen.getByLabelText("选择 Agent")).toBeDisabled();
  });
  it("offers an executable attachment action and retries upload independently", async () => {
    const { host } = setup(); await screen.findByText("从一份材料开始");
    vi.mocked(host.upload!).mockResolvedValueOnce(readerFailure("unavailable", "network", true));
    fireEvent.change(screen.getByLabelText("选择论文文件"), { target: { files: [new File(["pdf"], "paper.pdf")] } });
    fireEvent.click(await screen.findByRole("button", { name: "重试上传" }));
    await screen.findByText("已上传");
    fireEvent.click(screen.getByRole("button", { name: "开始阅读附件" }));
    await waitFor(() => expect(host.sendMessage).toHaveBeenCalledWith(expect.objectContaining({ content: "请阅读附件", receipt: null, attachmentIds: ["upload-1"] })));
    expect(host.continueReading).not.toHaveBeenCalled();
  });
  it("keeps drafts editable while running, allows approval retry, and rejects stale snapshots", async () => {
    const { host, update } = setup(); await screen.findByText("从一份材料开始"); update(running);
    expect(screen.getByRole("textbox")).toBeEnabled();
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "下一条草稿" } });
    vi.mocked(host.approve!).mockResolvedValueOnce(readerFailure("unavailable", "failed", true));
    fireEvent.click(screen.getByRole("button", { name: "拒绝" }));
    await screen.findByText("提交失败，请重试。");
    expect(screen.getByRole("button", { name: "拒绝" })).toBeEnabled();
    fireEvent.click(screen.getByRole("button", { name: "拒绝" }));
    await waitFor(() => expect(host.approve).toHaveBeenCalledTimes(2));
    update({ ...empty, revision: 2 });
    expect(screen.getByText("正在解析")).toBeInTheDocument();
    expect(screen.getByRole("textbox")).toHaveValue("下一条草稿");
  });
  it("sends explicit explanations unchanged and displays the requested answer", async () => {
    const { host, update } = setup(); await screen.findByText("从一份材料开始");
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "请讲解这段" } });
    fireEvent.click(screen.getByRole("button", { name: "发送 ↑" }));
    await waitFor(() => expect(host.sendMessage).toHaveBeenCalledWith(expect.objectContaining({ content: "请讲解这段" })));
    update({ ...empty, revision: 2, conversation: [{ messageId: "answer", chunkId: "", role: "assistant", content: "这是用户请求的讲解。" }] });
    expect(screen.getByText("这是用户请求的讲解。")).toBeInTheDocument();
    expect(host.continueReading).not.toHaveBeenCalled();
  });
  it("resets the real host session and clears draft, attachments and stale events", async () => {
    const { host, update } = setup(); await screen.findByText("从一份材料开始"); update(running);
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "old draft" } });
    fireEvent.click(screen.getByRole("button", { name: "停止并新建" }));
    await waitFor(() => expect(host.newSession).toHaveBeenCalledWith("session-1"));
    await screen.findByRole("button", { name: "新建会话" });
    expect(screen.queryByText("正在解析")).not.toBeInTheDocument();
    expect(screen.getByRole("textbox")).toHaveValue("");
    update({ ...running, revision: 4 });
    expect(screen.queryByText("正在解析")).not.toBeInTheDocument();
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "新问题" } });
    fireEvent.click(screen.getByRole("button", { name: "发送 ↑" }));
    await waitFor(() => expect(host.sendMessage).toHaveBeenCalledWith(expect.objectContaining({ sessionId: "session-2" })));
  });
  it("ignores a late upload after reset and sends a fresh question without the saved cursor", async () => {
    const { host, update } = setup(); await screen.findByText("从一份材料开始");
    let resolve!: (v: ReaderHostResult<{ attachmentId: string; name: string }>) => void;
    vi.mocked(host.upload!).mockReturnValue(new Promise(r => { resolve = r; }));
    fireEvent.change(screen.getByLabelText("选择论文文件"), { target: { files: [new File(["pdf"], "late.pdf")] } });
    fireEvent.click(screen.getByRole("button", { name: "新建会话" }));
    await waitFor(() => expect(screen.queryByText("late.pdf")).not.toBeInTheDocument());
    await act(async () => resolve(readerSuccess({ attachmentId: "late", name: "late.pdf" })));
    expect(screen.queryByText("late.pdf")).not.toBeInTheDocument();
    update({ ...empty, sessionId: "session-2", revision: 11, sessionFresh: true, timeline: [], status: "reading",
      current: { sourceId: "saved", planId: "plan", chunkId: "old", index: 2, total: 4, sectionPath: [], sourceLines: [1,2], sourceMarkdown: "old text", translation: null, images: [], relevantGlossary: [], presentationStatus: "source-ready" } });
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "新话题" } });
    fireEvent.click(screen.getByRole("button", { name: "发送 ↑" }));
    await waitFor(() => expect(host.sendMessage).toHaveBeenCalledWith(expect.objectContaining({ receipt: null, attachmentIds: [] })));
  });
  it("does not pull an upward reader to streaming output", async () => {
    const { update } = setup(); await screen.findByText("从一份材料开始"); update(running);
    const pane = screen.getByRole("main");
    Object.defineProperties(pane, { scrollHeight: { value: 2000 }, clientHeight: { value: 500 } });
    pane.scrollTop = 150; fireEvent.scroll(pane);
    update({ ...running, revision: 4, conversation: [{ ...running.conversation[0], content: "新增内容" }] });
    expect(pane.scrollTop).toBe(150);
    fireEvent.click(screen.getByRole("button", { name: "有新内容 · 回到底部 ↓" }));
    expect(pane.scrollTop).toBe(2000);
  });
});
