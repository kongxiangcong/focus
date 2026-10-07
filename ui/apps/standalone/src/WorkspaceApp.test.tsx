// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { readerSuccess, type BlogArtifactName, type BlogStatus, type IngestionItem, type ReaderHostResult, type ReaderHost, type ReadingPreparation, type ReadingWindow } from "@focus/reader-contracts";
import { WorkspaceApp } from "./WorkspaceApp";
const empty: ReadingWindow = { status: "empty", current: null, history: [], conversation: [], source: { sourceId: "", title: "", topicId: null }, sessionId: "s1",
  agent: { run: null, catalog: { sources: [], topics: [] }, backend: "codex", backends: [{ id: "codex", label: "Codex" }, { id: "deepseek", label: "DeepSeek" }] } };
function blogStatus(overrides: Partial<BlogStatus> = {}, artifacts: Partial<Record<BlogArtifactName, { status: BlogStatus["artifacts"]["html"]["status"]; updatedAt: string | null }>> = {}): BlogStatus {
  return {
    sourceId: "a-paper", generated: true, methodVersion: "article-blog-v1", runStatus: "completed",
    artifacts: { value_analysis: { status: "completed", updatedAt: "2026-09-24T00:00:00Z" }, reading_blog: { status: "completed", updatedAt: "2026-09-24T00:00:00Z" }, html: { status: "completed", updatedAt: "2026-09-24T00:00:00Z" }, ...artifacts },
    valueAnalysis: { applicable: true, direction: "design_space_exploration", reason: "主贡献是设计变量与搜索选择" },
    verificationLevel: "paper_reading", warnings: [], error: null, ...overrides,
  };
}
function setup(initialInbox: readonly IngestionItem[] = [], initialWindow: ReadingWindow = empty) {
  const staged: IngestionItem = { itemId: "item-1", fileName: "test.pdf", status: "awaiting_confirmation", topicTitle: "编译", topicId: null, sourceId: null, documentStatus: "not_started", topicStatus: "not_started", services: ["mineru"] };
  const confirmed: IngestionItem = { ...staged, status: "confirmed", confirmation: { services: ["mineru"], purpose: "register source", scope: "ingestion" } };
  const processing: IngestionItem = { ...staged, status: "processing" };
  const cancelled: IngestionItem = { ...staged, status: "cancelled" };
  const host: ReaderHost = {
    getReadingWindow: vi.fn(async () => readerSuccess(initialWindow)), continueReading: vi.fn(async () => readerSuccess(empty)), sendMessage: vi.fn(async () => readerSuccess(empty)),
    listTopics: vi.fn(async () => readerSuccess([{ topicId: "topic", title: "编译", sourceIds: ["a-paper"] }])),
    listSources: vi.fn(async () => readerSuccess([{ sourceId: "a-paper", title: "A Paper", kind: "paper" as const, parseStatus: "ready" as const, error: null, noteCount: 2, topicIds: ["topic"], progress: { completed: 1, total: 4, planId: "plan-001", chunkId: "chunk-002" } }])),
    listInbox: vi.fn(async () => readerSuccess(initialInbox)), stageIngestion: vi.fn(async () => readerSuccess(staged)),
    listBatches: vi.fn(async () => readerSuccess([])),
    clearFinishedStatuses: vi.fn(async () => readerSuccess(empty)),
    startBatch: vi.fn(async () => readerSuccess({ batchId: "batch-1", topicId: "topic", status: "confirmed" as const, error: null, items: [] })),
    controlBatch: vi.fn(async () => readerSuccess({ batchId: "batch-1", topicId: "topic", status: "paused" as const, error: null, items: [] })),
    createTopic: vi.fn(async () => readerSuccess({})), manageTopic: vi.fn(async () => readerSuccess({})),
    deletionImpact: vi.fn(async id => readerSuccess({ sourceId: id, title: "A Paper", topics: [{ topicId: "topic", title: "编译", sourceIds: [id] }], assets: { bundle: true, blog: true, notes: true, plans: 1, progress: true } })),
    clearSource: vi.fn(async () => readerSuccess(empty)),
    saveSourceDetails: vi.fn(async () => readerSuccess(empty)),
    renameSource: vi.fn(async () => readerSuccess({})),
    startIngestion: vi.fn(async () => readerSuccess(confirmed)),
    confirmIngestion: vi.fn(async () => readerSuccess(confirmed)),
    processIngestion: vi.fn(async () => readerSuccess(processing)), continueIngestion: vi.fn(async () => readerSuccess(processing)), cancelIngestion: vi.fn(async () => readerSuccess(cancelled)),
    resubmitIngestion: vi.fn(async () => readerSuccess(processing)),
    sourceOriginalUrl: id => `/library/sources/${id}/original`, sourceContentUrl: id => `/library/sources/${id}/content`,
    openSource: vi.fn(async () => readerSuccess(empty)), deleteSource: vi.fn(async () => readerSuccess(empty)), rereadSource: vi.fn(async () => readerSuccess(empty)),
    blogStatus: vi.fn(async () => readerSuccess(blogStatus({ generated: false }))),
    generateBlog: vi.fn(async () => readerSuccess(blogStatus({ runStatus: "running" }))),
    regenerateBlog: vi.fn(async () => readerSuccess(blogStatus())),
    cancelBlog: vi.fn(async () => readerSuccess(blogStatus({ runStatus: "cancelled" }))),
    blogUrl: (id: string) => `/library/sources/${id}/blog/html`,
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

it("accepts saved HTML and defaults to parsing with blog generation", async () => {
  const { host } = setup();
  const staged: IngestionItem = { itemId: "html-1", fileName: "article.html", status: "awaiting_confirmation", topicTitle: "编译", topicId: null, sourceId: null, documentStatus: "not_started", topicStatus: "not_started", services: ["local-html"] };
  vi.mocked(host.stageIngestion!).mockResolvedValue(readerSuccess(staged));
  await screen.findByRole("heading", { name: "A Paper" });
  fireEvent.click(screen.getByRole("button", { name: "上传" }));
  fireEvent.change(screen.getByRole("combobox", { name: "专题" }), { target: { value: "编译" } });
  const file = new File(["<html>article</html>"], "article.html", { type: "text/html" });
  fireEvent.change(screen.getByLabelText("上传材料"), { target: { files: [file] } });
  expect(screen.getByRole("checkbox", { name: "仅解析入库" })).not.toBeChecked();
  expect(screen.queryByText(/本地 HTML 解析器（不上传原件）/)).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "开始解析并生成博客" }));
  await waitFor(() => expect(host.startBatch).toHaveBeenCalledWith(["html-1"], expect.any(String), true));
  expect(host.stageIngestion).toHaveBeenCalled();
  expect(host.processIngestion).not.toHaveBeenCalled();
});
afterEach(cleanup);
it("shows the selected PDF backend and queued progress in the visible Inbox", async () => {
  const item: IngestionItem = { itemId: "pdf-1", fileName: "paper.pdf", status: "processing", topicTitle: null,
    topicId: null, sourceId: null, documentStatus: "not_started", topicStatus: "not_started",
    parserBackend: "local-mineru", selectionReason: "本地 MinerU 4.0.8 Standard V1 可用", parserProgress: { status: "queued" } };
  setup([item]);
  fireEvent.click(screen.getByRole("button", { name: "任务详情" }));
  await screen.findByText(/本地 MinerU · 本地 MinerU 4.0.8 Standard V1 可用 · 排队中/);
});
it.each(["check", "open"])("retains the newest shared configuration when a late %s response arrives after another page refreshed", async action => {
  history.replaceState(null, "", action === "check" ? "/settings" : "/library");
  const codex = { backend: "codex" as const, model: "gpt-6-astra", runtimePath: null, credentialFile: null };
  const deepseek = { ...codex, backend: "deepseek" as const, model: "deepseek-v4-flash" };
  const initial = { ...empty, revision: 1, configuration: { saved: codex, effective: codex, pending: false, busy: false, refreshBlocked: false } };
  let publish!: (result: ReturnType<typeof readerSuccess<ReadingWindow>>) => void;
  let resolveSave!: (result: ReturnType<typeof readerSuccess<ReadingWindow>>) => void;
  const host: ReaderHost = {
    getReadingWindow: vi.fn(async () => readerSuccess(initial)),
    sendMessage: vi.fn(async () => readerSuccess(initial)),
    refreshBackendConfiguration: vi.fn(async () => readerSuccess(initial)),
    continueReading: vi.fn(async () => readerSuccess(initial)),
    listSources: vi.fn(async () => readerSuccess([{ sourceId: "a-paper", title: "A Paper", kind: "paper" as const, parseStatus: "ready" as const, error: null, noteCount: 0, topicIds: [], progress: { completed: 0, total: 0, planId: null, chunkId: null } }])),
    listTopics: vi.fn(async () => readerSuccess([])),
    subscribe: callback => { publish = callback; return () => {}; },
    backendSetup: vi.fn(async (action, input) => readerSuccess({ backend: input.backend, runtimePath: null, status: action === "prepare" ? "installed" : "success", message: "OK" })),
    saveBackendConfiguration: vi.fn(() => new Promise<ReturnType<typeof readerSuccess<ReadingWindow>>>(resolve => { resolveSave = resolve; })),
    openSource: vi.fn(() => new Promise<ReturnType<typeof readerSuccess<ReadingWindow>>>(resolve => { resolveSave = resolve; })),
  };
  render(<WorkspaceApp host={host} />);
  if (action === "check") {
    await screen.findByRole("radio", { name: "Codex" });
    fireEvent.click(screen.getByRole("radio", { name: "DeepSeek" }));
    fireEvent.click(screen.getByRole("button", { name: "连接检查" }));
    await screen.findByText(/连接检查通过；已检模型/);
    fireEvent.click(screen.getByRole("button", { name: "保存并应用" }));
  } else {
    fireEvent.click(await screen.findByRole("button", { name: "详细" }));
    fireEvent.click(screen.getByRole("button", { name: "准备阅读" }));
  }
  if (action === "check") await waitFor(() => expect(host.saveBackendConfiguration).toHaveBeenCalled());
  await act(async () => publish(readerSuccess({ ...initial, revision: 3, agent: { ...empty.agent!, backend: "deepseek" }, configuration: { ...initial.configuration, saved: deepseek, effective: deepseek } })));
  await act(async () => resolveSave(readerSuccess({ ...initial, revision: 2, configuration: { ...initial.configuration, saved: deepseek, pending: true } })));
  expect(screen.queryByText("配置更改，需要刷新页面")).not.toBeInTheDocument();
  if (action === "open") fireEvent.click(screen.getByRole("link", { name: "设置" }));
  expect(screen.getByRole("radio", { name: "DeepSeek" })).toBeChecked();
});
it("edits original metadata and Topic membership through Host actions", async () => {
  const { host } = setup();
  await screen.findByRole("heading", { name: "A Paper" });
  if (screen.getByRole("button", { name: "详细" }).getAttribute("aria-expanded") === "false") fireEvent.click(screen.getByRole("button", { name: "详细" }));
  fireEvent.click(screen.getByRole("button", { name: "管理来源" }));
  fireEvent.change(screen.getByRole("textbox", { name: "来源原题" }), { target: { value: "Correct title" } });
  fireEvent.click(screen.getByRole("button", { name: "保存" }));
  await waitFor(() => expect(host.saveSourceDetails).toHaveBeenCalledWith("a-paper", "Correct title", ["topic"], expect.any(String)));
  await waitFor(() => expect(screen.queryByRole("textbox", { name: "来源原题" })).not.toBeInTheDocument());
  if (screen.getByRole("button", { name: "详细" }).getAttribute("aria-expanded") === "false") fireEvent.click(screen.getByRole("button", { name: "详细" }));
  fireEvent.click(screen.getByRole("button", { name: "管理来源" }));
  fireEvent.click(screen.getByRole("checkbox", { name: "编译" }));
  expect(host.manageTopic).not.toHaveBeenCalled();
  expect(host.saveSourceDetails).toHaveBeenCalledTimes(1);
  fireEvent.click(screen.getByRole("button", { name: "取消" }));
  expect(host.saveSourceDetails).toHaveBeenCalledTimes(1);
  expect(host.deleteSource).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button', { name: '管理来源' }));
  fireEvent.click(screen.getByRole('button', { name: '不关联专题' }));
  expect(screen.getByRole('checkbox', { name: '编译' })).not.toBeChecked();
  fireEvent.click(screen.getByRole('button', { name: '保存' }));
  await waitFor(() => expect(host.saveSourceDetails).toHaveBeenNthCalledWith(2, 'a-paper', 'A Paper', [], expect.any(String)));
});
it("freezes a mixed selection into one Topic batch and exposes each result", async () => {
  const { host } = setup();
  vi.mocked(host.stageIngestion!).mockImplementation(async file => readerSuccess({
    itemId: file.name, fileName: file.name, status: "awaiting_confirmation", topicTitle: "编译", topicId: null,
    sourceId: null, documentStatus: "not_started", topicStatus: "not_started",
  }));
  await screen.findByRole("heading", { name: "A Paper" });
  fireEvent.click(screen.getByRole("button", { name: "上传" }));
  fireEvent.change(screen.getByRole("combobox", { name: "专题" }), { target: { value: "编译" } });
  const files = [new File(["%PDF"], "one.pdf"), new File(["<html>"], "two.html")];
  fireEvent.change(screen.getByLabelText("上传材料"), { target: { files } });
  expect(screen.getByLabelText("上传材料")).toHaveAttribute("multiple");
  vi.mocked(host.listBatches!).mockResolvedValue(readerSuccess([{
    batchId: "batch-1", topicId: "topic", status: "partial", error: null,
    items: [
      { itemId: "one.pdf", fileName: "one.pdf", sourceId: "a-paper", status: "completed", ingestionStatus: "completed", blog: blogStatus(), error: null },
      { itemId: "two.html", fileName: "two.html", sourceId: null, status: "failed", ingestionStatus: "failed", blog: null, error: { error_id: "article_image_missing", message: "图片缺失" } },
    ],
  }]));
  fireEvent.click(screen.getByRole("button", { name: "开始解析并生成博客" }));
  await waitFor(() => expect(host.startBatch).toHaveBeenCalledWith(["one.pdf", "two.html"], expect.any(String), true));
  expect(host.stageIngestion).toHaveBeenNthCalledWith(1, files[0], { topicTitle: "编译" });
  expect(host.stageIngestion).toHaveBeenNthCalledWith(2, files[1], { topicTitle: "编译" });
  fireEvent.click(screen.getByRole("button", { name: "任务详情" }));
  fireEvent.click(await screen.findByText("当前任务 / 待处理", { selector: "summary" }));
  expect(await screen.findByText("编译 · 部分完成")).toBeVisible();
  expect(screen.getByText("图片缺失")).toBeVisible();
  fireEvent.click(screen.getByRole("button", { name: "继续剩余工作" }));
  await waitFor(() => expect(host.controlBatch).toHaveBeenCalledWith("batch-1", "continue", expect.any(String), undefined, undefined));
  expect(host.confirmIngestion).not.toHaveBeenCalled();
});
it("lands in Library and persists the chosen font across remounts", async () => {
  const app = setup(); await screen.findByRole("heading", { name: "A Paper" });
  expect(location.pathname).toBe("/library");
  fireEvent.click(screen.getByRole("link", { name: "设置" }));
  fireEvent.change(screen.getByRole("slider", { name: "字号" }), { target: { value: "3" } });
  expect(screen.getByText("阅读字号预览 · 特大")).toHaveStyle({ fontSize: "26px" });
  expect(screen.getByRole("radio", { name: "DeepSeek" })).toBeEnabled();
  fireEvent.click(screen.getByRole("button", { name: "保存并应用" }));
  app.unmount(); setup();
  expect(await screen.findByRole("slider", { name: "字号" })).toHaveValue("3");
  fireEvent.click(screen.getByRole("link", { name: "阅读" }));
  expect(screen.getByRole("complementary", { name: "阅读进度与操作" })).toBeVisible();
  expect(document.querySelector(".focus-mist")).toHaveAttribute("data-font-size", "extra");
  expect(document.querySelector(".focus-mist")).toHaveStyle({ "--reader-reading-size": "26px" });
});
it("starts parsing and blog with one explicit confirmation", async () => {
  const { host } = setup(); await screen.findByRole("heading", { name: "A Paper" });
  const pdf = new File(["%PDF test"], "test.pdf", { type: "application/pdf" });
  fireEvent.click(screen.getByRole("button", { name: "上传" }));
  fireEvent.change(screen.getByRole("combobox", { name: "专题" }), { target: { value: "编译" } });
  fireEvent.change(screen.getByLabelText("上传材料"), { target: { files: [pdf] } });
  expect(host.stageIngestion).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "开始解析并生成博客" }));
  await waitFor(() => expect(host.stageIngestion).toHaveBeenCalledWith(pdf, { topicTitle: "编译" }));
  await waitFor(() => expect(host.startBatch).toHaveBeenCalledWith(["item-1"], expect.any(String), true));
  expect(host.confirmIngestion).not.toHaveBeenCalled();
  expect(host.processIngestion).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "详细" }));
  await waitFor(() => expect(screen.getByRole("button", { name: "删除" })).toBeEnabled());
  fireEvent.click(screen.getByRole("button", { name: "删除" }));
  expect(host.deleteSource).not.toHaveBeenCalled();
  fireEvent.click(await screen.findByRole("button", { name: "永久删除" }));
  await waitFor(() => expect(host.deleteSource).toHaveBeenCalledWith("a-paper"));
  await waitFor(() => expect(screen.queryByRole("button", { name: "从头阅读" })).not.toBeInTheDocument());
  expect(host.rereadSource).not.toHaveBeenCalled();
});
it("filters source cards, exposes source resources, and rejects unsupported ingestion formats", async () => {
  const { host } = setup(); await screen.findByRole("heading", { name: "A Paper" });
  fireEvent.click(screen.getByRole("button", { name: "详细" }));
  expect(document.querySelector(".source-badge")?.closest("article")).toBeInTheDocument();
  expect(screen.getByRole("progressbar", { name: "A Paper 阅读进度" })).toHaveAttribute("value", "1");
  fireEvent.change(screen.getByRole("searchbox"), { target: { value: "missing" } });
  expect(screen.getByText("暂无匹配材料")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "重置" }));
  const page = screen.getByRole("main");
  expect(screen.getByRole("link", { name: "原件" })).toHaveAttribute("href", "/library/sources/a-paper/original");
  expect(screen.getByRole("link", { name: "正文" })).toHaveAttribute("href", "/library/sources/a-paper/content");
  fireEvent.drop(page, { dataTransfer: { files: [new File(["text"], "file.txt")] } });
  expect(host.stageIngestion).not.toHaveBeenCalled();
  expect(screen.getByRole("alert")).toHaveTextContent("请选择 PDF 或 SingleFile HTML");
});

