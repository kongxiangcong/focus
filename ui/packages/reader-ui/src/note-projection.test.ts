import { expect, it } from "vitest";
import type { ReaderChunk, SourceNote } from "@focus/reader-contracts";
import { projectSourceNotes } from "./note-projection";

const chunk: ReaderChunk = { sourceId: "source", planId: "plan", chunkId: "one", index: 1, total: 2,
  bundleVersion: "v1", sourceLines: [1, 10], sourceMarkdown: "Text", sectionPath: [], translation: null, images: [], relevantGlossary: [], presentationStatus: "source-ready" as const };
const note: SourceNote = { noteId: "n1", sourceId: "source", revision: 1, bundle: "v1", content: "A note",
  kind: "thought", origin: "user", evidenceRole: "explanation", anchor: { sourceId: "source", bundle: "v1", sourceLines: [8, 16] },
  referenceStatus: "current", sourceUpdated: false, deleted: false, canUndo: false };
const groups = [{ id: "first", chunk }, { id: "second", chunk: { ...chunk, chunkId: "two", index: 2, sourceLines: [11, 20] as const } }];

it("projects a note once to the most overlapping paragraph, breaking ties by index", () => {
  expect([...projectSourceNotes([note], groups)]).toEqual([["second", [note]]]);
  const tied = { ...note, anchor: { ...note.anchor!, sourceLines: [8, 13] as const } };
  expect([...projectSourceNotes([tied], [...groups].reverse())]).toEqual([["first", [tied]]]);
});

it("leaves unanchored, old, unloaded, foreign and permanently deleted notes in materials only", () => {
  const notes: SourceNote[] = [
    { ...note, anchor: null }, { ...note, sourceUpdated: true },
    { ...note, anchor: { ...note.anchor!, bundle: "old" } },
    { ...note, anchor: { ...note.anchor!, sourceLines: [50, 60] } },
    { ...note, sourceId: "other" }, { ...note, anchor: { ...note.anchor!, sourceId: "other" } },
    { ...note, deleted: true },
  ];
  expect(projectSourceNotes(notes, groups).size).toBe(0);
  expect(projectSourceNotes([note], [{ id: "unknown", chunk: { ...chunk, bundleVersion: undefined } }]).size).toBe(0);
});

it("keeps undoable notes and uses only the latest occurrence of a revisited paragraph", () => {
  const deleted = { ...note, deleted: true, canUndo: true };
  expect([...projectSourceNotes([deleted], [...groups, { ...groups[1], id: "revisit" }])]).toEqual([["revisit", [deleted]]]);
});

it("projects discussion placement as small-chunk notes while excluding sentence notes", () => {
  const placed: SourceNote = { ...note, anchor: null, placement: note.anchor! };
  expect([...projectSourceNotes([placed], groups)]).toEqual([["second", [placed]]]);
  const sentence: SourceNote = { ...note, sentence: { planId: "plan", chunkId: "one", layer: "source", range: { start: 0, end: 4 }, quote: { exact: "Text", prefix: "", suffix: "" } } };
  expect(projectSourceNotes([sentence], groups).size).toBe(0);
});
