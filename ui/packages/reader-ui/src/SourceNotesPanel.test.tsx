import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ReaderChunk, SourceNote } from "@focus/reader-contracts";
import { SourceNotesPanel } from "./SourceNotesPanel";

afterEach(cleanup);
const chunk: ReaderChunk = { sourceId: "paper", planId: "plan-001", chunkId: "chunk-001", index: 2,
  total: 3, sectionPath: [], sourceLines: [5, 9], sourceMarkdown: "Quoted sentence.", translation: null,
  images: [], relevantGlossary: [], bundleVersion: "bundle-v1", presentationStatus: "source-ready" };
const base: SourceNote = { noteId: "note-whole", sourceId: "paper", revision: 1, content: "Whole thought", kind: "thought",
  origin: "user", evidenceRole: "explanation", bundle: "bundle-v1", anchor: null, placement: null, sentence: null,
  referenceStatus: "current", sourceUpdated: false, deleted: false, canUndo: true };
const location = { sourceId: "paper", bundle: "bundle-v1", sourceLines: [5, 9] as const };
const sentence: SourceNote = { ...base, noteId: "note-sentence", content: "A sentence remark", anchor: location,
  sentence: { planId: "plan-001", chunkId: "chunk-001", layer: "source", range: { start: 0, end: 16 },
    quote: { exact: "Quoted sentence.", prefix: "", suffix: "" } } };
const callbacks = () => ({ onOpenSentence: vi.fn(), onEdit: vi.fn(), onChange: vi.fn(), onDraftChange: vi.fn(), onCancelEdit: vi.fn() });

describe("SourceNotesPanel", () => {
  it("groups paragraph, whole-source and sentence notes without duplicating sentence remarks", () => {
    const paragraph = { ...base, noteId: "note-paragraph", content: "Paragraph thought", placement: location };
    render(<SourceNotesPanel notes={[base, paragraph, sentence]} chunks={[chunk]} {...callbacks()} />);
    expect(screen.getByText("笔记 · 3")).toBeInTheDocument();
    const small = within(screen.getByRole("group", { name: "小段笔记" }));
    expect(small.getByText("Paragraph thought")).toBeInTheDocument();
    expect(small.getByText("第 2 段")).toBeInTheDocument();
    expect(small.queryByText("A sentence remark")).not.toBeInTheDocument();
    expect(within(screen.getByRole("group", { name: "整篇笔记" })).getByText("Whole thought")).toBeInTheDocument();
    const remarks = within(screen.getByRole("group", { name: "句子备注" }));
    expect(remarks.getByText("「Quoted sentence.」")).toBeInTheDocument();
    expect(remarks.getByText("A sentence remark")).toBeInTheDocument();
    expect(screen.getAllByText("A sentence remark")).toHaveLength(1);
    expect(screen.getByText("「Quoted sentence.」").closest("li")).toHaveAttribute("title", "「Quoted sentence.」\nA sentence remark");
  });

  it("opens loaded sentence notes through callbacks and keeps sentence deletion separate", () => {
    const handlers = callbacks();
    render(<SourceNotesPanel notes={[sentence]} chunks={[chunk]} {...handlers} />);
    fireEvent.click(screen.getByText("「Quoted sentence.」"));
    expect(handlers.onOpenSentence).toHaveBeenCalledWith(sentence, false, chunk);
    fireEvent.click(screen.getByRole("button", { name: "编辑" }));
    expect(handlers.onOpenSentence).toHaveBeenCalledWith(sentence, true, chunk);
    fireEvent.click(screen.getByRole("button", { name: "删除" }));
    expect(handlers.onChange).toHaveBeenCalledWith(sentence, "delete");
    expect(handlers.onEdit).not.toHaveBeenCalled();
  });

  it("shows unresolved positions, labels unloaded paragraph notes by lines and explains unloaded sentences", () => {
    const handlers = callbacks();
    render(<SourceNotesPanel notes={[sentence, { ...base, noteId: "unloaded", content: "Unloaded thought", anchor: location }]}
      chunks={[]} lostSentenceNoteIds={new Set([sentence.noteId])} {...handlers} />);
    expect(screen.getByText("原文位置已失效")).toBeInTheDocument();
    expect(screen.getByText("第 5–9 行")).toBeInTheDocument();
    fireEvent.click(screen.getByText("「Quoted sentence.」"));
    expect(screen.getByRole("status")).toHaveTextContent("该段未加载");
    expect(within(screen.getByRole("group", { name: "句子备注" })).getByRole("button", { name: "编辑" })).toBeDisabled();
    expect(handlers.onOpenSentence).not.toHaveBeenCalled();
  });

  it("counts live notes, preserves deleted note undo and flags stale-bundle remarks", () => {
    render(<SourceNotesPanel notes={[{ ...base, deleted: true }, { ...sentence, sourceUpdated: true }]}
      chunks={[chunk]} {...callbacks()} />);
    expect(screen.getByText("笔记 · 1")).toBeInTheDocument();
    expect(screen.getByText("已删除，可撤销")).toBeInTheDocument();
    expect(screen.getByText("原文位置已失效")).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "撤销" })).toHaveLength(2);
  });

  it("navigates sentence notes to their exact loaded Plan before considering overlapping lines", () => {
    const handlers = callbacks();
    const otherPlan = { ...chunk, planId: "plan-002", index: 1 };
    render(<SourceNotesPanel notes={[sentence]} chunks={[otherPlan, chunk]} {...handlers} />);
    fireEvent.click(screen.getByText("「Quoted sentence.」"));
    expect(handlers.onOpenSentence).toHaveBeenCalledWith(sentence, false, chunk);
  });

  it("uses the last repeated exact chunk occurrence, matching inline annotation ownership", () => {
    const handlers = callbacks(), latest = { ...chunk, sourceMarkdown: "Latest rendered occurrence" };
    render(<SourceNotesPanel notes={[sentence]} chunks={[chunk, latest]} {...handlers} />);
    fireEvent.click(screen.getByText("「Quoted sentence.」"));
    expect(handlers.onOpenSentence).toHaveBeenCalledWith(sentence, false, latest);
  });

  it("keeps a loaded lost sentence remark readable and editable without jumping to an unrelated position", () => {
    const handlers = callbacks();
    render(<SourceNotesPanel notes={[sentence]} chunks={[chunk]} lostSentenceNoteIds={new Set([sentence.noteId])} {...handlers} />);
    fireEvent.click(screen.getByText("「Quoted sentence.」"));
    expect(screen.getByRole("status")).toHaveTextContent("原文位置已失效");
    expect(handlers.onOpenSentence).not.toHaveBeenCalled();
    const edit = screen.getByRole("button", { name: "编辑" });
    expect(edit).toBeEnabled();
    fireEvent.click(edit);
    expect(handlers.onOpenSentence).toHaveBeenCalledWith(sentence, true, chunk);
  });
});
