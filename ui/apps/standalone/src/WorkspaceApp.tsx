import { type CSSProperties, useEffect, useRef, useState } from "react";
import { createReaderId, type BlogArtifactName, type BlogArtifactStatus, type BlogRegenerationTarget, type BlogStatus, type IngestionItem, type LibrarySource, type LibraryTopic, type ReaderHost, type ReaderHostResult, type ReadingWindow } from "@focus/reader-contracts";
import { FocusReader, TaskProgress } from "@focus/reader-ui";

type Route = "/library" | "/reading" | "/settings";
type FontSize = "small" | "standard" | "large" | "extra";
const fontOptions: [FontSize, string][] = [["small", "紧凑"], ["standard", "标准"], ["large", "较大"], ["extra", "特大"]];
function readFont(): FontSize {
  try { const value = localStorage.getItem("focus.fontSize"); return fontOptions.some(([key]) => key === value) ? value as FontSize : "standard"; }
  catch { return "standard"; }
}
function routeFromLocation(): Route { return ["/library", "/reading", "/settings"].includes(location.pathname) ? location.pathname as Route : "/library"; }

function readingStatus(source: LibrarySource) {
  return source.readingStatus ?? (source.progress.planId && source.progress.chunkId === null ? "completed" : source.progress.completed ? "reading" : source.progress.planId ? "ready" : "unplanned");
}

const blogArtifacts: readonly [BlogArtifactName, string][] = [["value_analysis", "价值分析"], ["reading_blog", "带读博客"], ["html", "HTML"]];
const blogStatusText: Record<BlogArtifactStatus, string> = {
  pending: "待生成", generating: "生成中", completed: "已完成", failed: "失败", not_applicable: "不适用",
};
/** Retry is named by granularity: only the failed document is re-run. */
const blogRetryLabel: Record<BlogArtifactName, string> = {
  value_analysis: "重新生成价值分析", reading_blog: "重新生成带读博客", html: "重新生成 HTML",
};

