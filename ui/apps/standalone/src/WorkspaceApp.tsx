import { useEffect, useRef, useState } from "react";
import type { LibrarySource, LibraryTopic, ReaderHost, ReaderHostResult, ReadingWindow } from "@focus/reader-contracts";
import { FocusReader } from "@focus/reader-ui";

type Route = "/library" | "/reading" | "/settings";
type FontSize = "small" | "standard" | "large" | "extra";
const fontOptions: [FontSize, string][] = [["small", "紧凑"], ["standard", "标准"], ["large", "较大"], ["extra", "特大"]];
function readFont(): FontSize {
  try { const value = localStorage.getItem("focus.fontSize"); return fontOptions.some(([key]) => key === value) ? value as FontSize : "standard"; }
  catch { return "standard"; }
}
function routeFromLocation(): Route { return ["/library", "/reading", "/settings"].includes(location.pathname) ? location.pathname as Route : "/library"; }

export function WorkspaceApp({ host }: { host: ReaderHost }) {
  const [route, setRoute] = useState<Route>(routeFromLocation);
  const [fontSize, setFontSize] = useState<FontSize>(readFont);
  const [view, setView] = useState<ReadingWindow | null>(null);
  const [sources, setSources] = useState<readonly LibrarySource[]>([]);
  const [topics, setTopics] = useState<readonly LibraryTopic[]>([]);
  const [topic, setTopic] = useState("");
  const [query, setQuery] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState("");
  const [confirm, setConfirm] = useState<{ source: LibrarySource; action: "delete" | "reread" } | null>(null);
  const file = useRef<HTMLInputElement>(null);
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
  useEffect(() => { if (route === "/library") void refresh(); }, [route, view?.agent?.run?.status, host]);
  useEffect(() => { if (confirm) confirmation.current?.showModal(); else confirmation.current?.close(); }, [confirm]);

  async function operate(label: string, operation: () => Promise<ReaderHostResult<ReadingWindow>>, read = false) {
    if (locked.current || active) return;
    locked.current = true; setBusy(label); setError("");
    try {
      const result = await operation();
      if (!result.ok) { setError(result.error.message); return; }
      setView(result.value); setConfirm(null);
      if (read) navigate("/reading");
      await refresh();
    } catch (e) { setError(String(e)); }
    finally { locked.current = false; setBusy(""); }
  }
  const filtered = sources.filter(s => (!topic || s.topicIds.includes(topic)) && s.title.toLowerCase().includes(query.toLowerCase()));
  const completed = sources.filter(s => s.progress.total > 0 && s.progress.completed === s.progress.total).length;

  return <div className="workspace-app">
    <header className="workspace-nav">
      <a className="workspace-logo" href="/library" onClick={e => { e.preventDefault(); navigate("/library"); }}>focus<span>.</span></a>
      <nav aria-label="应用导航">{([["/library", "知识库"], ["/reading", "阅读"], ["/settings", "设置"]] as const).map(([path, title]) =>
        <a key={path} href={path} aria-current={route === path ? "page" : undefined} onClick={e => { e.preventDefault(); navigate(path); }}>{title}</a>)}</nav>
      <span className="workspace-private"><i /> 私人阅读工作台</span>
    </header>
    {route !== "/reading" && error && <div className="workspace-error" role="alert">{error}<button onClick={() => { setError(""); void refresh(); }}>重试连接</button></div>}
    <div className="workspace-reading" hidden={route !== "/reading"}><FocusReader host={host} appearance="mist" fontSize={fontSize} visible={route === "/reading"} /></div>
    {route === "/library" && <main className="library-page">
      <div className="page-heading"><div><p className="workspace-eyebrow">YOUR READING, IN ONE PLACE</p><h1>把好奇心，留在这里。</h1><p>整理材料，沿着原文，继续每一次思考。</p></div>
        <div><input ref={file} className="workspace-sr-only" aria-label="上传论文 PDF" type="file" accept="application/pdf,.pdf" onChange={e => {
          const selected = e.target.files?.[0]; e.target.value = "";
          if (selected && host.uploadSource) void operate("上传与解析", () => host.uploadSource!(selected));
        }} /><button className="workspace-primary" disabled={!!busy || active || !host.uploadSource} onClick={() => file.current?.click()}>＋ 上传 PDF</button><small>上传后自动解析原文与图片</small></div>
      </div>
      <div className="library-stats"><span><strong>{sources.length.toString().padStart(2, "0")}</strong> 份材料</span><span><strong>{topics.length.toString().padStart(2, "0")}</strong> 个专题</span><span><strong>{completed.toString().padStart(2, "0")}</strong> 份已读完</span><span><strong>{sources.reduce((sum, s) => sum + s.noteCount, 0).toString().padStart(2, "0")}</strong> 条阅读笔记</span></div>
      {view?.agent?.run && <div className="library-run" role="status"><span>{active ? "正在处理材料…" : view.agent.run.status === "failed" || view.agent.run.status === "interrupted" ? "上次任务未完成" : "上次任务已结束"}{view.agent.run.error && ` · ${view.agent.run.error}`}</span><button onClick={() => navigate("/reading")}>查看对话与任务 →</button></div>}
      {!host.listSources && <p role="status">当前宿主未提供知识库管理。可进入阅读查看演示材料。</p>}
      <div className="library-layout"><aside className="library-topics"><p className="workspace-eyebrow">TOPICS / 专题</p><button aria-pressed={!topic} onClick={() => setTopic("")}>全部材料 <span>{sources.length}</span></button>{topics.map(t => <button key={t.topicId} aria-pressed={topic === t.topicId} onClick={() => setTopic(t.topicId)}>{t.title}<span>{t.sourceIds.length}</span></button>)}<p className="library-topic-hint">同一份材料，可以属于多个专题。</p></aside>
        <section className="library-sources" aria-label="材料列表"><div className="library-toolbar"><h2>{topics.find(t => t.topicId === topic)?.title ?? "全部材料"}<small>{filtered.length}</small></h2><input type="search" aria-label="搜索材料" placeholder="搜索标题…" value={query} onChange={e => setQuery(e.target.value)} /></div>
          {loading ? <p role="status" className="library-empty">正在读取材料…</p> : filtered.length === 0 ? <div className="library-empty"><span>＋</span><h3>{query || topic ? "没有匹配的材料" : "第一份材料，是一个开始。"}</h3><p>{query || topic ? "试试其他标题或专题。" : "上传一份 PDF，原文、图片和阅读位置都会留在这里。"}</p></div> : <div className="library-table-scroll"><table><thead><tr><th>材料</th><th>解析</th><th>阅读进度</th><th>笔记</th><th>专题</th><th>操作</th></tr></thead><tbody>{filtered.map(s => <tr key={s.sourceId}>
            <td><button className="library-title" disabled={!!busy || active || !host.openSource || s.parseStatus !== "ready"} onClick={() => void operate("打开材料", () => host.openSource!(s.sourceId), true)}>{s.title}</button><small>{s.kind === "paper" ? "PAPER / 论文" : "ARTICLE / 文章"}</small></td>
            <td><span className={`parse-status ${s.parseStatus}`} title={s.error ?? undefined}>{s.parseStatus === "ready" ? "已解析" : "需检查"}</span></td>
            <td><span>{s.progress.total ? `${s.progress.completed} / ${s.progress.total}` : "尚未开始"}</span><progress aria-label={`${s.title} 阅读进度`} value={s.progress.completed} max={s.progress.total || 1} /></td>
            <td>{s.noteCount}</td><td className="library-topic-cell">{s.topicIds.map(id => topics.find(t => t.topicId === id)?.title ?? id).join("、") || "—"}</td>
            <td><div className="library-row-actions"><button disabled={!!busy || active || !host.rereadSource || s.parseStatus !== "ready"} onClick={() => setConfirm({ source: s, action: "reread" })}>重读</button><button disabled={!!busy || active || !host.deleteSource} onClick={() => setConfirm({ source: s, action: "delete" })}>删除</button></div></td>
          </tr>)}</tbody></table></div>}
          <p className="library-footnote">进度跟随实际阅读位置 · 笔记为已保存总数</p>
        </section></div>
      {busy && <p role="status">{busy}…</p>}
    </main>}
    {route === "/settings" && <main className="settings-page"><p className="workspace-eyebrow">MAKE ROOM FOR READING</p><h1>让阅读，更合心意。</h1>
      <section><div><span className="settings-index">01</span><h2>Agent 平台</h2><p>切换平台会开启新对话，保留材料、笔记和阅读位置。</p></div><div className="settings-options">{view?.agent?.backends?.map(b => <label className={`backend-option ${view.agent?.backend === b.id ? "selected" : ""}`} key={b.id}><input type="radio" name="backend" checked={view.agent?.backend === b.id} disabled={!!b.unavailableReason || !!busy || active || !host.selectBackend} onChange={() => view.sessionId && void operate("切换 Agent", () => host.selectBackend!(b.id, view.sessionId!))} /><span><strong>{b.label}</strong><small>{b.unavailableReason ?? (view.agent?.backend === b.id ? "当前默认" : "可选择")}</small></span></label>) ?? <p>连接本地后台后显示可用平台。</p>}</div></section>
      <section><div><span className="settings-index">02</span><h2>阅读主题</h2><p>柔和的光，把注意力留给当前段落。</p></div><div className="theme-options"><div className="theme-mist" aria-label="当前主题：雾光 Mist"><span>雾光</span><small>MIST · 当前默认</small></div><p>留白 · 极夜 · 流动 · 共读 <span>后续开放</span></p></div></section>
      <section><div><span className="settings-index">03</span><h2>正文字号</h2><p>选择舒服的阅读尺度。</p></div><div><div className="font-options">{fontOptions.map(([key, label]) => <button key={key} aria-pressed={fontSize === key} onClick={() => { setFontSize(key); try { localStorage.setItem("focus.fontSize", key); } catch { setError("浏览器未允许保存字号设置。"); } }}>{label}</button>)}</div><p className={`font-preview font-${fontSize}`}>阅读，是把别人的思考，变成自己的问题。</p></div></section>
    </main>}
    <dialog className="workspace-confirm" ref={confirmation} onCancel={() => setConfirm(null)}><h2>{confirm?.action === "delete" ? "删除这份材料？" : "从头重读？"}</h2><p>{confirm?.source.title}</p><p>{confirm?.action === "delete" ? "原文、图片、计划与笔记将永久删除，专题引用也会移除。" : "将清除这份材料的所有阅读笔记与当前进度，保留解析原文和图片，然后重新规划阅读。"}</p><div><button disabled={!!busy} onClick={() => setConfirm(null)}>取消</button><button className="workspace-primary" disabled={!!busy || active} onClick={() => {
      if (!confirm) return;
      const { source, action } = confirm;
      void operate(action === "delete" ? "删除" : "重读", () => action === "delete" ? host.deleteSource!(source.sourceId) : host.rereadSource!(source.sourceId), action === "reread");
    }}>{busy || (confirm?.action === "delete" ? "永久删除" : "清除并重读")}</button></div>{error && <p role="alert">{error}</p>}</dialog>
  </div>;
}