it("restores authoritative Inbox state after refresh and continues attachment recovery", async () => {
  const recovering: IngestionItem = { itemId: "recover", fileName: "paper.pdf", status: "topic_attachment_pending", topicTitle: "系统", topicId: null, sourceId: "a-paper", documentStatus: "published", topicStatus: "pending_recovery" };
  const { host } = setup([recovering]);
  fireEvent.click(screen.getByRole("button", { name: "任务详情" }));
  expect(await screen.findByText("文档已入库，专题关联待恢复")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "继续" }));
  await waitFor(() => expect(host.continueIngestion).toHaveBeenCalledWith("recover", expect.any(String)));
});
it("offers explicit reconfirmation for a recoverable Inbox item", async () => {
  const interrupted: IngestionItem = { itemId: "recover", fileName: "paper.pdf", status: "interrupted", topicTitle: "系统", topicId: null, sourceId: null, documentStatus: "not_started", topicStatus: "not_started", services: ["mineru"] };
  const { host } = setup([interrupted]);
  fireEvent.click(screen.getByRole("button", { name: "任务详情" }));
  fireEvent.click(await screen.findByRole("button", { name: "重新确认并开始" }));
  await waitFor(() => expect(host.startBatch).toHaveBeenCalledWith(["recover"], expect.any(String)));
  expect(host.processIngestion).not.toHaveBeenCalled();
});
it("persists brightness and omits the unused network control", async () => {
  setup(); await screen.findByRole("heading", { name: "A Paper" });
  fireEvent.click(screen.getByRole("link", { name: "设置" }));
  fireEvent.change(screen.getByRole("slider", { name: "亮度" }), { target: { value: "90" } });
  expect(localStorage.getItem("focus.brightness")).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "保存并应用" }));
  expect(localStorage.getItem("focus.brightness")).toBe("90");
  expect(screen.queryByRole("switch", { name: "网络" })).not.toBeInTheDocument();
});
it("shows the original unfinished task instead of a new one when the same file is added again", async () => {
  const { host } = setup();
  const existing: IngestionItem = { itemId: "item-1", fileName: "test.pdf", status: "status_check_required", topicTitle: "编译", topicId: null, sourceId: null, documentStatus: "not_started", topicStatus: "not_started", services: ["mineru"], duplicate: true };
  vi.mocked(host.stageIngestion!).mockResolvedValue(readerSuccess(existing));
  vi.mocked(host.listInbox!).mockResolvedValue(readerSuccess([existing]));
  await screen.findByRole("heading", { name: "A Paper" });
  fireEvent.click(screen.getByRole("button", { name: "上传" }));
  fireEvent.change(screen.getByRole("combobox", { name: "专题" }), { target: { value: "编译" } });
  fireEvent.change(screen.getByLabelText("上传材料"), { target: { files: [new File(["%PDF test"], "test.pdf", { type: "application/pdf" })] } });
  fireEvent.click(screen.getByRole("button", { name: "开始解析并生成博客" }));

  const notice = await screen.findByText(/该原件已有未完成任务/);
  expect(notice.closest("[role=status]")).not.toBeNull();
  expect(notice).toHaveTextContent("已回到原任务；不会重复解析。");
  fireEvent.click(screen.getByRole("button", { name: "任务详情" }));
  const row = document.querySelector(".library-inbox-item");
  expect(row).toHaveTextContent("test.pdf");
  expect(row).toHaveTextContent("远端状态待核对");
  expect(row).toHaveTextContent("编译");
  expect(host.processIngestion).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "关闭" }));
  expect(screen.queryByText(/该原件已有未完成任务/)).not.toBeInTheDocument();
});
it("explains the duplicate-parsing risk next to an explicit resubmission action", async () => {
  const unknown: IngestionItem = { itemId: "item-1", fileName: "paper.pdf", status: "status_check_required", topicTitle: "编译", topicId: null, sourceId: null, documentStatus: "not_started", topicStatus: "not_started", services: ["mineru"], remoteReference: false, resubmitRisk: { choiceId: "choice-1" } };
  const { host } = setup([unknown]);
  fireEvent.click(screen.getByRole("button", { name: "任务详情" }));
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
  fireEvent.click(screen.getByRole("button", { name: "任务详情" }));
  expect(await screen.findByText("上次提交结果未知，重新提交可能重复解析。")).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "继续" })).not.toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "重新提交" }));

  await waitFor(() => expect(host.resubmitIngestion).toHaveBeenCalledWith("item-1", expect.any(String), "choice-1"));
  expect(host.continueIngestion).not.toHaveBeenCalled();
});
it("generates a blog from the source card and shows the three sub-statuses", async () => {
  const { host } = setup();
  fireEvent.click(await screen.findByRole("button", { name: "详细" }));
  fireEvent.click(screen.getByRole("button", { name: "生成博客" }));
  await waitFor(() => expect(host.generateBlog).toHaveBeenCalledWith("a-paper", expect.any(String)));
  expect(await screen.findByText("价值分析")).toBeInTheDocument();
  expect(screen.getByText("带读博客")).toBeInTheDocument();
  expect(screen.getByText("HTML")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "打开博客" })).toBeEnabled();
  expect(screen.getByRole("button", { name: "重新生成" })).toBeEnabled();
});
it("names the retry button by the failed artifact only", async () => {
  const { host } = setup();
  host.generateBlog = vi.fn(async () => readerSuccess(blogStatus({}, { html: { status: "failed", updatedAt: null } })));
  fireEvent.click(await screen.findByRole("button", { name: "详细" }));
  fireEvent.click(screen.getByRole("button", { name: "生成博客" }));
  const retry = await screen.findByRole("button", { name: "重新生成 HTML" });
  expect(screen.queryByRole("button", { name: "重新生成价值分析" })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "重新生成带读博客" })).not.toBeInTheDocument();
  fireEvent.click(retry);
  await waitFor(() => expect(host.regenerateBlog).toHaveBeenCalledWith("a-paper", expect.any(String), "html"));
});
it("cancels a running blog through the shared host contract", async () => {
  const { host } = setup();
  fireEvent.click(await screen.findByRole("button", { name: "详细" }));
  fireEvent.click(screen.getByRole("button", { name: "生成博客" }));
  fireEvent.click(await screen.findByRole("button", { name: "取消生成" }));
  await waitFor(() => expect(host.cancelBlog).toHaveBeenCalledWith("a-paper"));
});
it("explains a skipped value analysis instead of showing it as pending", async () => {
  const { host } = setup();
  host.generateBlog = vi.fn(async () => readerSuccess(blogStatus({
    valueAnalysis: { applicable: false, direction: null, reason: "主贡献是数据集与训练技巧" },
    warnings: ["本次运行环境无网络，未检索论文内链接与官方仓库"],
  }, { value_analysis: { status: "not_applicable", updatedAt: null } })));
  fireEvent.click(await screen.findByRole("button", { name: "详细" }));
  fireEvent.click(screen.getByRole("button", { name: "生成博客" }));
  expect(await screen.findByText(/架构价值分析不适用：主贡献是数据集与训练技巧/)).toBeInTheDocument();
  expect(screen.queryByText(/降级与证据缺口：/)).not.toBeInTheDocument();
  expect(screen.queryByText(/本次运行环境无网络/)).not.toBeInTheDocument();
});
it("opens the blog in the embedded viewer from the same host surface", async () => {
  const { host } = setup();
  fireEvent.click(await screen.findByRole("button", { name: "详细" }));
  fireEvent.click(screen.getByRole("button", { name: "生成博客" }));
  fireEvent.click(await screen.findByRole("button", { name: "打开博客" }));
  const frame = await screen.findByTitle("博客");
  expect(frame).toHaveAttribute("src", "/library/sources/a-paper/blog/html");
  fireEvent.click(screen.getByRole("button", { name: "关闭" }));
  expect(screen.queryByTitle("博客")).not.toBeInTheDocument();
});
it("always includes blog in the explicit ingestion confirmation", async () => {
  const staged: IngestionItem = { itemId: "item-1", fileName: "paper.pdf", status: "awaiting_confirmation", topicTitle: "编译", topicId: null, sourceId: null, documentStatus: "not_started", topicStatus: "not_started", services: ["mineru"] };
  const { host } = setup([staged]);
  fireEvent.click(screen.getByRole("button", { name: "任务详情" }));
  expect(screen.queryByRole("checkbox", { name: /同时生成博客/ })).not.toBeInTheDocument();
  await screen.findByRole("button", { name: "开始解析并生成博客" });
  fireEvent.click(screen.getByRole("button", { name: "开始解析并生成博客" }));
  await waitFor(() => expect(host.startBatch).toHaveBeenCalledWith(["item-1"], expect.any(String)));
});
it("offers querying the original task first when a remote reference exists", async () => {
  const unknown: IngestionItem = { itemId: "item-1", fileName: "paper.pdf", status: "status_check_required", topicTitle: "编译", topicId: null, sourceId: null, documentStatus: "not_started", topicStatus: "not_started", services: ["mineru"], remoteReference: true, resubmitRisk: { choiceId: "choice-1" } };
  const { host } = setup([unknown]);
  fireEvent.click(screen.getByRole("button", { name: "任务详情" }));
  expect(await screen.findByRole("button", { name: "查询并续接原任务" })).toBeEnabled();
  expect(screen.getByText("上次提交结果未知，重新提交可能重复解析。")).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "查询并续接原任务" }));

  await waitFor(() => expect(host.continueIngestion).toHaveBeenCalledWith("item-1", expect.any(String)));
  expect(host.resubmitIngestion).not.toHaveBeenCalled();
});

