import { expect, it, vi } from "vitest";
import { HttpReaderHost } from "./http-reader-host";
import { FixtureReaderHost } from "./fixture-reader-host";
import { sentenceNoteText, type CreateHighlightInput, type CreateSourceNoteInput, type ReadingWindow, type ReaderHostResult } from "@focus/reader-contracts";

const value = <T,>(result: ReaderHostResult<T>): T => { if (!result.ok) throw new Error(result.error.code); return result.value; };
async function highlightInput(host: FixtureReaderHost): Promise<CreateHighlightInput> {
  const chunk = value(await host.getReadingWindow()).current!;
  return { sourceId: chunk.sourceId, requestId: "highlight-create", chunk: { planId: chunk.planId, chunkId: chunk.chunkId }, layer: "source", range: { start: 0, end: 4 }, quote: { exact: "阅读界面", prefix: "", suffix: "需要保留上下文" } };
}

it("sends highlight operations with escaped identities and the bound instance header", async () => {
  const fetch = vi.fn<typeof globalThis.fetch>().mockResolvedValue(new Response(JSON.stringify({ ok: true, value: null })));
  const host = new HttpReaderHost({ baseUrl: "http://localhost", instanceId: "active", fetch });
  const sentence = { layer: "source" as const, range: { start: 0, end: 2 }, quote: { exact: "原句", prefix: "", suffix: "" } };
  await host.createHighlight({ sourceId: "source/id", requestId: "create-123", chunk: { planId: "p", chunkId: "c" }, ...sentence });
  await host.changeHighlight("source/id", "hl/id", "delete", 1, "delete-123");
  await host.highlightRequestResult("source/id", "request/id");
  const urls = fetch.mock.calls.map(([url]) => url);
  expect(urls).toEqual([
    "http://localhost/library/sources/source%2Fid/highlights",
    "http://localhost/library/sources/source%2Fid/highlights/hl%2Fid/delete",
    "http://localhost/library/sources/source%2Fid/highlights/requests/request%2Fid",
  ]);
  expect(fetch.mock.calls.slice(0, 2).map(([, init]) => init?.method)).toEqual(["POST", "POST"]);
  expect(JSON.parse(fetch.mock.calls[0][1]!.body as string)).toEqual({ requestId: "create-123", chunk: { planId: "p", chunkId: "c" }, ...sentence });
  expect(JSON.parse(fetch.mock.calls[1][1]!.body as string)).toEqual({ expectedRevision: 1, requestId: "delete-123" });
  for (const [, init] of fetch.mock.calls) expect(new Headers(init?.headers).get("X-FOCUS-Instance")).toBe("active");
});

it("passes sentence note bodies and actionable annotation errors through HTTP", async () => {
  const fetch = vi.fn<typeof globalThis.fetch>();
  const host = new HttpReaderHost({ baseUrl: "http://localhost", fetch });
  const sentence = { layer: "source" as const, range: { start: 0, end: 2 }, quote: { exact: "原句", prefix: "", suffix: "" } };
  for (const code of ["note_sentence_invalid", "highlight_bundle_changed", "highlight_invalid", "highlight_request_conflict"]) {
    fetch.mockResolvedValueOnce(new Response(JSON.stringify({ ok: false, error: { code, message: "changed", retryable: false } }), { status: 409 }));
    const result = await host.createSourceNote({ sourceId: "demo", requestId: "sentence-request", kind: "thought", origin: "user", content: "备注", chunk: { planId: "p", chunkId: "c" }, sentence });
    expect(result).toMatchObject({ ok: false, error: { code } });
  }
  expect(JSON.parse(fetch.mock.calls[0][1]!.body as string).sentence).toEqual(sentence);
});

