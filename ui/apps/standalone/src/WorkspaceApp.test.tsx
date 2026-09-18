// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { readerSuccess, type ReaderHost, type ReadingWindow } from "@focus/reader-contracts";
import { WorkspaceApp } from "./WorkspaceApp";
const empty: ReadingWindow = { status: "empty", current: null, history: [], conversation: [], source: { sourceId: "", title: "", topicId: null }, sessionId: "s1",
  agent: { run: null, catalog: { sources: [], topics: [] }, backend: "codex", backends: [{ id: "codex", label: "Codex" }, { id: "workbuddy", label: "WorkBuddy", unavailableReason: "待接入" }] } };
function setup() {
  const host: ReaderHost = {
    getReadingWindow: vi.fn(async () => readerSuccess(empty)), continueReading: vi.fn(async () => readerSuccess(empty)), sendMessage: vi.fn(async () => readerSuccess(empty)),
    listTopics: vi.fn(async () => readerSuccess([{ topicId: "topic", title: "编译", sourceIds: ["a-paper"] }])),
    listSources: vi.fn(async () => readerSuccess([{ sourceId: "a-paper", title: "A Paper", kind: "paper" as const, parseStatus: "ready" as const, error: null, noteCount: 2, topicIds: ["topic"], progress: { completed: 1, total: 4, planId: "plan-001", chunkId: "chunk-002" } }])),
    openSource: vi.fn(async () => readerSuccess(empty)), deleteSource: vi.fn(async () => readerSuccess(empty)), rereadSource: vi.fn(async () => readerSuccess(empty)), uploadSource: vi.fn(async () => readerSuccess(empty)),
  };
  return { host, ...render(<WorkspaceApp host={host} />) };
}
beforeEach(() => {
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
it("uploads a PDF automatically and dispatches explicit destructive operations only after confirmation", async () => {
  const { host } = setup(); await screen.findByRole("button", { name: "A Paper" });
  const pdf = new File(["%PDF test"], "test.pdf", { type: "application/pdf" });
  fireEvent.click(screen.getByRole("button", { name: "上传" }));
  fireEvent.change(screen.getByRole("combobox", { name: "专题" }), { target: { value: "编译" } });
  fireEvent.change(screen.getByLabelText("上传材料"), { target: { files: [pdf] } });
  expect(host.uploadSource).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "确认上传" }));
  await waitFor(() => expect(host.uploadSource).toHaveBeenCalledWith(pdf, { topic: "编译", uploader: "孔祥聪" }));
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
it("filters source cards and supports HTML drop while rejecting unsupported files", async () => {
  const { host } = setup(); await screen.findByRole("button", { name: "A Paper" });
  expect(screen.getByText("PDF").closest("article")).toBeInTheDocument();
  expect(screen.getByRole("progressbar", { name: "A Paper 阅读进度" })).toHaveAttribute("value", "1");
  fireEvent.change(screen.getByRole("searchbox"), { target: { value: "missing" } });
  expect(screen.getByText("暂无匹配材料")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "重置" }));
  const page = screen.getByRole("main");
  const html = new File(["<p>Article</p>"], "article.html", { type: "text/html" });
  fireEvent.drop(page, { dataTransfer: { files: [html] } });
  expect(host.uploadSource).not.toHaveBeenCalled();
  fireEvent.change(screen.getByRole("combobox", { name: "专题" }), { target: { value: "新专题" } });
  fireEvent.click(screen.getByRole("button", { name: "确认上传" }));
  await waitFor(() => expect(host.uploadSource).toHaveBeenCalledWith(html, { topic: "新专题", uploader: "孔祥聪" }));
  await waitFor(() => expect(screen.getByRole("button", { name: "上传" })).toBeEnabled());
  fireEvent.drop(page, { dataTransfer: { files: [new File(["text"], "file.txt")] } });
  expect(host.uploadSource).toHaveBeenCalledTimes(1);
  expect(screen.getByRole("alert")).toHaveTextContent("请选择 PDF、HTML 或 Markdown");
});
it("persists brightness and leaves unsupported network control disabled", async () => {
  setup(); await screen.findByRole("button", { name: "A Paper" });
  fireEvent.click(screen.getByRole("link", { name: "设置" }));
  fireEvent.change(screen.getByRole("slider", { name: "亮度" }), { target: { value: "90" } });
  expect(localStorage.getItem("focus.brightness")).toBe("90");
  expect(screen.getByRole("switch", { name: "网络" })).toBeDisabled();
});