it("clears source discussion only after irreversible confirmation and supports cancellation", async () => {
  const { host } = setup();
  fireEvent.click(await screen.findByRole("button", { name: "详细" }));
  fireEvent.click(screen.getByRole("button", { name: "重新阅读" }));
  expect(screen.getByText(/将清除本篇讨论、笔记和阅读记录/)).toBeVisible();
  fireEvent.click(screen.getByRole("button", { name: "取消" }));
  expect(host.clearSource).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "重新阅读" }));
  fireEvent.click(screen.getByRole("button", { name: "确认重新阅读" }));
  await waitFor(() => expect(host.clearSource).toHaveBeenCalledWith("a-paper", expect.any(String)));
  expect(host.deleteSource).not.toHaveBeenCalled();
});

it("keeps cards compact, expands details, and persists list display", async () => {
  const app = setup();
  const title = await screen.findByRole("heading", { name: "A Paper" });
  const card = title.closest("article")!;
  expect(within(card).getAllByRole("button").map(button => button.textContent)).toEqual(["打开博客", "继续阅读", "详细"]);
  expect(screen.queryByRole("button", { name: "管理来源" })).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "打开博客" })).toBeDisabled();
  fireEvent.click(screen.getByRole("button", { name: "详细" }));
  expect(screen.getByRole("button", { name: "详细" })).toHaveAttribute("aria-expanded", "true");
  expect(screen.getByText("解析：已完成")).toBeVisible();
  expect(screen.getByRole("button", { name: "管理来源" })).toBeVisible();
  fireEvent.click(screen.getByRole("button", { name: "列表显示" }));
  expect(card.parentElement).toHaveAttribute("data-view", "list");
  fireEvent.click(screen.getByRole("button", { name: "详细" }));
  expect(within(card).getAllByRole("button")).toHaveLength(3);
  fireEvent.click(screen.getByRole("button", { name: "继续阅读" }));
  await waitFor(() => expect(app.host.openSource).toHaveBeenCalledWith("a-paper", expect.any(String)));
  app.unmount(); setup();
  await screen.findByRole("heading", { name: "A Paper" });
  expect(screen.getByRole("button", { name: "列表显示" })).toHaveAttribute("aria-pressed", "true");
});
it("keeps preparation details collapsed while its main action reflects progress", async () => {
  const { host } = setup();
  const preparation: ReadingPreparation = { source_id: "a-paper", status: "running", step: "context", completed: 0, total: 0, ready: false, error: null, plan_id: null };
  vi.mocked(host.openSource!).mockResolvedValue(readerSuccess({ ...empty, preparations: { "a-paper": preparation } }));
  const card = (await screen.findByRole("heading", { name: "A Paper" })).closest("article")!;
  fireEvent.click(within(card).getByRole("button", { name: "继续阅读" }));
  await within(card).findByRole("button", { name: "阅读准备中…" });
  expect(within(card).queryByText("阅读准备中 · 正在分析全文")).not.toBeInTheDocument();
  expect(within(card).getByRole("button", { name: "详细" })).toHaveAttribute("aria-expanded", "false");
  expect(within(card).getByRole("button", { name: "阅读准备中…" })).toBeDisabled();

  fireEvent.click(within(card).getByRole("button", { name: "详细" }));
  expect(within(card).getByText("阅读准备中 · 正在分析全文")).toBeVisible();
  expect(host.openSource).toHaveBeenCalledTimes(1);
});
it.each([
  ["plan", "running", false, 0, 0, null, "阅读准备中 · 正在生成计划"],
  ["translate", "running", false, 9, 10, null, "阅读准备中 · 正在翻译 · 9/10 段"],
  ["check", "running", false, 10, 10, null, "阅读准备中 · 正在检查 · 10/10 段"],
  ["ready", "ready", true, 10, 10, null, "阅读已准备好，可手动点击开始阅读"],
  ["translate", "failed", false, 9, 10, "网络错误", "阅读准备失败 · 网络错误"],
  ["translate", "interrupted", false, 9, 10, null, "阅读准备已中断"],
] as const)("reveals %s/%s preparation only when details are requested", async (step, status, ready, completed, total, error, message) => {
  const preparation: ReadingPreparation = { source_id: "a-paper", step, status, ready, completed, total, error, plan_id: ready ? "plan-001" : null };
  const { host } = setup([], { ...empty, preparations: { "a-paper": preparation } });
  const card = (await screen.findByRole("heading", { name: "A Paper" })).closest("article")!;
  expect(within(card).getByRole("button", { name: "详细" })).toHaveAttribute("aria-expanded", "false");
  expect(within(card).queryByText(message)).not.toBeInTheDocument();
  fireEvent.click(within(card).getByRole("button", { name: "详细" }));
  expect(within(card).getByText(message)).toBeVisible();
  if (ready) {
    fireEvent.click(within(card).getByRole("button", { name: "继续阅读" }));
    await waitFor(() => expect(host.openSource).toHaveBeenCalledWith("a-paper", expect.any(String)));
  }
});
it.each([
  ["invalid", "completed", 4, "failed"],
  ["ready", "unplanned", 0, "unread"],
  ["ready", "reading", 0, "unread"],
  ["ready", "reading", 1, "reading"],
  ["ready", "completed", 4, "completed"],
] as const)("projects %s / %s / %i to the %s card state", async (parseStatus, readingStatus, completed, expected) => {
  const { host } = setup();
  vi.mocked(host.listSources!).mockResolvedValue(readerSuccess([{ sourceId: "a-paper", title: "A Paper", kind: "paper", parseStatus, readingStatus, error: null, noteCount: 0, topicIds: [], progress: { completed, total: 4, planId: "plan-001", chunkId: readingStatus === "completed" ? null : "chunk-001" } }]));
  // The initial refresh starts before the mock replacement; trigger a fresh projection.
  await screen.findByRole("heading", { name: "A Paper" });
  fireEvent.click(screen.getByRole("link", { name: "设置" }));
  fireEvent.click(screen.getByRole("link", { name: "知识库" }));
  await waitFor(() => expect(screen.getByRole("heading", { name: "A Paper" }).closest("article")).toHaveAttribute("data-status", expected));
});

