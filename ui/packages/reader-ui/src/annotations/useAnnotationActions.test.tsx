import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import { useState } from "react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import type { CreateHighlightInput, CreateSourceNoteInput, ReadingWindow, ReaderHostResult } from "@focus/reader-contracts";
import { FixtureReaderHost } from "../../../../apps/standalone/src/adapters/fixture-reader-host";
import { useAnnotationActions } from "./useAnnotationActions";

beforeEach(() => sessionStorage.clear());
afterEach(cleanup);
const value = <T,>(result: ReaderHostResult<T>): T => { if (!result.ok) throw new Error(result.error.message); return result.value; };
function deferred<T>() { let resolve!: (value: T) => void; const promise = new Promise<T>(r => { resolve = r; }); return { promise, resolve }; }
function input(view: ReadingWindow): CreateHighlightInput {
  const c = view.current!;
  return { sourceId: c.sourceId, requestId: "highlight-action", chunk: { planId: c.planId, chunkId: c.chunkId }, layer: "source", range: { start: 0, end: 4 }, quote: { exact: "阅读界面", prefix: "", suffix: "需要保留上下文" } };
}
function noteInput(view: ReadingWindow): CreateSourceNoteInput {
  const h = input(view);
  return { sourceId: h.sourceId, requestId: "note-action", content: "保留我的草稿", kind: "thought", origin: "user", chunk: h.chunk, sentence: { layer: h.layer, range: h.range, quote: h.quote } };
}

it("shows one optimistic highlight before the Host response and replaces its temporary identity on success", async () => {
  const host = new FixtureReaderHost(), initial = value(await host.getReadingWindow()), payload = input(initial);
  const response = await host.createHighlight(payload), pending = deferred<ReaderHostResult<ReadingWindow>>();
  vi.spyOn(host, "createHighlight").mockReturnValueOnce(pending.promise);
  const { result } = renderHook(() => { const [view, accept] = useState(initial); return useAnnotationActions({ host, view, accept, scope: "source:0" }); });
  let write!: Promise<ReaderHostResult<ReadingWindow>>;
  act(() => { write = result.current.createHighlight(payload); });
  expect(result.current.highlights).toHaveLength(1);
  expect(result.current.highlights[0].highlightId).toBe("p-highlight-action");
  expect(result.current.fresh["h:p-highlight-action"]).toEqual(["hl"]);
  expect(result.current.busy).toBe(true);
  await act(async () => { pending.resolve(response); await write; });
  expect(result.current.highlights).toEqual(value(response).sourceHighlights);
  expect(result.current.busy).toBe(false);
});

it("keeps newer snapshot records when two successful requests finish out of order", async () => {
  const host = new FixtureReaderHost(), initial = value(await host.getReadingWindow()), firstInput = input(initial);
  const secondInput = { ...firstInput, requestId: "second-highlight", range: { start: 5, end: 8 }, quote: { exact: "需要保", prefix: "", suffix: "" } };
  const firstResponse = await host.createHighlight(firstInput), secondResponse = await host.createHighlight(secondInput);
  const a = deferred<ReaderHostResult<ReadingWindow>>(), b = deferred<ReaderHostResult<ReadingWindow>>();
  vi.spyOn(host, "createHighlight").mockReturnValueOnce(a.promise).mockReturnValueOnce(b.promise);
  const { result } = renderHook(() => { const [view, accept] = useState(initial); return useAnnotationActions({ host, view, accept, scope: "source:0" }); });
  let first!: Promise<ReaderHostResult<ReadingWindow>>, second!: Promise<ReaderHostResult<ReadingWindow>>;
  act(() => { first = result.current.createHighlight(firstInput); second = result.current.createHighlight(secondInput); });
  await act(async () => { b.resolve(secondResponse); await second; });
  expect(result.current.highlights).toHaveLength(2);
  await act(async () => { a.resolve(firstResponse); await first; });
  expect(result.current.highlights).toEqual(value(secondResponse).sourceHighlights);
});

