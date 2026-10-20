// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { readerSuccess, type LibrarySource, type ReaderHost, type ReadingWindow } from "@focus/reader-contracts";
import { WorkspaceApp } from "../WorkspaceApp";
import { UNFILED } from "./topic-view";

const empty: ReadingWindow = { status: "empty", current: null, history: [], conversation: [], source: { sourceId: "", title: "", topicId: null }, sessionId: "s" };
const sources: LibrarySource[] = ["A", "B", "C"].map((title, index) => ({ sourceId: `${title}-paper`, title, kind: "paper", parseStatus: "ready", error: null, noteCount: 0, topicIds: index === 2 ? [] : ["topic"], progress: { completed: index === 0 ? 4 : 1, total: 4, planId: "plan", chunkId: index === 0 ? null : "chunk-2" } }));
function setup() {
  let order: readonly string[] = ["A-paper", "B-paper"];
  const host: ReaderHost = {
    getReadingWindow: vi.fn(async () => readerSuccess(empty)), continueReading: vi.fn(async () => readerSuccess(empty)), sendMessage: vi.fn(async () => readerSuccess(empty)),
    listSources: vi.fn(async () => readerSuccess(sources)), listTopics: vi.fn(async () => readerSuccess([{ topicId: "topic", title: "编译", sourceIds: order }])),
    saveSourceDetails: vi.fn(async () => readerSuccess(empty)),
    manageTopic: vi.fn(async (_id, _action, payload) => { order = payload.sourceIds!; return readerSuccess({}); }),
  };
  render(<WorkspaceApp host={host} />); return host;
}
async function selectTopic() { await screen.findByRole("button", { name: "A" }); fireEvent.change(screen.getByRole("combobox", { name: "筛选专题" }), { target: { value: "topic" } }); }
function row(id: string) { return screen.getByRole("button", { name: id }).closest("article")!; }
function order() { return within(screen.getByRole("list", { name: "来源" })).getAllByRole("listitem").map(el => el.getAttribute("data-source-id")); }
function dragStart(id: string) { const dataTransfer = { types: ["text/plain"], setData: vi.fn(), effectAllowed: "", dropEffect: "", files: [] }; fireEvent.dragStart(row(id).querySelector("[draggable]")!, { dataTransfer }); return dataTransfer; }
beforeEach(() => { history.replaceState(null, "", "/library"); localStorage.clear(); HTMLDialogElement.prototype.showModal = function () { this.setAttribute("open", ""); }; HTMLDialogElement.prototype.close = function () { this.removeAttribute("open"); }; });
afterEach(cleanup);

