import "@testing-library/jest-dom/vitest";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { readerFailure, readerSuccess, type ReaderChunk, type ReaderHost, type ReadingWindow, type SourceNote } from "@focus/reader-contracts";
import { ChunkNoteList } from "./ChunkNoteList";

beforeEach(() => sessionStorage.clear()); afterEach(cleanup);
const chunk: ReaderChunk = { sourceId: "source", planId: "plan-001", chunkId: "chunk-001", index: 2, total: 2,
  bundleVersion: "bundle", sourceLines: [5, 10], sourceMarkdown: "Source passage", translation: null, images: [],
  relevantGlossary: [], sectionPath: [], presentationStatus: "source-ready" };
const note: SourceNote = { noteId: "note-one", sourceId: "source", revision: 1, bundle: "bundle", content: "A thought",
  kind: "thought", origin: "user", evidenceRole: "explanation", anchor: { sourceId: "source", bundle: "bundle", sourceLines: [5, 10] },
  sourceUpdated: false, referenceStatus: "current", deleted: false, canUndo: true };
const view: ReadingWindow = { source: { sourceId: "source", title: "Source", topicId: null }, status: "reading", current: chunk,
  history: [], conversation: [], sourceNotes: [note], noteOperation: { sourceId: "source", status: "saved", note } };
function setup(notes: readonly SourceNote[] = []) {
  const host: ReaderHost = { getReadingWindow: vi.fn(), continueReading: vi.fn(), sendMessage: vi.fn(),
    createSourceNote: vi.fn(async () => readerSuccess(view)), changeSourceNote: vi.fn(async () => readerSuccess(view)) };
  const onAccept = vi.fn(), onToast = vi.fn();
  const result = render(<ChunkNoteList host={host} chunk={chunk} notes={notes} onAccept={onAccept} onToast={onToast} />);
  return { host, onAccept, onToast, ...result };
}

it("saves a paragraph note directly with the owning chunk and selected kind", async () => {
  const { host, onAccept } = setup();
  fireEvent.click(screen.getByRole("button", { name: "+ 记小段笔记" }));
  fireEvent.click(screen.getByRole("radio", { name: "问题" }));
  fireEvent.change(screen.getByRole("textbox", { name: "小段笔记" }), { target: { value: "What is the limitation?" } });
  fireEvent.keyDown(screen.getByRole("textbox", { name: "小段笔记" }), { key: "Enter" });
  await waitFor(() => expect(host.createSourceNote).toHaveBeenCalledWith(expect.objectContaining({ sourceId: "source", content: "What is the limitation?",
    kind: "question", origin: "user", chunk: { planId: "plan-001", chunkId: "chunk-001" }, requestId: expect.any(String) })));
  expect(host.sendMessage).not.toHaveBeenCalled();
  expect(onAccept).toHaveBeenCalledWith(view);
});

it("retains a failed draft and offers a new whole-source save when the chunk bundle changed", async () => {
  const { host } = setup();
  vi.mocked(host.createSourceNote!).mockResolvedValueOnce(readerFailure("note_bundle_changed", "这段原文已更新，可改存为整篇笔记"));
  fireEvent.click(screen.getByRole("button", { name: "+ 记小段笔记" }));
  fireEvent.change(screen.getByRole("textbox", { name: "小段笔记" }), { target: { value: "Keep this input" } });
  fireEvent.click(screen.getByRole("button", { name: "保存" }));
  await screen.findByRole("alert");
  expect(screen.getByRole("textbox", { name: "小段笔记" })).toHaveValue("Keep this input");
  fireEvent.click(screen.getByRole("button", { name: "存为整篇笔记" }));
  await waitFor(() => expect(host.createSourceNote).toHaveBeenCalledTimes(2));
  const [first, second] = vi.mocked(host.createSourceNote!).mock.calls.map(([input]) => input);
  expect(second).not.toHaveProperty("chunk");
  expect(second.requestId).not.toBe(first.requestId);
});

it("restores paragraph drafts across remounts and ignores composition Enter and Shift+Enter", async () => {
  const first = setup();
  fireEvent.click(screen.getByRole("button", { name: "+ 记小段笔记" }));
  const input = screen.getByRole("textbox", { name: "小段笔记" });
  fireEvent.change(input, { target: { value: "Recover my paragraph thought" } });
  fireEvent.keyDown(input, { key: "Enter", isComposing: true });
  fireEvent.keyDown(input, { key: "Enter", shiftKey: true });
  expect(first.host.createSourceNote).not.toHaveBeenCalled();
  first.unmount();
  setup(); fireEvent.click(screen.getByRole("button", { name: "+ 记小段笔记" }));
  expect(screen.getByRole("textbox", { name: "小段笔记" })).toHaveValue("Recover my paragraph thought");
});