it("T23/T24 allows unclassified parse-only upload with an explicit immutable scope", async () => {
  const { host } = setup();
  await screen.findByRole("heading", { name: "A Paper" });
  fireEvent.click(screen.getByRole('button', { name: /^编译/ }));
  fireEvent.click(screen.getByRole("button", { name: "上传" }));
  expect(screen.getByRole('combobox', { name: '专题' })).toHaveValue('');
  fireEvent.click(screen.getByRole("checkbox", { name: "仅解析入库" }));
  const file = new File(["%PDF test"], "unclassified.pdf");
  fireEvent.change(screen.getByLabelText("上传材料"), { target: { files: [file] } });
  fireEvent.click(screen.getByRole("button", { name: "仅解析入库" }));
  await waitFor(() => expect(host.startBatch).toHaveBeenCalledWith(["item-1"], expect.any(String), false));
  expect(host.stageIngestion).toHaveBeenCalledWith(file, {});
});

it.each(["existing", "new", "unclassified"] as const)("uploads with a %s topic from the expandable picker", async mode => {
  const { host } = setup();
  await screen.findByRole("heading", { name: "A Paper" });
  fireEvent.click(screen.getByRole("button", { name: "上传" }));
  const topic = screen.getByRole("combobox", { name: "专题" });
  expect(topic).toHaveAttribute("aria-expanded", "false");
  fireEvent.click(screen.getByRole("button", { name: "展开已有专题" }));
  expect(screen.getByRole("listbox", { name: "已有专题" })).toBeVisible();
  fireEvent.click(screen.getByRole("option", { name: "编译" }));
  expect(topic).toHaveValue("编译");
  expect(topic).toHaveAttribute("aria-expanded", "false");
  if (mode === "new") {
    fireEvent.change(topic, { target: { value: "架构探索" } });
    fireEvent.keyDown(topic, { key: "Escape" });
  } else if (mode === "unclassified") {
    fireEvent.click(screen.getByRole("button", { name: "展开已有专题" }));
    fireEvent.keyDown(topic, { key: "ArrowDown" });
    fireEvent.keyDown(topic, { key: "Enter" });
    expect(topic).toHaveValue("");
  }
  const parseOnly = screen.getByRole("checkbox", { name: "仅解析入库" });
  fireEvent.click(parseOnly);
  expect(parseOnly).toBeChecked();
  fireEvent.click(parseOnly);
  expect(parseOnly).not.toBeChecked();
  const file = new File(["%PDF test"], "topic.pdf");
  fireEvent.change(screen.getByLabelText("上传材料"), { target: { files: [file] } });
  fireEvent.click(screen.getByRole("button", { name: "开始解析并生成博客" }));
  await waitFor(() => expect(host.startBatch).toHaveBeenCalledWith(["item-1"], expect.any(String), true));
  expect(host.stageIngestion).toHaveBeenCalledWith(file, mode === "unclassified" ? {} : { topicTitle: mode === "new" ? "架构探索" : "编译" });
});

