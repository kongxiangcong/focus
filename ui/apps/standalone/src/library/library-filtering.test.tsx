// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { readerSuccess, type BlogStatus, type IngestionItem, type LibrarySource, type ProcessingBatch, type ReaderHost, type ReadingWindow } from "@focus/reader-contracts";
import { WorkspaceApp } from "../WorkspaceApp";
import { UNFILED } from "./topic-view";

const chunk = { sourceId: "A", planId: "plan", chunkId: "chunk-2", index: 2, total: 4, sectionPath: ["Paper", "Methods"], sourceLines: [1, 2] as const, sourceMarkdown: "text", translation: null, images: [], relevantGlossary: [], presentationStatus: "presented" as const };
const empty: ReadingWindow = { status: "empty", current: null, history: [], conversation: [], source: { sourceId: "", title: "", topicId: null } };
const reading: ReadingWindow = { ...empty, status: "reading", source: { sourceId: "A", title: "Alpha", topicId: null }, current: chunk };
const sources: LibrarySource[] = [
  { sourceId: "A", title: "Alpha", kind: "paper", parseStatus: "ready", error: null, noteCount: 0, topicIds: ["topic"], progress: { completed: 1, total: 4, planId: "plan", chunkId: "chunk-2" } },
  { sourceId: "B", title: "Beta", kind: "paper", parseStatus: "ready", error: null, noteCount: 0, topicIds: ["topic"], progress: { completed: 0, total: 4, planId: "plan", chunkId: "chunk-1" } },
  { sourceId: "C", title: "Gamma", kind: "paper", parseStatus: "ready", error: null, noteCount: 0, topicIds: [], progress: { completed: 4, total: 4, planId: "plan", chunkId: null } },
  { sourceId: "D", title: "Delta", kind: "paper", parseStatus: "invalid", error: "broken", noteCount: 0, topicIds: [], progress: { completed: 0, total: 0, planId: null, chunkId: null } },
];
const item: IngestionItem = { itemId: "pending", fileName: "pending.pdf", status: "failed", topicId: "topic", topicTitle: "编译", sourceId: null, documentStatus: "not_started", topicStatus: "not_started", parserBackend: "local-mineru", parserProgress: { status: "queued", percent: 25 } };
const batch: ProcessingBatch = { batchId: "batch", topicId: "topic", status: "partial", error: null, items: [{ itemId: "batch-item", fileName: "batch.pdf", sourceId: null, status: "failed", ingestionStatus: "failed", error: null, blog: null }] };
function setup(options: { sources?: readonly LibrarySource[]; view?: ReadingWindow; inbox?: readonly IngestionItem[]; batches?: readonly ProcessingBatch[]; overrides?: Partial<ReaderHost> } = {}) {
  const host: ReaderHost = {
    getReadingWindow: vi.fn(async () => readerSuccess(options.view ?? empty)), continueReading: vi.fn(async () => readerSuccess(empty)), sendMessage: vi.fn(async () => readerSuccess(empty)),
    listSources: vi.fn(async () => readerSuccess(options.sources ?? sources)), listTopics: vi.fn(async () => readerSuccess([{ topicId: "topic", title: "编译", sourceIds: ["A", "B"] }, { topicId: "other", title: "空专题", sourceIds: [] }])),
    listInbox: vi.fn(async () => readerSuccess(options.inbox ?? [])), listBatches: vi.fn(async () => readerSuccess(options.batches ?? [])),
    manageTopic: vi.fn(async () => readerSuccess({})), openSource: vi.fn(async () => readerSuccess(empty)),
    stageIngestion: vi.fn(async () => readerSuccess(item)), startBatch: vi.fn(async () => readerSuccess(batch)),
    continueIngestion: vi.fn(async () => readerSuccess({ ...item, status: "processing" as const })), controlBatch: vi.fn(async () => readerSuccess(batch)),
    ...options.overrides,
  };
  render(<WorkspaceApp host={host} />); return host;
}
async function loaded() { await act(async () => {}); await screen.findByRole("button", { name: "Alpha" }); }
function filters() { return within(screen.getByRole("group", { name: "按状态筛选" })); }
function chooseTopic(topic: string) { fireEvent.change(screen.getByRole("combobox", { name: "筛选专题" }), { target: { value: topic } }); }
beforeEach(() => { history.replaceState(null, "", "/library"); localStorage.clear(); HTMLDialogElement.prototype.showModal = function () { this.setAttribute("open", ""); }; HTMLDialogElement.prototype.close = function () { this.removeAttribute("open"); }; });
afterEach(cleanup);

