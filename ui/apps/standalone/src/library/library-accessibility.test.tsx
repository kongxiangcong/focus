// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { readerSuccess, type LibrarySource, type ReaderHost, type ReadingWindow } from "@focus/reader-contracts";
import { WorkspaceApp } from "../WorkspaceApp";

const source: LibrarySource = { sourceId: "a", title: "Alpha", kind: "paper", parseStatus: "ready", error: null, noteCount: 0, topicIds: [], progress: { completed: 1, total: 4, planId: "p", chunkId: "c" } };
const empty: ReadingWindow = { status: "empty", source: { sourceId: "", title: "", topicId: null }, current: null, history: [], conversation: [] };
function setup(mobile = false) {
  vi.stubGlobal("matchMedia", vi.fn((query: string) => ({ matches: mobile && query.includes("760px"), addEventListener: vi.fn(), removeEventListener: vi.fn() })));
  const host: ReaderHost = { getReadingWindow: vi.fn(async () => readerSuccess(empty)), continueReading: vi.fn(async () => readerSuccess(empty)), sendMessage: vi.fn(async () => readerSuccess(empty)), listSources: vi.fn(async () => readerSuccess([source])), listTopics: vi.fn(async () => readerSuccess([])), openSource: vi.fn(async () => readerSuccess(empty)), saveSourceDetails: vi.fn(async () => readerSuccess(empty)) };
  render(<WorkspaceApp host={host} />); return host;
}
beforeEach(() => { history.replaceState(null, "", "/library"); localStorage.clear(); HTMLDialogElement.prototype.showModal = function () { this.setAttribute("open", ""); }; HTMLDialogElement.prototype.close = function () { this.removeAttribute("open"); }; });
afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });

it("keeps panel and menu DOM during rapid close/reopen while immediately removing their accessible controls", async () => {
  setup(); const title = await screen.findByRole("button", { name: "Alpha" }); fireEvent.click(title);
  const panel = screen.getByRole("complementary", { name: "来源详情" });
  fireEvent.click(within(panel).getByRole("button", { name: "关闭详情" }));
  expect(panel).toHaveAttribute("inert"); expect(panel).toHaveAttribute("aria-hidden", "true"); expect(screen.queryByRole("complementary", { name: "来源详情" })).not.toBeInTheDocument(); expect(title).toHaveFocus();
  fireEvent.click(title); expect(screen.getByRole("complementary", { name: "来源详情" })).toBe(panel); expect(panel).not.toHaveAttribute("inert");
  const more = screen.getByRole("button", { name: "更多" }); fireEvent.click(more); const menu = screen.getByRole("group", { name: "更多操作" });
  fireEvent.keyDown(menu, { key: "Escape" }); expect(menu).toHaveAttribute("inert"); expect(screen.queryByRole("group", { name: "更多操作" })).not.toBeInTheDocument(); expect(more).toHaveFocus();
  fireEvent.click(more); expect(screen.getByRole("group", { name: "更多操作" })).toBe(menu);
});
it("traps the mobile sheet, makes background inert, permits native dialogs and restores the title on close", async () => {
  setup(true); const title = await screen.findByRole("button", { name: "Alpha" }); fireEvent.click(title);
  const panel = screen.getByRole("dialog", { name: "来源详情" }); expect(panel).toHaveAttribute("aria-modal", "true"); expect(panel).toHaveFocus();
  for (const selector of [".workspace-nav", ".workspace-header", ".library-sources"]) expect(document.querySelector(selector)).toHaveAttribute("inert");
  const controls = within(panel).getAllByRole("button").filter(button => !(button as HTMLButtonElement).disabled), first = controls[0], last = controls.at(-1)!;
  fireEvent.keyDown(panel, { key: "Tab" }); expect(first).toHaveFocus(); first.focus(); fireEvent.keyDown(first, { key: "Tab", shiftKey: true }); expect(last).toHaveFocus(); fireEvent.keyDown(last, { key: "Tab" }); expect(first).toHaveFocus();
  const dialog = document.createElement("dialog"), button = document.createElement("button"); dialog.setAttribute("open", ""); dialog.append(button); document.body.append(dialog); button.focus(); expect(button).toHaveFocus(); dialog.remove();
  const originalFocus = title.focus.bind(title); vi.spyOn(title, "focus").mockImplementation(() => { expect(title.closest("[inert]")).toBeNull(); expect(document.querySelector(".workspace-header")).not.toHaveAttribute("inert"); originalFocus(); });
  fireEvent.keyDown(panel, { key: "Escape" }); expect(title).toHaveFocus(); expect(panel).toHaveAttribute("inert");
  for (const selector of [".workspace-nav", ".workspace-header", ".library-sources"]) expect(document.querySelector(selector)).not.toHaveAttribute("inert");
  fireEvent.click(title); expect(screen.getByRole("dialog", { name: "来源详情" })).toBe(panel);
});
it("retains the task frame across Escape and reopen and restores the disclosure focus", async () => {
  setup(); await screen.findByRole("button", { name: "Alpha" }); const toggle = screen.getByRole("button", { name: "任务详情" }); fireEvent.click(toggle);
  const frame = screen.getByRole("region", { name: "任务框" }); fireEvent.keyDown(frame, { key: "Escape" }); expect(frame).toHaveAttribute("inert"); expect(frame).toHaveAttribute("aria-hidden", "true"); expect(toggle).toHaveFocus(); expect(screen.queryByRole("region", { name: "任务框" })).not.toBeInTheDocument();
  fireEvent.click(toggle); expect(screen.getByRole("region", { name: "任务框" })).toBe(frame);
});
it("keeps IME composition local until compositionend in the shared header", async () => {
  setup(); await screen.findByRole("button", { name: "Alpha" }); const search = screen.getByRole("searchbox"); expect(search.closest(".workspace-header")).toBeInTheDocument();
  fireEvent.compositionStart(search); fireEvent.change(search, { target: { value: "中文" } }); expect(search).toHaveValue("中文"); expect(screen.getByRole("button", { name: "Alpha" })).toBeInTheDocument();
  fireEvent.compositionEnd(search); expect(screen.queryByRole("button", { name: "Alpha" })).not.toBeInTheDocument(); expect(screen.getByText("没有标题匹配这次搜索。")).toBeInTheDocument();
  await act(async () => fireEvent.click(screen.getByRole("button", { name: "清除搜索" }))); expect(search).toHaveValue(""); expect(screen.getByRole("button", { name: "Alpha" })).toBeInTheDocument();
});
it("preserves progress semantics while exposing a transform-only visual fill", async () => {
  setup(); const progress = await screen.findByRole("progressbar", { name: "Alpha 阅读进度" }); expect(progress).toHaveAttribute("aria-valuenow", "1"); expect(progress).toHaveAttribute("aria-valuemax", "4"); expect(progress.firstElementChild).toHaveStyle({ transform: "scaleX(0.25)" });
});