it('clears terminal statuses while an active chat continues, and keeps source management available later', async () => {
  const failed: IngestionItem = { itemId: 'failed', fileName: 'failed.pdf', status: 'failed', topicId: null, topicTitle: null, sourceId: null, documentStatus: 'failed', topicStatus: 'not_started' };
  const initial: ReadingWindow = { ...empty, workItems: [
    { kind: 'chat', targetId: 'chat-active', status: 'running', label: '正在回答问题' },
    { kind: 'blog', targetId: 'a-paper', status: 'failed', label: '旧博客失败', error: 'old failure' },
  ], agent: { ...empty.agent!, run: { runId: 'chat-active', status: 'running', approvals: [], activity: [], error: null } } };
  const { host } = setup([failed], initial);
  vi.mocked(host.clearFinishedStatuses!).mockImplementation(async () => {
    vi.mocked(host.listInbox!).mockResolvedValue(readerSuccess([{ ...failed, dismissed: true }]));
    return readerSuccess({ ...initial, workItems: initial.workItems!.map(item => ({ ...item, dismissed: item.status === 'failed' })) });
  });
  await screen.findByRole('heading', { name: 'A Paper' });
  fireEvent.click(screen.getByRole('button', { name: '任务详情' }));
  expect(screen.getByText('failed.pdf')).toBeVisible();
  fireEvent.click(screen.getByRole('button', { name: '全部清空' }));
  await waitFor(() => expect(screen.queryByText('failed.pdf')).not.toBeInTheDocument());
  expect(screen.queryByText('old failure')).not.toBeInTheDocument();
  expect(screen.getByText('正在回答问题 · 进行中')).toBeVisible();
  expect(host.clearFinishedStatuses).toHaveBeenCalledWith(expect.any(String));
});

