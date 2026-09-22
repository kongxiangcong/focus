// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { readerSuccess, type IngestionItem, type ReaderHost, type ReadingWindow } from "@focus/reader-contracts";
import { WorkspaceApp } from "./WorkspaceApp";
const empty: ReadingWindow = { status: "empty", current: null, history: [], conversation: [], source: { sourceId: "", title: "", topicId: null }, sessionId: "s1",
  agent: { run: null, catalog: { sources: [], topics: [] }, backend: "codex", backends: [{ id: "codex", label: "Codex" }, { id: "workbuddy", label: "WorkBuddy", unavailableReason: "待接入" }] } };
function setup(initialInbox: readonly IngestionItem[] = []) {
  const staged: IngestionItem = { itemId: "item-1", fileName: "test.pdf", status: "awaiting_confirmation", topicTitle: "编译", topicId: null, sourceId: null, documentStatus: "not_started", topicStatus: "not_started", services: ["mineru"] };
  const confirmed: IngestionItem = { ...staged, status: "confirmed", confirmation: { services: ["mineru"], purpose: "register source", scope: "ingestion" } };
  const processing: IngestionItem = { ...staged, status: "processing" };
  const cancelled: IngestionItem = { ...staged, status: "cancelled" };
  const host: ReaderHost = {
    getReadingWindow: vi.fn(async () => readerSuccess(empty)), continueReading: vi.fn(async () => readerSuccess(empty)), sendMessage: vi.fn(async () => readerSuccess(empty)),
    listTopics: vi.fn(async () => readerSuccess([{ topicId: "topic", title: "编译", sourceIds: ["a-paper"] }])),
    listSources: vi.fn(async () => readerSuccess([{ sourceId: "a-paper", title: "A Paper", kind: "paper" as const, parseStatus: "ready" as const, error: null, noteCount: 2, topicIds: ["topic"], progress: { completed: 1, total: 4, planId: "plan-001", chunkId: "chunk-002" } }])),
    listInbox: vi.fn(async () => readerSuccess(initialInbox)), stageIngestion: vi.fn(async () => readerSuccess(staged)),
    confirmIngestion: vi.fn(async () => readerSuccess(confirmed)),
    processIngestion: vi.fn(async () => readerSuccess(processing)), continueIngestion: vi.fn(async () => readerSuccess(processing)), cancelIngestion: vi.fn(async () => readerSuccess(cancelled)),
    resubmitIngestion: vi.fn(async () => readerSuccess(processing)),
    sourceOriginalUrl: id => `/library/sources/${id}/original`, sourceContentUrl: id => `/library/sources/${id}/content`,
    openSource: vi.fn(async () => readerSuccess(empty)), deleteSource: vi.fn(async () => readerSuccess(empty)), rereadSource: vi.fn(async () => readerSuccess(empty)),
  };
  return { host, ...render(<WorkspaceApp host={host} />) };
}
beforeEach(() => {
  const values = new Map<string, string>();
  Object.defineProperty(window, "localStorage", { configurable: true, value: {
    getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => values.set(key, value),
    removeItem: (key: string) => values.delete(key),
    clear: () => values.clear(),
  } });
  history.replaceState(null, "", "/"); localStorage.clear();
  HTMLDialogElement.prototype.showModal = function () { this.setAttribute("open", ""); };
  HTMLDialogElement.prototype.close = function () { this.removeAttribute("open"); };
});
afterEach(cleanup);
it("lands in Library and persists the chosen font across remounts", async () => {
  const app = setup(); await screen.findByRole("button", { name: "A Paper" });
  expect(location.pathname).toBe("/library");
  fireEvent.click(screen.getByRole("link", { name: "设置" }));
  fireEvent.change(screen.getByRole("slider", { name: "字号" }), { target: { value: "3" } });
  expect(screen.getByRole("radio", { name: /WorkBuddy/ })).toBeDisabled();
  app.unmount(); setup();
  expect(await screen.findByRole("slider", { name: "字号" })).toHaveValue("3");
  fireEvent.click(screen.getByRole("link", { name: "阅读" }));
  expect(screen.getByRole("complementary", { name: "阅读进度与操作" })).toBeVisible();
});
it("stages a PDF without processing and starts only after explicit confirmation", async () => {
  const { host } = setup(); await screen.findByRole("button", { name: "A Paper" });
  const pdf = new File(["%PDF test"], "test.pdf", { type: "application/pdf" });
  fireEvent.click(screen.getByRole("button", { name: "上传" }));
  fireEvent.change(screen.getByRole("combobox", { name: "专题" }), { target: { value: "编译" } });
  fireEvent.change(screen.getByLabelText("上传材料"), { target: { files: [pdf] } });
  expect(host.stageIngestion).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "放入 Inbox" }));
  await waitFor(() => expect(host.stageIngestion).toHaveBeenCalledWith(pdf, { topicId: "topic" }));
  const statement = await screen.findByText(/仅用于建立 Source 并关联专题/);
  expect(statement).toHaveTextContent("将调用 MinerU 处理此 PDF");
  expect(statement).not.toHaveTextContent("Codex");
  expect(statement).toHaveTextContent("不做 AI 内容审核");
  expect(host.confirmIngestion).not.toHaveBeenCalled();
  expect(host.processIngestion).not.toHaveBeenCalled();
  fireEvent.click(await screen.findByRole("button", { name: "确认并开始" }));
  await waitFor(() => expect(host.confirmIngestion).toHaveBeenCalledWith("item-1"));
  await waitFor(() => expect(host.processIngestion).toHaveBeenCalledWith("item-1", expect.any(String)));
  await waitFor(() => expect(screen.getByRole("button", { name: "删除" })).toBeEnabled());
  fireEvent.click(screen.getByRole("button", { name: "删除" }));
  expect(host.deleteSource).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "永久删除" }));
  await waitFor(() => expect(host.deleteSource).toHaveBeenCalledWith("a-paper"));
  await waitFor(() => expect(screen.getByRole("button", { name: "从头阅读" })).toBeEnabled());
  fireEvent.click(screen.getByRole("button", { name: "从头阅读" }));
  fireEvent.click(screen.getByRole("button", { name: "确认从头阅读" }));
  await waitFor(() => expect(host.rereadSource).toHaveBeenCalledWith("a-paper"));
  await waitFor(() => expect(location.pathname).toBe("/reading"));
});
it("filters source cards, exposes source resources, and only accepts PDF ingestion", async () => {
  const { host } = setup(); await screen.findByRole("button", { name: "A Paper" });
  expect(document.querySelector(".source-badge")?.closest("article")).toBeInTheDocument();
  expect(screen.getByRole("progressbar", { name: "A Paper 阅读进度" })).toHaveAttribute("value", "1");
  fireEvent.change(screen.getByRole("searchbox"), { target: { value: "missing" } });
  expect(screen.getByText("暂无匹配材料")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "重置" }));
  const page = screen.getByRole("main");
  expect(screen.getByRole("link", { name: "PDF 原件" })).toHaveAttribute("href", "/library/sources/a-paper/original");
  expect(screen.getByRole("link", { name: "正文" })).toHaveAttribute("href", "/library/sources/a-paper/content");
  fireEvent.drop(page, { dataTransfer: { files: [new File(["text"], "file.html")] } });
  expect(host.stageIngestion).not.toHaveBeenCalled();
  expect(screen.getByRole("alert")).toHaveTextContent("请选择 PDF");
});