it("edits paragraph content and deletes with an undo action using the returned revision", async () => {
  const { host, onToast } = setup([note]);
  vi.mocked(host.changeSourceNote!).mockResolvedValue(readerSuccess({ ...view,
    noteOperation: { sourceId: "source", status: "changed", operation: "edit", note: { ...note, revision: 2 } } }));
  fireEvent.click(screen.getByRole("button", { name: "编辑" }));
  fireEvent.change(screen.getByRole("textbox", { name: "小段笔记" }), { target: { value: "Edited thought" } });
  fireEvent.click(screen.getByRole("button", { name: "保存" }));
  await waitFor(() => expect(host.changeSourceNote).toHaveBeenCalledWith("source", "note-one", "edit", 1, expect.any(String), "Edited thought"));
  vi.mocked(host.changeSourceNote!).mockResolvedValue(readerSuccess({ ...view,
    noteOperation: { sourceId: "source", status: "changed", operation: "delete", note: { ...note, revision: 3, deleted: true } } }));
  fireEvent.click(screen.getByRole("button", { name: "删除" }));
  await waitFor(() => expect(onToast).toHaveBeenCalledWith("已删除小段笔记", expect.objectContaining({ label: "撤销" })));
  onToast.mock.calls.at(-1)![1].run();
  await waitFor(() => expect(host.changeSourceNote).toHaveBeenLastCalledWith("source", "note-one", "undo", 3, expect.any(String), undefined));
});

it("shows pending paragraph content optimistically and reuses its failed request after remount", async () => {
  const first = setup();
  let resolve!: (value: ReturnType<typeof readerFailure>) => void;
  vi.mocked(first.host.createSourceNote!).mockImplementationOnce(() => new Promise(done => { resolve = done; }));
  fireEvent.click(screen.getByRole("button", { name: "+ 记小段笔记" }));
  fireEvent.change(screen.getByRole("textbox", { name: "小段笔记" }), { target: { value: "Pending paragraph thought" } });
  fireEvent.click(screen.getByRole("button", { name: "保存" }));
  expect(screen.getByRole("status")).toHaveTextContent("Pending paragraph thought");
  await act(async () => resolve(readerFailure("unavailable", "暂时无法保存")));
  expect(screen.getByRole("textbox", { name: "小段笔记" })).toHaveValue("Pending paragraph thought");
  const originalId = vi.mocked(first.host.createSourceNote!).mock.calls[0][0].requestId;
  first.unmount(); const second = setup();
  fireEvent.click(screen.getByRole("button", { name: "+ 记小段笔记" }));
  fireEvent.click(screen.getByRole("button", { name: "保存" }));
  await waitFor(() => expect(second.host.createSourceNote).toHaveBeenCalledWith(expect.objectContaining({ requestId: originalId })));
});

it("keeps edits typed after a paragraph save began when that earlier request succeeds", async () => {
  const { host } = setup(); let resolve!: (value: ReturnType<typeof readerSuccess<ReadingWindow>>) => void;
  vi.mocked(host.createSourceNote!).mockImplementationOnce(() => new Promise(done => { resolve = done; }));
  fireEvent.click(screen.getByRole("button", { name: "+ 记小段笔记" }));
  const input = screen.getByRole("textbox", { name: "小段笔记" });
  fireEvent.change(input, { target: { value: "First captured version" } });
  fireEvent.click(screen.getByRole("button", { name: "保存" }));
  fireEvent.change(input, { target: { value: "Newer unsaved draft" } });
  await act(async () => resolve(readerSuccess(view)));
  expect(screen.getByRole("textbox", { name: "小段笔记" })).toHaveValue("Newer unsaved draft");
  expect(JSON.parse(sessionStorage.getItem("focus.chunkNoteDrafts")!)["source:plan-001:chunk-001"].text).toBe("Newer unsaved draft");
});

it("hides a pending paragraph deletion and restores the entry on failure", async () => {
  const { host } = setup([note]); let resolve!: (value: ReturnType<typeof readerFailure>) => void;
  vi.mocked(host.changeSourceNote!).mockImplementationOnce(() => new Promise(done => { resolve = done; }));
  fireEvent.click(screen.getByRole("button", { name: "删除" }));
  expect(screen.queryByText("A thought")).not.toBeInTheDocument();
  await act(async () => resolve(readerFailure("unavailable", "暂时无法删除")));
  expect(screen.getByText("A thought")).toBeInTheDocument();
  expect(screen.getByRole("alert")).toHaveTextContent("暂时无法删除");
});