it("T2 appearance previews can be cancelled without touching saved settings", async () => {
  setup(); await screen.findByRole("heading", { name: "A Paper" });
  fireEvent.click(screen.getByRole("link", { name: "设置" }));
  fireEvent.change(screen.getByRole("slider", { name: "亮度" }), { target: { value: "90" } });
  fireEvent.change(screen.getByRole("slider", { name: "字号" }), { target: { value: "3" } });
  expect(localStorage.getItem("focus.fontSize")).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "取消修改" }));
  expect(screen.getByRole("slider", { name: "字号" })).toHaveValue("1");
  expect(screen.getByRole("slider", { name: "亮度" })).toHaveValue("100");
});

it("T17/T18 routes expose all work and Stop targets only the selected preparation", async () => {
  const { host } = setup([], { ...empty, workItems: [
    { kind: "preparation", targetId: "a-paper", status: "running", label: "准备 A" },
    { kind: "blog", targetId: "b-paper", status: "running", label: "生成 B" },
  ] });
  host.cancelPreparation = vi.fn(async () => readerSuccess(empty));
  host.stop = vi.fn(async () => readerSuccess(empty));
  await screen.findByRole("heading", { name: "A Paper" });
  fireEvent.click(screen.getByRole("link", { name: "设置" }));
  fireEvent.click(screen.getByRole("button", { name: "任务详情" }));
  const frame = screen.getByLabelText("任务框");
  expect(frame).toHaveTextContent("生成 B");
  fireEvent.click(within(frame).getByRole("button", { name: "取消准备" }));
  await waitFor(() => expect(host.cancelPreparation).toHaveBeenCalledWith("a-paper"));
  expect(host.stop).not.toHaveBeenCalled();
});

