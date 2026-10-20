import { useEffect, useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import type { BlogArtifactName, BlogArtifactStatus, BlogRegenerationTarget, BlogStatus, LibrarySource, LibraryTopic, ReaderHost, ReadingWindow } from "@focus/reader-contracts";
import { primaryAction, sourceStatus } from "./source-status";
import { SourceRow } from "./SourceRow";
import { SourceCard } from "./SourceCard";
import { SourceInspector } from "./SourceInspector";
import { SourceMenu } from "./SourceMenu";
import type { SourceViewProps } from "./SourceParts";

export type LibraryPageProps = {
  dragging: boolean; setDragging: (value: boolean) => void; uploadDisabled: boolean; chooseUpload: (files?: readonly File[]) => void;
  selectedTopic: LibraryTopic | undefined; managementBusy: boolean; host: ReaderHost;
  openManagement: (kind: "create" | "rename" | "delete" | "source", id?: string, title?: string) => void;
  topics: readonly LibraryTopic[]; topic: string; filtered: readonly LibrarySource[]; libraryView: "cards" | "list";
  setLibraryView: (value: "cards" | "list") => void; query: string; setQuery: (value: string) => void; setTopic: (value: string) => void; loading: boolean;
  view: ReadingWindow | null;
  preparationHidden: (id: string) => boolean; blogs: Readonly<Record<string, BlogStatus>>; setBlogViewer: (id: string) => void;
  busy: string; active: boolean; enterReading: (id: string) => Promise<void>; preparationFailed: (id: string) => boolean; retryPreparation: (id: string) => Promise<void>;
  refreshBlog: (id: string) => Promise<void>; moreSource: string | null; setMoreSource: (id: string | null) => void;
  moveSource: (id: string, offset: number) => void; setConfirm: (value: { source: LibrarySource; action: "delete" | "reread" | "replan" | "clear"; requestId?: string } | null) => void;
  confirmDelete: (source: LibrarySource) => Promise<void>; preparationNotice: (id: string) => ReactNode; activateCandidate: (id: string) => Promise<void>;
  blogArtifacts: readonly [BlogArtifactName, string][]; blogStatusText: Record<BlogArtifactStatus, string>; blogRetryLabel: Record<BlogArtifactName, string>;
  generateBlog: (id: string) => Promise<void>; cancelBlog: (id: string) => Promise<void>; regenerateBlog: (id: string, target: BlogRegenerationTarget) => Promise<void>;
};

export function LibraryPage(page: LibraryPageProps) {
  const { dragging, setDragging, uploadDisabled, chooseUpload, selectedTopic, managementBusy, host, openManagement, topics, topic, filtered, libraryView, setLibraryView, query, setQuery, setTopic, loading, busy, active, view, preparationHidden, blogs, enterReading, refreshBlog, setMoreSource } = page;
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [inspectorOpen, setInspectorOpen] = useState(false);
  const [docked, setDocked] = useState(true);
  const root = useRef<HTMLElement>(null);
  const selected = filtered.find(source => source.sourceId === selectedId);
  useEffect(() => {
    if (!root.current || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(entries => setDocked(entries[0].contentRect.width >= 1040));
    observer.observe(root.current); return () => observer.disconnect();
  }, []);
  function select(id: string, open = true) {
    setSelectedId(id); setMoreSource(null);
    document.getElementById(`source-title-${id}`)?.focus();
    if (open) { setInspectorOpen(true); if (!blogs[id]) void refreshBlog(id); }
  }
  function closeInspector() { setInspectorOpen(false); if (selectedId) document.getElementById(`source-title-${selectedId}`)?.focus(); }
  function keyboard(event: KeyboardEvent<HTMLElement>) {
    const target = event.target as HTMLElement;
    if (target.closest("input, textarea, select, [contenteditable=true], .library-source-more, .library-inspector")) return;
    if (event.key === "Escape") { closeInspector(); return; }
    if (event.altKey || event.ctrlKey || event.metaKey || !["ArrowUp", "ArrowDown"].includes(event.key)) return;
    const id = target.closest<HTMLElement>("[data-source-id]")?.dataset.sourceId;
    if (!id) return;
    event.preventDefault();
    const index = filtered.findIndex(source => source.sourceId === id), next = filtered[Math.max(0, Math.min(filtered.length - 1, index + (event.key === "ArrowDown" ? 1 : -1)))];
    if (next) { select(next.sourceId, inspectorOpen); document.getElementById(`source-title-${next.sourceId}`)?.focus(); }
  }
  function presentation(source: LibrarySource): SourceViewProps {
    const preparation = view?.preparations?.[source.sourceId], action = primaryAction(source, preparation, preparationHidden(source.sourceId), { busy, active, canOpen: !!host.openSource });
    return { source, status: sourceStatus(source, preparation, preparationHidden(source.sourceId)), action, blog: blogs[source.sourceId], topics, selected: selectedId === source.sourceId, expanded: inspectorOpen && selectedId === source.sourceId, candidate: !!(preparation?.candidate && preparation.ready), onSelect: () => select(source.sourceId), onTopic: setTopic, onPrimary: () => { if (!action.disabled) { if (action.kind === "inspect") select(source.sourceId); else void enterReading(source.sourceId); } }, menu: <SourceMenu source={source} page={page} /> };
  }
  return <main ref={root} className="library-page" data-dragging={dragging} onKeyDown={keyboard} onKeyDownCapture={event => { if (event.key === "Escape" && page.moreSource) { event.stopPropagation(); setMoreSource(null); document.getElementById(`source-more-trigger-${page.moreSource}`)?.focus(); } }}
    onDragOver={event => { event.preventDefault(); if (!uploadDisabled) setDragging(true); }}
    onDragLeave={event => { if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setDragging(false); }}
    onDrop={event => { event.preventDefault(); setDragging(false); if (!uploadDisabled) chooseUpload(Array.from(event.dataTransfer.files)); }}>
    <div className="library-layout" data-inspector={!!selected && inspectorOpen}>
      <section className="library-sources" aria-label="材料列表">{selectedTopic && <div><button disabled={managementBusy || !host.manageTopic} onClick={() => openManagement("rename", selectedTopic.topicId, selectedTopic.title)}>重命名专题</button><button disabled={managementBusy || !host.manageTopic} onClick={() => openManagement("delete", selectedTopic.topicId, selectedTopic.title)}>删除专题</button></div>}
        <div className="library-toolbar"><h2>{topics.find(t => t.topicId === topic)?.title ?? "全部材料"}<small>{filtered.length}</small></h2><div className="library-view-switch" role="group" aria-label="显示方式">{([["list", "列表"], ["cards", "卡片"]] as const).map(([mode, label]) => <button key={mode} aria-label={`${label}显示`} aria-pressed={libraryView === mode} onClick={() => { setLibraryView(mode); setMoreSource(null); try { localStorage.setItem("focus.libraryView", mode); } catch { /* The current view remains usable without storage. */ } }}>{label}</button>)}</div><input type="search" aria-label="搜索材料" placeholder="搜索标题" value={query} onChange={event => setQuery(event.target.value)} /></div>
        {selectedTopic && libraryView === "cards" && <p className="library-view-hint">切换到列表视图后可调整专题顺序</p>}
        {loading ? <p role="status" className="library-empty">读取中…</p> : filtered.length === 0 ? <div className="library-empty"><span aria-hidden="true">▤</span><p>{query || topic ? "暂无匹配材料" : "放入第一份材料"}</p><button className="workspace-primary" disabled={uploadDisabled} onClick={() => { if (query || topic) { setQuery(""); setTopic(""); } else chooseUpload(); }}>{query || topic ? "重置" : "上传"}</button></div> : <div className="library-source-list" data-view={libraryView} role="list" aria-label="来源">{filtered.map(source => libraryView === "list" ? <SourceRow key={source.sourceId} {...presentation(source)} /> : <SourceCard key={source.sourceId} {...presentation(source)} />)}</div>}
        {busy && <p role="status">{busy}中…</p>}
      </section>
      {selected && inspectorOpen && <SourceInspector source={selected} page={page} presentation={presentation(selected)} docked={docked} onClose={closeInspector} />}
    </div>
  </main>;
}
