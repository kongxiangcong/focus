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
  const app = setup(); await screen.findByText("A Paper");
  expect(location.pathname).toBe("/library");
  fireEvent.click(screen.getByRole("link", { name: "设置" }));
  fireEvent.click(screen.getByRole("button", { name: "特大" }));
  expect(screen.getByRole("radio", { name: /WorkBuddy/ })).toBeDisabled();
  app.unmount(); setup();
  expect(await screen.findByRole("button", { name: "特大" })).toHaveAttribute("aria-pressed", "true");
  fireEvent.click(screen.getByRole("link", { name: "阅读" }));
  expect(screen.getByRole("complementary", { name: "阅读进度与操作" })).toBeVisible();
});
it("uploads a PDF automatically and dispatches explicit destructive operations only after confirmation", async () => {
  const { host } = setup(); await screen.findByText("A Paper");
  const pdf = new File(["%PDF test"], "test.pdf", { type: "application/pdf" });
  fireEvent.change(screen.getByLabelText("上传论文 PDF"), { target: { files: [pdf] } });
  await waitFor(() => expect(host.uploadSource).toHaveBeenCalledWith(pdf));
  await waitFor(() => expect(screen.getByRole("button", { name: "删除" })).toBeEnabled());
  fireEvent.click(screen.getByRole("button", { name: "删除" }));
  expect(host.deleteSource).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "永久删除" }));
  await waitFor(() => expect(host.deleteSource).toHaveBeenCalledWith("a-paper"));
  await waitFor(() => expect(screen.getByRole("button", { name: "重读" })).toBeEnabled());
  fireEvent.click(screen.getByRole("button", { name: "重读" }));
  fireEvent.click(screen.getByRole("button", { name: "清除并重读" }));
  await waitFor(() => expect(host.rereadSource).toHaveBeenCalledWith("a-paper"));
  await waitFor(() => expect(location.pathname).toBe("/reading"));
});