it("T22 source refresh does not await every blog status", async () => {
  const { host } = setup();
  host.blogStatus = vi.fn(() => new Promise<ReaderHostResult<BlogStatus>>(() => {}));
  await screen.findByRole("heading", { name: "A Paper" });
  expect(host.blogStatus).not.toHaveBeenCalled();
});

it("T20 retries the failed operation with the same request identity", async () => {
  const { host } = setup();
  vi.mocked(host.openSource!).mockResolvedValueOnce({ ok: false, error: { code: "unavailable", message: "结果未知", retryable: true } }).mockResolvedValue(readerSuccess(empty));
  await screen.findByRole("heading", { name: "A Paper" });
  fireEvent.click(screen.getByRole("button", { name: "继续阅读" }));
  await screen.findByRole("button", { name: "重试此操作" });
  const firstRequest = vi.mocked(host.openSource!).mock.calls[0][1];
  fireEvent.click(screen.getByRole("button", { name: "重试此操作" }));
  await waitFor(() => expect(host.openSource).toHaveBeenCalledTimes(2));
  expect(vi.mocked(host.openSource!).mock.calls[1][1]).toBe(firstRequest);
});

it("T19 disconnection is never presented as idle and keeps the last known task", async () => {
  let emit!: Parameters<NonNullable<ReaderHost["subscribe"]>>[0];
  const { host } = setup();
  host.subscribe = callback => { emit = callback; return () => {}; };
  cleanup(); render(<WorkspaceApp host={host} />);
  await screen.findByRole("heading", { name: "A Paper" });
  await act(async () => emit({ ok: false, error: { code: "unavailable", message: "offline", retryable: true } }));
  expect(screen.getByText("连接中断，正在恢复")).toBeInTheDocument();
  expect(screen.queryByText("当前无工作")).not.toBeInTheDocument();
});


