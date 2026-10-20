import { createReaderId, type LibrarySource } from "@focus/reader-contracts";
import type { LibraryPageProps } from "./LibraryPage";

export type SourceActions = Pick<LibraryPageProps, "busy" | "active" | "host" | "view" | "managementBusy" | "openManagement" | "setConfirm" | "confirmDelete">;
export function SourceResetActions({ source: s, actions: { busy, active, host, view, managementBusy, setConfirm, confirmDelete }, menu = false }: { source: LibrarySource; actions: SourceActions; menu?: boolean }) {
  return <><button disabled={!!busy || active || !host.replanSource || s.parseStatus !== "ready"} onClick={() => setConfirm({ source: s, action: "replan" })}>重新规划</button>
    <button disabled={!!busy || !host.clearSource || view?.clearBusySources?.includes(s.sourceId)} onClick={() => setConfirm({ source: s, action: "clear", requestId: createReaderId() })}>重新阅读</button>
    {menu && <hr />}<button className="library-more-danger" disabled={managementBusy || !host.deleteSource || !host.deletionImpact} onClick={() => void confirmDelete(s)}>{menu ? "删除…" : "删除来源…"}</button></>;
}
export function SourceMenu({ source: s, page }: { source: LibrarySource; page: LibraryPageProps }) {
  const { moreSource, setMoreSource, managementBusy, sortingReason, host, openManagement, selectedTopic, moveSource } = page;
  const close = () => { setMoreSource(null); document.getElementById(`source-more-trigger-${s.sourceId}`)?.focus(); };
  return <div className="library-source-more" data-more-source={s.sourceId} onClick={event => event.stopPropagation()} onDoubleClick={event => event.stopPropagation()} onKeyDown={event => { if (event.key === "Escape") { event.stopPropagation(); close(); } }}>
    <button id={`source-more-trigger-${s.sourceId}`} aria-label="更多" title="更多操作" aria-expanded={moreSource === s.sourceId} aria-controls={`source-more-${s.sourceId}`} onClick={() => setMoreSource(moreSource === s.sourceId ? null : s.sourceId)}>⋯</button>
    {moreSource === s.sourceId && <div className="library-more-menu" id={`source-more-${s.sourceId}`} role="group" aria-label="更多操作" onClick={event => { if ((event.target as HTMLElement).closest("button")) close(); }}>
      <button disabled={managementBusy || !host.saveSourceDetails} onClick={() => openManagement("source", s.sourceId, s.title)}>管理来源</button>
      {selectedTopic && <button aria-label={`${s.title} 上移`} title={sortingReason || undefined} disabled={!!sortingReason || selectedTopic.sourceIds.indexOf(s.sourceId) === 0} onClick={() => moveSource(s.sourceId, -1)}>上移</button>}
      {selectedTopic && <button aria-label={`${s.title} 下移`} title={sortingReason || undefined} disabled={!!sortingReason || selectedTopic.sourceIds.indexOf(s.sourceId) === selectedTopic.sourceIds.length - 1} onClick={() => moveSource(s.sourceId, 1)}>下移</button>}
      <SourceResetActions source={s} actions={page} menu />
    </div>}
  </div>;
}
