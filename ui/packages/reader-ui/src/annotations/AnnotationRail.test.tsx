import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import type { ReaderChunk, ReaderHost, ReadingHighlight, SourceNote } from "@focus/reader-contracts";
import { AnnotationRail } from "./AnnotationRail";
import { projectSourceNotes } from "../note-projection";

afterEach(cleanup);
const chunk: ReaderChunk = { sourceId: "source", planId: "plan-001", chunkId: "chunk-001", index: 1, total: 2,
  bundleVersion: "bundle", sourceLines: [1, 10], sourceMarkdown: "Quoted sentence.", translation: null, images: [],
  relevantGlossary: [], sectionPath: [], presentationStatus: "source-ready" };
const location = { sourceId: "source", bundle: "bundle", sourceLines: [1, 10] as const };
const locator = { planId: "plan-001", chunkId: "chunk-001", layer: "source" as const, range: { start: 0, end: 16 }, quote: { exact: "Quoted sentence.", prefix: "", suffix: "" } };
const note: SourceNote = { noteId: "note-one", sourceId: "source", revision: 1, bundle: "bundle", content: "A sentence remark",
  kind: "thought", origin: "user", evidenceRole: "explanation", anchor: location, sentence: locator,
  sourceUpdated: false, referenceStatus: "current", deleted: false, canUndo: true };
const highlight: ReadingHighlight = { ...locator, ...location, highlightId: "highlight-one", revision: 1, deleted: false, canUndo: true, sourceUpdated: false };
const host: ReaderHost = { getReadingWindow: vi.fn(), continueReading: vi.fn(), sendMessage: vi.fn() };

it("renders cards only for sentence remarks and keeps paragraph notes below their own section", () => {
  const anchored = { ...note, noteId: "paragraph", sentence: null, content: "Anchored paragraph note" };
  const placed = { ...anchored, noteId: "placed", anchor: null, placement: location, content: "Discussion paragraph note", origin: "dialogue" as const };
  const projected = projectSourceNotes([note, anchored, placed], [{ id: "group", chunk }]);
  render(<AnnotationRail chunk={chunk} host={host} notes={projected.get("group") ?? []}
    marks={[{ key: "h:only", start: 20, end: 25, highlight: { ...highlight, highlightId: "only" } },
      { key: "n:note-one", start: 0, end: 16, note: { ...note, sentence: locator }, highlight }]}
    onAccept={vi.fn()} onDiscuss={vi.fn()} onEdit={vi.fn()} onDelete={vi.fn()} onLink={vi.fn()} />);
  expect(document.querySelectorAll("[data-anno-card]")).toHaveLength(1);
  expect(document.querySelector(".reader-anno-card")).toHaveClass("has-hl");
  const rail = screen.getByRole("complementary", { name: "第 1 段笔记" });
  expect(within(rail).getByText("Quoted sentence.")).toBeInTheDocument();
  expect(within(rail).getByText("A sentence remark")).toBeInTheDocument();
  expect(within(rail).getByText("Anchored paragraph note")).toBeInTheDocument();
  expect(within(rail).getByText("Discussion paragraph note")).toBeInTheDocument();
  expect(within(rail).getByText("来自讨论")).toBeInTheDocument();
});

it("routes card edit, full-annotation delete and historical-chunk discussion through callbacks", () => {
  const onEdit = vi.fn(), onDelete = vi.fn(), onDiscuss = vi.fn(), onLink = vi.fn();
  const mark = { key: "n:note-one", start: 0, end: 16, note: { ...note, sentence: locator }, highlight };
  render(<AnnotationRail chunk={chunk} host={host} notes={[]} marks={[mark]}
    onAccept={vi.fn()} onDiscuss={onDiscuss} onEdit={onEdit} onDelete={onDelete} onLink={onLink} />);
  fireEvent.click(screen.getByRole("button", { name: "编辑备注" })); expect(onEdit).toHaveBeenCalledWith(note);
  fireEvent.click(screen.getByRole("button", { name: "删除标注" })); expect(onDelete).toHaveBeenCalledWith(mark);
  fireEvent.click(screen.getByRole("button", { name: "就这段讨论" })); expect(onDiscuss).toHaveBeenCalledOnce();
  expect(screen.getByText("本段还没有小段笔记")).toBeInTheDocument();
});