export function WorkspaceApp({ host }: { host: ReaderHost }) {
  const [route, setRoute] = useState<Route>(routeFromLocation);
  const [fontSize, setFontSize] = useState<FontSize>(readFont);
  const [brightness, setBrightness] = useState(() => { try { return Math.max(85, Math.min(110, Number(localStorage.getItem("focus.brightness") ?? 100) || 100)); } catch { return 100; } });
  const [dragging, setDragging] = useState(false);
  const [view, setView] = useState<ReadingWindow | null>(null);
  const [sources, setSources] = useState<readonly LibrarySource[]>([]);
  const [topics, setTopics] = useState<readonly LibraryTopic[]>([]);
  const [inbox, setInbox] = useState<readonly IngestionItem[]>([]);
  const [topic, setTopic] = useState("");
  const [query, setQuery] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState("");
  const [confirm, setConfirm] = useState<{ source: LibrarySource; action: "delete" | "reread" | "replan" } | null>(null);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [uploadTopic, setUploadTopic] = useState("");
  const [blogs, setBlogs] = useState<Readonly<Record<string, BlogStatus>>>({});
  const [generateBlogs, setGenerateBlogs] = useState(false);
  const [blogViewer, setBlogViewer] = useState("");
  const uploadDialog = useRef<HTMLDialogElement>(null);
  const confirmation = useRef<HTMLDialogElement>(null);
  const locked = useRef(false);
  const requestVersion = useRef(0);
  const active = !!view?.agent?.run && ["running", "approval", "stopping"].includes(view.agent.run.status);

  function navigate(next: Route) { history.pushState(null, "", next); setRoute(next); setError(""); }
  async function refresh() {
    if (!host.listSources || !host.listTopics) { setLoading(false); return; }
    const version = ++requestVersion.current;
    try {
      const [sourceResult, topicResult, inboxResult] = await Promise.all([host.listSources(), host.listTopics(), host.listInbox?.()]);
      if (version !== requestVersion.current) return;
      if (sourceResult.ok) {
        setSources(sourceResult.value);
        if (host.blogStatus) {
          const statuses = await Promise.all(sourceResult.value.map(source => host.blogStatus!(source.sourceId)));
          if (version !== requestVersion.current) return;
          setBlogs(Object.fromEntries(statuses.filter(result => result.ok).map(result => [result.value.sourceId, result.value])));
        }
      } else setError(sourceResult.error.message);
      if (topicResult.ok) setTopics(topicResult.value); else setError(topicResult.error.message);
      if (inboxResult) { if (inboxResult.ok) setInbox(inboxResult.value); else setError(inboxResult.error.message); }
    } catch (e) { if (version === requestVersion.current) setError(String(e)); }
    finally { if (version === requestVersion.current) setLoading(false); }
  }
  useEffect(() => {
    if (location.pathname !== routeFromLocation()) history.replaceState(null, "", "/library");
    const pop = () => setRoute(routeFromLocation()); window.addEventListener("popstate", pop);
    let alive = true;
    const accept = (result: ReaderHostResult<ReadingWindow>) => {
      if (!alive) return;
      if (result.ok) setView(old => old?.revision !== undefined && result.value.revision !== undefined && old.revision > result.value.revision ? old : result.value);
      else setError(result.error.message);
    };
    void host.getReadingWindow().then(accept);
    const unsubscribe = host.subscribe?.(accept);
    return () => { alive = false; unsubscribe?.(); window.removeEventListener("popstate", pop); requestVersion.current++; };
  }, [host]);
  useEffect(() => { if (route !== "/settings") void refresh(); }, [route, view?.agent?.run?.status, host]);
  useEffect(() => {
    if (!inbox.some(item => item.status === "processing")) return;
    const timer = window.setInterval(() => void refresh(), 1200);
    return () => window.clearInterval(timer);
  }, [inbox, host]);
  useEffect(() => { if (confirm) confirmation.current?.showModal(); else confirmation.current?.close(); }, [confirm]);
  useEffect(() => { if (view?.blog) setBlogs(view.blog); }, [view?.blog]);
  useEffect(() => {
    const running = Object.values(blogs).filter(blog => blog.runStatus === "running").map(blog => blog.sourceId);
    if (running.length === 0 || !host.blogStatus) return;
    const timer = window.setInterval(() => running.forEach(id => void refreshBlog(id)), 1500);
    return () => window.clearInterval(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [blogs, host]);

  useEffect(() => { if (uploadOpen) uploadDialog.current?.showModal(); else uploadDialog.current?.close(); }, [uploadOpen]);

  async function operate(label: string, operation: () => Promise<ReaderHostResult<ReadingWindow>>, read = false) {
    if (locked.current || active) return;
    locked.current = true; setBusy(label); setError("");
    try {
      const result = await operation();
      if (!result.ok) { setError(result.error.message); return; }
      setView(result.value); setConfirm(null);
      if (read) navigate("/reading");
      if (label === "上传") { setUploadOpen(false); setSelectedFile(null); }
      await refresh();
    } catch (e) { setError(String(e)); }
    finally { locked.current = false; setBusy(""); }
  }
  function replaceInbox(item: IngestionItem) { setInbox(current => [item, ...current.filter(existing => existing.itemId !== item.itemId)]); }
  async function ingest(label: string, operation: () => Promise<ReaderHostResult<IngestionItem>>, closeUpload = false) {
    if (locked.current) return;
    locked.current = true; setBusy(label); setError(""); setNotice("");
    try {
      const result = await operation();
      if (!result.ok) { setError(result.error.message); return; }
      replaceInbox(result.value);
      if (result.value.duplicate) setNotice("该原件已有未完成任务，已回到原任务；不会重复解析。");
      if (closeUpload) { setUploadOpen(false); setSelectedFile(null); }
    } catch (e) { setError(String(e)); }
    finally { locked.current = false; setBusy(""); }
  }
  async function refreshBlog(sourceId: string) {
    if (!host.blogStatus) return;
    const result = await host.blogStatus(sourceId);
    if (result.ok) setBlogs(current => ({ ...current, [sourceId]: result.value }));
  }
  async function blogAction(sourceId: string, operation: () => Promise<ReaderHostResult<BlogStatus>>) {
    setError("");
    const result = await operation();
    if (!result.ok) { setError(result.error.message); return; }
    setBlogs(current => ({ ...current, [sourceId]: result.value }));
  }
  async function generateBlog(sourceId: string) {
    if (!host.generateBlog) return;
    setBusy("生成博客");
    try { await blogAction(sourceId, () => host.generateBlog!(sourceId, createReaderId())); }
    finally { setBusy(""); }
  }
  async function regenerateBlog(sourceId: string, artifact: BlogRegenerationTarget) {
    if (!host.regenerateBlog) return;
    setBusy(artifact === "all" ? "重新生成" : blogRetryLabel[artifact]);
    try { await blogAction(sourceId, () => host.regenerateBlog!(sourceId, createReaderId(), artifact)); }
    finally { setBusy(""); }
  }
  async function cancelBlog(sourceId: string) {
    if (!host.cancelBlog) return;
    setBusy("取消博客生成");
    try { await blogAction(sourceId, () => host.cancelBlog!(sourceId)); }
    finally { setBusy(""); }
  }
  async function confirmAndStart(item: IngestionItem) {
    if (!host.confirmIngestion || !host.processIngestion || locked.current) return;
    locked.current = true; setBusy("确认"); setError(""); setNotice("");
    try {
      const confirmed = await host.confirmIngestion(item.itemId, generateBlogs);
      if (!confirmed.ok) { setError(confirmed.error.message); return; }
      replaceInbox(confirmed.value); setBusy("入库");
      const started = await host.processIngestion(item.itemId, createReaderId());
      if (!started.ok) { setError(started.error.message); return; }
      replaceInbox(started.value);
    } catch (e) { setError(String(e)); }
    finally { locked.current = false; setBusy(""); }
  }
  const filtered = sources.filter(s => (!topic || s.topicIds.includes(topic)) && (s.title + " " + (s.shortName ?? "")).toLowerCase().includes(query.toLowerCase()));
  function chooseUpload(selected?: File) {
    if (selected && !/\.pdf$/i.test(selected.name)) { setError("请选择 PDF"); return; }
    setSelectedFile(selected ?? null);
    setUploadTopic(topics.find(t => t.topicId === topic)?.title ?? "");
    setError(""); setUploadOpen(true);
  }
  const uploadDisabled = !!busy || active || !host.stageIngestion;
  const statusText: Record<IngestionItem["status"], string> = {
    awaiting_confirmation: "待确认", confirmed: "已确认，等待开始", processing: "处理中", status_check_required: "远端状态待核对",
    retry_waiting: "等待继续", failed: "处理失败，可继续", commit_conflict: "提交冲突，可继续", topic_attachment_pending: "文档已入库，专题关联待恢复",
    cancelled: "已取消，可继续", interrupted: "处理曾中断，可继续", completed: "入库完成",
  };
  const resumableStatuses: readonly IngestionItem["status"][] = ["retry_waiting", "failed", "commit_conflict", "topic_attachment_pending", "cancelled", "interrupted"];
  return <div className="workspace-app" style={{ "--reader-brightness": brightness / 100 } as CSSProperties}>
    <header className="workspace-nav">
      <a className="workspace-logo" href="/library" onClick={e => { e.preventDefault(); navigate("/library"); }}>focus<span>.</span></a>
      <nav aria-label="应用导航">{([["/library", "知识库", "▤"], ["/reading", "阅读", "☷"], ["/settings", "设置", "☼"]] as const).map(([path, title, icon]) =>
        <a key={path} href={path} aria-current={route === path ? "page" : undefined} onClick={e => { e.preventDefault(); navigate(path); }}><span aria-hidden="true">{icon}</span>{title}</a>)}</nav>
    </header>
    {!uploadOpen && error && <div className="workspace-error" role="alert">{error}<button onClick={() => { setError(""); void refresh(); }}>重试</button></div>}
    {notice && <div className="workspace-notice" role="status">{notice}<button onClick={() => setNotice("")}>知道了</button></div>}
    <div className="workspace-reading" hidden={route !== "/reading"}>
      <div className="reading-library-picker"><select aria-label="阅读专题" value={topic} onChange={e => setTopic(e.target.value)}><option value="">全部专题</option>{topics.map(t => <option key={t.topicId} value={t.topicId}>{t.title}</option>)}</select><select aria-label="选择阅读材料" value={sources.some(s => s.sourceId === view?.source.sourceId && (!topic || s.topicIds.includes(topic))) ? view?.source.sourceId : ""} disabled={!!busy || active} onChange={e => { if (e.target.value && host.openSource) void operate("打开", () => host.openSource!(e.target.value)); }}><option value="">选择材料</option>{sources.filter(s => !topic || s.topicIds.includes(topic)).map(s => <option key={s.sourceId} value={s.sourceId}>{s.shortName || s.title}</option>)}</select></div>
      <FocusReader host={host} appearance="mist" fontSize={fontSize} visible={route === "/reading"} /></div>
    {route === "/library" && <main className="library-page" data-dragging={dragging}
      onDragOver={e => { e.preventDefault(); if (!uploadDisabled) setDragging(true); }}
      onDragLeave={e => { if (!e.currentTarget.contains(e.relatedTarget as Node | null)) setDragging(false); }}
      onDrop={e => { e.preventDefault(); setDragging(false); if (!uploadDisabled) chooseUpload(e.dataTransfer.files[0]); }}>
      <div className="page-heading"><h1>知识库</h1>
        <button className="workspace-primary" disabled={uploadDisabled} onClick={() => chooseUpload()}>上传</button>
      </div>
      {view?.agent?.run && <div className="library-run"><TaskProgress run={view.agent.run} /><button onClick={() => navigate("/reading")}>查看</button></div>}
      {inbox.length > 0 && <section className="library-inbox" aria-label="Inbox"><div className="library-inbox-heading"><h2>Inbox</h2><button disabled={!!busy} onClick={() => void refresh()}>刷新状态</button></div>{inbox.map(item => <article key={item.itemId} className="library-inbox-item" data-status={item.status}>
        <div><strong>{item.fileName}</strong><span>{statusText[item.status]}</span><small>{item.topicTitle ?? topics.find(t => t.topicId === item.topicId)?.title ?? "不关联专题"}</small></div>
        {item.status === "awaiting_confirmation" && <div className="inbox-confirmation"><p>将调用 {(item.services ?? item.confirmation?.services ?? ["mineru"]).map(service => service === "mineru" ? "MinerU" : service).join("、")} 处理此 PDF，仅用于建立 Source 并关联专题；不会创建翻译或阅读计划，也不做 AI 内容审核。</p>
          <label className="inbox-blog-option"><input type="checkbox" checked={generateBlogs} onChange={e => setGenerateBlogs(e.target.checked)} />同时生成博客（入库完成后自动接续带读博客，架构类论文另生成价值分析）</label>
          <button className="workspace-primary" disabled={!!busy} onClick={() => void confirmAndStart(item)}>确认并开始</button></div>}
        {item.status === "processing" && <button disabled={!!busy || !host.cancelIngestion} onClick={() => host.cancelIngestion && void ingest("取消", () => host.cancelIngestion!(item.itemId))}>取消</button>}
        {(item.status === "status_check_required" || (item.status === "cancelled" && item.resubmitRisk)) && <div className="inbox-confirmation inbox-resubmission">
          <p>上次提交结果未知，重新提交可能重复解析。</p>
          <div className="inbox-resubmission-actions">
            {item.remoteReference && <button disabled={!!busy || !host.continueIngestion} onClick={() => host.continueIngestion && void ingest("查询", () => host.continueIngestion!(item.itemId, createReaderId()))}>查询并续接原任务</button>}
            <button className="workspace-primary" disabled={!!busy || !host.resubmitIngestion || !item.resubmitRisk} onClick={() => host.resubmitIngestion && item.resubmitRisk && void ingest("重新提交", () => host.resubmitIngestion!(item.itemId, createReaderId(), item.resubmitRisk!.choiceId))}>重新提交</button>
          </div>
        </div>}
        {["retry_waiting", "failed", "commit_conflict", "topic_attachment_pending", "interrupted"].includes(item.status) && <button disabled={!!busy || !host.continueIngestion} onClick={() => host.continueIngestion && void ingest("继续", () => host.continueIngestion!(item.itemId, createReaderId()))}>继续</button>}
        {item.status === "cancelled" && !item.resubmitRisk && <button disabled={!!busy || !host.continueIngestion} onClick={() => host.continueIngestion && void ingest("继续", () => host.continueIngestion!(item.itemId, createReaderId()))}>继续</button>}
        {["status_check_required", ...resumableStatuses].includes(item.status) && <button disabled={!!busy || !host.confirmIngestion || !host.processIngestion} onClick={() => void confirmAndStart(item)}>重新确认并开始</button>}
        {item.sourceId && <div className="inbox-links">{host.sourceOriginalUrl && <a href={host.sourceOriginalUrl(item.sourceId)} target="_blank" rel="noreferrer">PDF 原件</a>}{host.sourceContentUrl && <a href={host.sourceContentUrl(item.sourceId)} target="_blank" rel="noreferrer">正文</a>}</div>}
        {(item.error || item.topicError) && <p className="inbox-error">{item.topicError?.message ?? item.error?.message}</p>}
      </article>)}</section>}
      <div className="library-layout"><aside className="library-topics" aria-label="专题"><h2>专题</h2><button aria-pressed={!topic} onClick={() => setTopic("")}>全部 <span>{sources.length}</span></button>{topics.map(t => <button key={t.topicId} aria-pressed={topic === t.topicId} onClick={() => setTopic(t.topicId)}>{t.title}<span>{t.sourceIds.length}</span></button>)}</aside>
        <section className="library-sources" aria-label="材料列表"><div className="library-toolbar"><h2>{topics.find(t => t.topicId === topic)?.title ?? "全部材料"}<small>{filtered.length}</small></h2><input type="search" aria-label="搜索材料" placeholder="搜索标题" value={query} onChange={e => setQuery(e.target.value)} /></div>
          {loading ? <p role="status" className="library-empty">读取中…</p> : filtered.length === 0 ? <div className="library-empty"><span aria-hidden="true">▤</span><p>{query || topic ? "暂无匹配材料" : "放入第一份材料"}</p><button className="workspace-primary" disabled={uploadDisabled} onClick={() => { if (query || topic) { setQuery(""); setTopic(""); } else chooseUpload(); }}>{query || topic ? "重置" : "上传"}</button></div> : <div className="library-cards">{filtered.map(s => <article className="library-card" data-reading-status={readingStatus(s)} key={s.sourceId}>
            <div className="library-card-top"><span className="source-badge">{s.format ?? (s.kind === "paper" ? "PDF" : "HTML")}</span>{s.parseStatus !== "ready" && <span title={s.error ?? undefined}>需检查</span>}</div>
            <h3><button className="library-title" disabled={!!busy || active || !host.openSource || s.parseStatus !== "ready"} onClick={() => void operate("打开", () => host.openSource!(s.sourceId), true)}>{s.shortName || s.title}</button></h3>
            <p className="library-metadata" title={s.title}>{[s.publishedAt, s.venue].filter(Boolean).join(" · ")}</p>
            <div className="library-progress"><progress aria-label={`${s.title} 阅读进度`} value={s.progress.completed} max={s.progress.total || 1} /><span>{s.progress.completed} / {s.progress.total}</span></div>
            <p className="library-metadata">{s.preparation && (s.preparation.ready ? "阅读已准备好" : `准备阅读 ${s.preparation.completed}/${s.preparation.total} · 点击阅读继续准备`)}</p>
            <div className="library-card-bottom"><small>{({ ready: "待阅读", reading: "阅读中", completed: "已读完", unplanned: "待规划" })[readingStatus(s)]}</small><div className="library-row-actions">{host.sourceOriginalUrl && <a href={host.sourceOriginalUrl(s.sourceId)} target="_blank" rel="noreferrer">PDF 原件</a>}{host.sourceContentUrl && <a href={host.sourceContentUrl(s.sourceId)} target="_blank" rel="noreferrer">正文</a>}<button disabled={!!busy || active || !host.openSource || s.parseStatus !== "ready"} onClick={() => void operate("打开", () => host.openSource!(s.sourceId), true)}>阅读</button><button disabled={!!busy || active || !host.rereadSource || s.parseStatus !== "ready"} onClick={() => setConfirm({ source: s, action: "reread" })}>从头阅读</button><button disabled={!!busy || active || !host.replanSource || s.parseStatus !== "ready"} onClick={() => setConfirm({ source: s, action: "replan" })}>重新规划</button><button disabled={!!busy || active || !host.deleteSource} onClick={() => setConfirm({ source: s, action: "delete" })}>删除</button></div></div>
            <div className="library-tags" aria-label="专题标签">{s.topicIds.map(id => <button key={id} onClick={() => setTopic(id)}>{topics.find(t => t.topicId === id)?.title ?? id}</button>)}</div>
            <section className="library-blog" aria-label={`${s.title} 博客`}>
              {!blogs[s.sourceId]?.generated ? <button disabled={!!busy || !host.generateBlog || s.parseStatus !== "ready"} onClick={() => void generateBlog(s.sourceId)}>生成博客</button> : <>
                <ul className="blog-statuses">{blogArtifacts.map(([name, label]) => <li key={name} data-status={blogs[s.sourceId].artifacts?.[name]?.status ?? "pending"}><span>{label}</span><small>{blogStatusText[(blogs[s.sourceId].artifacts?.[name]?.status ?? "pending") as BlogArtifactStatus]}</small></li>)}</ul>
                {blogs[s.sourceId].valueAnalysis.applicable === false && <p className="blog-note">论文价值分析不适用：{blogs[s.sourceId].valueAnalysis.reason}</p>}
                {blogs[s.sourceId].warnings.length > 0 && <p className="blog-note" role="status">降级与证据缺口：{blogs[s.sourceId].warnings.join("；")}</p>}
                {blogs[s.sourceId].error && <p className="blog-note" role="alert">{blogs[s.sourceId].error?.message}</p>}
                <div className="blog-actions">
                  {blogs[s.sourceId].runStatus === "running" && <button disabled={!!busy || !host.cancelBlog} onClick={() => void cancelBlog(s.sourceId)}>取消生成</button>}
                  {blogArtifacts.filter(([name]) => blogs[s.sourceId].artifacts?.[name]?.status === "failed").map(([name]) => <button key={name} disabled={!!busy || !host.regenerateBlog} onClick={() => void regenerateBlog(s.sourceId, name)}>{blogRetryLabel[name]}</button>)}
                  {blogArtifacts.every(([name]) => blogs[s.sourceId].artifacts?.[name]?.status !== "failed") && <button disabled={!!busy || !host.regenerateBlog} onClick={() => void regenerateBlog(s.sourceId, "all")}>重新生成</button>}
                  {host.blogUrl && <button disabled={blogs[s.sourceId].artifacts?.html?.status !== "completed"} onClick={() => setBlogViewer(s.sourceId)}>打开博客</button>}
                </div>
              </>}
            </section>
          </article>)}</div>}
        </section></div>
      {busy && <p role="status">{busy}中…</p>}
    </main>}
    {route === "/settings" && <main className="settings-page"><h1>设置</h1>
      <section className="focus-reader__appearance-panel"><div className="settings-row"><h2>后端</h2><div className="settings-options">{(view?.agent?.backends ?? [{ id: "codex", label: "Codex" }, { id: "workbuddy", label: "WorkBuddy", unavailableReason: "待接入" }]).map(b => <label className="backend-option" key={b.id}><input type="radio" name="backend" checked={view?.agent?.backend === b.id} disabled={b.id === "workbuddy" || !!b.unavailableReason || !!busy || active || !host.selectBackend || !view?.sessionId} onChange={() => view?.sessionId && void operate("切换", () => host.selectBackend!(b.id, view.sessionId!))} /><span>{b.label}<small>{b.id === "workbuddy" ? "待接入" : b.unavailableReason ? "不可用" : "可用"}</small></span></label>)}</div></div>
      <div className="settings-row"><label htmlFor="brightness">亮度</label><input id="brightness" type="range" min="85" max="110" value={brightness} onChange={e => { setBrightness(Number(e.target.value)); try { localStorage.setItem("focus.brightness", e.target.value); } catch { setError("无法保存亮度"); } }} /></div>
      <div className="settings-row"><label htmlFor="font-size">字号</label><input id="font-size" type="range" min="0" max="3" step="1" value={fontOptions.findIndex(([key]) => key === fontSize)} aria-valuetext={fontOptions.find(([key]) => key === fontSize)?.[1]} onChange={e => { const value = fontOptions[Number(e.target.value)][0]; setFontSize(value); try { localStorage.setItem("focus.fontSize", value); } catch { setError("无法保存字号"); } }} /></div>
      <div className="settings-row"><label htmlFor="network">网络</label><span className="settings-network" title="当前后端协议未提供网络控制接口"><small>待接入</small><input id="network" className="focus-reader__toggle" type="checkbox" role="switch" checked={false} disabled /></span></div></section>
    </main>}
    <dialog className="workspace-confirm workspace-upload" ref={uploadDialog} onCancel={() => setUploadOpen(false)}>
      <form onSubmit={e => { e.preventDefault(); if (selectedFile && host.stageIngestion) { const existing = topics.find(t => t.title === uploadTopic.trim()); void ingest("暂存", () => host.stageIngestion!(selectedFile, existing ? { topicId: existing.topicId } : uploadTopic.trim() ? { topicTitle: uploadTopic.trim() } : {}), true); } }}>
        <h2>暂存 PDF</h2>
        <label>专题<input list="upload-topics" required maxLength={120} value={uploadTopic} onChange={e => setUploadTopic(e.target.value)} placeholder="选择或新建专题" /></label>
        <datalist id="upload-topics">{topics.map(t => <option key={t.topicId} value={t.title} />)}</datalist>
        <label className="upload-file">{selectedFile?.name ?? "PDF"}<input aria-label="上传材料" type="file" accept=".pdf,application/pdf" onChange={e => setSelectedFile(e.target.files?.[0] ?? null)} /></label>
        <p>此步只把文件放入 Inbox，不调用任何解析服务，也不做 AI 内容审核。暂存后可核对目标专题与处理范围，再明确确认。</p>
        {error && <p role="alert">{error}</p>}
        <div className="upload-actions"><button type="button" disabled={!!busy} onClick={() => setUploadOpen(false)}>取消</button><button type="submit" className="workspace-primary" disabled={uploadDisabled || !selectedFile || !uploadTopic.trim()}>{busy ? "暂存中…" : "放入 Inbox"}</button></div>
      </form>
    </dialog>
    {blogViewer && host.blogUrl && <dialog className="workspace-blog-viewer" open onCancel={() => setBlogViewer("")}>
      <div className="blog-viewer-head"><h2>博客：{sources.find(s => s.sourceId === blogViewer)?.shortName || sources.find(s => s.sourceId === blogViewer)?.title}</h2>
        <div><a href={host.blogUrl(blogViewer)} target="_blank" rel="noreferrer">新窗口打开</a><button onClick={() => setBlogViewer("")}>关闭</button></div></div>
      <iframe title="博客" src={host.blogUrl(blogViewer)} />
    </dialog>}
    <dialog className="workspace-confirm" ref={confirmation} onCancel={() => setConfirm(null)}><h2>{confirm?.action === "delete" ? "删除材料？" : confirm?.action === "replan" ? "重新规划？" : "从头阅读？"}</h2><p>{confirm?.source.title}</p><p>{confirm?.action === "delete" ? "原文、图片、计划与笔记将永久删除，专题引用也会移除。" : confirm?.action === "replan" ? "重新分段并准备译文；保留旧计划、译文和笔记，不重复解析。" : "回到第一段，保留现有分段、译文和笔记。"}</p><div><button disabled={!!busy} onClick={() => setConfirm(null)}>取消</button><button className="workspace-primary" disabled={!!busy || active} onClick={() => {
      if (!confirm) return;
      const { source, action } = confirm;
      void operate(action === "delete" ? "删除" : action === "replan" ? "重新规划" : "从头阅读", () => action === "delete" ? host.deleteSource!(source.sourceId) : action === "replan" ? host.replanSource!(source.sourceId) : host.rereadSource!(source.sourceId), action === "reread");
    }}>{busy || (confirm?.action === "delete" ? "永久删除" : confirm?.action === "replan" ? "确认重新规划" : "确认从头阅读")}</button></div>{error && <p role="alert">{error}</p>}</dialog>
  </div>;
}
