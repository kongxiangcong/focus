import type { SourceNote } from "@focus/reader-contracts";
export function AnnotationNotePop({ note, onEdit, onDelete }: { note: SourceNote; onEdit: () => void; onDelete: () => void }) {
  return <><div className="reader-anno-pop__quote">{note.sentence?.quote.exact}</div>
    <div className="reader-anno-pop__text">{note.content}</div><div className="reader-anno-pop__bar">
      <button type="button" className="reader-anno-ghost" onClick={onEdit}>编辑</button>
      <button type="button" className="reader-anno-ghost danger" onClick={onDelete}>删除标注</button>
    </div></>;
}
