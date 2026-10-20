import type { ReactNode } from "react";
import { createReaderId, type BlogArtifactName, type BlogArtifactStatus, type BlogRegenerationTarget, type BlogStatus, type LibrarySource, type LibraryTopic, type ReaderHost, type ReadingWindow } from "@focus/reader-contracts";
import { sourceStatus } from "./source-status";

export type LibraryPageProps = {
  dragging: boolean; setDragging: (value: boolean) => void; uploadDisabled: boolean; chooseUpload: (files?: readonly File[]) => void;
  selectedTopic: LibraryTopic | undefined; managementBusy: boolean; host: ReaderHost;
  openManagement: (kind: "create" | "rename" | "delete" | "source", id?: string, title?: string) => void;
  topics: readonly LibraryTopic[]; topic: string; filtered: readonly LibrarySource[]; libraryView: "cards" | "list";
  setLibraryView: (value: "cards" | "list") => void; query: string; setQuery: (value: string) => void; setTopic: (value: string) => void; loading: boolean;
  readingStatus: (source: LibrarySource) => "unplanned" | "ready" | "reading" | "completed"; view: ReadingWindow | null;
  preparationHidden: (id: string) => boolean; blogs: Readonly<Record<string, BlogStatus>>; setBlogViewer: (id: string) => void;
  busy: string; active: boolean; enterReading: (id: string) => Promise<void>; preparationFailed: (id: string) => boolean; retryPreparation: (id: string) => Promise<void>;
  expandedSources: ReadonlySet<string>; toggleDetails: (id: string) => void; moreSource: string | null; setMoreSource: (id: string | null) => void;
  moveSource: (id: string, offset: number) => void; setConfirm: (value: { source: LibrarySource; action: "delete" | "reread" | "replan" | "clear"; requestId?: string } | null) => void;
  confirmDelete: (source: LibrarySource) => Promise<void>; preparationNotice: (id: string) => ReactNode; activateCandidate: (id: string) => Promise<void>;
  blogArtifacts: readonly [BlogArtifactName, string][]; blogStatusText: Record<BlogArtifactStatus, string>; blogRetryLabel: Record<BlogArtifactName, string>;
  generateBlog: (id: string) => Promise<void>; cancelBlog: (id: string) => Promise<void>; regenerateBlog: (id: string, target: BlogRegenerationTarget) => Promise<void>;
};

