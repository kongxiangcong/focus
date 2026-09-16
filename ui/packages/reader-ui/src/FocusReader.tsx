import { cursorReceipt, type ReaderChunk, type ReaderAttachment, type ReaderHost, type ReadingWindow,
  type ReaderHostResult, type SendReaderMessageInput, type ContinueReadingInput } from "@focus/reader-contracts";
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { AgentControls } from "./AgentControls";
import { ReadingChunk, ReaderConversation, chunkKey } from "./ReadingChunk";
import "./reader-shell.css";

type Upload = { id: string; file: File; state: "uploading" | "ready" | "failed"; attachment?: ReaderAttachment; error?: string };
type Failure = { message: string; label: string; retry: () => void };
export interface FocusReaderProps { host: ReaderHost }

export function FocusReader({ host }: FocusReaderProps) {
  const [view, setView] = useState<ReadingWindow | null>(null);
  const [draft, setDraft] = useState("");
  const [uploads, setUploads] = useState<Upload[]>([]);
  const [reference, setReference] = useState<ReaderChunk | null>(null);
  const [operation, setOperation] = useState("");
  const [failure, setFailure] = useState<Failure | null>(null);
  const [connection, setConnection] = useState("");
  const [panel, setPanel] = useState<"materials" | "contents" | "settings" | null>(null);
  const [largeText, setLargeText] = useState(false);
  const [newContent, setNewContent] = useState(false);
  const stream = useRef<HTMLElement>(null);
  const dialog = useRef<HTMLDialogElement>(null);
  const composer = useRef<HTMLTextAreaElement>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const follow = useRef(true);
  const revision = useRef(-1);
  const session = useRef<string | undefined>(undefined);
  const epoch = useRef(0);
  const locked = useRef(false);
  const alive = useRef(true);
  const draftRef = useRef(draft); draftRef.current = draft;

  function clearSessionUI() {
    epoch.current += 1;
    setDraft(""); setUploads([]); setReference(null); setFailure(null); setPanel(null);
    setNewContent(false); follow.current = true;
  }
  function accept(value: ReadingWindow) {
    if (!alive.current || (value.revision !== undefined && value.revision < revision.current)) return;
    if (session.current && value.sessionId && value.sessionId !== session.current) clearSessionUI();
    session.current = value.sessionId;
    revision.current = value.revision ?? revision.current;
    setView(value);
    setConnection("");
  }
  async function reconnect() {
    const result = await host.getReadingWindow();
    if (result.ok) accept(result.value);
    else setConnection(result.error.message);
  }
  useEffect(() => {
    alive.current = true; epoch.current += 1; revision.current = -1; session.current = undefined;
    setView(null); clearSessionUI();
    const controller = new AbortController();
    void host.getReadingWindow(controller.signal).then(result => {
      if (controller.signal.aborted) return;
      if (result.ok) accept(result.value); else setConnection(result.error.message);
    });
    const unsubscribe = host.subscribe?.(result => {
      if (result.ok) accept(result.value); else setConnection(result.error.message);
    });
    return () => { alive.current = false; epoch.current += 1; controller.abort(); unsubscribe?.(); };
  }, [host]);

  useEffect(() => {
    if (panel) dialog.current?.showModal(); else dialog.current?.close();
  }, [panel]);

  const current = view?.current ?? null;
  const agent = view?.agent;
  const active = !!agent?.run && ["running", "approval", "stopping"].includes(agent.run.status);
  const uploading = uploads.some(u => u.state === "uploading");
  const blocked = active || !!operation;
  const chunks = view ? [...view.history, ...(current ? [current] : [])] : [];
  const entries = view?.timeline ?? [
    ...chunks.map(chunk => ({ kind: "reading" as const, chunk })),
    ...(view?.conversation ?? []).map(m => ({ kind: "message" as const, messageId: m.messageId })),
  ];
  const visibleChunks = entries.flatMap(e => e.kind === "reading" ? [e.chunk] : []);
  const displayEmpty = entries.length === 0;
  const contentVersion = `${view?.sessionId}:${entries.length}:${view?.conversation.map(m => m.content).join('\n')}:${current?.translation?.length}`;
  useLayoutEffect(() => {
    const pane = stream.current;
    if (!pane) return;
    if (follow.current) {
      pane.scrollTop = pane.scrollHeight;
      setNewContent(false);
    } else setNewContent(true);
  }, [contentVersion]);

  async function perform(label: string, task: () => Promise<ReaderHostResult<ReadingWindow>>, success?: () => void) {
    if (locked.current) return;
    locked.current = true; setOperation(label); setFailure(null);
    const started = epoch.current;
    try {
      const result = await task();
      if (!alive.current || started !== epoch.current) return;
      if (result.ok) { accept(result.value); success?.(); }
      else if (result.error.code === "cursor-changed") setFailure({ message: result.error.message, label: "更新阅读位置", retry: () => { setFailure(null); void reconnect(); } });
      else setFailure({ message: result.error.message, label: `重试${label}`, retry: () => void perform(label, task, success) });
    } catch (error) {
      if (alive.current && started === epoch.current) setFailure({ message: String(error), label: `重试${label}`, retry: () => void perform(label, task, success) });
    } finally { locked.current = false; if (alive.current) setOperation(""); }
  }
  function send(content = draft, clear = true, includeAttachments = true) {
    if (!view || blocked || uploading || !content.trim()) return;
    const selected = reference;
    const attachmentIds = (includeAttachments ? uploads : []).flatMap(u => u.attachment ? [u.attachment.attachmentId] : []);
    const sentUploads = (includeAttachments ? uploads : []).filter(u => u.state === "ready").map(u => u.id);
    const input: SendReaderMessageInput = {
      sessionId: view.sessionId, receipt: selected ? { sourceId: selected.sourceId, planId: selected.planId, chunkId: selected.chunkId } : visibleChunks.some(c => current && chunkKey(c) === chunkKey(current)) ? cursorReceipt(view) : null,
      content: content.trim(), requestId: crypto.randomUUID(), attachmentIds,
    };
    void perform("发送", () => host.sendMessage(input), () => {
      if (clear && draftRef.current === content) setDraft("");
      setUploads(old => old.filter(u => !sentUploads.includes(u.id)));
      setReference(null); setPanel(null);
    });
  }
  function next() {
    if (!view || !current || blocked) return;
    const input: ContinueReadingInput = { receipt: cursorReceipt(view)!, requestId: crypto.randomUUID(), sessionId: view.sessionId };
    void perform("下一段", () => host.continueReading(input), () => setReference(null));
  }
  function reset() {
    if (!host.newSession || !view?.sessionId) return;
    const id = view.sessionId;
    void perform("新建会话", () => host.newSession!(id), () => {
      clearSessionUI();
      if (stream.current) stream.current.scrollTop = 0;
      composer.current?.focus({ preventScroll: true });
    });
  }
  function resume() {
    if (!host.resumeReading || !view?.sessionId) return;
    void perform("恢复阅读", () => host.resumeReading!(view.sessionId!), () => { follow.current = true; });
  }
  async function upload(file: File, id: string = crypto.randomUUID()) {
    if (!host.upload) return;
    const started = epoch.current;
    setUploads(old => [...old.filter(u => u.id !== id), { id, file, state: "uploading" }]);
    try {
      const result = await host.upload(file);
      if (!alive.current || started !== epoch.current) return;
      setUploads(old => old.map(u => u.id !== id ? u : result.ok ? { ...u, state: "ready", attachment: result.value } : { ...u, state: "failed", error: result.error.message }));
    } catch (error) {
      if (alive.current && started === epoch.current) setUploads(old => old.map(u => u.id !== id ? u : { ...u, state: "failed", error: String(error) }));
    }
  }
  function referenceChunk(chunk: ReaderChunk) { setReference(chunk); composer.current?.focus({ preventScroll: true }); }
  function review(chunk: ReaderChunk) {
    setPanel(null); setReference(chunk); follow.current = false;
    const target = Array.from(stream.current?.querySelectorAll<HTMLElement>("[data-chunk-key]") ?? []).find(el => el.dataset.chunkKey === chunkKey(chunk));
    target?.scrollIntoView({ block: "start", behavior: "instant" });
  }

  return <div className="focus-reader" data-large-text={largeText}>
    <header className="focus-header">
      <span className="focus-brand">FOCUS<span>.</span></span>
      <button className="focus-title" title={view?.source.title} onClick={() => setPanel("materials")}>{view?.source.sourceId ? view.source.title : "阅读工作台"}</button>
      <nav aria-label="阅读操作">
        <button onClick={() => setPanel("materials")}>材料</button>
        <button onClick={() => setPanel("contents")}>目录</button>
        <button onClick={() => setPanel("settings")}>设置</button>
        <button className="focus-new" disabled={!host.newSession || !view || !!operation} onClick={reset}>{active ? "停止并新建" : "新建会话"}</button>
      </nav>
    </header>
    <main className="focus-stream" ref={stream} aria-label="阅读与对话" tabIndex={0} onScroll={() => {
      const el = stream.current!;
      follow.current = el.scrollHeight - el.scrollTop - el.clientHeight < 100;
      if (follow.current) setNewContent(false);
    }}>
      <div className="focus-content">
        {!view && <p role="status">{connection ? "暂时无法连接" : "正在打开…"}</p>}
        {view && displayEmpty && <section className="focus-start">
          <span className="focus-start__label">FOCUS / READING</span>
          <h1>从一份材料开始</h1>
          <p>打开材料，或在下方输入阅读需求。</p>
          <div><button className="focus-primary" onClick={() => setPanel("materials")}>打开材料</button>
            {host.upload && <button onClick={() => fileInput.current?.click()}>上传 PDF / HTML</button>}
            {(current || view.history.length > 0) && host.resumeReading && <button onClick={resume} disabled={blocked}>继续上次阅读</button>}</div>
        </section>}
        {entries.map(e => {
          if (e.kind === "reading") return <ReadingChunk key={chunkKey(e.chunk)} chunk={e.chunk} onReference={referenceChunk} />;
          const message = view?.conversation.find(m => m.messageId === e.messageId);
          return message ? <ReaderConversation key={e.messageId} messages={[message]} /> : null;
        })}
        {view?.status === "completed" && !view.sessionFresh && !displayEmpty && <p className="focus-finished">已读完 · 可以继续提问，或<button onClick={() => setPanel("materials")}>打开其他材料</button></p>}
      </div>
    </main>
    <div className="focus-bottom">
      {newContent && <button className="focus-new-content" onClick={() => {
        follow.current = true; setNewContent(false); if (stream.current) stream.current.scrollTop = stream.current.scrollHeight;
      }}>有新内容 · 回到底部 ↓</button>}
      <div className="focus-composer-wrap">
        {agent?.backend && agent.backends && host.selectBackend && view?.sessionId && <div className="focus-backend">
          <label>Agent <select aria-label="选择 Agent" value={agent.backend} disabled={blocked || uploading}
            onChange={e => { const name = e.target.value; const id = view.sessionId!;
              void perform("切换 Agent", () => host.selectBackend!(name, id)); }}>
            {agent.backends.map(b => <option key={b.id} value={b.id} disabled={!!b.unavailableReason}>{b.label}</option>)}
          </select></label>
          <small>切换将开启新对话，保留材料、笔记和阅读位置</small>
          {agent.backends.filter(b => b.unavailableReason).map(b => <details key={b.id}>
            <summary>{b.label}</summary><p>{b.unavailableReason}</p>
          </details>)}
        </div>}
        {connection && <div className="focus-error" role="alert">{connection}<button onClick={() => void reconnect()}>重新连接</button></div>}
        {failure && <div className="focus-error" role="alert">{failure.message}<button disabled={!!operation} onClick={failure.retry}>{failure.label}</button><button aria-label="关闭错误" onClick={() => setFailure(null)}>×</button></div>}
        {agent && <AgentControls agent={agent} onStop={() => void perform("停止", () => host.stop!())} onAnswer={async input => {
          const result = await host.approve?.(input);
          if (result?.ok) { accept(result.value); return true; } return false;
        }} />}
        {reference && <div className="focus-reference"><span>引用第 {reference.index} 段 · {reference.sectionPath.at(-1)}</span><button aria-label="取消引用" onClick={() => setReference(null)}>×</button></div>}
        {uploads.length > 0 && <ul className="focus-attachments">{uploads.map(u => <li key={u.id}>
          <span title={u.file.name}>{u.file.name}</span><small>{u.state === "uploading" ? "上传中" : u.state === "failed" ? "上传失败" : "已上传"}</small>
          {u.state === "failed" && <button title={u.error} onClick={() => void upload(u.file, u.id)}>重试上传</button>}
          <button aria-label={`移除 ${u.file.name}`} onClick={() => setUploads(old => old.filter(v => v.id !== u.id))}>移除</button>
        </li>)}</ul>}
        <form className="focus-composer" onSubmit={e => { e.preventDefault(); send(); }}>
          <label className="focus-sr-only" htmlFor="focus-question">输入问题或阅读需求</label>
          <textarea id="focus-question" ref={composer} rows={2} value={draft} placeholder="输入问题，或告诉 Agent 你想读什么…"
            onChange={e => setDraft(e.target.value)} onKeyDown={e => {
              if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); send(); }
            }} />
          <div className="focus-composer__actions">
            <div>{host.upload && <><input ref={fileInput} className="focus-sr-only" aria-label="选择论文文件" type="file" accept=".pdf,.html" multiple onChange={e => {
              Array.from(e.target.files ?? []).forEach(f => void upload(f)); e.target.value = "";
            }} /><button type="button" onClick={() => fileInput.current?.click()} aria-label="添加附件">＋ 附件</button></>}
              {uploads.some(u => u.state === "ready") && <button type="button" disabled={blocked || uploading} onClick={() => send("请阅读附件", false)}>开始阅读附件</button>}
            </div>
            <button type="submit" className="focus-primary" disabled={!view || blocked || uploading || !draft.trim()}>{operation === "发送" ? "发送中…" : "发送 ↑"}</button>
          </div>
        </form>
        {current && visibleChunks.some(c => chunkKey(c) === chunkKey(current)) && <div className="focus-next"><button disabled={blocked} onClick={next}>{operation === "下一段" ? "正在打开…" : "下一段 →"}</button></div>}
      </div>
    </div>
    <dialog ref={dialog} className="focus-dialog" onCancel={() => setPanel(null)} onClick={e => { if (e.target === dialog.current) setPanel(null); }}>
      <header><h2>{panel === "materials" ? "材料" : panel === "contents" ? "已加载段落" : "阅读设置"}</h2><button aria-label="关闭" onClick={() => setPanel(null)}>×</button></header>
      {panel === "materials" && <>
        {view?.source.sourceId && <p className="focus-full-title">{view.source.title}</p>}
        {host.upload && <button onClick={() => { setPanel(null); fileInput.current?.click(); }}>上传 PDF / HTML</button>}
        {agent?.catalog.sources.length ? <section><h3>来源</h3>{agent.catalog.sources.map(s => <button className="focus-material" disabled={blocked} key={s.sourceId} onClick={() => send(`开始阅读 Source ${s.sourceId}`, false, false)}>{s.title}</button>)}</section> : <p>暂无已保存的材料。</p>}
        {!!agent?.catalog.topics.length && <section><h3>专题</h3>{agent.catalog.topics.map(t => <button className="focus-material" disabled={blocked} key={t.topicId} onClick={() => send(`开始阅读 Topic ${t.topicId}`, false, false)}>{t.title}</button>)}</section>}
      </>}
      {panel === "contents" && <nav aria-label="已加载段落">{visibleChunks.length ? visibleChunks.map(c => <button className="focus-material" key={chunkKey(c)} onClick={() => review(c)}>第 {c.index} 段 · {c.sectionPath.at(-1)}</button>) : <p>打开材料后显示。</p>}</nav>}
      {panel === "settings" && <label><input type="checkbox" checked={largeText} onChange={e => setLargeText(e.target.checked)} /> 使用较大正文字号</label>}
    </dialog>
  </div>;
}
