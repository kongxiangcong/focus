import { ChunkNoteList, type ChunkNoteListProps } from "./ChunkNoteList";

export interface ChunkNotesProps extends ChunkNoteListProps { onDiscuss?: () => void; variant?: "rail" }
export function ChunkNotes({ onDiscuss, ...props }: ChunkNotesProps) {
  const count = props.notes.filter(note => !note.deleted && !note.sentence).length;
  return <section className="reader-chunk-notes" aria-label="小段笔记">
    <header>小段笔记 <small>{count}</small></header>
    {!count && <p className="reader-chunk-notes__empty">本段还没有小段笔记</p>}
    <ChunkNoteList {...props} />
    {onDiscuss && <button className="reader-anno-ghost" onClick={onDiscuss}>就这段讨论</button>}
  </section>;
}