it("restores authoritative Inbox state after refresh and continues attachment recovery", async () => {
  const recovering: IngestionItem = { itemId: "recover", fileName: "paper.pdf", status: "topic_attachment_pending", topicTitle: "系统", topicId: null, sourceId: "a-paper", documentStatus: "published", topicStatus: "pending_recovery" };
  const { host } = setup([recovering]);
  expect(await screen.findByText("文档已入库，专题关联待恢复")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "继续" }));
  await waitFor(() => expect(host.continueIngestion).toHaveBeenCalledWith("recover", expect.any(String)));
});
it("offers explicit reconfirmation for a recoverable Inbox item", async () => {
  const interrupted: IngestionItem = { itemId: "recover", fileName: "paper.pdf", status: "interrupted", topicTitle: "系统", topicId: null, sourceId: null, documentStatus: "not_started", topicStatus: "not_started", services: ["mineru"] };
  const { host } = setup([interrupted]);
  fireEvent.click(await screen.findByRole("button", { name: "重新确认并开始" }));
  await waitFor(() => expect(host.confirmIngestion).toHaveBeenCalledWith("recover"));
  await waitFor(() => expect(host.processIngestion).toHaveBeenCalledWith("recover", expect.any(String)));
});
it("persists brightness and leaves unsupported network control disabled", async () => {
  setup(); await screen.findByRole("button", { name: "A Paper" });
  fireEvent.click(screen.getByRole("link", { name: "设置" }));
  fireEvent.change(screen.getByRole("slider", { name: "亮度" }), { target: { value: "90" } });
  expect(localStorage.getItem("focus.brightness")).toBe("90");
  expect(screen.getByRole("switch", { name: "网络" })).toBeDisabled();
});
it("shows the original unfinished task instead of a new one when the same file is added again", async () => {
  const { host } = setup();
  const existing: IngestionItem = { itemId: "item-1", fileName: "test.pdf", status: "status_check_required", topicTitle: "编译", topicId: null, sourceId: null, documentStatus: "not_started", topicStatus: "not_started", services: ["mineru"], duplicate: true };
  vi.mocked(host.stageIngestion!).mockResolvedValue(readerSuccess(existing));
  await screen.findByRole("button", { name: "A Paper" });
  fireEvent.click(screen.getByRole("button", { name: "上传" }));
  fireEvent.change(screen.getByRole("combobox", { name: "专题" }), { target: { value: "编译" } });
  fireEvent.change(screen.getByLabelText("上传材料"), { target: { files: [new File(["%PDF test"], "test.pdf", { type: "application/pdf" })] } });
  fireEvent.click(screen.getByRole("button", { name: "放入 Inbox" }));

  const notice = await screen.findByText(/该原件已有未完成任务/);
  expect(notice.closest("[role=status]")).not.toBeNull();
  expect(notice).toHaveTextContent("已回到原任务；不会重复解析。");
  const row = document.querySelector(".library-inbox-item");
  expect(row).toHaveTextContent("test.pdf");
  expect(row).toHaveTextContent("远端状态待核对");
  expect(row).toHaveTextContent("编译");
  expect(host.processIngestion).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "知道了" }));
  expect(screen.queryByText(/该原件已有未完成任务/)).not.toBeInTheDocument();
});
it("explains the duplicate-parsing risk next to an explicit resubmission action", async () => {
  const unknown: IngestionItem = { itemId: "item-1", fileName: "paper.pdf", status: "status_check_required", topicTitle: "编译", topicId: null, sourceId: null, documentStatus: "not_started", topicStatus: "not_started", services: ["mineru"], remoteReference: false, resubmitRisk: { choiceId: "choice-1" } };
  const { host } = setup([unknown]);
  expect(await screen.findByText("远端状态待核对")).toBeInTheDocument();
  expect(screen.getByText("上次提交结果未知，重新提交可能重复解析。")).toBeInTheDocument();
  // Without a remote reference, a plain continue is never offered as a way out;
  // reconfirming the changed scope stays a separate, explicit action.
  expect(screen.queryByRole("button", { name: "继续" })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "查询并续接原任务" })).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "重新确认并开始" })).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "重新提交" }));

  await waitFor(() => expect(host.resubmitIngestion).toHaveBeenCalledWith("item-1", expect.any(String), "choice-1"));
  expect(host.continueIngestion).not.toHaveBeenCalled();
  expect(host.processIngestion).not.toHaveBeenCalled();
});
it("offers resubmission instead of a doomed continue for a cancelled acceptance-unknown item", async () => {
  const cancelled: IngestionItem = { itemId: "item-1", fileName: "paper.pdf", status: "cancelled", topicTitle: "编译", topicId: null, sourceId: null, documentStatus: "not_started", topicStatus: "not_started", services: ["mineru"], remoteReference: false, resubmitRisk: { choiceId: "choice-1" } };
  const { host } = setup([cancelled]);
  expect(await screen.findByText("上次提交结果未知，重新提交可能重复解析。")).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "继续" })).not.toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "重新提交" }));

  await waitFor(() => expect(host.resubmitIngestion).toHaveBeenCalledWith("item-1", expect.any(String), "choice-1"));
  expect(host.continueIngestion).not.toHaveBeenCalled();
});
it("offers querying the original task first when a remote reference exists", async () => {
  const unknown: IngestionItem = { itemId: "item-1", fileName: "paper.pdf", status: "status_check_required", topicTitle: "编译", topicId: null, sourceId: null, documentStatus: "not_started", topicStatus: "not_started", services: ["mineru"], remoteReference: true, resubmitRisk: { choiceId: "choice-1" } };
  const { host } = setup([unknown]);
  expect(await screen.findByRole("button", { name: "查询并续接原任务" })).toBeEnabled();
  expect(screen.getByText("上次提交结果未知，重新提交可能重复解析。")).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "查询并续接原任务" }));

  await waitFor(() => expect(host.continueIngestion).toHaveBeenCalledWith("item-1", expect.any(String)));
  expect(host.resubmitIngestion).not.toHaveBeenCalled();
});
