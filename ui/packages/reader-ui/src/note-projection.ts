import type { ReaderChunk, SourceNote } from "@focus/reader-contracts";

/** Source anchors own notes; a reading occurrence only supplies a display location. */
export function projectSourceNotes(notes: readonly SourceNote[], groups: readonly { id: string; chunk: ReaderChunk | null }[]) {
  const projected = new Map<string, SourceNote[]>();
  for (const note of notes) {
    const anchor = note.anchor ?? note.placement;
    if ((!note.canUndo && note.deleted) || !anchor || note.sentence != null || note.sourceUpdated) continue;
    let owner: typeof groups[number] | undefined;
    let overlap = 0;
    for (const group of groups) {
      const chunk = group.chunk;
      if (!chunk || chunk.sourceId !== note.sourceId || chunk.sourceId !== anchor.sourceId ||
          !chunk.bundleVersion || chunk.bundleVersion !== anchor.bundle) continue;
      const lines = Math.min(chunk.sourceLines[1], anchor.sourceLines[1]) -
        Math.max(chunk.sourceLines[0], anchor.sourceLines[0]) + 1;
      // Equal repeated occurrences use the latest display, without duplicating the note.
      if (lines > 0 && (lines > overlap || (lines === overlap && chunk.index <= owner!.chunk!.index))) {
        owner = group; overlap = lines;
      }
    }
    if (owner) projected.set(owner.id, [...(projected.get(owner.id) ?? []), note]);
  }
  return projected;
}