it("counts completed phases, shows Unfiled and shares the Topic selection", async () => {
  const host = setup(); await selectTopic();
  const nav = screen.getByRole("group", { name: "专题" });
  expect(within(nav).getByRole("button", { name: "编译1/2" })).toHaveAttribute("title", "已读完 1 / 2 篇");
  expect(screen.getByRole("region", { name: "专题概览" })).toHaveTextContent("已读完 1 / 2 篇 · 1 篇阅读中");
  fireEvent.click(within(nav).getByRole("button", { name: "未归类1" }));
  expect(screen.getByRole("combobox", { name: "筛选专题" })).toHaveValue(UNFILED);
  expect(order()).toEqual(["C-paper"]); expect(screen.queryByRole("region", { name: "专题概览" })).not.toBeInTheDocument(); expect(host.manageTopic).not.toHaveBeenCalled();
});
it("previews locally and submits exactly one reorder only on drop", async () => {
  const host = setup(); await selectTopic(); const transfer = dragStart("A");
  fireEvent.dragOver(row("B"), { dataTransfer: transfer }); fireEvent.dragOver(row("B"), { dataTransfer: transfer }); expect(order()).toEqual(["B-paper", "A-paper"]); expect(host.manageTopic).not.toHaveBeenCalled();
  fireEvent.drop(row("B"), { dataTransfer: transfer }); fireEvent.dragEnd(row("A").querySelector("[draggable]")!, { dataTransfer: transfer });
  await waitFor(() => expect(host.manageTopic).toHaveBeenCalledTimes(1));
  expect(host.manageTopic).toHaveBeenCalledWith("topic", "reorder", { sourceIds: ["B-paper", "A-paper"] });
  await waitFor(() => expect(screen.queryByText("更新知识库中…")).not.toBeInTheDocument()); expect(order()).toEqual(["B-paper", "A-paper"]);
  expect(screen.queryByRole("dialog", { name: /上传/ })).not.toBeInTheDocument();
});
it("rolls failed previews back and retains the existing retry", async () => {
  const host = setup(); await selectTopic(); vi.mocked(host.manageTopic!).mockResolvedValueOnce({ ok: false, error: { code: "unknown", message: "排序失败", retryable: true } });
  const transfer = dragStart("A"); fireEvent.dragOver(row("B"), { dataTransfer: transfer }); fireEvent.drop(row("B"), { dataTransfer: transfer });
  await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("排序失败")); await waitFor(() => expect(order()).toEqual(["A-paper", "B-paper"]));
  fireEvent.click(screen.getByRole("button", { name: "重试此操作" })); await waitFor(() => expect(host.manageTopic).toHaveBeenCalledTimes(2));
  await waitFor(() => expect(order()).toEqual(["B-paper", "A-paper"]));
});
it("cancels a drag without committing and preserves manifest ordinals under search", async () => {
  const host = setup(); await selectTopic(); const transfer = dragStart("A"); fireEvent.dragOver(row("B"), { dataTransfer: transfer }); fireEvent.dragEnd(row("A").querySelector("[draggable]")!, { dataTransfer: transfer });
  expect(order()).toEqual(["A-paper", "B-paper"]); expect(host.manageTopic).not.toHaveBeenCalled();
  fireEvent.change(screen.getByRole("searchbox", { name: "搜索材料" }), { target: { value: "B" } }); expect(within(row("B")).getByLabelText("专题顺序 2")).toHaveTextContent("2");
});
it("uses Alt arrows to reorder while keeping focus on the original title", async () => {
  const host = setup(); await selectTopic(); const title = screen.getByRole("button", { name: "A" }); title.focus(); fireEvent.keyDown(title, { altKey: true, key: "ArrowDown" });
  await waitFor(() => expect(order()).toEqual(["B-paper", "A-paper"])); expect(title).toHaveFocus(); expect(host.manageTopic).toHaveBeenCalledTimes(1);
  fireEvent.keyDown(title, { altKey: true, key: "ArrowUp" }); await waitFor(() => expect(order()).toEqual(["A-paper", "B-paper"])); expect(title).toHaveFocus();
});
it.each(["search", "cards"])("disables drag, Alt arrows and menu sorting for %s", async mode => {
  const host = setup(); await selectTopic();
  if (mode === "search") fireEvent.change(screen.getByRole("searchbox", { name: "搜索材料" }), { target: { value: "A" } }); else fireEvent.click(screen.getByRole("button", { name: "卡片显示" }));
  const title = screen.getByRole("button", { name: "A" }); fireEvent.keyDown(title, { altKey: true, key: "ArrowDown" });
  fireEvent.click(within(row("A")).getByRole("button", { name: "更多" })); expect(screen.getByRole("button", { name: "A 下移" })).toBeDisabled(); expect(host.manageTopic).not.toHaveBeenCalled();
  expect(screen.getByRole("region", { name: "专题概览" })).toHaveTextContent(mode === "search" ? "搜索时暂停排序" : "切换到列表视图后可调整专题顺序");
  if (mode === "search") expect(row("A").querySelector("[draggable]")).toHaveAttribute("draggable", "false");
});
it("blocks a second reorder while the first operation is busy", async () => {
  const host = setup(); await selectTopic(); let resolve!: () => void;
  vi.mocked(host.manageTopic!).mockImplementationOnce(() => new Promise(done => { resolve = () => done(readerSuccess({})); }));
  fireEvent.keyDown(screen.getByRole("button", { name: "A" }), { altKey: true, key: "ArrowDown" });
  expect(screen.getByRole("region", { name: "专题概览" })).toHaveTextContent("当前任务正在使用材料");
  fireEvent.keyDown(screen.getByRole("button", { name: "B" }), { altKey: true, key: "ArrowUp" }); expect(host.manageTopic).toHaveBeenCalledTimes(1);
  expect(row("A").querySelector("[draggable]")).toHaveAttribute("draggable", "false"); await act(async () => resolve());
});

it("retains a selected Unfiled option when its final source is categorized", async () => {
  const host = setup(); await selectTopic();
  fireEvent.change(screen.getByRole("combobox", { name: "筛选专题" }), { target: { value: UNFILED } });
  fireEvent.click(within(row("C")).getByRole("button", { name: "更多" })); fireEvent.click(screen.getByRole("button", { name: "管理来源" }));
  fireEvent.click(screen.getByRole("checkbox", { name: "编译" }));
  vi.mocked(host.listSources!).mockResolvedValue(readerSuccess(sources.map(s => ({ ...s, topicIds: ["topic"] }))));
  fireEvent.click(screen.getByRole("button", { name: "保存" }));
  await waitFor(() => expect(screen.queryByRole("button", { name: "C" })).not.toBeInTheDocument());
  expect(screen.getByRole("combobox", { name: "筛选专题" })).toHaveValue(UNFILED);
  expect(within(screen.getByRole("group", { name: "专题" })).queryByRole("button", { name: /未归类/ })).not.toBeInTheDocument();
});
