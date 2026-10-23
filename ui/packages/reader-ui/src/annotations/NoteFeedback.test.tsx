import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { readerSuccess, type ReaderChunk, type ReaderHost, type ReadingWindow, type SourceNote } from "@focus/reader-contracts";
import { FocusReader } from "../FocusReader";
const chunk: ReaderChunk = { sourceId: "demo-paper", planId: "p1", chunkId: "c1", index: 1, total: 1, sectionPath: ["Method"],
  sourceLines: [1, 4], sourceMarkdown: "Reading content.", translation: null, images: [], relevantGlossary: [], bundleVersion: "v1", presentationStatus: "source-ready" };
const initial: ReadingWindow = { status: "reading", sessionId: "s1", source: { sourceId: "demo-paper", title: "Demo", topicId: null }, current: chunk, history: [], conversation: [], sourceNotes: [] };
beforeEach(() => {
  localStorage.clear(); sessionStorage.clear(); HTMLElement.prototype.scrollTo = vi.fn(); HTMLElement.prototype.scrollIntoView = vi.fn();
  HTMLDialogElement.prototype.showModal = function () { this.setAttribute("open", ""); }; HTMLDialogElement.prototype.close = function () { this.removeAttribute("open"); };
});
afterEach(cleanup);
async function saveFromDiscussion(placed: boolean, detached = false) {
  const note: SourceNote = { noteId: "n1", sourceId: "demo-paper", revision: 1, content: "讨论中的结论", kind: "thought", origin: "dialogue", evidenceRole: "explanation",
    bundle: "v1", anchor: null, placement: placed ? { sourceId: "demo-paper", bundle: "v1", sourceLines: [1, 4] } : null,
    referenceStatus: "current", sourceUpdated: false, deleted: false, canUndo: true };
  const saved: ReadingWindow = { ...initial, sourceNotes: [note], noteFeedback: { sourceId: "demo-paper", status: "saved" } };
  const host: ReaderHost = { getReadingWindow: vi.fn(async () => readerSuccess(initial)), continueReading: vi.fn(), sendMessage: vi.fn(async () => readerSuccess(saved)) };
  if (detached) localStorage.setItem("focus.attachNotes", "false");
  render(<FocusReader host={host} appearance="mist" />); await screen.findByText("Reading content.");
  fireEvent.change(screen.getByRole("textbox", { name: "输入问题或阅读需求" }), { target: { value: "记一下" } });
  fireEvent.click(screen.getByRole("button", { name: "发送" }));
}
it("announces the projected paragraph after discussion save and jumps only on View", async () => {
  await saveFromDiscussion(true);
  await screen.findByText("已存为第 1 段的小段笔记");
  expect(screen.queryByRole("button", { name: /返回刚才位置/ })).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "查看" }));
  expect(await screen.findByRole("button", { name: /返回刚才位置/ })).toBeInTheDocument();
});
it("announces a whole-source note when no paragraph can own it", async () => {
  await saveFromDiscussion(false); await screen.findByText("已存为整篇笔记，可在资料栏查看");
  expect(screen.queryByRole("button", { name: "查看" })).not.toBeInTheDocument();
});
it("automatically expands the saved paragraph note while attachment is off", async () => {
  await saveFromDiscussion(true, true);
  const toggle = await screen.findByRole("button", { name: /小段笔记 · 1/ });
  expect(toggle).toHaveAttribute("aria-expanded", "true");
  const target = document.querySelector<HTMLElement>(".focus-stream [data-chunk-note-id='n1']");
  expect(target).toBeVisible();
  fireEvent.click(toggle); expect(toggle).toHaveAttribute("aria-expanded", "false");
});
it("saves an unreferenced answer as a whole-source note even when a reading chunk is current", async () => {
  const window: ReadingWindow = { ...initial, conversation: [{ messageId: "answer", sourceId: "demo-paper", chunkId: "", role: "assistant", content: "这是整篇讨论的回答" }] };
  const host: ReaderHost = { getReadingWindow: vi.fn(async () => readerSuccess(window)), continueReading: vi.fn(), sendMessage: vi.fn(async () => readerSuccess(window)) };
  render(<FocusReader host={host} appearance="mist" />);
  fireEvent.click(await screen.findByRole("button", { name: "存为笔记" }));
  await waitFor(() => expect(host.sendMessage).toHaveBeenCalledWith(expect.objectContaining({ receipt: null, sourceId: "demo-paper" })));
});