it("uses the persisted navigation cursor, opens details and calls the existing reading action", async () => {
  const host = setup({ view: { ...reading, navigationCurrent: { ...chunk, index: 3, sectionPath: ["Results"] } } }); await loaded();
  const strip = screen.getByRole("region", { name: "继续阅读" }); expect(strip).toHaveTextContent("Results · 第 3 段 / 共 4 段");
  fireEvent.click(within(strip).getByRole("button", { name: "查看 Alpha 详情" })); expect(screen.getByRole("complementary", { name: "来源详情" })).toHaveTextContent("Alpha");
  await act(async () => fireEvent.click(within(strip).getByRole("button", { name: "继续阅读" })));
  expect(host.openSource).toHaveBeenCalledWith("A", expect.any(String));
});
it.each(["missing-source", "missing-cursor", "missing-section", "invalid-index", "invalid-total", "wrong-source", "completed", "topic", "query", "filter"])("hides continue reading for %s without guessing", async condition => {
  const view = { ...reading, current: { ...chunk } };
  if (condition === "missing-source") view.source = empty.source;
  if (condition === "missing-cursor") view.current = null as unknown as typeof chunk;
  if (condition === "missing-section") view.current.sectionPath = [];
  if (condition === "invalid-index") view.current.index = 0;
  if (condition === "invalid-total") view.current.total = 0;
  if (condition === "wrong-source") view.current.sourceId = "B";
  setup({ view, sources: condition === "completed" ? sources.map(s => s.sourceId === "A" ? { ...s, progress: { ...s.progress, chunkId: null } } : s) : sources }); await loaded();
  if (condition === "topic") chooseTopic("topic");
  if (condition === "query") fireEvent.change(screen.getByRole("searchbox"), { target: { value: "Alpha" } });
  if (condition === "filter") fireEvent.click(filters().getByRole("button", { name: "阅读中1" }));
  expect(screen.queryByRole("region", { name: "继续阅读" })).not.toBeInTheDocument();
});
it("counts and applies all five filters including blog failures within Topic and search scope", async () => {
  setup({ view: { ...empty, blog: { A: { error: { message: "blog failure" }, artifacts: {} } as BlogStatus } } }); await loaded();
  await waitFor(() => expect(filters().getByRole("button", { name: "需处理2" })).toBeEnabled());
  for (const name of ["全部4", "阅读中1", "未开始1", "已读完1", "需处理2"]) expect(filters().getByRole("button", { name })).toBeEnabled();
  for (const [name, titles] of [["阅读中1", ["Alpha"]], ["未开始1", ["Beta"]], ["已读完1", ["Gamma"]], ["需处理2", ["Alpha", "Delta"]], ["全部4", ["Alpha", "Beta", "Gamma", "Delta"]]] as const) {
    fireEvent.click(filters().getByRole("button", { name })); expect(within(screen.getByRole("list", { name: "来源" })).getAllByRole("listitem").map(row => within(row).getByRole("heading").textContent)).toEqual(titles);
  }
  chooseTopic("topic"); expect(filters().getByRole("button", { name: "全部2" })).toBeEnabled(); expect(filters().getByRole("button", { name: "已读完0" })).toBeDisabled();
  fireEvent.change(screen.getByRole("searchbox"), { target: { value: "Beta" } }); expect(filters().getByRole("button", { name: "全部1" })).toBeEnabled(); expect(filters().getByRole("button", { name: "阅读中0" })).toBeDisabled();
});
it("keeps the selected zero-count filter enabled, shows filter empty state and pauses every ordering route", async () => {
  const host = setup(); await loaded(); chooseTopic("topic"); fireEvent.click(filters().getByRole("button", { name: "阅读中1" }));
  expect(screen.getByText("筛选时暂停排序；显示全部状态后可调整专题顺序。")).toBeInTheDocument();
  const title = screen.getByRole("button", { name: "Alpha" }); expect(title.closest("article")!.querySelector("[draggable]")).toHaveAttribute("draggable", "false");
  fireEvent.keyDown(title, { altKey: true, key: "ArrowDown" }); fireEvent.click(screen.getByRole("button", { name: "更多" })); expect(screen.getByRole("button", { name: "Alpha 下移" })).toBeDisabled(); expect(host.manageTopic).not.toHaveBeenCalled();
  chooseTopic("other"); expect(filters().getByRole("button", { name: "阅读中0" })).toBeEnabled(); expect(filters().getByRole("button", { name: "全部0" })).toBeDisabled();
  expect(screen.getByText("当前筛选下没有材料。")).toBeInTheDocument(); fireEvent.click(screen.getByRole("button", { name: "显示全部状态" })); expect(filters().getByRole("button", { name: "全部0" })).toBeEnabled();
});
it("distinguishes empty library, search and empty Topic with their specific actions", async () => {
  setup({ sources: [] }); await screen.findByText("知识库还是空的。把 PDF 或 SingleFile HTML 拖到这里，或点击上传。"); fireEvent.click(screen.getByRole("button", { name: "上传材料" })); expect(screen.getByRole("dialog")).toBeInTheDocument(); cleanup();
  setup(); await loaded(); fireEvent.change(screen.getByRole("searchbox"), { target: { value: "absent" } }); expect(screen.getByText("没有标题匹配这次搜索。")).toBeInTheDocument(); fireEvent.click(screen.getByRole("button", { name: "清除搜索" })); expect(screen.getByRole("button", { name: "Alpha" })).toBeInTheDocument();
  chooseTopic("other"); expect(screen.getByText("这个专题还没有来源。可从任意来源的「管理来源」中加入专题。")).toBeInTheDocument(); fireEvent.click(screen.getByRole("button", { name: "查看全部材料" })); expect(screen.getByRole("button", { name: "Alpha" })).toBeInTheDocument();
});
it.each(["result", "rejection", "sync-throw"])("distinguishes listSources %s failure and reconnects", async failure => {
  const listSources = vi.fn().mockImplementationOnce(() => { if (failure === "sync-throw") throw new Error("offline"); return failure === "rejection" ? Promise.reject(new Error("offline")) : Promise.resolve({ ok: false, error: { code: "unknown", message: "offline", retryable: true } }); }).mockResolvedValue(readerSuccess(sources));
  setup({ overrides: { listSources } }); await screen.findByText("无法连接 FOCUS 后端，列表未能读取。已有数据未受影响。"); expect(screen.queryByText(/知识库还是空的/)).not.toBeInTheDocument();
  await act(async () => fireEvent.click(screen.getByRole("button", { name: "重新连接" }))); await loaded(); expect(listSources).toHaveBeenCalledTimes(2);
});
it("does not misclassify unrelated failures or a refresh failure with loaded sources as empty connection failure", async () => {
  setup({ sources: [], overrides: { listInbox: vi.fn(async () => ({ ok: false, error: { code: "unknown", message: "Inbox failure", retryable: true } } as const)) } });
  await screen.findByText(/知识库还是空的/); expect(screen.queryByText(/无法连接 FOCUS 后端/)).not.toBeInTheDocument(); cleanup();
  const host = setup(); await loaded(); vi.mocked(host.listSources!).mockResolvedValue({ ok: false, error: { code: "unknown", message: "offline", retryable: true } });
  fireEvent.click(screen.getByRole("link", { name: "设置" })); await act(async () => fireEvent.click(screen.getByRole("link", { name: "知识库" })));
  expect(screen.getByRole("button", { name: "Alpha" })).toBeInTheDocument(); expect(screen.queryByText(/无法连接 FOCUS 后端/)).not.toBeInTheDocument();
});
it("projects the same Inbox and batch data, hides registered or finished items and reuses recovery callbacks", async () => {
  const host = setup({ inbox: [item, { ...item, itemId: "registered", fileName: "registered.pdf", sourceId: "A" }, { ...item, itemId: "done", fileName: "done.pdf", status: "completed" }], batches: [batch] }); await loaded();
  const shadows = screen.getByRole("region", { name: "入库中" }); expect(within(shadows).getByText("pending.pdf")).toBeInTheDocument(); expect(within(shadows).getByText("batch.pdf")).toBeInTheDocument(); expect(within(shadows).queryByText("registered.pdf")).not.toBeInTheDocument(); expect(within(shadows).queryByText("done.pdf")).not.toBeInTheDocument();
  expect(shadows).toHaveTextContent("本地 MinerU · 处理失败，可继续 · 排队中"); expect(shadows).toHaveTextContent("25%"); expect(within(shadows).getByRole("progressbar")).toHaveAttribute("aria-valuenow", "25"); expect(within(shadows).getAllByRole("status")[0]).not.toHaveTextContent("25%");
  fireEvent.click(within(shadows).getByRole("button", { name: "pending.pdf 任务详情" })); const tasks = document.querySelector(".workspace-task-frame") as HTMLElement; expect(within(tasks).getByText("pending.pdf")).toBeInTheDocument(); expect(within(tasks).getByText("batch.pdf")).toBeInTheDocument();
  await act(async () => fireEvent.click(within(shadows).getByRole("button", { name: "继续" }))); expect(host.continueIngestion).toHaveBeenCalledWith("pending", expect.any(String));
  await act(async () => fireEvent.click(within(shadows).getByRole("button", { name: "重试未完成步骤" }))); expect(host.controlBatch).toHaveBeenCalledWith("batch", "retry-item", expect.any(String), "batch-item", undefined);
  chooseTopic("other"); expect(screen.queryByRole("region", { name: "入库中" })).not.toBeInTheDocument();
});
it("keeps risky resubmission only in task details and matches title-only targets and Unfiled", async () => {
  const host = setup({ inbox: [{ ...item, topicId: null, resubmitRisk: { choiceId: "risk" } }, { ...item, itemId: "loose", fileName: "loose.pdf", topicId: null, topicTitle: null }], batches: [{ ...batch, items: [{ ...batch.items[0], resubmitRisk: { choice_id: "risk" } }] }] }); await loaded(); chooseTopic("topic");
  const shadows = screen.getByRole("region", { name: "入库中" }); expect(within(shadows).queryByRole("button", { name: "继续" })).not.toBeInTheDocument(); expect(within(shadows).queryByRole("button", { name: "重试未完成步骤" })).not.toBeInTheDocument(); expect(within(shadows).getAllByRole("button")).toHaveLength(2); expect(host.continueIngestion).not.toHaveBeenCalled();
  chooseTopic(UNFILED); expect(screen.getByRole("region", { name: "入库中" })).toHaveTextContent("loose.pdf"); expect(screen.getByRole("region", { name: "入库中" })).not.toHaveTextContent("pending.pdf");
});
it("prefills the real Topic for upload and file drop, never Unfiled, and shows a page overlay", async () => {
  const host = setup(); await loaded(); chooseTopic("topic"); fireEvent.click(screen.getByRole("button", { name: "上传" })); expect(screen.getByRole("combobox", { name: "专题" })).toHaveValue("编译"); fireEvent.click(screen.getByRole("button", { name: "取消" }));
  const dataTransfer = { types: ["Files"], files: [new File(["pdf"], "test.pdf", { type: "application/pdf" })] };
  fireEvent.dragOver(screen.getByRole("main"), { dataTransfer }); expect(screen.getByText("松开即可上传")).toBeInTheDocument(); fireEvent.drop(screen.getByRole("main"), { dataTransfer }); expect(screen.getByText("松开即可上传").closest(".library-drop")).toHaveAttribute("aria-hidden", "true"); expect(screen.getByText("松开即可上传").closest(".library-drop")).toHaveAttribute("inert"); expect(screen.getByRole("combobox", { name: "专题" })).toHaveValue("编译"); expect(host.stageIngestion).not.toHaveBeenCalled(); fireEvent.click(screen.getByRole("button", { name: "取消" }));
  chooseTopic(UNFILED); fireEvent.click(screen.getByRole("button", { name: "上传" })); expect(screen.getByRole("combobox", { name: "专题" })).toHaveValue("");
});
