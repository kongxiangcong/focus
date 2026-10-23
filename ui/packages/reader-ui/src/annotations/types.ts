import type { AnnotationLayer, ReaderChunk, SentenceQuote, SourceNote } from "@focus/reader-contracts";
export interface SelectionDraft { chunk: ReaderChunk; layer: AnnotationLayer; start: number; end: number; quote: SentenceQuote; text: string; groupId?: string }
export type EditorTarget = { isNew: true; draft: SelectionDraft } | { isNew: false; note: SourceNote };
export interface AnnotationToastValue { message: string; actionLabel?: string; action?: () => void }
export const editorKey = (target: EditorTarget) => target.isNew
  ? `${target.draft.chunk.sourceId}:${target.draft.chunk.planId}:${target.draft.chunk.chunkId}:${target.draft.layer}:${target.draft.start}-${target.draft.end}`
  : `${target.note.sourceId}:note:${target.note.noteId}`;