it("does not let an older pending edit cover a newer acknowledged revision", async () => {
  const host = new FixtureReaderHost(), initial = value(await host.getReadingWindow()), payload = noteInput(initial);
  const created = value(await host.createSourceNote(payload)), note = created.noteOperation!.note!;
  const firstResponse = await host.changeSourceNote(note.sourceId, note.noteId, "edit", 1, "first-edit", "旧修改");
  const secondResponse = await host.changeSourceNote(note.sourceId, note.noteId, "edit", 2, "second-edit", "新修改");
  const a = deferred<ReaderHostResult<ReadingWindow>>(), b = deferred<ReaderHostResult<ReadingWindow>>();
  vi.spyOn(host, "changeSourceNote").mockReturnValueOnce(a.promise).mockReturnValueOnce(b.promise);
  const { result } = renderHook(() => { const [view, accept] = useState(created); return useAnnotationActions({ host, view, accept, scope: "source:0" }); });
  let first!: Promise<ReaderHostResult<ReadingWindow>>, second!: Promise<ReaderHostResult<ReadingWindow>>;
  act(() => { first = result.current.editNote(note, "旧修改", "first-edit"); second = result.current.editNote({ ...note, revision: 2 }, "新修改", "second-edit"); });
  await act(async () => { b.resolve(secondResponse); await second; });
  expect(result.current.notes[0]).toMatchObject({ revision: 3, content: "新修改" });
  await act(async () => { a.resolve(firstResponse); await first; });
  expect(result.current.notes[0]).toMatchObject({ revision: 3, content: "新修改" });
});

it("rolls a failed note out of the display and retries the same request without losing its save callbacks", async () => {
  const host = new FixtureReaderHost(), initial = value(await host.getReadingWindow()), payload = noteInput(initial);
  host.writeOutcome = "failed";
  const create = vi.spyOn(host, "createSourceNote"), onNoteSaved = vi.fn(), onNoteFailed = vi.fn();
  const { result } = renderHook(() => { const [view, accept] = useState(initial); return useAnnotationActions({ host, view, accept, scope: "source:0", onNoteSaved, onNoteFailed }); });
  await act(async () => { await result.current.createNote(payload); });
  expect(result.current.notes).toEqual([]);
  expect(onNoteFailed).toHaveBeenCalledWith(payload.requestId);
  expect(onNoteSaved).not.toHaveBeenCalled();
  expect(result.current.toast).toMatchObject({ message: "备注未保存", actionLabel: "重试" });
  host.writeOutcome = "success";
  act(() => result.current.toast!.action!());
  await waitFor(() => expect(result.current.notes).toHaveLength(1));
  expect(create.mock.calls.map(([input]) => input.requestId)).toEqual([payload.requestId, payload.requestId]);
  expect(onNoteSaved).toHaveBeenCalledWith(payload.requestId, expect.objectContaining({ content: payload.content }));
  expect(sessionStorage.getItem("focus.annotationRequests")).toBeNull();
});

it("does not offer a stale-bundle write for retry", async () => {
  const host = new FixtureReaderHost(), initial = value(await host.getReadingWindow()); host.writeOutcome = "bundle_changed";
  const { result } = renderHook(() => { const [view, accept] = useState(initial); return useAnnotationActions({ host, view, accept, scope: "source:0" }); });
  await act(async () => { await result.current.createHighlight(input(initial)); });
  expect(result.current.highlights).toEqual([]);
  expect(result.current.toast).toEqual(expect.objectContaining({ message: "这段原文已更新，标注未保存" }));
  expect(result.current.toast?.action).toBeUndefined();
  expect(sessionStorage.getItem("focus.annotationRequests")).toBeNull();
});

it("treats an ok snapshot with a revision conflict as an unsaved draft and requires a new request to resubmit", async () => {
  const host = new FixtureReaderHost(), initial = value(await host.getReadingWindow()), payload = noteInput(initial);
  const created = value(await host.createSourceNote(payload)), original = created.noteOperation!.note!;
  await host.changeSourceNote(payload.sourceId, original.noteId, "edit", 1, "remote-note-edit", "其他窗口的内容");
  const onNoteSaved = vi.fn(), onNoteFailed = vi.fn(), onNoteConflict = vi.fn();
  const { result } = renderHook(() => { const [view, accept] = useState(created); return useAnnotationActions({ host, view, accept, scope: "source:0", onNoteSaved, onNoteFailed, onNoteConflict }); });
  await act(async () => { const response = await result.current.editNote(original, "我的修改", "conflict-note"); expect(response.ok).toBe(true); });
  expect(onNoteSaved).not.toHaveBeenCalled();
  expect(onNoteFailed).toHaveBeenCalledWith("conflict-note");
  expect(onNoteConflict).toHaveBeenCalledWith("conflict-note", expect.objectContaining({ revision: 2, content: "其他窗口的内容" }), "我的修改");
  expect(result.current.toast?.action).toBeUndefined();
  expect(result.current.notes[0].content).toBe("其他窗口的内容");
  await act(async () => { await result.current.editNote(result.current.notes[0], "我的修改", "explicit-note-resubmit"); });
  expect(result.current.notes[0]).toMatchObject({ revision: 3, content: "我的修改" });
  expect(onNoteSaved).toHaveBeenCalledWith("explicit-note-resubmit", expect.objectContaining({ revision: 3 }));
});

