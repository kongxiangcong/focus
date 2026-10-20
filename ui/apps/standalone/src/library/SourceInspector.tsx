import { useEffect, useRef } from "react";
import type { BlogArtifactStatus } from "@focus/reader-contracts";
import type { LibraryPageProps } from "./LibraryPage";
import { SourceKind, SourceMeta, SourcePrimary, SourceState, type SourceViewProps } from "./SourceParts";
import { SourceResetActions } from "./SourceMenu";

export function SourceInspector({ source: s, page, presentation, onClose, docked }: { source: SourceViewProps["source"]; page: LibraryPageProps; presentation: SourceViewProps; onClose: () => void; docked: boolean }) {
  const panel = useRef<HTMLElement>(null);
  const { host, busy, active, view, blogs, preparationHidden, preparationFailed, retryPreparation, activateCandidate, preparationNotice, managementBusy, openManagement, setBlogViewer, blogArtifacts, blogStatusText, blogRetryLabel, generateBlog, cancelBlog, regenerateBlog } = page;
  const blog = blogs[s.sourceId];
  useEffect(() => { if (!docked) panel.current?.focus({ preventScroll: true }); }, [docked, s.sourceId]);
  return <aside ref={panel} className="library-inspector" id={`source-details-${s.sourceId}`} role={docked ? "complementary" : "dialog"} aria-label="来源详情" tabIndex={-1} onKeyDown={event => { if (event.key === "Escape") { event.stopPropagation(); onClose(); } }}>
    <header className="library-inspector-head"><SourceKind source={s} /><button aria-label="关闭详情" onClick={onClose}>×</button></header>
    <div className="library-inspector-body"><h2>{s.displayTitle || s.title}</h2>{s.displayTitle && <p className="library-inspector-original">{s.title}</p>}
      <div className="library-inspector-primary"><SourceState {...presentation} bar={false} /><SourcePrimary {...presentation} solid />
        {view?.preparations?.[s.sourceId]?.candidate && view.preparations[s.sourceId].ready && <button className="workspace-primary" disabled={!!busy || active || !host.activateReadingCandidate || view.readingRevision === undefined} onClick={() => void activateCandidate(s.sourceId)}>打开新计划</button>}
        {preparationHidden(s.sourceId) && preparationFailed(s.sourceId) && view?.preparations?.[s.sourceId]?.selected_ready && <button disabled={!!busy || active || (!host.resumePreparation && !host.replanSource)} onClick={() => void retryPreparation(s.sourceId)}>准备阅读</button>}
      </div>
      {preparationNotice(s.sourceId)}{s.parseStatus !== "ready" && s.error && <p className="library-inspector-error">{s.error}</p>}
      <section className="library-inspector-section" aria-label="专题标签"><h3>专题</h3><SourceMeta source={{ ...s, venue: null, publishedAt: null }} topics={page.topics} onTopic={page.setTopic} /><button disabled={managementBusy || !host.saveSourceDetails} onClick={() => openManagement("source", s.sourceId, s.title)}>编辑</button></section>
      <section className="library-inspector-section library-blog" aria-label={`${s.title} 博客`}><h3>博客</h3>
        <ul className="blog-statuses">{blogArtifacts.map(([name, label]) => <li key={name} data-status={blog?.artifacts?.[name]?.status ?? "pending"}><span>{label}</span><small>{blogStatusText[(blog?.artifacts?.[name]?.status ?? "pending") as BlogArtifactStatus]}</small></li>)}</ul>
        {blog?.valueAnalysis.applicable === false && <p className="blog-note">架构价值分析不适用：{blog.valueAnalysis.reason}</p>}
        {blog?.error && <p className="blog-note" role="alert">{blog.error.message}</p>}
        <div className="blog-actions"><button disabled={!host.blogUrl || !blog?.generated || blog?.artifacts?.html?.status !== "completed"} onClick={() => setBlogViewer(s.sourceId)}>打开博客</button>
          {!blog?.generated ? <button disabled={!!busy || !host.generateBlog || s.parseStatus !== "ready"} onClick={() => void generateBlog(s.sourceId)}>生成博客</button> : <>
            {blog.runStatus === "running" && <button disabled={!!busy || !host.cancelBlog} onClick={() => void cancelBlog(s.sourceId)}>取消生成</button>}
            {blogArtifacts.filter(([name]) => blog.artifacts?.[name]?.status === "failed").map(([name]) => <button key={name} disabled={!!busy || blog.executing || !host.regenerateBlog} onClick={() => void regenerateBlog(s.sourceId, name)}>{blogRetryLabel[name]}</button>)}
            {blogArtifacts.every(([name]) => blog.artifacts?.[name]?.status !== "failed") && <button disabled={!!busy || blog.executing || !host.regenerateBlog} onClick={() => void regenerateBlog(s.sourceId, "all")}>重新生成</button>}
          </>}
        </div>
      </section>
      <section className="library-inspector-section"><h3>来源</h3><dl className="library-source-facts">{s.venue && <><dt>出处</dt><dd>{s.venue}</dd></>}{s.publishedAt && <><dt>日期</dt><dd>{s.publishedAt}</dd></>}<dt>笔记</dt><dd>{s.noteCount} 条</dd><dt>格式</dt><dd>{s.format ?? (s.kind === "paper" ? "PDF" : "HTML")}</dd><dt>Source ID</dt><dd><code>{s.sourceId}</code></dd></dl>
        <p className="library-parse-status">解析：{s.parseStatus === "ready" ? "已完成" : "失败"}{s.error ? ` · ${s.error}` : ""}</p>
        <div className="library-row-actions">{host.sourceOriginalUrl && <a href={host.sourceOriginalUrl(s.sourceId)} target="_blank" rel="noreferrer">原件</a>}{host.sourceContentUrl && <a href={host.sourceContentUrl(s.sourceId)} target="_blank" rel="noreferrer">正文</a>}<button disabled={managementBusy || !host.saveSourceDetails} onClick={() => openManagement("source", s.sourceId, s.title)}>编辑标题</button></div>
      </section>
      <section className="library-inspector-section" data-tone="danger"><h3>重置与删除</h3><div className="library-row-actions"><SourceResetActions source={s} actions={page} /></div></section>
    </div>
  </aside>;
}