it.each(["searchbox", "combobox"] as const)("closes the menu before the inspector from the shared header %s", async role => {
  setup(); const title = await screen.findByRole("button", { name: "Alpha" }); fireEvent.click(title);
  const control = screen.getByRole(role), more = screen.getByRole("button", { name: "更多" }), panel = screen.getByRole("complementary", { name: "来源详情" });
  fireEvent.click(more); control.focus(); fireEvent.keyDown(control, { key: "Escape" });
  expect(screen.queryByRole("group", { name: "更多操作" })).not.toBeInTheDocument(); expect(more).toHaveFocus(); expect(panel).toHaveAttribute("data-open", "true");
  control.focus(); fireEvent.keyDown(control, { key: "Escape" }); expect(panel).toHaveAttribute("inert"); expect(title).toHaveFocus();
});
it("does not handle header Escape during IME composition or while a native dialog is open", async () => {
  setup(); const title = await screen.findByRole("button", { name: "Alpha" }); fireEvent.click(title);
  const search = screen.getByRole("searchbox"), more = screen.getByRole("button", { name: "更多" }), panel = screen.getByRole("complementary", { name: "来源详情" }); fireEvent.click(more);
  for (const properties of [{ isComposing: true }, { keyCode: 229 }]) { search.focus(); fireEvent.keyDown(search, { key: "Escape", ...properties }); expect(more).toHaveAttribute("aria-expanded", "true"); expect(panel).toHaveAttribute("data-open", "true"); expect(search).toHaveFocus(); }
  const dialog = document.createElement("dialog"); dialog.setAttribute("open", ""); document.body.append(dialog);
  fireEvent.keyDown(search, { key: "Escape" }); expect(more).toHaveAttribute("aria-expanded", "true"); expect(panel).toHaveAttribute("data-open", "true"); dialog.remove();
  fireEvent.keyDown(search, { key: "Escape" }); expect(more).toHaveAttribute("aria-expanded", "false"); expect(panel).toHaveAttribute("data-open", "true");
});
