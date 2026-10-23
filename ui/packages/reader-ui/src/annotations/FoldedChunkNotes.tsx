import { useCallback, useEffect, useState } from "react";
import { ChunkNoteList, type ChunkNoteListProps } from "./ChunkNoteList";
import { ChunkNotesFold } from "./ChunkNotesFold";

export function FoldedChunkNotes(props: ChunkNoteListProps & { freshToken?: number }) {
  const [editing, setEditing] = useState(false), [createSignal, setCreateSignal] = useState(0), [savedId, setSavedId] = useState<string>();
  useEffect(() => { setEditing(false); setCreateSignal(0); setSavedId(undefined); },
    [props.chunk.sourceId, props.chunk.planId, props.chunk.chunkId, props.resetVersion, props.noteClearVersion]);
  const editingChanged = useCallback((active: boolean) => { setEditing(active); props.onEditingChange?.(active); }, [props.onEditingChange]);
  const freshNoteId = props.freshNoteId ?? savedId;
  return <ChunkNotesFold key={`${props.chunk.sourceId}:${props.chunk.planId}:${props.chunk.chunkId}:${props.resetVersion ?? 0}:${props.noteClearVersion ?? 0}`}
    count={props.notes.filter(note => !note.deleted).length} canCreate={!!props.host.createSourceNote} editing={editing}
    freshKey={freshNoteId ? `${freshNoteId}:${props.freshToken ?? 0}` : null} onCreate={() => setCreateSignal(value => value + 1)}>
    <ChunkNoteList {...props} freshNoteId={freshNoteId} hideCreate createSignal={createSignal} onEditingChange={editingChanged}
      onSaved={note => { if (!props.notes.some(item => item.noteId === note.noteId)) setSavedId(note.noteId); props.onSaved?.(note); }} />
  </ChunkNotesFold>;
}
