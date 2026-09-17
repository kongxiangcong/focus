import { type CSSProperties, useEffect, useRef, useState } from "react";
import type { LibrarySource, LibraryTopic, ReaderHost, ReaderHostResult, ReadingWindow } from "@focus/reader-contracts";
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

export function WorkspaceApp({ host }: { host: ReaderHost }) {
  const [route, setRoute] = useState<Route>(routeFromLocation);
  const [fontSize, setFontSize] = useState<FontSize>(readFont);
  const [brightness, setBrightness] = useState(() => { try { return Math.max(85, Math.min(110, Number(localStorage.getItem("focus.brightness") ?? 100) || 100)); } catch { return 100; } });
  const [dragging, setDragging] = useState(false);
  const [view, setView] = useState<ReadingWindow | null>(null);
  const [sources, setSources] = useState<readonly LibrarySource[]>([]);
  const [topics, setTopics] = useState<readonly LibraryTopic[]>([]);
  const [topic, setTopic] = useState("");
  const [query, setQuery] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState("");
  const [confirm, setConfirm] = useState<{ source: LibrarySource; action: "delete" | "reread" } | null>(null);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [uploadTopic, setUploadTopic] = useState("");
  const [uploader, setUploader] = useState("孔祥聪");
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
      const [sourceResult, topicResult] = await Promise.all([host.listSources(), host.listTopics()]);
      if (version !== requestVersion.current) return;
      if (sourceResult.ok) setSources(sourceResult.value); else setError(sourceResult.error.message);
      if (topicResult.ok) setTopics(topicResult.value); else setError(topicResult.error.message);
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
  useEffect(() => { if (confirm) confirmation.current?.showModal(); else confirmation.current?.close(); }, [confirm]);

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
  const filtered = sources.filter(s => (!topic || s.topicIds.includes(topic)) && (s.title + " " + (s.shortName ?? "")).toLowerCase().includes(query.toLowerCase()));
  function chooseUpload(selected?: File) {
    if (selected && !/\.(pdf|html|md|markdown)$/i.test(selected.name)) { setError("请选择 PDF、HTML 或 Markdown"); return; }
    setSelectedFile(selected ?? null);
    setUploadTopic(topics.find(t => t.topicId === topic)?.title ?? "");
    setError(""); setUploadOpen(true);
  }
  const uploadDisabled = !!busy || active || !host.uploadSource;
  return <div className="workspace-app" style={{ "--reader-brightness": brightness / 100 } as CSSProperties}>
    <header className="workspace-nav">
      <a className="workspace-logo" href="/library" onClick={e => { e.preventDefault(); navigate("/library"); }}>focus<span>.</span></a>
      <nav aria-label="应用导航">{([["/library", "知识库", "▤"], ["/reading", "阅读", "☷"], ["/settings", "设置", "☼"]] as const).map(([path, title, icon]) =>
        <a key={path} href={path} aria-current={route === path ? "page" : undefined} onClick={e => { e.preventDefault(); navigate(path); }}><span aria-hidden="true">{icon}</span>{title}</a>)}</nav>
    </header>
    {!uploadOpen && error && <div className="workspace-error" role="alert">{error}<button onClick={() => { setError(""); void refresh(); }}>重试</button></div>}
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
      <div className="library-layout"><aside className="library-topics" aria-label="专题"><h2>专题</h2><button aria-pressed={!topic} onClick={() => setTopic("")}>全部 <span>{sources.length}</span></button>{topics.map(t => <button key={t.topicId} aria-pressed={topic === t.topicId} onClick={() => setTopic(t.topicId)}>{t.title}<span>{t.sourceIds.length}</span></button>)}</aside>
        <section className="library-sources" aria-label="材料列表"><div className="library-toolbar"><h2>{topics.find(t => t.topicId === topic)?.title ?? "全部材料"}<small>{filtered.length}</small></h2><input type="search" aria-label="搜索材料" placeholder="搜索标题" value={query} onChange={e => setQuery(e.target.value)} /></div>
          {loading ? <p role="status" className="library-empty">读取中…</p> : filtered.length === 0 ? <div className="library-empty"><span aria-hidden="true">▤</span><p>{query || topic ? "暂无匹配材料" : "放入第一份材料"}</p><button className="workspace-primary" disabled={uploadDisabled} onClick={() => { if (query || topic) { setQuery(""); setTopic(""); } else chooseUpload(); }}>{query || topic ? "重置" : "上传"}</button></div> : <div className="library-cards">{filtered.map(s => <article className="library-card" data-reading-status={readingStatus(s)} key={s.sourceId}>
            <div className="library-card-top"><span className="source-badge">{s.format ?? (s.kind === "paper" ? "PDF" : "HTML")}</span>{s.parseStatus !== "ready" && <span title={s.error ?? undefined}>需检查</span>}</div>
            <h3><button className="library-title" disabled={!!busy || active || !host.openSource || s.parseStatus !== "ready"} onClick={() => void operate("打开", () => host.openSource!(s.sourceId), true)}>{s.shortName || s.title}</button></h3>
            <p className="library-metadata" title={s.title}>{[s.publishedAt, s.venue].filter(Boolean).join(" · ")}</p>
            <div className="library-progress"><progress aria-label={`${s.title} 阅读进度`} value={s.progress.completed} max={s.progress.total || 1} /><span>{s.progress.completed} / {s.progress.total}</span></div>
            <div className="library-card-bottom"><small>{({ ready: "待阅读", reading: "阅读中", completed: "已读完", unplanned: "待规划" })[readingStatus(s)]}</small><div className="library-row-actions"><button disabled={!!busy || active || !host.openSource || s.parseStatus !== "ready"} onClick={() => void operate("打开", () => host.openSource!(s.sourceId), true)}>阅读</button><button disabled={!!busy || active || !host.rereadSource || s.parseStatus !== "ready"} onClick={() => setConfirm({ source: s, action: "reread" })}>重读</button><button disabled={!!busy || active || !host.deleteSource} onClick={() => setConfirm({ source: s, action: "delete" })}>删除</button></div></div>
            <div className="library-tags" aria-label="专题标签">{s.topicIds.map(id => <button key={id} onClick={() => setTopic(id)}>{topics.find(t => t.topicId === id)?.title ?? id}</button>)}</div>
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
      <form onSubmit={e => { e.preventDefault(); if (selectedFile && host.uploadSource) void operate("上传", () => host.uploadSource!(selectedFile, { topic: uploadTopic.trim(), uploader: uploader.trim() })); }}>
        <h2>上传材料</h2>
        <label>专题<input list="upload-topics" required maxLength={120} value={uploadTopic} onChange={e => setUploadTopic(e.target.value)} placeholder="选择或新建专题" /></label>
        <datalist id="upload-topics">{topics.map(t => <option key={t.topicId} value={t.title} />)}</datalist>
        <label>用户<input required maxLength={100} value={uploader} onChange={e => setUploader(e.target.value)} /></label>
        <label className="upload-file">{selectedFile?.name ?? "PDF / HTML / Markdown"}<input aria-label="上传材料" type="file" accept=".pdf,.html,.md,.markdown" onChange={e => setSelectedFile(e.target.files?.[0] ?? null)} /></label>
        {error && <p role="alert">{error}</p>}
        <div className="upload-actions"><button type="button" disabled={!!busy} onClick={() => setUploadOpen(false)}>取消</button><button type="submit" className="workspace-primary" disabled={uploadDisabled || !selectedFile || !uploadTopic.trim() || !uploader.trim()}>{busy ? "上传中…" : "确认上传"}</button></div>
      </form>
    </dialog>
    <dialog className="workspace-confirm" ref={confirmation} onCancel={() => setConfirm(null)}><h2>{confirm?.action === "delete" ? "删除材料？" : "从头重读？"}</h2><p>{confirm?.source.title}</p><p>{confirm?.action === "delete" ? "原文、图片、计划与笔记将永久删除，专题引用也会移除。" : "将清除这份材料的所有阅读笔记与当前进度，保留解析原文和图片，然后重新规划阅读。"}</p><div><button disabled={!!busy} onClick={() => setConfirm(null)}>取消</button><button className="workspace-primary" disabled={!!busy || active} onClick={() => {
      if (!confirm) return;
      const { source, action } = confirm;
      void operate(action === "delete" ? "删除" : "重读", () => action === "delete" ? host.deleteSource!(source.sourceId) : host.rereadSource!(source.sourceId), false);
    }}>{busy || (confirm?.action === "delete" ? "永久删除" : "确认重读")}</button></div>{error && <p role="alert">{error}</p>}</dialog>
  </div>;
}
