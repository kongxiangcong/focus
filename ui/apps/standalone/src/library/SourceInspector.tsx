import { useEffect, useLayoutEffect, useRef, useState } from "react";
import type { BlogArtifactStatus } from "@focus/reader-contracts";
import type { LibraryPageProps } from "./LibraryPage";
import { SourceKind, SourceMeta, SourcePrimary, SourceState, type SourceViewProps } from "./SourceParts";
import { SourceResetActions } from "./SourceMenu";

export function SourceInspector({ source: s, page, presentation, onClose, docked, open }: { source: SourceViewProps["source"]; page: LibraryPageProps; presentation: SourceViewProps; onClose: () => void; docked: boolean; open: boolean }) {
  const panel = useRef<HTMLElement>(null);
  const { host, busy, active, view, blogs, preparationHidden, preparationFailed, retryPreparation, activateCandidate, preparationNotice, managementBusy, openManagement, setBlogViewer, blogArtifacts, blogStatusText, blogRetryLabel, generateBlog, cancelBlog, regenerateBlog } = page;
  const blog = blogs[s.sourceId];
  const [mobile, setMobile] = useState(() => !!globalThis.matchMedia?.("(max-width: 760px)").matches);
  useEffect(() => { const media = globalThis.matchMedia?.("(max-width: 760px)"); if (!media) return; const update = () => setMobile(media.matches); update(); media.addEventListener?.("change", update); return () => media.removeEventListener?.("change", update); }, []);
  useLayoutEffect(() => {
    if (!open) return;
    if (!docked || mobile) panel.current?.focus({ preventScroll: true });
    if (!mobile) return;
    const app = panel.current?.closest(".workspace-app");
    const background = Array.from(app?.querySelectorAll<HTMLElement>(".workspace-nav, .workspace-header, .workspace-reading, .library-sources") ?? []);
    const prior = background.map(node => node.hasAttribute("inert")); background.forEach(node => node.setAttribute("inert", ""));
    const contain = (event: FocusEvent) => { if (document.querySelector("dialog[open]") || panel.current?.contains(event.target as Node)) return; panel.current?.focus({ preventScroll: true }); };
    document.addEventListener("focusin", contain);
    return () => { background.forEach((node, index) => { if (!prior[index]) node.removeAttribute("inert"); }); document.removeEventListener("focusin", contain); };
  }, [open, docked, mobile, s.sourceId]);
  return <><div className="library-inspector-backdrop" data-open={open && mobile} aria-hidden="true" onClick={onClose} /><aside ref={panel} className="library-inspector" data-open={open} aria-hidden={!open} inert={!open} id={`source-details-${s.sourceId}`} role={docked && !mobile ? "complementary" : "dialog"} aria-modal={open && mobile ? true : undefined} aria-label="来源详情" tabIndex={-1} onKeyDown={event => {
    if (event.key === "Escape") { event.stopPropagation(); onClose(); }
    if (event.key !== "Tab" || !mobile || !open || document.querySelector("dialog[open]")) return;
    const controls = Array.from(panel.current?.querySelectorAll<HTMLElement>("button:not(:disabled), a[href], input:not(:disabled), select:not(:disabled), textarea:not(:disabled), [tabindex='0']") ?? []).filter(node => !node.closest("[inert], [hidden]"));
    const first = controls[0], last = controls.at(-1), active = document.activeElement;
    if (event.shiftKey && (active === first || active === panel.current)) { event.preventDefault(); (last ?? panel.current)?.focus(); }
    else if (!event.shiftKey && (active === last || active === panel.current)) { event.preventDefault(); (first ?? panel.current)?.focus(); }
  }}>

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
  </aside></>;
}
