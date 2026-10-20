import { useEffect, useRef, useState, type DragEvent, type KeyboardEvent, type ReactNode } from "react";
import type { BlogArtifactName, BlogArtifactStatus, BlogRegenerationTarget, BlogStatus, LibrarySource, LibraryTopic, ReaderHost, ReadingWindow } from "@focus/reader-contracts";
import { matchesStatus, primaryAction, sourceStatus, statusFilters, type StatusFilter } from "./source-status";
import { LibraryEmpty, type EmptyKind } from "./LibraryEmpty";
import { IngestionRows, type IngestionRowsProps } from "./IngestionRows";
import { UNFILED } from "./topic-view";
import { TopicHead } from "./TopicHead";
import { SourceRow } from "./SourceRow";
import { SourceCard } from "./SourceCard";
import { SourceInspector } from "./SourceInspector";
import { SourceMenu } from "./SourceMenu";
import type { SourceViewProps } from "./SourceParts";

export type LibraryPageProps = Pick<IngestionRowsProps, "taskInbox" | "taskBatches" | "statusText" | "itemStatusText" | "continueInbox" | "controlBatch" | "onTasks"> & {
  scoped: readonly LibrarySource[]; statusFilter: StatusFilter; setStatusFilter: (filter: StatusFilter) => void; sourcesFailed: boolean; refresh: () => Promise<void>;
  sources: readonly LibrarySource[]; unfiledCount: number; sortingReason: string; reorderTopic: (topicId: string, sourceIds: readonly string[]) => Promise<boolean>;
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
  const { sources, unfiledCount, sortingReason, reorderTopic, dragging, setDragging, uploadDisabled, chooseUpload, selectedTopic, managementBusy, host, openManagement, topics, topic, filtered, libraryView, setLibraryView, query, setQuery, setTopic, loading, busy, active, view, preparationHidden, blogs, enterReading, refreshBlog, setMoreSource } = page;
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [inspectorOpen, setInspectorOpen] = useState(false);
  const [docked, setDocked] = useState(true);
  const root = useRef<HTMLElement>(null);
  const [preview, setPreview] = useState<readonly string[] | null>(null);
  const drag = useRef<{ id: string; over?: string; topicId: string; original: readonly string[]; order: readonly string[] } | null>(null);
  const submitting = useRef(false);
  const previewTopic = useRef<string | null>(null);
  const rows = preview && selectedTopic?.topicId === previewTopic.current ? [...filtered].sort((a, b) => preview.indexOf(a.sourceId) - preview.indexOf(b.sourceId)) : filtered;
  useEffect(() => { if (!submitting.current) { drag.current = null; setPreview(null); } }, [topic, query, libraryView, sortingReason, selectedTopic]);
  function startDrag(event: DragEvent, id: string) {
    event.stopPropagation();
    if (!selectedTopic || sortingReason || submitting.current) { event.preventDefault(); return; }
    event.dataTransfer.effectAllowed = "move"; event.dataTransfer.setData("text/plain", id);
    drag.current = { id, topicId: selectedTopic.topicId, original: selectedTopic.sourceIds, order: [...selectedTopic.sourceIds] };
    previewTopic.current = selectedTopic.topicId; setPreview(drag.current.order);
  }
  function previewDrag(event: DragEvent, id: string) {
    const current = drag.current;
    if (!current || sortingReason || submitting.current) return;
    event.preventDefault(); event.stopPropagation(); event.dataTransfer.dropEffect = "move";
    if (current.over === id) return;
    current.over = id;
    if (current.id === id) return;
    const order = [...current.order], from = order.indexOf(current.id), to = order.indexOf(id);
    if (from < 0 || to < 0) return;
    order.splice(from, 1); order.splice(to, 0, current.id); current.order = order; setPreview(order);
  }
  async function dropDrag(event: DragEvent) {
    const current = drag.current;
    if (!current) return;
    event.preventDefault(); event.stopPropagation(); drag.current = null;
    if (sortingReason || current.topicId !== selectedTopic?.topicId || current.order.every((id, i) => id === current.original[i])) { setPreview(null); return; }
    submitting.current = true;
    try { await reorderTopic(current.topicId, current.order); }
    finally { submitting.current = false; setPreview(null); }
  }
  function endDrag() { drag.current = null; if (!submitting.current) setPreview(null); }
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
    if (event.altKey && !event.ctrlKey && !event.metaKey && ["ArrowUp", "ArrowDown"].includes(event.key) && target.matches(".library-source-title")) {
      event.preventDefault();
      const id = target.closest<HTMLElement>("[data-source-id]")?.dataset.sourceId;
      if (id && selectedTopic && !sortingReason) { page.moveSource(id, event.key === "ArrowUp" ? -1 : 1); target.focus(); }
      return;
    }
    if (event.altKey || event.ctrlKey || event.metaKey || !["ArrowUp", "ArrowDown"].includes(event.key)) return;
    const id = target.closest<HTMLElement>("[data-source-id]")?.dataset.sourceId;
    if (!id) return;
    event.preventDefault();
    const index = rows.findIndex(source => source.sourceId === id), next = rows[Math.max(0, Math.min(rows.length - 1, index + (event.key === "ArrowDown" ? 1 : -1)))];
    if (next) { select(next.sourceId, inspectorOpen); document.getElementById(`source-title-${next.sourceId}`)?.focus(); }
  }
  function presentation(source: LibrarySource): SourceViewProps {
    const preparation = view?.preparations?.[source.sourceId], action = primaryAction(source, preparation, preparationHidden(source.sourceId), { busy, active, canOpen: !!host.openSource });
    return { source, status: sourceStatus(source, preparation, preparationHidden(source.sourceId)), action, blog: blogs[source.sourceId], topics, selected: selectedId === source.sourceId, expanded: inspectorOpen && selectedId === source.sourceId, candidate: !!(preparation?.candidate && preparation.ready), onSelect: () => select(source.sourceId), onTopic: setTopic, onPrimary: () => { if (!action.disabled) { if (action.kind === "inspect") select(source.sourceId); else void enterReading(source.sourceId); } }, menu: <SourceMenu source={source} page={page} /> };
  }
  const current = !topic && !query && page.statusFilter === "all" ? sources.find(source => source.sourceId === view?.source.sourceId && sourceStatus(source, view?.preparations?.[source.sourceId], preparationHidden(source.sourceId)).phase === "reading") : undefined;
  const cursor = view?.navigationCurrent ?? view?.current;
  const continuation = current && cursor && cursor.sourceId === current.sourceId && cursor.sectionPath.at(-1)?.trim() && Number.isInteger(cursor.index) && cursor.index > 0 && Number.isInteger(cursor.total) && cursor.total >= cursor.index ? { source: current, cursor, action: primaryAction(current, view?.preparations?.[current.sourceId], preparationHidden(current.sourceId), { busy, active, canOpen: !!host.openSource }) } : undefined;
  const emptyKind: EmptyKind | null = sources.length === 0 && page.sourcesFailed ? "offline" : sources.length === 0 ? "library" : filtered.length ? null : query ? "search" : page.statusFilter !== "all" ? "filter" : "topic";
  function emptyAction() { if (emptyKind === "offline") void page.refresh(); else if (emptyKind === "library") chooseUpload(); else if (emptyKind === "search") setQuery(""); else if (emptyKind === "filter") page.setStatusFilter("all"); else setTopic(""); }
  return <main ref={root} className="library-page" data-dragging={dragging} onKeyDown={keyboard} onKeyDownCapture={event => { if (event.key === "Escape" && page.moreSource) { event.stopPropagation(); setMoreSource(null); document.getElementById(`source-more-trigger-${page.moreSource}`)?.focus(); } }}
    onDragOver={event => { if (!event.dataTransfer.types?.includes("Files") && !event.dataTransfer.files?.length) return; event.preventDefault(); if (!uploadDisabled) setDragging(true); }}
    onDragLeave={event => { if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setDragging(false); }}
    onDrop={event => { if (!event.dataTransfer.types?.includes("Files") && !event.dataTransfer.files?.length) return; event.preventDefault(); setDragging(false); if (!uploadDisabled) chooseUpload(Array.from(event.dataTransfer.files)); }}>
    <div className="library-layout" data-inspector={!!selected && inspectorOpen}>
      <section className="library-sources" aria-label="材料列表">
        <div className="library-toolbar"><h2>{selectedTopic?.title ?? (topic === UNFILED ? "未归类" : "全部材料")}<small>{filtered.length}</small></h2><select className="library-topic-select" aria-label="筛选专题" value={topic} onChange={event => setTopic(event.target.value)}><option value="">全部材料</option>{topics.map(t => <option key={t.topicId} value={t.topicId}>{t.title}</option>)}{(unfiledCount > 0 || topic === UNFILED) && <option value={UNFILED}>未归类</option>}</select><div className="library-view-switch" role="group" aria-label="显示方式">{([["list", "列表"], ["cards", "卡片"]] as const).map(([mode, label]) => <button key={mode} aria-label={`${label}显示`} aria-pressed={libraryView === mode} onClick={() => { setLibraryView(mode); setMoreSource(null); try { localStorage.setItem("focus.libraryView", mode); } catch { /* The current view remains usable without storage. */ } }}>{label}</button>)}</div><input type="search" aria-label="搜索材料" placeholder="搜索标题" value={query} onChange={event => setQuery(event.target.value)} /></div>
        {selectedTopic && <TopicHead topic={selectedTopic} sources={sources} view={view} preparationHidden={preparationHidden} disabled={managementBusy || !host.manageTopic} reason={sortingReason} onRename={() => openManagement("rename", selectedTopic.topicId, selectedTopic.title)} onDelete={() => openManagement("delete", selectedTopic.topicId, selectedTopic.title)} />}
        {continuation && <section className="library-continue" aria-label="继续阅读"><button className="library-continue-text" aria-label={`查看 ${continuation.source.displayTitle || continuation.source.title} 详情`} onClick={() => select(continuation.source.sourceId)}><small>继续阅读</small><strong>{continuation.source.displayTitle || continuation.source.title}</strong><span>{continuation.cursor.sectionPath.at(-1)} · 第 {continuation.cursor.index} 段 / 共 {continuation.cursor.total} 段</span></button><button className="workspace-primary" disabled={continuation.action.disabled} title={continuation.action.title} onClick={() => void enterReading(continuation.source.sourceId)}>继续阅读</button></section>}
        <div className="library-filters" role="group" aria-label="按状态筛选">{statusFilters.map(([filter, label]) => { const count = page.scoped.filter(source => matchesStatus(sourceStatus(source, view?.preparations?.[source.sourceId], preparationHidden(source.sourceId)), filter, blogs[source.sourceId])).length; return <button key={filter} aria-pressed={page.statusFilter === filter} disabled={count === 0 && page.statusFilter !== filter} onClick={() => page.setStatusFilter(filter)}>{label}<span>{count}</span></button>; })}</div>
        <IngestionRows {...page} canContinue={!!host.continueIngestion} canControl={!!host.controlBatch} />
        {loading ? <p role="status" className="library-empty">读取中…</p> : emptyKind ? <LibraryEmpty kind={emptyKind} disabled={emptyKind === "library" && uploadDisabled} onAction={emptyAction} /> : <div className="library-source-list" data-view={libraryView} role="list" aria-label="来源">{rows.map(source => libraryView === "list" ? <SourceRow key={source.sourceId} {...presentation(source)} ordinal={selectedTopic ? selectedTopic.sourceIds.indexOf(source.sourceId) + 1 : undefined} sortingReason={sortingReason} onDragStart={event => startDrag(event, source.sourceId)} onDragOver={event => previewDrag(event, source.sourceId)} onDrop={event => void dropDrag(event)} onDragEnd={endDrag} /> : <SourceCard key={source.sourceId} {...presentation(source)} />)}</div>}
        {busy && <p role="status">{busy}中…</p>}
      </section>
      {selected && inspectorOpen && <SourceInspector source={selected} page={page} presentation={presentation(selected)} docked={docked} onClose={closeInspector} />}
    </div>
    {dragging && <div className="library-drop" role="status"><div><strong>松开即可上传</strong><span>PDF 由服务器选择 MinerU 解析；SingleFile HTML 本地解析{selectedTopic ? ` · 默认加入 #${selectedTopic.title}` : ""}</span></div></div>}
  </main>;
}
