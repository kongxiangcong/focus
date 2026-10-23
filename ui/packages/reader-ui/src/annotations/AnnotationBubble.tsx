import { useEffect, useRef } from "react";
function Pen({ note = false }: { note?: boolean }) {
  return <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4" aria-hidden="true" className={`reader-anno-icon--${note ? "note" : "hl"}`}><path d="m3 10 7-7 3 3-7 7H3zM9 4l3 3M2 15h12" /></svg>;
}
export function AnnotationBubble({ mode, highlight = false, hasNote = false, crossBlock = false, overlap = false, canHighlight, canNote,
  onHighlight, onNote, onDelete, onReference }: {
  mode: "selection" | "annotation"; highlight?: boolean; hasNote?: boolean; crossBlock?: boolean; overlap?: boolean;
  canHighlight: boolean; canNote: boolean; onHighlight: () => void; onNote: () => void; onDelete: () => void; onReference: () => void;
}) {
  const el = useRef<HTMLDivElement>(null);
  useEffect(() => { if (mode === "annotation") el.current?.querySelector("button")?.focus({ preventScroll: true }); }, [mode]);
  const annotate = !crossBlock && !overlap;
  return <div ref={el} className="reader-anno-bubble" role="toolbar" aria-label={mode === "selection" ? "选区操作" : "标注操作"} onPointerDown={event => event.preventDefault()}>
    {overlap && <span className="reader-anno-bubble__msg">与已有标注重叠，请缩小选区</span>}
    {annotate && canHighlight && <button type="button" aria-pressed={mode === "annotation" ? highlight : undefined} onClick={onHighlight}><Pen />{highlight ? "取消重点" : "重点"}</button>}
    {annotate && canNote && <button type="button" onClick={onNote}><Pen note />{hasNote ? "编辑备注" : "备注"}</button>}
    {annotate && (canHighlight || canNote) && <span className="reader-anno-bubble__sep" />}
    {mode === "annotation" ? <button type="button" onClick={onDelete}>删除标注</button> : <button type="button" onClick={onReference}>引用提问</button>}
  </div>;
}
