import { useEffect, useId, useState, type ReactNode } from "react";
export function ChunkNotesFold({ count, canCreate, onCreate, editing = false, freshKey, children }: {
  count: number; canCreate: boolean; onCreate: () => void; editing?: boolean; freshKey?: string | null; children: ReactNode;
}) {
  const [expanded, setExpanded] = useState(false), id = useId();
  useEffect(() => { if (freshKey || editing) setExpanded(true); }, [freshKey, editing]);
  const open = editing || (expanded && count > 0);
  if (!count && !canCreate && !editing) return null;
  return <section className="reader-chunk-notes-fold" data-open={open} aria-label="小段笔记">
    <div className="reader-chunk-notes-fold__row">
      {count > 0 && <button type="button" className="reader-anno-ghost reader-chunk-notes-fold__toggle" aria-expanded={open} aria-controls={id}
        disabled={editing} onClick={() => setExpanded(value => !value)}><svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true"><path d="m6 3 5 5-5 5" /></svg>小段笔记 · {count}</button>}
      {canCreate && <button type="button" className="reader-anno-ghost" disabled={editing} onClick={() => { setExpanded(true); onCreate(); }}>+ 记小段笔记</button>}
    </div>
    <div className="reader-chunk-notes-fold__body"><div id={id} className="reader-chunk-notes-fold__inner" inert={!open} aria-hidden={!open}>
      <div className="reader-chunk-notes-fold__panel">{children}</div>
    </div></div>
  </section>;
}
