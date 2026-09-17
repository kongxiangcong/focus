import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { readerSuccess, type ReaderHost, type ReadingWindow } from "@focus/reader-contracts";
import { FocusReader } from "./FocusReader";

afterEach(cleanup);
beforeEach(() => {
  HTMLElement.prototype.scrollIntoView = vi.fn();
  HTMLElement.prototype.scrollTo = vi.fn();
  HTMLDialogElement.prototype.showModal = function () { this.setAttribute("open", ""); };
  HTMLDialogElement.prototype.close = function () { this.removeAttribute("open"); };
});
const current = { sourceId: "demo-paper", planId: "plan-001", chunkId: "chunk-001", index: 1, total: 2,
  sectionPath: ["Method"], sourceLines: [1, 4] as const, sourceMarkdown: "![Figure](images/image-001.png)\n\nOriginal paragraph.",
  translation: null, images: [], relevantGlossary: [], presentationStatus: "source-ready" as const };
const first: ReadingWindow = { status: "reading", sessionId: "s1", source: { sourceId: "demo-paper", title: "Demo", topicId: null }, current, history: [], conversation: [] };
function setup() {
  const next = { ...current, chunkId: "chunk-002", index: 2, sectionPath: ["Results"] };
  const second: ReadingWindow = { ...first, current: next, history: [current] };
  const host: ReaderHost = {
    getReadingWindow: vi.fn(async () => readerSuccess(first)),
    continueReading: vi.fn(async () => readerSuccess(second)),
    sendMessage: vi.fn(async () => readerSuccess(second)),
  };
  render(<FocusReader host={host} appearance="mist" />);
  return host;
}
it("disables unread navigation, advances once, and reviews history without moving the Cursor", async () => {
  const host = setup();
  const nav = await screen.findByRole("navigation", { name: "段落目录" });
  await waitFor(() => expect(within(nav).getByRole("button", { name: /02/ })).toBeDisabled());
  fireEvent.click(screen.getByRole("button", { name: "下一段 →" }));
  await screen.findByRole("heading", { name: "Results" });
  expect(host.continueReading).toHaveBeenCalledTimes(1);
  fireEvent.click(within(nav).getByRole("button", { name: /01.*Method/ }));
  expect(host.continueReading).toHaveBeenCalledTimes(1);
  fireEvent.change(screen.getByRole("textbox"), { target: { value: "这段是什么意思？" } });
  fireEvent.click(screen.getByRole("button", { name: "发送 ↑" }));
  await waitFor(() => expect(host.sendMessage).toHaveBeenCalledWith(expect.objectContaining({ receipt: expect.objectContaining({ chunkId: "chunk-001" }) })));
  expect(host.continueReading).toHaveBeenCalledTimes(1);
});
it("renders bundle images and preserves the draft when collapsing the composer", async () => {
  setup();
  const image = await screen.findByRole("img", { name: "Figure" });
  expect(image).toHaveAttribute("src", "/reader/assets/demo-paper/images/image-001.png");
  fireEvent.change(screen.getByRole("textbox"), { target: { value: "草稿" } });
  fireEvent.click(screen.getByRole("button", { name: "对话 · 收起 −" }));
  expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "提问 / 展开对话 ＋" }));
  expect(screen.getByRole("textbox")).toHaveValue("草稿");
});
