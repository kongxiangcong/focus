import { createReaderId, cursorReceipt, type ReaderChunk, type ReaderAttachment, type ReaderHost, type ReadingWindow,
  type ReaderHostResult, type SendReaderMessageInput, type ContinueReadingInput, type SourceNote, type ReadingProgressEntry } from "@focus/reader-contracts";
import { type CSSProperties, useEffect, useLayoutEffect, useRef, useState } from "react";
import { AgentControls } from "./AgentControls";
import { ReadingChunk, ReaderConversation, chunkKey } from "./ReadingChunk";
import "./reader-shell.css";
import "./mist-reader.css";

type Upload = { id: string; file: File; state: "uploading" | "ready" | "failed"; attachment?: ReaderAttachment; error?: string };
type Failure = { message: string; label: string; retry: () => void };
export interface FocusReaderProps { host: ReaderHost; appearance?: "mist" | "conversation"; fontSize?: "small" | "standard" | "large" | "extra"; visible?: boolean }

export function FocusReader({ host, appearance = "conversation", fontSize = "standard", visible = true }: FocusReaderProps) {
  const mist = appearance === "mist";
  const [collapsed, setCollapsed] = useState(false);
  const [view, setView] = useState<ReadingWindow | null>(null);
  const [draft, setDraft] = useState("");
  const [uploads, setUploads] = useState<Upload[]>([]);
  const [reference, setReference] = useState<ReaderChunk | null>(null);
  const [reviewChunk, setReviewChunk] = useState<ReaderChunk | null>(null);
  const [discussionFocus, setDiscussionFocus] = useState<string | null>(null);
  const [operation, setOperation] = useState("");
  const [failure, setFailure] = useState<Failure | null>(null);
  const [connection, setConnection] = useState("");
  const [panel, setPanel] = useState<"materials" | "contents" | "settings" | null>(null);
  const [largeText, setLargeText] = useState(false);
  const [newContent, setNewContent] = useState(false);
  const [editingNoteId, setEditingNoteId] = useState<string | null>(null);
  const [editDraft, setEditDraft] = useState("");
  const [editBaseRevision, setEditBaseRevision] = useState<number | null>(null);
  const [noteError, setNoteError] = useState("");
  const [noteConflict, setNoteConflict] = useState<SourceNote | null>(null);
  const [editingProgressId, setEditingProgressId] = useState<string | null>(null);
  const [progressDraft, setProgressDraft] = useState("");
  const [progressBaseRevision, setProgressBaseRevision] = useState<number | null>(null);
  const [progressConflict, setProgressConflict] = useState<ReadingProgressEntry | null>(null);
  const [progressError, setProgressError] = useState("");
  const stream = useRef<HTMLElement>(null);
  const dialog = useRef<HTMLDialogElement>(null);
  const composer = useRef<HTMLTextAreaElement>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const follow = useRef(true);
  const revision = useRef(-1);
  const session = useRef<string | undefined>(undefined);
  const displayedSource = useRef<string | undefined>(undefined);
  const epoch = useRef(0);
  const locked = useRef(false);
  const alive = useRef(true);
  const draftRef = useRef(draft); draftRef.current = draft;

  function clearSessionUI() {
    epoch.current += 1;
    setDraft(""); setUploads([]); setReference(null); setReviewChunk(null); setFailure(null); setPanel(null);
    setDiscussionFocus(null);
    setNewContent(false); setEditingNoteId(null); setEditDraft(""); setEditBaseRevision(null); setNoteError(""); setNoteConflict(null);
    setEditingProgressId(null); setProgressDraft(""); setProgressBaseRevision(null); setProgressConflict(null); setProgressError(""); follow.current = true;
  }
  function accept(value: ReadingWindow) {
    if (!alive.current || (value.revision !== undefined && value.revision < revision.current)) return;
    if (session.current && value.sessionId && value.sessionId !== session.current) clearSessionUI();
    if (displayedSource.current && value.source.sourceId !== displayedSource.current) clearSessionUI();
    session.current = value.sessionId;
    displayedSource.current = value.source.sourceId;
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
    alive.current = true; epoch.current += 1; revision.current = -1; session.current = undefined; displayedSource.current = undefined;
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
  useEffect(() => { setReviewChunk(null); }, [view?.source.sourceId, view?.readingRevision]);
  const agent = view?.agent;
  const active = !!agent?.run && ["running", "approval", "stopping"].includes(agent.run.status);
  const uploading = uploads.some(u => u.state === "uploading");
  const blocked = active || !!operation;
  const chunks = view ? [...view.history, ...(current ? [current] : [])] : [];
  const displayed = reviewChunk ?? current;
  const entries = [
    ...(displayed ? [{ kind: "reading" as const, chunk: displayed }] : []),
    ...(view?.conversation ?? []).map(message => ({ kind: "message" as const, messageId: message.messageId })),
  ];
  const visibleChunks = entries.flatMap(e => e.kind === "reading" ? [e.chunk] : []);
  const focusedIndex = displayed && !active && discussionFocus !== chunkKey(displayed) ? 0 : entries.length - 1;
  const displayEmpty = view?.status === "empty" && entries.length === 0;
  const contentVersion = `${view?.sessionId}:${displayed?.chunkId}:${entries.length}:${view?.conversation.map(m => m.content).join('\n')}:${displayed?.translation?.length}`;
  function settle() {
    const pane = stream.current;
    if (!pane) return;
    if (!mist) { pane.scrollTop = pane.scrollHeight; return; }
    const target = pane.querySelector<HTMLElement>('[data-current-output="true"]');
    if (!target) return;
    const area = pane.getBoundingClientRect(), box = target.getBoundingClientRect();
    const top = pane.scrollTop + box.top - area.top - Math.max(24, (pane.clientHeight - box.height) / 2);
    pane.scrollTo?.({ top, behavior: globalThis.matchMedia?.("(prefers-reduced-motion: reduce)").matches ? "instant" : "smooth" });
  }
  useLayoutEffect(() => {
    const pane = stream.current;
    if (!pane) return;
    if (follow.current) {
      settle();
      setNewContent(false);
    } else setNewContent(true);
  }, [contentVersion, focusedIndex, visible, fontSize, collapsed]);
  useEffect(() => {
    const pane = stream.current;
    if (!mist || !pane || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(() => { if (follow.current && visible) settle(); });
    const content = pane.querySelector(".focus-content");
    if (content) observer.observe(content);
    return () => observer.disconnect();
  }, [mist, visible, view !== null]);

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
    setDiscussionFocus(displayed ? chunkKey(displayed) : null);
    follow.current = true;
    const selected = reference ?? reviewChunk;
    const attachmentIds = (includeAttachments ? uploads : []).flatMap(u => u.attachment ? [u.attachment.attachmentId] : []);
    const sentUploads = (includeAttachments ? uploads : []).filter(u => u.state === "ready").map(u => u.id);
    const input: SendReaderMessageInput = {
      sessionId: view.sessionId, receipt: selected ? { sourceId: selected.sourceId, planId: selected.planId, chunkId: selected.chunkId } : visibleChunks.some(c => current && chunkKey(c) === chunkKey(current)) ? cursorReceipt(view) : null,
      content: content.trim(), attachmentIds,
      sourceId: selected?.sourceId ?? (view.source.sourceId || undefined),
    };
    void perform("发送", () => {
      input.requestId ??= createReaderId();
      return host.sendMessage(input);
    }, () => {
      if (clear && draftRef.current === content) setDraft("");
      setUploads(old => old.filter(u => !sentUploads.includes(u.id)));
      setReference(null); setPanel(null);
    });
  }
  function next() {
    if (!view || !current || blocked || reviewChunk || current.index === current.total) return;
    const input: ContinueReadingInput = { receipt: cursorReceipt(view)!, sessionId: view.sessionId };
    void perform("下一段", () => {
      input.requestId ??= createReaderId();
      return host.continueReading(input);
    }, () => { setReference(null); setDiscussionFocus(null); });
  }
  function reset() {
    if (!host.newSession || !view?.sessionId || blocked) return;
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
  async function upload(file: File, id: string = createReaderId()) {
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
  function finish() {
    if (!view || !current || blocked || reviewChunk || current.index !== current.total || !host.finishReading) return;
    const input = { receipt: cursorReceipt(view)!, sessionId: view.sessionId, requestId: createReaderId() };
    void perform("完成本篇", () => host.finishReading!(input), () => setReference(null));
  }
  function reread() {
    if (!view || blocked || !host.rereadReading || view.readingRevision === undefined) return;
    const chunk = current ?? view.history.at(-1);
    if (!chunk) return;
    const input = { receipt: { sourceId: chunk.sourceId, planId: chunk.planId,
      chunkId: current?.chunkId ?? null, readingRevision: view.readingRevision },
      sessionId: view.sessionId, requestId: createReaderId() };
    void perform("从头重读", () => host.rereadReading!(input), () => { setReviewChunk(null); setReference(null); });
  }
  async function changeNote(note: SourceNote, action: "edit" | "delete" | "undo", expectedRevision = note.revision) {
    if (!host.changeSourceNote || !view) return;
    const content = action === "edit" ? editDraft : undefined;
    const result = await host.changeSourceNote(note.sourceId, note.noteId, action, expectedRevision, createReaderId(), content);
    if (!result.ok) { setNoteError(result.error.message); return; }
    accept(result.value);
    const outcome = result.value.noteOperation;
    if (outcome?.status === "conflict") {
      setNoteConflict(outcome.current ?? null);
      setNoteError("笔记已由另一处修改；你的输入仍在，可查看新版后重新提交。");
    } else {
      setEditingNoteId(null); setEditDraft(""); setEditBaseRevision(null); setNoteConflict(null); setNoteError("");
    }
  }
  async function changeProgress(entry: ReadingProgressEntry, action: "edit" | "delete", expectedRevision = entry.revision) {
    if (!host.changeReadingProgress) return;
    const result = await host.changeReadingProgress(entry.progress_id, action, expectedRevision,
      createReaderId(), action === "edit" ? progressDraft : undefined);
    if (!result.ok) { setProgressError(result.error.message); return; }
    accept(result.value);
    if (result.value.progressOperation?.status === "conflict") {
      setProgressConflict(result.value.progressOperation.current ?? null);
      setProgressError("阅读记录已改变；输入已保留，请查看当前版本后重新提交。");
    } else {
      setEditingProgressId(null); setProgressDraft(""); setProgressBaseRevision(null);
      setProgressConflict(null); setProgressError("");
    }
  }
  function referenceChunk(chunk: ReaderChunk) { setReference(chunk); setCollapsed(false); requestAnimationFrame(() => composer.current?.focus({ preventScroll: true })); }
  function review(chunk: ReaderChunk) {
    setDiscussionFocus(null);
    setPanel(null);
    if (current && chunk.chunkId === current.chunkId) { setReviewChunk(null); return; }
    if (!host.reviewChunk) { setReviewChunk(chunk); return; }
    void perform("回看", () => host.reviewChunk!(chunk.sourceId, chunk.planId, chunk.chunkId), () => {
      setReviewChunk(chunk); setReference(null); follow.current = true;
    });
  }

  const outline = view?.outline ?? Array.from({ length: current?.total ?? chunks.at(-1)?.total ?? 0 }, (_, i) => ({ chunkId: `chunk-${String(i + 1).padStart(3, "0")}`, index: i + 1, sectionPath: [] as string[] }));
  const progressEntries = view?.readingProgress ?? [];
  return <div className={`focus-reader${mist ? " focus-mist" : ""}`} data-font-size={fontSize} data-large-text={largeText || fontSize === "large" || fontSize === "extra"} data-composer-collapsed={collapsed}>
    {mist && <aside className="mist-sidebar" aria-label="阅读进度与操作">
      <div className="mist-progress-label"><span>阅读进度</span><span>{view?.status === "completed" ? "已读完" : `${current?.index ?? 0} / ${current?.total ?? 0}`}</span></div>
      <nav className="mist-outline" aria-label="段落目录">{outline.map(item => {
        const loaded = chunks.find(c => c.chunkId === item.chunkId);
        return <button key={item.chunkId} disabled={!loaded} aria-current={current?.chunkId === item.chunkId && !reviewChunk ? "step" : undefined}
          onClick={() => loaded && review(loaded)}><span>{String(item.index).padStart(2, "0")}</span><span className="focus-sr-only">{loaded?.sectionPath.at(-1) ?? item.sectionPath.at(-1) ?? "未读段落"}</span></button>;
      })}</nav>
    </aside>}
    {!mist && <header className="focus-header">
      <span className="focus-brand">FOCUS<span>.</span></span>
      <button className="focus-title" title={view?.source.title} onClick={() => setPanel("materials")}>{view?.source.sourceId ? view.source.title : "阅读工作台"}</button>
      <nav aria-label="阅读操作">
        <button onClick={() => setPanel("materials")}>材料</button>
        <button onClick={() => setPanel("contents")}>目录</button>
        <button onClick={() => setPanel("settings")}>设置</button>
        <button className="focus-new" disabled={!host.newSession || !view || blocked} onClick={reset}>新建会话</button>
      </nav>
    </header>}
    <main className="focus-stream" ref={stream} aria-label="阅读与对话" tabIndex={0} onWheel={() => { if (mist) follow.current = false; }} onTouchStart={() => { if (mist) follow.current = false; }} onKeyDown={e => { if (mist && ["PageUp", "PageDown", "Home", "End", "ArrowUp", "ArrowDown"].includes(e.key)) follow.current = false; }} onScroll={() => {
      if (mist) return;
      const el = stream.current!;
      follow.current = el.scrollHeight - el.scrollTop - el.clientHeight < 100;
      if (follow.current) setNewContent(false);
    }}>
      <div className="focus-content">
        {!view && <p role="status">{connection ? "暂时无法连接" : "正在打开…"}</p>}
        {reviewChunk && <p className="focus-review-banner">正在回看第 {reviewChunk.index} 段 · 正式位置未改变 <button onClick={() => { setReviewChunk(null); setReference(null); }}>返回当前阅读</button></p>}
        {view && displayEmpty && <section className="focus-start">
          <span className="focus-start__label" aria-hidden="true">▤</span>
          <h1>{view.readingUnavailable ? view.source.title : view.source.sourceId ? `讨论 ${view.source.title}` : "打开一份材料"}</h1>
          {view.readingUnavailable && <p role="status">{view.readingUnavailable}</p>}
          <div><button className="focus-primary" onClick={() => setPanel("materials")}>打开材料</button>
            {!mist && host.upload && <button onClick={() => fileInput.current?.click()}>上传</button>}
            {(current || view.history.length > 0) && host.resumeReading && <button onClick={resume} disabled={blocked}>恢复阅读</button>}</div>
        </section>}
        {entries.map((e, index) => {
          const message = e.kind === "message" ? view?.conversation.find(m => m.messageId === e.messageId) : null;
          const content = e.kind === "reading" ? <ReadingChunk chunk={e.chunk} onReference={referenceChunk} /> : message ? <ReaderConversation messages={[message]} /> : null;
          return <div key={e.kind === "reading" ? chunkKey(e.chunk) : e.messageId} className="focus-output" data-current-output={index === focusedIndex}
            style={mist ? { "--depth-opacity": Math.max(.38, 1 - Math.abs(focusedIndex - index) * .18) } as CSSProperties : undefined}>{content}</div>;
        })}
        {view?.status === "completed" && !reviewChunk && <div className="focus-finished">已完成本篇 <button disabled={!host.rereadReading || blocked} onClick={reread}>从头重读</button><button onClick={() => setPanel("contents")}>查看已读段落</button></div>}
      </div>
    </main>
    {mist && <nav className="mist-history-rail" aria-label="历史提问">{view?.conversation.filter(m => m.role === "user").map(m => <button key={m.messageId} aria-label={m.content} onClick={() => {
      follow.current = false;
      const target = Array.from(stream.current?.querySelectorAll<HTMLElement>("[data-message-id]") ?? []).find(el => el.dataset.messageId === m.messageId);
      target?.scrollIntoView({ block: "center", behavior: "instant" });
    }}><span className="mist-history-line" /><span className="mist-history-label">{m.content}</span></button>)}</nav>}
    <div className="focus-bottom" role={mist ? "complementary" : undefined} aria-label={mist ? "阅读助手" : undefined}>


      {newContent && <button className="focus-new-content" onClick={() => {
        follow.current = true; setNewContent(false); settle();
      }}>{mist ? "查看新内容" : "有新内容 · 回到底部 ↓"}</button>}
      <div className="focus-composer-wrap">
        {view?.noteFeedback && <p role="status" className="focus-note-feedback">{view.noteFeedback.status === "saved" ? "已记下" : "未保存，可重试"}</p>}
        {view?.source.sourceId && view.sourceNotes && <details className="focus-source-notes"><summary>笔记 · {view.sourceNotes.filter(note => !note.deleted).length}</summary>
          {noteError && <p role="alert">{noteError}</p>}
          {view.sourceNotes.length === 0 ? <p>明确说“记下来”后，笔记会保存在这篇材料下。</p> :
            <ol>{view.sourceNotes.filter(note => !note.deleted || note.canUndo).map(note => <li key={note.noteId}>
              {editingNoteId === note.noteId ? <div><textarea aria-label="编辑笔记" value={editDraft} onChange={event => setEditDraft(event.target.value)} />
                {noteConflict && <p>已保存版本：{noteConflict.content}</p>}
                {noteConflict ? <button disabled={!editDraft.trim()} onClick={() => void changeNote(note, "edit", noteConflict.revision)}>重新提交</button> :
                  <button disabled={!editDraft.trim()} onClick={() => void changeNote(note, "edit", editBaseRevision ?? note.revision)}>保存修改</button>}
                <button onClick={() => { setEditingNoteId(null); setEditBaseRevision(null); setNoteConflict(null); setNoteError(""); }}>取消</button></div> :
                <><span>{note.deleted ? "已删除，可撤销" : note.content}</span>
                  {!note.deleted && <button onClick={() => { setEditingNoteId(note.noteId); setEditDraft(note.content); setEditBaseRevision(note.revision); setNoteConflict(null); setNoteError(""); }}>编辑</button>}
                  {note.canUndo && <button onClick={() => void changeNote(note, "undo")}>撤销</button>}

                </>}
            </li>)}</ol>}
        </details>}
        {view?.source.sourceId && view.readingProgress && <details className="focus-source-notes"><summary>阅读记录 · {progressEntries.filter(entry => !entry.deleted).length}</summary>
          {progressError && <p role="alert">{progressError}</p>}
          {progressEntries.length === 0 ? <p>推进或完成本篇后，此处显示已读记录。</p> : <ol>{progressEntries.map(entry =>
            <li key={entry.progress_id}>
              <small>第 {entry.reading_pass} 轮 · {entry.chunk_id}</small>
              {editingProgressId === entry.progress_id ? <div>
                <textarea aria-label="更正阅读记录" value={progressDraft} onChange={event => setProgressDraft(event.target.value)} />
                {progressConflict && <p>当前版本：{progressConflict.topic ?? progressConflict.fact}</p>}
                <button disabled={!progressDraft.trim()} onClick={() => void changeProgress(entry, "edit", progressConflict?.revision ?? progressBaseRevision ?? entry.revision)}>{progressConflict ? "重新提交" : "保存更正"}</button>
                <button onClick={() => { setEditingProgressId(null); setProgressConflict(null); setProgressError(""); }}>取消</button>
              </div> : <>
                <span>{entry.deleted ? "已删除" : [entry.fact, entry.topic, entry.user_understanding].filter(Boolean).join(" · ")}</span>
                {!entry.deleted && <button onClick={() => { setEditingProgressId(entry.progress_id); setProgressDraft(entry.topic ?? entry.fact); setProgressBaseRevision(entry.revision); setProgressConflict(null); setProgressError(""); }}>更正</button>}
                {!entry.deleted && <button onClick={() => void changeProgress(entry, "delete")}>删除</button>}
                {!entry.deleted && ["pending", "failed", "interrupted"].includes(entry.status) && host.retryReadingProgress &&
                  <button onClick={() => void perform("补记", () => host.retryReadingProgress!(entry.progress_id, createReaderId()))}>补记</button>}
                {!entry.deleted && entry.status === "generating" && <small>整理中…</small>}
                {!entry.deleted && entry.status === "generating" && host.cancelReadingProgress &&
                  <button onClick={() => void perform("停止补记", () => host.cancelReadingProgress!(entry.progress_id))}>停止补记</button>}
                {!entry.deleted && (entry.status === "failed" || entry.status === "interrupted") && <small>生成未完成，已读位置不受影响。</small>}
              </>}
            </li>)}</ol>}
        </details>}
        {mist && <button className="mist-composer-toggle" aria-expanded={!collapsed} onClick={() => setCollapsed(!collapsed)}>{collapsed ? "展开" : "收起"}</button>}
        {connection && <div className="focus-error" role="alert">{connection}<button onClick={() => void reconnect()}>重新连接</button></div>}
        {failure && <div className="focus-error" role="alert">{failure.message}<button disabled={!!operation} onClick={failure.retry}>{failure.label}</button><button aria-label="关闭错误" onClick={() => setFailure(null)}>×</button></div>}
        {operation && !active && <p className="focus-operation" role="status">{operation === "下一段" ? "正在打开下一段…" : `${operation}中…`}</p>}
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
        <form hidden={mist && collapsed} className="focus-composer" onSubmit={e => { e.preventDefault(); send(); }}>
          <label className="focus-sr-only" htmlFor="focus-question">输入问题或阅读需求</label>
          <textarea id="focus-question" ref={composer} rows={mist ? 1 : 2} disabled={blocked} value={draft} placeholder="问问这段原文…"
            onChange={e => setDraft(e.target.value)} onKeyDown={e => {
              if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); send(); }
            }} />
          <div className="focus-composer__actions">
            <div>{!mist && host.upload && <><input ref={fileInput} className="focus-sr-only" aria-label="选择论文文件" type="file" accept=".pdf,.html" multiple onChange={e => {
              Array.from(e.target.files ?? []).forEach(f => void upload(f)); e.target.value = "";
            }} /><button type="button" onClick={() => fileInput.current?.click()} aria-label="添加附件">＋ 附件</button></>}
              {uploads.some(u => u.state === "ready") && <button type="button" disabled={blocked || uploading} onClick={() => send("请阅读附件", false)}>阅读附件</button>}
            </div>
            <button type="submit" className="focus-primary" disabled={!view || blocked || uploading || !draft.trim()}>{operation === "发送" ? "发送中…" : "发送 ↑"}</button>
          </div>
        </form>
        {!mist && current && !reviewChunk && <div className="focus-next"><button disabled={blocked} onClick={current.index === current.total ? finish : next}>{current.index === current.total ? "完成本篇" : operation === "下一段" ? "正在打开…" : "下一段 →"}</button></div>}
      </div>
    </div>
    {mist && <footer className="mist-reading-actions"><span title={view?.source.title}>{view?.source.title || "阅读工作台"}</span><button onClick={() => setPanel("materials")}>材料</button><button disabled={!host.newSession || !view || blocked} onClick={reset}>新会话</button>{view?.sessionFresh && host.resumeReading && <button disabled={blocked} onClick={resume}>恢复</button>}{reviewChunk ? <button onClick={() => { setReviewChunk(null); setReference(null); }}>返回当前阅读</button> : current ? <button className="focus-reader__continue" disabled={blocked} onClick={() => { follow.current = true; current.index === current.total ? finish() : next(); }}>{current.index === current.total ? "完成本篇" : operation === "下一段" ? "打开中" : "继续"}</button> : null}</footer>}
    <dialog ref={dialog} className="focus-dialog" onCancel={() => setPanel(null)} onClick={e => { if (e.target === dialog.current) setPanel(null); }}>
      <header><h2>{panel === "materials" ? "材料" : panel === "contents" ? "已加载段落" : "阅读设置"}</h2><button aria-label="关闭" onClick={() => setPanel(null)}>×</button></header>
      {panel === "materials" && <>
        {view?.source.sourceId && <p className="focus-full-title">{view.source.title}</p>}
        {!mist && host.upload && <button onClick={() => { setPanel(null); fileInput.current?.click(); }}>上传</button>}
        {agent?.catalog.sources.length ? <section><h3>来源</h3>{agent.catalog.sources.map(s => <button className="focus-material" disabled={blocked} key={s.sourceId} onClick={() => { follow.current = true; if (host.openSource) void perform("加载材料", () => host.openSource!(s.sourceId), () => setPanel(null)); else send(`开始阅读 Source ${s.sourceId}`, false, false); }}>{s.title}</button>)}</section> : <p>暂无已保存的材料。</p>}
        {!!agent?.catalog.topics.length && <section><h3>专题</h3>{agent.catalog.topics.map(t => <button className="focus-material" disabled={blocked} key={t.topicId} onClick={() => send(`开始阅读 Topic ${t.topicId}`, false, false)}>{t.title}</button>)}</section>}
      </>}
      {panel === "contents" && <nav aria-label="已读段落">{chunks.length ? chunks.map(c => <button className="focus-material" key={chunkKey(c)} onClick={() => review(c)}>第 {c.index} 段 · {c.sectionPath.at(-1)}</button>) : <p>打开材料后显示。</p>}</nav>}
      {panel === "settings" && <label><input type="checkbox" checked={largeText} onChange={e => setLargeText(e.target.checked)} /> 使用较大正文字号</label>}
    </dialog>
  </div>;
}
