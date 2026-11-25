import type { ReaderChunk, SourceNote } from "@focus/reader-contracts";
import { readingOwner } from "./reading-owner";
import { noteBelongsToChunk } from "./selected-source-note";

/** Source anchors own notes; a reading occurrence only supplies a display location. */
export function projectSourceNotes(notes: readonly SourceNote[], groups: readonly { id: string; chunk: ReaderChunk | null }[]) {
  const projected = new Map<string, SourceNote[]>();
  for (const note of notes) {
    const anchor = note.anchor ?? note.placement;
    if ((!note.canUndo && note.deleted) || note.sentence != null || note.sourceUpdated) continue;
    if (note.selection) {
      for (const group of groups) {
        if (group.chunk && noteBelongsToChunk(note, group.chunk)) projected.set(group.id, [...(projected.get(group.id) ?? []), note]);
      }
      continue;
    }
    if (!anchor) continue;
    const owner = readingOwner(groups, note.sourceId, anchor);
    if (owner) projected.set(owner.id, [...(projected.get(owner.id) ?? []), note]);
  }
  return projected;
}
