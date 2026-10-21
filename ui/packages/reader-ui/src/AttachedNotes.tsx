import type { ReaderChunk, SourceNote } from "@focus/reader-contracts";
import { MarkdownContent } from "./MarkdownContent";

const kinds = { thought: "想法", conclusion: "结论", question: "问题", example: "例子", concept: "概念" };

export function AttachedNotes({ chunk, notes, onDiscuss, onOpenNote }: {
  chunk: ReaderChunk;
  notes: readonly SourceNote[];
  onDiscuss: () => void;
  onOpenNote: (note: SourceNote) => void;
}) {
  return <aside className="reading-group-notes" aria-label={`第 ${chunk.index} 段笔记`}>
    <header><span>笔记</span><small>{notes.filter(note => !note.deleted).length}</small></header>
    <div className="reading-group-notes__body" tabIndex={0} aria-label={`第 ${chunk.index} 段笔记内容`}>
      {notes.length ? <ol>{notes.map(note => <li key={note.noteId} data-note-id={note.noteId}>
        {note.deleted ? <p>已删除</p> : <>
          <div className="reading-note-meta">{kinds[note.kind]}{note.origin === "dialogue" && <span>来自讨论</span>}</div>
          <MarkdownContent text={note.content} sourceId={note.sourceId} />
        </>}
        <button className="reading-note-edit" onClick={() => onOpenNote(note)}>{note.deleted ? "查看／撤销" : "编辑"}</button>
      </li>)}</ol> : <p className="reading-notes-empty">本段还没有笔记</p>}
    </div>
    <button className="reading-group-ask" onClick={onDiscuss}>就这段讨论</button>
  </aside>;
}
