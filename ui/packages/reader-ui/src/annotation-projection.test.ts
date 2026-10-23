import { expect, it } from "vitest";
import type { ReadingHighlight, SourceNote, ReaderChunk } from "@focus/reader-contracts";
import { buildMarks, groupLocated, quoteAt, resolveRange, type Located } from "./annotation-projection";

const highlight = (start = 0, end = 2, exact = "原句"): ReadingHighlight => ({ highlightId: "h1", sourceId: "s", planId: "p", chunkId: "c", layer: "source", range: { start, end }, quote: { exact, prefix: "", suffix: "" }, revision: 1, bundle: "b", sourceLines: [1, 4], deleted: false, canUndo: true, sourceUpdated: false });
const note = (): SourceNote => ({ noteId: "n1", sourceId: "s", revision: 1, content: "备注", kind: "thought", origin: "user", evidenceRole: "explanation", bundle: "b", anchor: { sourceId: "s", bundle: "b", sourceLines: [1, 4] }, sentence: highlight(), referenceStatus: "current", sourceUpdated: false, deleted: false, canUndo: true });
const chunk = (overrides: Partial<ReaderChunk> = {}): ReaderChunk => ({ sourceId: "s", planId: "p", chunkId: "c", index: 1, total: 2, sourceLines: [1, 4], bundleVersion: "b", sourceMarkdown: "原句", sectionPath: [], images: [], relevantGlossary: [], translation: null, presentationStatus: "source-ready", ...overrides });

it("resolves exact offsets, then scores quote context and distance after text changes", () => {
  expect(resolveRange("原句正文", highlight())).toEqual({ start: 0, end: 2 });
  expect(resolveRange("新前缀原句正文", highlight())).toEqual({ start: 3, end: 5 });
  expect(resolveRange("甲原句一 乙原句二", { range: { start: 0, end: 2 }, quote: { exact: "原句", prefix: "乙", suffix: "二" } })).toEqual({ start: 6, end: 8 });
  expect(resolveRange("原句  原句", { range: { start: 3, end: 5 }, quote: { exact: "原句", prefix: "", suffix: "" } })).toEqual({ start: 4, end: 6 });
  expect(resolveRange("已删除", highlight())).toBeNull();
  expect(quoteAt("x".repeat(40) + "😀原句" + "y".repeat(40), 40, 44)).toEqual({ exact: "😀原句", prefix: "x".repeat(32), suffix: "y".repeat(32) });
});

it("keeps 32-unit quote context within surrogate boundaries for UTF-8 persistence", () => {
  const text = "😀" + "x".repeat(31) + "target" + "y".repeat(31) + "😀";
  expect(quoteAt(text, 33, 39)).toEqual({ exact: "target", prefix: "x".repeat(31), suffix: "y".repeat(31) });
});

it("merges same-range highlight and sentence note into one stable note-keyed mark", () => {
  const h: Located = { kind: "highlight", item: highlight() }, n: Located = { kind: "note", item: { ...note(), sentence: highlight() } };
  const { marks, lost } = buildMarks("原句正文", [h, n], "source");
  expect(marks).toHaveLength(1); expect(lost).toEqual([]);
  expect(marks[0]).toMatchObject({ key: "n:n1", start: 0, end: 2, highlight: h.item, note: n.item });
});

it("retains the first nonoverlapping record, prioritises notes and reports conflicts as lost", () => {
  const n: Located = { kind: "note", item: { ...note(), sentence: highlight() } };
  const h: Located = { kind: "highlight", item: highlight(0, 3, "原句正") };
  const duplicate: Located = { kind: "note", item: { ...note(), noteId: "n2", sentence: highlight() } };
  const missing: Located = { kind: "highlight", item: highlight(20, 22, "丢失") };
  const result = buildMarks("原句正文", [h, duplicate, n, missing], "source");
  expect(result.marks).toHaveLength(1); expect(result.marks[0].note?.noteId).toBe("n2");
  expect(result.lost).toEqual(expect.arrayContaining([h, n, missing]));
  expect(buildMarks("原句", [{ kind: "highlight", item: highlight() }, { kind: "highlight", item: { ...highlight(), highlightId: "h2" } }], "source").lost).toHaveLength(1);
  expect(buildMarks("原句", [{ kind: "highlight", item: highlight() }], "translation")).toEqual({ marks: [], lost: [] });
});

it("groups records by exact chunk or current-bundle line overlap, using the last repeated occurrence", () => {
  const h = highlight(), n = note();
  const groups = [{ id: "old", chunk: chunk() }, { id: "latest", chunk: chunk() }];
  expect([...groupLocated([h], [n, { ...n, noteId: "whole", sentence: null }], groups).keys()]).toEqual(["latest"]);
  const rebuilt = [{ id: "wide", chunk: chunk({ planId: "new", chunkId: "wide", index: 2, sourceLines: [1, 8] }) }, { id: "narrow", chunk: chunk({ planId: "new", chunkId: "narrow", index: 1 }) }];
  expect([...groupLocated([h], [], rebuilt).keys()]).toEqual(["narrow"]);
  expect(groupLocated([{ ...h, deleted: true }, { ...h, sourceUpdated: true }], [], groups).size).toBe(0);
  expect(groupLocated([h], [], [{ id: "stale", chunk: chunk({ bundleVersion: "old" }) }]).size).toBe(0);
});