it("keeps work and upload history hidden until the shared disclosure is opened, then hides both again", async () => {
  const item: IngestionItem = { itemId: "pending-1", fileName: "pending.pdf", status: "processing", topicTitle: null, topicId: null, sourceId: null, documentStatus: "not_started", topicStatus: "not_started" };
  const { host } = setup([item], { ...empty, workItems: [
    { kind: "ingestion", targetId: "pending-1", status: "running", label: "解析 pending.pdf" },
    { kind: "blog", targetId: "b-paper", status: "running", label: "生成 B" },
  ] });
  vi.mocked(host.listBatches!).mockResolvedValue(readerSuccess([{ batchId: "done", topicId: null, status: "completed", items: [], error: null }]));
  cleanup(); render(<WorkspaceApp host={host} />);
  await screen.findByRole("heading", { name: "A Paper" });
  const toggle = screen.getByRole("button", { name: "任务详情" });
  expect(toggle).toHaveAttribute("aria-expanded", "false");
  expect(toggle).toHaveTextContent("2 项进行中");
  expect(screen.queryByLabelText("任务框")).not.toBeInTheDocument();
  expect(screen.queryByText("pending.pdf")).not.toBeInTheDocument();
  fireEvent.click(toggle);
  expect(screen.getByLabelText("任务框")).toHaveTextContent("生成 B");
  expect(screen.getByText("pending.pdf")).toBeVisible();
  expect(screen.queryByText("解析 pending.pdf · 进行中")).not.toBeInTheDocument();
  expect(screen.getByText("已完成任务").closest("details")).not.toHaveAttribute("open");
  expect(screen.getByText("未关联专题 · 完成")).toBeInTheDocument();
  fireEvent.click(toggle);
  expect(screen.queryByLabelText("任务框")).not.toBeInTheDocument();
});

it("uses a modal blog viewer and restores the workspace on Escape", async () => {
  const { host } = setup();
  host.blogStatus = vi.fn(async () => readerSuccess(blogStatus()));
  await screen.findByRole("heading", { name: "A Paper" });
  fireEvent.click(screen.getByRole("button", { name: "详细" }));
  await waitFor(() => expect(screen.getByRole("button", { name: "打开博客" })).toBeEnabled());
  const modal = vi.spyOn(HTMLDialogElement.prototype, "showModal");
  fireEvent.click(screen.getByRole("button", { name: "打开博客" }));
  const dialog = screen.getByTitle("博客").closest("dialog")!;
  expect(modal).toHaveBeenCalled();
  fireEvent(dialog, new Event("cancel", { bubbles: false }));
  expect(screen.queryByTitle("博客")).not.toBeInTheDocument();
  modal.mockRestore();
});

function failedPreparationWindow(dismissed = false, attempt = "attempt-1"): ReadingWindow {
  return { ...empty, preparations: { "a-paper": {
    source_id: "a-paper", status: "failed", step: "translate", completed: 1, total: 4,
    ready: false, selected_ready: false, plan_id: "plan-001", error: "Runtime timed out",
    attempt, timed_out: true, dismissed,
  } }, workItems: dismissed ? [] : [{ kind: "preparation", targetId: "a-paper", status: "failed", label: "准备阅读 · A Paper", error: "Runtime timed out" }] };
}

it("removes a timed-out preparation immediately, without confirmation, retry or cancellation", async () => {
  const { host } = setup([], failedPreparationWindow());
  let resolve!: (result: ReturnType<typeof readerSuccess<ReadingWindow>>) => void;
  host.dismissPreparation = vi.fn(() => new Promise<ReaderHostResult<ReadingWindow>>(done => { resolve = done; }));
  host.cancelPreparation = vi.fn(async () => readerSuccess(empty));
  host.resumePreparation = vi.fn(async () => readerSuccess(empty));
  const confirm = vi.spyOn(window, "confirm");
  cleanup(); render(<WorkspaceApp host={host} />);
  await screen.findByRole("heading", { name: "A Paper" });
  fireEvent.click(screen.getByRole("button", { name: "任务详情" }));
  expect(screen.getByText("准备超时", { exact: true })).toBeVisible();
  expect(screen.getByRole("button", { name: "重试" })).toBeEnabled();
  expect(screen.queryByText(/待处理/)).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "关闭准备阅读提示" }));
  expect(screen.queryByText("准备超时", { exact: true })).not.toBeInTheDocument();
  expect(screen.queryByLabelText("准备阅读状态")).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "准备阅读" })).toBeEnabled();
  expect(host.dismissPreparation).toHaveBeenCalledWith("a-paper", "attempt-1");
  expect(host.cancelPreparation).not.toHaveBeenCalled();
  expect(host.resumePreparation).not.toHaveBeenCalled();
  expect(confirm).not.toHaveBeenCalled();
  await act(async () => resolve(readerSuccess(failedPreparationWindow(true))));
  expect(screen.queryByText("准备超时", { exact: true })).not.toBeInTheDocument();
  confirm.mockRestore();
});

it("keeps dismissed preparation hidden after reload and exposes the next explicit attempt", async () => {
  const { host } = setup([], failedPreparationWindow(true));
  host.dismissPreparation = vi.fn(async () => readerSuccess(empty));
  host.resumePreparation = vi.fn(async () => readerSuccess(failedPreparationWindow(false, "attempt-2")));
  cleanup(); render(<WorkspaceApp host={host} />);
  await screen.findByRole("heading", { name: "A Paper" });
  fireEvent.click(screen.getByRole("button", { name: "任务详情" }));
  fireEvent.click(screen.getByRole("button", { name: "详细" }));
  expect(screen.queryByLabelText("准备阅读状态")).not.toBeInTheDocument();
  expect(host.resumePreparation).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "准备阅读" }));
  await waitFor(() => expect(host.resumePreparation).toHaveBeenCalledWith("a-paper", expect.any(String)));
  expect(screen.getAllByLabelText("准备阅读状态")).toHaveLength(2);
  expect(screen.getAllByText("准备超时", { exact: true })).toHaveLength(2);
});

it("restores a preparation card and reports persistence failure if dismiss could not be saved", async () => {
  const { host } = setup([], failedPreparationWindow());
  host.dismissPreparation = vi.fn(async (): Promise<ReaderHostResult<ReadingWindow>> => ({ ok: false as const, error: { code: "unavailable", message: "关闭提示未保存", retryable: true } }));
  cleanup(); render(<WorkspaceApp host={host} />);
  await screen.findByRole("heading", { name: "A Paper" });
  fireEvent.click(screen.getByRole("button", { name: "任务详情" }));
  fireEvent.click(screen.getByRole("button", { name: "关闭准备阅读提示" }));
  expect(await screen.findByText("关闭提示未保存", { selector: ".workspace-error" })).toBeVisible();
  expect(screen.getByText("准备超时", { exact: true })).toBeVisible();
});
