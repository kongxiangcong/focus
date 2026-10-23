import { useState } from "react";
import { sentenceNoteText, type ReaderChunk, type SourceNote } from "@focus/reader-contracts";
import "./source-notes-panel.css";

interface SourceNotesPanelProps {
  notes: readonly SourceNote[];
  chunks: readonly ReaderChunk[];
  lostSentenceNoteIds?: ReadonlySet<string>;
  editing?: { noteId: string | null; draft: string; revision: number | null; conflict: SourceNote | null };
  error?: string;
  onOpenSentence: (note: SourceNote, edit: boolean, chunk: ReaderChunk) => void;
  onEdit: (note: SourceNote) => void;
  onChange: (note: SourceNote, action: "edit" | "delete" | "undo", revision?: number) => void;
  onDraftChange: (value: string) => void;
  onCancelEdit: () => void;
}

function sourceNoteChunk(note: SourceNote, chunks: readonly ReaderChunk[]): ReaderChunk | undefined {
  const location = note.anchor ?? note.placement;
  if (!location) return;
  if (note.sentence) {
    const exact = chunks.find(chunk => chunk.sourceId === note.sourceId && chunk.bundleVersion === location.bundle &&
      chunk.planId === note.sentence!.planId && chunk.chunkId === note.sentence!.chunkId);
    if (exact) return exact;
  }
  if (note.sourceUpdated) return;
  let selected: ReaderChunk | undefined, overlap = 0;
  for (const chunk of chunks) {
    if (chunk.sourceId !== note.sourceId || chunk.sourceId !== location.sourceId || chunk.bundleVersion !== location.bundle) continue;
    const count = Math.min(chunk.sourceLines[1], location.sourceLines[1]) - Math.max(chunk.sourceLines[0], location.sourceLines[0]) + 1;
    if (count > overlap || (count > 0 && count === overlap && chunk.index < selected!.index)) {
      selected = chunk; overlap = count;
    }
  }
  return selected;
}

/** Source-owned notes grouped for the materials drawer; highlights are not notes. */
export function SourceNotesPanel({ notes, chunks, lostSentenceNoteIds, editing, error,
  onOpenSentence, onEdit, onChange, onDraftChange, onCancelEdit }: SourceNotesPanelProps) {
  const [notice, setNotice] = useState("");
  const visible = notes.filter(note => !note.deleted || note.canUndo);
  const grouped = [
    { title: "小段笔记", notes: visible.filter(note => !note.sentence && !note.sourceUpdated && !!(note.anchor ?? note.placement)) },
    { title: "整篇笔记", notes: visible.filter(note => !note.sentence && (note.sourceUpdated || !(note.anchor ?? note.placement))) },
    { title: "句子备注", notes: visible.filter(note => !!note.sentence) },
  ];
  const count = notes.filter(note => !note.deleted).length;
  return <details className="focus-source-notes" open>
    <summary>笔记 · {count}</summary>
    {error && <p role="alert">{error}</p>}
    {notice && <p role="status">{notice}</p>}
    {!visible.length ? <p>在正文中选中句子可以标重点或写备注；对讨论说“记下来”可保存小段笔记。</p> :
      grouped.map(group => <details className="source-notes-group" aria-label={group.title} key={group.title} open>
        <summary>{group.title} · {group.notes.filter(note => !note.deleted).length}</summary>
        <ol>{group.notes.map(note => {
          const chunk = sourceNoteChunk(note, chunks), location = note.anchor ?? note.placement;
          const lost = !!note.sentence && (note.sourceUpdated || lostSentenceNoteIds?.has(note.noteId));
          return <li key={note.noteId} data-source-note-id={note.noteId} title={sentenceNoteText(note)}>
            {group.title === "小段笔记" && location && <small>{chunk ? `第 ${chunk.index} 段` : `第 ${location.sourceLines[0]}–${location.sourceLines[1]} 行`}</small>}
            {note.sentence && <>
              <button className="source-note-quote" onClick={() => {
                if (!chunk) { setNotice("该段未加载"); return; }
                if (lost) { setNotice("原文位置已失效"); return; }
                setNotice(""); onOpenSentence(note, false, chunk);
              }}>「{note.sentence.quote.exact}」</button>
              {lost && <small className="source-note-lost">原文位置已失效</small>}
            </>}
            {editing?.noteId === note.noteId && !note.sentence ? <div>
              <textarea aria-label="编辑笔记" value={editing.draft} onChange={event => onDraftChange(event.target.value)} />
              {editing.conflict && <p>已保存版本：{sentenceNoteText(editing.conflict)}</p>}
              <button disabled={!editing.draft.trim()} onClick={() => onChange(note, "edit", editing.conflict?.revision ?? editing.revision ?? note.revision)}>{editing.conflict ? "重新提交" : "保存修改"}</button>
              <button onClick={onCancelEdit}>取消</button>
            </div> : <>
              <span className="source-note-content">{note.deleted ? "已删除，可撤销" : note.content}</span>
              {!note.deleted && <button disabled={!!note.sentence && !chunk} onClick={() => note.sentence && chunk ? onOpenSentence(note, true, chunk) : onEdit(note)}>编辑</button>}
              {!note.deleted && <button onClick={() => onChange(note, "delete")}>删除</button>}
              {note.canUndo && <button onClick={() => onChange(note, "undo")}>撤销</button>}
            </>}
          </li>;
        })}</ol>
      </details>)}
  </details>;
}