export function LibraryPage({ dragging, setDragging, uploadDisabled, chooseUpload, selectedTopic, managementBusy, host, openManagement, topics, topic, filtered, libraryView, setLibraryView, query, setQuery, setTopic, loading, readingStatus, view, preparationHidden, blogs, setBlogViewer, busy, active, enterReading, preparationFailed, retryPreparation, expandedSources, toggleDetails, moreSource, setMoreSource, moveSource, setConfirm, confirmDelete, preparationNotice, activateCandidate, blogArtifacts, blogStatusText, generateBlog, cancelBlog, regenerateBlog, blogRetryLabel }: LibraryPageProps) {
  return <main className="library-page" data-dragging={dragging}
      onDragOver={e => { e.preventDefault(); if (!uploadDisabled) setDragging(true); }}
      onDragLeave={e => { if (!e.currentTarget.contains(e.relatedTarget as Node | null)) setDragging(false); }}
      onDrop={e => { e.preventDefault(); setDragging(false); if (!uploadDisabled) chooseUpload(Array.from(e.dataTransfer.files)); }}>
      <div className="library-layout">
        <section className="library-sources" aria-label="材料列表">{selectedTopic && <div>
          <button disabled={managementBusy || !host.manageTopic} onClick={() => openManagement("rename", selectedTopic.topicId, selectedTopic.title)}>重命名专题</button>
          <button disabled={managementBusy || !host.manageTopic} onClick={() => openManagement("delete", selectedTopic.topicId, selectedTopic.title)}>删除专题</button>
        </div>}<div className="library-toolbar"><h2>{topics.find(t => t.topicId === topic)?.title ?? "全部材料"}<small>{filtered.length}</small></h2><div className="library-view-switch" role="group" aria-label="显示方式">{([["cards", "卡片显示"], ["list", "列表显示"]] as const).map(([mode, label]) => <button key={mode} aria-pressed={libraryView === mode} onClick={() => { setLibraryView(mode); try { localStorage.setItem("focus.libraryView", mode); } catch { /* The current view remains usable without storage. */ } }}>{label}</button>)}</div><input type="search" aria-label="搜索材料" placeholder="搜索标题" value={query} onChange={e => setQuery(e.target.value)} /></div>
          {loading ? <p role="status" className="library-empty">读取中…</p> : filtered.length === 0 ? <div className="library-empty"><span aria-hidden="true">▤</span><p>{query || topic ? "暂无匹配材料" : "放入第一份材料"}</p><button className="workspace-primary" disabled={uploadDisabled} onClick={() => { if (query || topic) { setQuery(""); setTopic(""); } else chooseUpload(); }}>{query || topic ? "重置" : "上传"}</button></div> : <div className="library-cards" data-view={libraryView}>{filtered.map(s => <article className="library-card" data-reading-status={readingStatus(s)} data-status={s.parseStatus !== "ready" ? "failed" : readingStatus(s) === "completed" ? "completed" : s.progress.completed > 0 ? "reading" : "unread"} key={s.sourceId}>
            <div className="library-overview">
              <h3 title={s.title}>{s.displayTitle || s.title}</h3>
              <p className="library-summary">{sourceStatus(s, view?.preparations?.[s.sourceId], preparationHidden(s.sourceId)).label}</p>
              <div className="library-progress"><progress aria-label={`${s.title} 阅读进度`} value={s.progress.completed} max={s.progress.total || 1} /><span>{s.progress.completed} / {s.progress.total}</span></div>
            </div>
            <div className="library-card-actions">
              <button disabled={!host.blogUrl || !blogs[s.sourceId]?.generated || blogs[s.sourceId]?.artifacts?.html?.status !== "completed"} onClick={() => setBlogViewer(s.sourceId)}>打开博客</button>
              <button title={active ? "请先完成或停止当前问答" : busy ? `${busy}中` : undefined} disabled={!!busy || active || !host.openSource || s.parseStatus !== "ready" || (view?.preparations?.[s.sourceId]?.status === "running" && !view.preparations[s.sourceId].selected_ready)} onClick={() => void enterReading(s.sourceId)}>{view?.preparations?.[s.sourceId]?.status === "running" && !view.preparations[s.sourceId].selected_ready ? "阅读准备中…" : preparationFailed(s.sourceId) && !view?.preparations?.[s.sourceId]?.selected_ready ? preparationHidden(s.sourceId) ? "准备阅读" : "重试准备" : readingStatus(s) === "completed" ? "查看已读" : s.progress.completed > 0 ? "继续阅读" : view?.preparations?.[s.sourceId]?.selected_ready || view?.preparations?.[s.sourceId]?.ready ? "开始阅读" : "准备阅读"}</button>
              {preparationHidden(s.sourceId) && preparationFailed(s.sourceId) && view?.preparations?.[s.sourceId]?.selected_ready && <button disabled={!!busy || active || (!host.resumePreparation && !host.replanSource)} onClick={() => void retryPreparation(s.sourceId)}>准备阅读</button>}
              <button aria-expanded={expandedSources.has(s.sourceId)} aria-controls={`source-details-${s.sourceId}`} onClick={() => toggleDetails(s.sourceId)}>详细</button>
              <button aria-expanded={moreSource === s.sourceId} aria-controls={`source-more-${s.sourceId}`} onClick={() => setMoreSource(moreSource === s.sourceId ? null : s.sourceId)}>更多</button>
            </div>
            {moreSource === s.sourceId && <div className="library-more-menu" id={`source-more-${s.sourceId}`} data-more-source={s.sourceId} role="group" aria-label="更多操作"
              onKeyDown={event => { if (event.key === "Escape") { setMoreSource(null); } }}
              onClick={event => { if ((event.target as HTMLElement).closest("button")) setMoreSource(null); }}>
              <button disabled={managementBusy || !host.saveSourceDetails} onClick={() => openManagement("source", s.sourceId, s.title)}>管理来源</button>
              {selectedTopic && <button aria-label={`${s.title} 上移`} disabled={managementBusy || selectedTopic.sourceIds.indexOf(s.sourceId) === 0} onClick={() => moveSource(s.sourceId, -1)}>上移</button>}
              {selectedTopic && <button aria-label={`${s.title} 下移`} disabled={managementBusy || selectedTopic.sourceIds.indexOf(s.sourceId) === selectedTopic.sourceIds.length - 1} onClick={() => moveSource(s.sourceId, 1)}>下移</button>}
              <button disabled={!!busy || active || !host.replanSource || s.parseStatus !== "ready"} onClick={() => setConfirm({ source: s, action: "replan" })}>重新规划</button>
              <button disabled={!!busy || !host.clearSource || view?.clearBusySources?.includes(s.sourceId)} onClick={() => setConfirm({ source: s, action: "clear", requestId: createReaderId() })}>重新阅读</button>
              <button className="library-more-danger" disabled={managementBusy || !host.deleteSource || !host.deletionImpact} onClick={() => void confirmDelete(s)}>删除</button>
            </div>}

            {expandedSources.has(s.sourceId) && <div className="library-details" id={`source-details-${s.sourceId}`}>
            {preparationNotice(s.sourceId)}
            <p className="library-parse-status">解析：{s.parseStatus === "ready" ? "已完成" : "失败"}{s.error ? ` · ${s.error}` : ""}</p>
            <div className="library-card-top"><span className="source-badge">{s.format ?? (s.kind === "paper" ? "PDF" : "HTML")}</span>{s.parseStatus !== "ready" && <span title={s.error ?? undefined}>需检查</span>}</div>
            <p className="library-metadata" title={s.title}>{[s.publishedAt, s.venue].filter(Boolean).join(" · ")}</p>
            <div className="library-card-bottom"><small>{sourceStatus(s, view?.preparations?.[s.sourceId], preparationHidden(s.sourceId)).label}</small><div className="library-row-actions">{host.sourceOriginalUrl && <a href={host.sourceOriginalUrl(s.sourceId)} target="_blank" rel="noreferrer">原件</a>}{host.sourceContentUrl && <a href={host.sourceContentUrl(s.sourceId)} target="_blank" rel="noreferrer">正文</a>}</div></div>
            {view?.preparations?.[s.sourceId]?.candidate && view.preparations[s.sourceId].ready && <button className="workspace-primary" disabled={!!busy || active || !host.activateReadingCandidate || view.readingRevision === undefined} onClick={() => void activateCandidate(s.sourceId)}>打开新计划</button>}
            <div className="library-tags" aria-label="专题标签"><span>属于专题：{s.topicIds.length === 0 ? "未分类" : ""}</span>{s.topicIds.map(id => <button key={id} onClick={() => setTopic(id)}>{topics.find(t => t.topicId === id)?.title ?? id}</button>)}</div>
            <section className="library-blog" aria-label={`${s.title} 博客`}>
              {!blogs[s.sourceId]?.generated ? <button disabled={!!busy || !host.generateBlog || s.parseStatus !== "ready"} onClick={() => void generateBlog(s.sourceId)}>生成博客</button> : <>
                <ul className="blog-statuses">{blogArtifacts.map(([name, label]) => <li key={name} data-status={blogs[s.sourceId].artifacts?.[name]?.status ?? "pending"}><span>{label}</span><small>{blogStatusText[(blogs[s.sourceId].artifacts?.[name]?.status ?? "pending") as BlogArtifactStatus]}</small></li>)}</ul>
                {blogs[s.sourceId].valueAnalysis.applicable === false && <p className="blog-note">架构价值分析不适用：{blogs[s.sourceId].valueAnalysis.reason}</p>}
                {blogs[s.sourceId].error && <p className="blog-note" role="alert">{blogs[s.sourceId].error?.message}</p>}
                <div className="blog-actions">
                  {blogs[s.sourceId].runStatus === "running" && <button disabled={!!busy || !host.cancelBlog} onClick={() => void cancelBlog(s.sourceId)}>取消生成</button>}
                  {blogArtifacts.filter(([name]) => blogs[s.sourceId].artifacts?.[name]?.status === "failed").map(([name]) => <button key={name} disabled={!!busy || blogs[s.sourceId]?.executing || !host.regenerateBlog} onClick={() => void regenerateBlog(s.sourceId, name)}>{blogRetryLabel[name]}</button>)}
                  {blogArtifacts.every(([name]) => blogs[s.sourceId].artifacts?.[name]?.status !== "failed") && <button disabled={!!busy || blogs[s.sourceId]?.executing || !host.regenerateBlog} onClick={() => void regenerateBlog(s.sourceId, "all")}>重新生成</button>}
                </div>
              </>}
            </section>
            </div>}
          </article>)}</div>}
        </section></div>
      {busy && <p role="status">{busy}中…</p>}
    </main>;
}