it("creates fixture highlights once and recovers their original request result", async () => {
  const host = new FixtureReaderHost();
  const before = value(await host.getReadingWindow());
  const input = await highlightInput(host);
  const first = value(await host.createHighlight(input));
  const record = first.highlightOperation!.highlight!;
  expect(record).toMatchObject({ ...input.chunk, layer: input.layer, range: input.range, quote: input.quote, revision: 1, sourceId: input.sourceId, bundle: "fixture-bundle-v1", deleted: false, canUndo: true, sourceUpdated: false });
  expect(record.sourceLines).toEqual(before.current!.sourceLines);
  expect(first.current).toEqual(before.current);
  expect(first.conversation).toEqual(before.conversation);
  expect(value(await host.createHighlight(input)).sourceHighlights).toEqual([record]);
  expect(value(await host.highlightRequestResult(input.sourceId, input.requestId))).toMatchObject({ status: "saved", highlight: record });
  expect(value(await host.highlightRequestResult(input.sourceId, "unknown-request"))).toBeNull();
  expect(await host.createHighlight({ ...input, quote: { ...input.quote, exact: "other" } })).toMatchObject({ ok: false });
});

it("rejects invalid fixture sentence coordinates, unavailable layers and request identities", async () => {
  const host = new FixtureReaderHost(), input = await highlightInput(host);
  const invalid: Record<string, unknown>[] = [
    { layer: "other" }, { layer: "translation" }, { range: { start: -1, end: 4 } },
    { range: { start: 0.5, end: 4 } }, { range: { start: true, end: 4 } }, { range: { start: 4, end: 4 } },
    { range: { start: 0, end: 2001 } }, { range: { start: 0, end: 4, extra: 0 } },
    { quote: { ...input.quote, exact: "" } }, { quote: { ...input.quote, exact: "x".repeat(2001) } },
    { quote: { ...input.quote, prefix: "x".repeat(65) } }, { quote: { ...input.quote, suffix: "x".repeat(65) } },
    { quote: { ...input.quote, extra: "" } }, { chunk: { ...input.chunk, chunkId: "missing" } },
    { chunk: null }, { requestId: "short" }, { requestId: "invalid_request" },
  ];
  for (const patch of invalid) expect(await host.createHighlight({ ...input, ...patch } as CreateHighlightInput), JSON.stringify(patch)).toMatchObject({ ok: false });
  expect(value(await host.getReadingWindow()).sourceHighlights).toHaveLength(0);
});

it("keeps highlight delete and single-step undo revisioned, conflict-aware and replayable", async () => {
  const host = new FixtureReaderHost(), input = await highlightInput(host);
  const created = value(await host.createHighlight(input)).highlightOperation!.highlight!;
  const deleted = value(await host.changeHighlight(input.sourceId, created.highlightId, "delete", 1, "delete-request"));
  expect(deleted.highlightOperation).toMatchObject({ status: "changed", operation: "delete", highlight: { revision: 2, deleted: true, canUndo: true } });
  expect(value(await host.changeHighlight(input.sourceId, created.highlightId, "delete", 1, "delete-request")).highlightOperation).toEqual(deleted.highlightOperation);
  expect(value(await host.changeHighlight(input.sourceId, created.highlightId, "undo", 1, "stale-request")).highlightOperation).toMatchObject({ status: "conflict", current: { revision: 2 } });
  const restored = value(await host.changeHighlight(input.sourceId, created.highlightId, "undo", 2, "restore-request"));
  expect(restored.highlightOperation).toMatchObject({ status: "changed", highlight: { revision: 3, deleted: false, canUndo: false } });
  expect(value(await host.changeHighlight(input.sourceId, created.highlightId, "undo", 3, "twice-request")).highlightOperation).toMatchObject({ status: "conflict" });
  expect(created).toMatchObject({ revision: 1, deleted: false });
});