it("retries only the failed half of a mark deletion and uses returned revisions to undo both records", async () => {
  const host = new FixtureReaderHost(), initial = value(await host.getReadingWindow()), hInput = input(initial);
  const h = value(await host.createHighlight(hInput)).highlightOperation!.highlight!;
  const seeded = value(await host.createSourceNote(noteInput(initial))), n = seeded.noteOperation!.note!;
  const highlights = vi.spyOn(host, "changeHighlight"), notes = vi.spyOn(host, "changeSourceNote");
  const { result } = renderHook(() => { const [view, accept] = useState(seeded); return useAnnotationActions({ host, view, accept, scope: "source:0" }); });
  host.failNext("note");
  await act(async () => { await result.current.deleteMark({ highlight: h, note: n }); });
  expect(result.current.toast).toMatchObject({ message: "标注只删除了一部分", actionLabel: "重试" });
  expect(result.current.highlights[0].deleted).toBe(true); expect(result.current.notes[0].deleted).toBe(false);
  act(() => result.current.toast!.action!());
  await waitFor(() => expect(result.current.toast?.actionLabel).toBe("撤销"));
  expect(highlights.mock.calls.filter(call => call[2] === "delete")).toHaveLength(1);
  expect(notes.mock.calls.filter(call => call[2] === "delete")).toHaveLength(2);
  expect(notes.mock.calls[0][4]).toBe(notes.mock.calls[1][4]);
  act(() => result.current.toast!.action!());
  await waitFor(() => expect(result.current.toast?.message).toBe("已恢复标注"));
  expect(highlights.mock.calls.at(-1)?.slice(2, 4)).toEqual(["undo", 2]);
  expect(notes.mock.calls.at(-1)?.slice(2, 4)).toEqual(["undo", 2]);
  expect(result.current.highlights[0]).toMatchObject({ revision: 3, deleted: false });
  expect(result.current.notes[0]).toMatchObject({ revision: 3, deleted: false });
});

it("ignores a late save after the source or clear epoch changes", async () => {
  const host = new FixtureReaderHost(), initial = value(await host.getReadingWindow()), payload = noteInput(initial);
  const response = await host.createSourceNote(payload), pending = deferred<ReaderHostResult<ReadingWindow>>();
  vi.spyOn(host, "createSourceNote").mockReturnValueOnce(pending.promise);
  const accept = vi.fn(), onNoteSaved = vi.fn(), onNoteFailed = vi.fn();
  const { result, rerender } = renderHook(({ scope }) => useAnnotationActions({ host, view: initial, accept, scope, onNoteSaved, onNoteFailed }), { initialProps: { scope: "source:0:0" } });
  let write!: Promise<ReaderHostResult<ReadingWindow>>;
  act(() => { write = result.current.createNote(payload); });
  rerender({ scope: "source:0:1" });
  await act(async () => { pending.resolve(response); await write; });
  expect(accept).not.toHaveBeenCalled(); expect(onNoteSaved).not.toHaveBeenCalled(); expect(onNoteFailed).not.toHaveBeenCalled();
  expect(result.current.notes).toEqual([]); expect(result.current.busy).toBe(false); expect(result.current.toast).toBeNull();
});

it("queries a persisted unresolved request on remount and recovers its acknowledged record without writing twice", async () => {
  const host = new FixtureReaderHost(), initial = value(await host.getReadingWindow()), payload = input(initial);
  const response = await host.createHighlight(payload), pending = deferred<ReaderHostResult<ReadingWindow>>();
  const create = vi.spyOn(host, "createHighlight").mockReturnValueOnce(pending.promise), query = vi.spyOn(host, "highlightRequestResult");
  const first = renderHook(() => useAnnotationActions({ host, view: initial, accept: vi.fn(), scope: "source:0" }));
  act(() => { void first.result.current.createHighlight(payload); });
  first.unmount();
  const { result } = renderHook(() => { const [view, accept] = useState(initial); return useAnnotationActions({ host, view, accept, scope: "source:0" }); });
  await waitFor(() => expect(result.current.highlights).toEqual(value(response).sourceHighlights));
  expect(query).toHaveBeenCalledWith(payload.sourceId, payload.requestId); expect(create).toHaveBeenCalledTimes(1);
  expect(sessionStorage.getItem("focus.annotationRequests")).toBeNull();
  pending.resolve(response);
});
