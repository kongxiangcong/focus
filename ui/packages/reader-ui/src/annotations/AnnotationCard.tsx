import type { SourceNote } from "@focus/reader-contracts";
import type { ResolvedMark } from "../annotation-projection";

export function AnnotationCard({ mark, linked, onLink, onEdit, onDelete, onPulse }: { mark: ResolvedMark;
  linked: boolean; onLink: (key: string | null) => void; onEdit: (note: SourceNote) => void;
  onDelete: (mark: ResolvedMark) => void; onPulse: (key: string) => void;
}) {
  const note = mark.note;
  if (!note || note.deleted) return null;
  const pending = note.noteId.startsWith("p-");
  return <div className={`reader-anno-card${mark.highlight ? " has-hl" : ""}${linked ? " is-linked" : ""}`}
    data-anno-card={mark.key} data-anno-ui tabIndex={0} role="group" aria-label={`句子备注：${note.sentence.quote.exact}`}
    onPointerEnter={() => onLink(mark.key)} onPointerLeave={() => onLink(null)} onFocus={() => onLink(mark.key)}
    onBlur={event => { if (!event.currentTarget.contains(event.relatedTarget)) onLink(null); }}
    onClick={event => { if (!(event.target as Element).closest("button,textarea,input,select")) onPulse(mark.key); }}
    onKeyDown={event => { if (event.target === event.currentTarget && (event.key === "Enter" || event.key === " ")) { event.preventDefault(); onPulse(mark.key); } }}>
    <div className="reader-anno-card__quote"><span>{note.sentence.quote.exact}</span></div>
    <div className="reader-anno-card__text">{note.content}</div>
    <div className="reader-anno-card__actions">
      <button className="reader-anno-icon-btn" aria-label="编辑备注" disabled={pending} onClick={() => onEdit(note)}><svg viewBox="0 0 16 16" aria-hidden="true" fill="none" stroke="currentColor"><path d="m10 2 4 4-7 7-4 1 1-4zM9 3l4 4" /></svg></button>
      <button className="reader-anno-icon-btn danger" aria-label="删除标注" disabled={pending} onClick={() => onDelete(mark)}><svg viewBox="0 0 16 16" aria-hidden="true" fill="none" stroke="currentColor"><path d="M3 4h10M6 4V2h4v2M4 4l1 10h6l1-10M7 6v6m2-6v6" /></svg></button>
    </div>
  </div>;
}