it("keeps a sentence note's locator intact across edit, delete and their single-step undo", async () => {
  const host = new FixtureReaderHost(), input = await highlightInput(host);
  const noteInput: CreateSourceNoteInput = { sourceId: input.sourceId, requestId: "note-create", kind: "thought", origin: "user", content: "备注", chunk: input.chunk,
    sentence: { layer: input.layer, range: input.range, quote: input.quote } };
  for (const patch of [{ chunk: undefined }, { kind: "question" }, { origin: "dialogue" }]) {
    expect(await host.createSourceNote({ ...noteInput, ...patch } as CreateSourceNoteInput)).toMatchObject({ ok: false, error: { code: "note_sentence_invalid" } });
  }
  const created = value(await host.createSourceNote(noteInput)).noteOperation!.note!;
  expect(created.sentence).toEqual({ ...noteInput.sentence, ...input.chunk });
  expect(sentenceNoteText(created)).toBe("「阅读界面」\n备注");
  expect(sentenceNoteText({ ...created, sentence: null })).toBe("备注");
  const edited = value(await host.changeSourceNote(input.sourceId, created.noteId, "edit", 1, "note-edit", "改后的备注")).noteOperation!.note!;
  expect(edited).toMatchObject({ content: "改后的备注", revision: 2, sentence: created.sentence });
  expect(value(await host.changeSourceNote(input.sourceId, created.noteId, "edit", 1, "note-stale", "冲突")).noteOperation).toMatchObject({ status: "conflict", current: edited, attemptedContent: "冲突" });
  const recovered = value(await host.changeSourceNote(input.sourceId, created.noteId, "undo", 2, "note-unedit")).noteOperation!.note!;
  expect(recovered).toMatchObject({ revision: 3, content: "备注", canUndo: false });
  const deleted = value(await host.changeSourceNote(input.sourceId, created.noteId, "delete", 3, "note-delete")).noteOperation!.note!;
  expect(deleted).toMatchObject({ revision: 4, deleted: true, canUndo: true });
  const restored = value(await host.changeSourceNote(input.sourceId, created.noteId, "undo", 4, "note-restore")).noteOperation!.note!;
  expect(restored).toMatchObject({ revision: 5, deleted: false, content: "备注", sentence: created.sentence, canUndo: false });
  expect(value(await host.sourceNoteRequestResult(input.sourceId, "note-edit"))).toMatchObject({ status: "changed", note: edited });
  expect(value(await host.changeSourceNote(input.sourceId, created.noteId, "undo", 5, "note-twice")).noteOperation).toMatchObject({ status: "conflict" });
  expect(created).toMatchObject({ revision: 1, content: "备注" });
});

it("can fail either fixture write independently and retry without duplicating the successful half", async () => {
  const host = new FixtureReaderHost(), input = await highlightInput(host);
  const highlight = value(await host.createHighlight(input)).highlightOperation!.highlight!;
  const noteInput: CreateSourceNoteInput = { sourceId: input.sourceId, requestId: "note-pair", chunk: input.chunk, kind: "thought", origin: "user", content: "备注" };
  const note = value(await host.createSourceNote(noteInput)).noteOperation!.note!;
  host.failNext("note");
  expect(await host.changeSourceNote(input.sourceId, note.noteId, "delete", 1, "note-delete")).toMatchObject({ ok: false });
  expect(value(await host.changeHighlight(input.sourceId, highlight.highlightId, "delete", 1, "hl-delete")).highlightOperation?.highlight?.revision).toBe(2);
  expect(value(await host.changeSourceNote(input.sourceId, note.noteId, "delete", 1, "note-delete")).noteOperation?.note?.revision).toBe(2);
  expect(value(await host.changeHighlight(input.sourceId, highlight.highlightId, "delete", 1, "hl-delete")).highlightOperation?.highlight?.revision).toBe(2);
  for (const outcome of ["failed", "bundle_changed"] as const) {
    host.writeOutcome = outcome;
    expect(await host.createHighlight({ ...input, requestId: "hl-failure" })).toMatchObject({ ok: false, error: { code: outcome === "failed" ? "unavailable" : "highlight_bundle_changed" } });
    expect(await host.createSourceNote({ ...noteInput, requestId: "note-failure" })).toMatchObject({ ok: false, error: { code: outcome === "failed" ? "unavailable" : "note_bundle_changed" } });
  }
});
