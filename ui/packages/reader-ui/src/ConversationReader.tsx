import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, type CSSProperties } from "react";
import { createReaderId, type ReaderHost, type ReaderHostResult, type ReaderMessage, type ReadingDocument, type ReadingOpening, type ReadingWindow, type ValidatedAnswerEvidence } from "@focus/reader-contracts";
import { MarkdownContent } from "./MarkdownContent";
import { projectEvidence } from "./source-evidence";
import type { RenderMark } from "./rehype-annotations";
import { readingFontSizes } from "./typography";
import { AgentControls } from "./AgentControls";
import { AssetInstanceContext } from "./asset-context";
import "./conversation-reader.css";

const safeRead = (key: string) => { try { return localStorage.getItem(key); } catch { return null; } };
const safeWrite = (key: string, value: string) => { try { localStorage.setItem(key, value); } catch { /* Session remains usable. */ } };
const reduced = () => window.document.documentElement.dataset.reducedMotion === "true" || typeof matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").matches;
export function messageEvidence(message: ReaderMessage, document: ReadingDocument, discussionId?: string) {
  return (message.evidence ?? []).filter(e => e.sourceId === document.sourceId && e.bundleVersion === document.bundleVersion &&
    e.messageId === message.messageId && e.discussionId === discussionId && e.answerRevision === message.answerRevision &&
    message.content.includes(`[[e:${e.evidenceId}]]`));
}
export function citedMarkdown(message: ReaderMessage, evidence: readonly ValidatedAnswerEvidence[]) {
  return message.content.replace(/\[\[e:([0-9a-f]{24})\]\]/g, (_, id: string) => {
    const e = evidence.find(e => e.evidenceId === id);
    return e ? `[${e.displayNumber}](#e-${id})` : "〔原文证据不可定位〕";
  }).replace(/\[\[e:[^\]]*$/, "");
}

type FullscreenControls = { fullscreen?: boolean; onFullscreenChange?: (next: boolean) => void };

export function ConversationReader({ host, visible = true, fontSize = "standard", ...fullscreenControls }: { host: ReaderHost; visible?: boolean; fontSize?: string } & FullscreenControls) {
  const [view, setView] = useState<ReadingWindow | null>(null), [error, setError] = useState("");
  const acceptView = useCallback((next: ReadingWindow) => setView(previous => previous && previous.workspace?.instanceId === next.workspace?.instanceId && (previous.revision ?? 0) > (next.revision ?? 0) ? previous : next), []);
  useEffect(() => {
    let live = true;
    const receive = (r: ReaderHostResult<ReadingWindow>) => { if (live) { if (r.ok) acceptView(r.value); else setError(r.error.message); } };
    void host.getReadingWindow().then(receive).catch(e => { if (live) setError(String(e)); });
    const off = host.subscribe?.(receive);
    return () => { live = false; off?.(); };
  }, [host]);
  if (!view) return <div className="conversation-reader" role="status">{error || "加载中…"}</div>;
  if (!view.source.sourceId) return <div className="conversation-reader" />;
  return <AssetInstanceContext.Provider value={view.workspace?.instanceId}><ReadingSurface key={`${view.workspace?.instanceId}:${view.source.sourceId}:${view.sourceBundleVersion ?? ""}:${view.sourceGeneration ?? view.resetVersion ?? 0}`} {...fullscreenControls} host={host} view={view} setView={acceptView} visible={visible} fontSize={fontSize} /></AssetInstanceContext.Provider>;
}

function ReadingSurface({ host, view, setView, visible, fontSize, fullscreen, onFullscreenChange }: { host: ReaderHost; view: ReadingWindow; setView: (v: ReadingWindow) => void; visible: boolean; fontSize: string } & FullscreenControls) {
  const sourceId = view.source.sourceId!;
  const [document, setDocument] = useState<ReadingDocument | null>(null), [opening, setOpening] = useState<ReadingOpening | null>(null);
  const [error, setError] = useState(""), [reload, setReload] = useState(0), [sending, setSending] = useState(false);
  const [selection, setSelection] = useState("");
  const [noteEdit, setNoteEdit] = useState<{ id: string; revision: number } | null>(null);
  const [noteDraft, setNoteDraft] = useState("");
  const [hoverEvidence, setHoverEvidence] = useState<string | undefined>();
  const [activeMessage, setActiveMessage] = useState<string | null>(null), [activeEvidence, setActiveEvidence] = useState<string | undefined>();
  const [mobile, setMobile] = useState("chat"), [guideOpen, setGuideOpen] = useState(true), [notesOpen, setNotesOpen] = useState(false);
  const [share, setShare] = useState(() => Math.max(40, Math.min(70, Number(safeRead("focus.sourceShare")) || 60)));
  const scope = `${view.workspace?.workspaceId ?? "local"}:${sourceId}:${view.sourceGeneration ?? view.resetVersion ?? 0}`;
  const draftKey = `focus.sourceDraft:${scope}:${view.discussionId ?? ""}`;
  const [draft, setDraft] = useState(() => safeRead(draftKey) ?? "");
  const original = useRef<HTMLDivElement>(null), chat = useRef<HTMLDivElement>(null), shell = useRef<HTMLDivElement>(null);
  const sendRequest = useRef<{ content: string; id: string } | null>(null);
  const sendBusy = useRef(false);
  const composer = useRef<HTMLTextAreaElement>(null), returnFocus = useRef<{ messageId: string; evidenceId: string } | null>(null);
  const manual = useRef(false), followChat = useRef(true), turn = useRef<{ seen: Set<string>; cancelled: boolean; located: boolean } | null>(null);
  const jumpOrigin = useRef<number | null>(null);
  const [cardAtTop, setCardAtTop] = useState(false);
  const [returnPosition, setReturnPosition] = useState<number | null>(null);
  const scrollAnimation = useRef<number | null>(null);
  useEffect(() => () => { if (scrollAnimation.current !== null) cancelAnimationFrame(scrollAnimation.current); }, []);
  const restored = useRef(false), bookmark = document ? `focus.sourceBookmark:${scope}:${document.bundleVersion}` : "";
  useEffect(() => { setDraft(safeRead(draftKey) ?? ""); setActiveMessage(safeRead(`focus.activeAnswer:${draftKey}`)); setActiveEvidence(undefined); turn.current = null; }, [draftKey]);
  useEffect(() => {
    let live = true, timer: ReturnType<typeof setTimeout>;
    setError("");
    void host.getSourceDocument!(sourceId).then(r => { if (live) { if (r.ok) setDocument(r.value); else setError(r.error.message); } }).catch(e => { if (live) setError(String(e)); });
    async function loadOpening(prepare: boolean) {
      try {
        const result = await host.getSourceOpening?.(sourceId, prepare);
        if (!live || !result) return;
        if (!result.ok) { setOpening(null); setError(result.error.message); return; }
        setOpening(result.value);
        if (result.value.status === "running") timer = setTimeout(() => void loadOpening(false), 1500);
      } catch (e) { if (live) setError(String(e)); }
    }
    void loadOpening(true);
    return () => { live = false; clearTimeout(timer); };
  }, [host, sourceId, reload]);
  const messages = view.conversation.filter(m => !m.sourceDeleted && (!m.sourceId || m.sourceId === sourceId));
  const latest = messages.filter(m => m.role === "assistant").at(-1);
  const selected = messages.find(m => m.messageId === activeMessage) ?? latest;
  const validated = document && selected ? messageEvidence(selected, document, view.discussionId) : [];
  // Revisions gate validity above; token-only changes must not reparse the full source.
  const evidenceKey = JSON.stringify(validated.map(e => [e.evidenceId, e.sourceId, e.bundleVersion, e.sourceLines, e.quote, e.displayNumber]));
  const evidence = useMemo(() => validated, [evidenceKey]);
  const sourceInput = useMemo(() => document ? { document, evidence, active: hoverEvidence ?? activeEvidence } : undefined, [document, evidence, hoverEvidence, activeEvidence]);
  const projections = useMemo(() => document ? projectEvidence(document, evidence) : [], [document, evidence]);
  const annotationKey = JSON.stringify([view.sourceHighlights, view.sourceNotes]);
  const permanentMarks = useMemo(() => {
    if (!document) return [];
    const annotations = [
      ...(view.sourceHighlights ?? []).filter(h => !h.deleted && !h.sourceUpdated && h.layer === "source").map(h => ({ id: h.highlightId, quote: h.quote, lines: h.sourceLines, bundle: h.bundle, highlight: true })),
      ...(view.sourceNotes ?? []).filter(n => !n.deleted && !n.sourceUpdated && n.sentence?.layer === "source" && (n.anchor ?? n.placement)).map(n => ({ id: n.noteId, quote: n.sentence!.quote, lines: (n.anchor ?? n.placement)!.sourceLines, bundle: n.bundle, highlight: false })),
    ];
    return annotations.flatMap(a => {
      const projected = projectEvidence(document, [{ evidenceId: a.id, sourceId, bundleVersion: a.bundle, messageId: "", discussionId: "", answerRevision: "", displayNumber: 0, sourceLines: a.lines, quote: a.quote, relation: "context" }])[0];
      return projected.kind === "exact" ? [{ key: a.id, start: projected.start!, end: projected.end!, ...(a.highlight ? { highlightId: a.id } : { noteId: a.id }), ariaLabel: a.highlight ? "重点" : "备注" } satisfies RenderMark] : [];
    });
  }, [document, annotationKey]);
  const active = projections.find(p => p.evidence.evidenceId === activeEvidence);
  const running = !!view.agent?.run && ["running", "approval", "stopping"].includes(view.agent.run.status);
  function cancelAuto() { jumpOrigin.current = null; setReturnPosition(null); if (scrollAnimation.current !== null) { cancelAnimationFrame(scrollAnimation.current); scrollAnimation.current = null; } manual.current = true; if (turn.current) turn.current.cancelled = true; original.current?.scrollTo({ top: original.current.scrollTop, behavior: "instant" }); }
  function target(id: string) { return original.current?.querySelector<HTMLElement>(`[data-evidence-ids~="${id}"], [data-evidence-block~="${id}"]`); }
  function moveTo(id: string, keyboard = false, automatic = false) {
    const el = target(id), pane = original.current;
    if (!el || !pane) return;
    if (jumpOrigin.current === null) { jumpOrigin.current = pane.scrollTop; setReturnPosition(pane.scrollTop); }
    manual.current = false; setActiveEvidence(id);
    if (!automatic) setMobile("original");
    if (scrollAnimation.current !== null) cancelAnimationFrame(scrollAnimation.current);
    const targetRect = el.getBoundingClientRect(), paneRect = pane.getBoundingClientRect();
    const visibleTarget = targetRect.top >= paneRect.top && targetRect.bottom <= paneRect.bottom;
    setCardAtTop(automatic && visibleTarget && targetRect.bottom > paneRect.bottom - 200);
    if (automatic && visibleTarget) return;
    const from = pane.scrollTop;
    const to = Math.max(0, Math.min(pane.scrollHeight - pane.clientHeight, from + el.getBoundingClientRect().top - pane.getBoundingClientRect().top - pane.clientHeight * .32));
    if (keyboard || reduced() || Math.abs(to - from) > pane.clientHeight * 1.2) pane.scrollTo({ top: to, behavior: "instant" });
    else {
      const started = performance.now();
      const duration = parseFloat(getComputedStyle(pane).getPropertyValue("--reader-duration-move")) || 240;
      const tick = (now: number) => { const t = Math.min(1, (now - started) / duration); pane.scrollTop = from + (to - from) * (1 - Math.pow(1 - t, 3)); scrollAnimation.current = t < 1 ? requestAnimationFrame(tick) : null; };
      scrollAnimation.current = requestAnimationFrame(tick);
    }
    if (keyboard) { el.tabIndex = -1; el.focus({ preventScroll: true }); }
  }
  const pendingJump = useRef<{ id: string; keyboard: boolean } | null>(null);
  useLayoutEffect(() => { if (pendingJump.current) { const jump = pendingJump.current; pendingJump.current = null; moveTo(jump.id, jump.keyboard); } }, [evidence, mobile]);
  function cite(message: ReaderMessage, id: string, keyboard: boolean) {
    cancelAuto(); returnFocus.current = { messageId: message.messageId, evidenceId: id };
    pendingJump.current = { id, keyboard }; safeWrite(`focus.activeAnswer:${draftKey}`, message.messageId); setActiveMessage(message.messageId); setActiveEvidence(id); setMobile("original");
    if (selected?.messageId === message.messageId) requestAnimationFrame(() => { if (pendingJump.current) { pendingJump.current = null; moveTo(id, keyboard); } });
  }
  useLayoutEffect(() => {
    if (!document || !original.current || restored.current) return;
    restored.current = true;
    try {
      const raw = safeRead(bookmark);
      const saved = raw ? JSON.parse(raw) : view.readingStarted && view.navigationCurrent?.bundleVersion === document.bundleVersion ? { line: view.navigationCurrent.sourceLines[0], offset: 0 } : null;
      if (saved && Number.isSafeInteger(saved.line) && Number.isFinite(saved.offset)) {
        const el = original.current.querySelector<HTMLElement>(`[data-source-line="${saved.line}"]`);
        if (el) original.current.scrollTop += el.getBoundingClientRect().top - original.current.getBoundingClientRect().top + saved.offset;
      }
    } catch { /* Ignore malformed display bookmarks, never mutate the Cursor. */ }
  }, [document, bookmark]);
  useEffect(() => {
    const pending = turn.current;
    if (!pending || pending.located || pending.cancelled || !latest || pending.seen.has(latest.messageId) || !evidence.length) return;
    const first = projections.find(p => p.kind !== "unavailable");
    if (first && selected?.messageId === latest.messageId) { pending.located = true; if ((shell.current?.clientWidth ?? 0) >= 960) moveTo(first.evidence.evidenceId, false, true); }
  }, [latest, evidence, projections]);
  useLayoutEffect(() => { if (followChat.current && chat.current) chat.current.scrollTop = chat.current.scrollHeight; }, [messages.at(-1)?.content]);
  async function apply(operation: Promise<ReaderHostResult<ReadingWindow>>) {
    try { const r = await operation; if (r.ok) { setView(r.value); return true; } setError(r.error.message); } catch (e) { setError(String(e)); }
    return false;
  }
  async function send() {
    if (!draft.trim() || sendBusy.current || sending || running) return;
    sendBusy.current = true;
    const content = draft.trim(); safeWrite(`focus.activeAnswer:${draftKey}`, ""); setSending(true); setError(""); setActiveMessage(null); setActiveEvidence(undefined);
    followChat.current = true; turn.current = { seen: new Set(messages.map(m => m.messageId)), cancelled: false, located: false };
    if (sendRequest.current?.content !== content) sendRequest.current = { content, id: createReaderId() };
    const ok = await apply(host.sendMessage({ sourceId, sessionId: view.sessionId, receipt: null, content, requestId: sendRequest.current.id }));
    if (ok) { sendRequest.current = null; setDraft(current => { if (current === draft) { safeWrite(draftKey, ""); return ""; } return current; }); } else turn.current = null;
    sendBusy.current = false; setSending(false);
  }
  function backToAnswer(id: string) {
    cancelAuto(); setMobile("chat"); setActiveEvidence(id);
    requestAnimationFrame(() => { const el = chat.current?.querySelector<HTMLElement>(`[data-message-id="${selected?.messageId}"] [data-citation="${id}"]`); el?.scrollIntoView({ block: "nearest", behavior: reduced() ? "instant" : "smooth" }); el?.focus({ preventScroll: true }); });
  }
  return <section ref={shell} className="conversation-reader" data-fullscreen={!!fullscreen} data-mobile={mobile} data-font-size={fontSize} hidden={!visible} style={{ "--source-share": `${share}%`, "--source-font-size": `${readingFontSizes[fontSize as keyof typeof readingFontSizes] ?? 18}px` } as CSSProperties}
    onKeyDown={e => { if (e.key === "Escape") { setActiveEvidence(undefined); const previous = returnFocus.current; if (previous) requestAnimationFrame(() => chat.current?.querySelector<HTMLElement>(`[data-message-id="${previous.messageId}"] [data-citation="${previous.evidenceId}"]`)?.focus({ preventScroll: true })); } }}>
    <header className="source-reader-toolbar"><nav aria-label="阅读视图"><button onClick={() => setMobile(mobile === "chat" ? "original" : "chat")}>{mobile === "chat" ? "查看原文" : "返回对话"}</button></nav><div>{onFullscreenChange && !fullscreen && <button onClick={() => { setMobile("chat"); onFullscreenChange(true); }}>对话全屏</button>}{(view.discussions?.length ?? 0) > 1 && host.selectDiscussionSource && <select aria-label="对话记录" value={view.discussionId ?? ""} disabled={running} onChange={e => void apply(host.selectDiscussionSource!(sourceId, e.target.value))}>{view.discussions!.map((d, i) => <option key={d.discussionId} value={d.discussionId}>对话 {i + 1}</option>)}</select>}<button onClick={() => setNotesOpen(!notesOpen)} aria-pressed={notesOpen}>笔记</button>{host.completeSource && document && <button disabled={!!view.sourceCompletion} onClick={() => void apply(host.completeSource!(sourceId, document.bundleVersion, document.generation ?? 0, createReaderId()))}>{view.sourceCompletion ? "已读完" : "标记读完"}</button>}{host.newSession && view.sessionId && <button disabled={running} onClick={() => void apply(host.newSession!(view.sessionId!))}>新会话</button>}</div></header>
    {error && <div role="alert" className="source-reader-error">{error}<button onClick={() => setReload(v => v + 1)}>重试</button></div>}
    <div className="source-reader-columns">
      <div className="source-original-pane">
        <div ref={original} className="source-original" aria-label="文章原文" tabIndex={0} onWheel={cancelAuto} onTouchStart={cancelAuto} onPointerDown={cancelAuto} onKeyDown={e => { if (["PageDown", "PageUp", "ArrowDown", "ArrowUp", "Home", "End", " "].includes(e.key)) cancelAuto(); }}
          onScroll={() => { if (manual.current && bookmark && original.current) {
            const top = original.current.getBoundingClientRect().top;
            const block = [...original.current.querySelectorAll<HTMLElement>("[data-source-line]")].find(el => el.getBoundingClientRect().bottom > top);
            if (block) safeWrite(bookmark, JSON.stringify({ line: Number(block.dataset.sourceLine), offset: top - block.getBoundingClientRect().top }));
          } }}
          onMouseUp={() => { const selectedText = window.getSelection()?.toString().trim() ?? ""; if (selectedText) { cancelAuto(); setSelection(selectedText.slice(0, 4000)); } }}
          onClick={e => { const id = (e.target as HTMLElement).closest<HTMLElement>("[data-evidence]")?.dataset.evidence; if (id) backToAnswer(id); else if ((e.target as HTMLElement).closest("[data-anno-key], [data-anno-bulb]")) setNotesOpen(true); }}>
          {document ? <article><MarkdownContent text={document.markdown} sourceId={sourceId} marks={permanentMarks} sourceEvidence={sourceInput} /></article> : <span role="status">加载中…</span>}
        </div>
        {selection && <div className="source-selection-actions"><button onClick={() => { const next = `${draft ? draft + "\n\n" : ""}> ${selection.replace(/\n/g, "\n> ")}\n\n`; setDraft(next); safeWrite(draftKey, next); setSelection(""); setMobile("chat"); requestAnimationFrame(() => composer.current?.focus()); }}>引用</button><button onClick={() => { setNoteDraft(`「${selection}」\n`); setNotesOpen(true); setSelection(""); }}>记笔记</button><button aria-label="取消选择" onClick={() => setSelection("")}>×</button></div>}
        {active && <aside className="source-evidence-card" data-top={cardAtTop} aria-label="原文证据"><button aria-label="关闭证据" onClick={() => setActiveEvidence(undefined)}>×</button><button onClick={() => backToAnswer(active.evidence.evidenceId)}>证据 {active.evidence.displayNumber}{active.kind === "block" ? " · 段落定位" : active.kind === "unavailable" ? " · 不可定位" : ""}</button><p>{active.evidence.quote.exact}</p>{returnPosition !== null && <button onClick={() => { if (original.current && jumpOrigin.current !== null) { manual.current = false; original.current.scrollTo({ top: jumpOrigin.current, behavior: "instant" }); } jumpOrigin.current = null; setReturnPosition(null); setActiveEvidence(undefined); }}>返回阅读位置</button>}</aside>}
      </div>
      <div className="source-splitter" role="separator" aria-label="调整原文宽度" aria-orientation="vertical" aria-valuemin={40} aria-valuemax={70} aria-valuenow={share} tabIndex={0}
        onKeyDown={e => { if (["ArrowLeft", "ArrowRight"].includes(e.key)) { e.preventDefault(); const v = Math.max(40, Math.min(70, share + (e.key === "ArrowLeft" ? -2 : 2))); setShare(v); safeWrite("focus.sourceShare", String(v)); } }}
        onPointerDown={e => { e.currentTarget.setPointerCapture(e.pointerId); }} onPointerMove={e => { if (!e.currentTarget.hasPointerCapture(e.pointerId) || !shell.current) return; const rect = shell.current.getBoundingClientRect(); const v = Math.max(40, Math.min(70, (e.clientX - rect.left) / rect.width * 100)); setShare(v); safeWrite("focus.sourceShare", String(v)); }} onPointerUp={e => e.currentTarget.releasePointerCapture(e.pointerId)} />
      <div className="source-chat-pane">
        <div ref={chat} className="source-chat" aria-label="文章对话" onWheel={() => { if (turn.current) turn.current.cancelled = true; }} onScroll={() => { const el = chat.current!; followChat.current = el.scrollHeight - el.clientHeight - el.scrollTop < 64; if (!followChat.current && turn.current) turn.current.cancelled = true; }}>
          {opening?.status === "ready" && opening.bundleVersion === document?.bundleVersion && <section className="source-opening"><button className="source-guide-toggle" onClick={() => setGuideOpen(!guideOpen)} aria-expanded={guideOpen}>{guideOpen ? "收起导读" : "导读"}</button>{guideOpen && <><ul>{opening.structure?.map(n => <li key={n.id} data-child={!!n.parentId}><button onClick={() => { cancelAuto(); setMobile("original"); requestAnimationFrame(() => { const blocks = [...(original.current?.querySelectorAll<HTMLElement>("[data-source-line]") ?? [])]; const el = blocks.find(b => Number(b.dataset.sourceLine) >= n.sourceLines[0]); el?.scrollIntoView({ block: "start", behavior: reduced() ? "instant" : "smooth" }); }); }}>{n.title}</button></li>)}</ul><p>{opening.guide}</p></>}</section>}
          {opening?.status === "running" && <div className="source-opening-skeleton" aria-label="正在准备导读" role="status"><i /><i /><i /></div>}
          {opening?.status === "failed" && <p role="alert">{opening.error}<button onClick={() => setReload(v => v + 1)}>重试导读</button></p>}
          {messages.map(message => { const refs = document ? messageEvidence(message, document, view.discussionId) : []; return <section key={message.messageId} data-message-id={message.messageId} data-role={message.role} tabIndex={-1} className="source-message" onClick={() => { if (message.role === "assistant" && selected?.messageId !== message.messageId) { cancelAuto(); safeWrite(`focus.activeAnswer:${draftKey}`, message.messageId); setActiveMessage(message.messageId); setActiveEvidence(undefined); } }}>
            <MarkdownContent text={message.role === "assistant" ? citedMarkdown(message, refs) : message.content} onCitation={(id, keyboard) => cite(message, id, keyboard)} onCitationHover={id => { if (message.messageId === selected?.messageId) setHoverEvidence(id); }} />
          </section>; })}
        </div>
        <form className="source-composer" onSubmit={e => { e.preventDefault(); void send(); }}>
          {view.agent && (running || !!view.agent.run?.error) && <AgentControls agent={view.agent} onStop={() => { if (host.stop) void apply(host.stop()); }} onAnswer={input => host.approve ? apply(host.approve(input)) : Promise.resolve(false)} />}
          <textarea ref={composer} aria-label="输入消息" placeholder="输入消息…" value={draft} onChange={e => { setDraft(e.target.value); safeWrite(draftKey, e.target.value); }} onKeyDown={e => { if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); void send(); } }} />
          <button type="submit" disabled={sending || running || !draft.trim()} aria-label="发送">↑</button>
        </form>
      </div>
    </div>
    {notesOpen && <aside className="source-notes-drawer"><button onClick={() => setNotesOpen(false)} aria-label="关闭笔记">×</button><textarea aria-label="笔记内容" value={noteDraft} onChange={e => setNoteDraft(e.target.value)} />{host.createSourceNote && <button disabled={!noteDraft.trim()} onClick={async () => { const request = noteEdit && host.changeSourceNote ? host.changeSourceNote(sourceId, noteEdit.id, "edit", noteEdit.revision, createReaderId(), noteDraft.trim()) : host.createSourceNote!({ sourceId, requestId: createReaderId(), content: noteDraft.trim(), kind: "thought", origin: "user" });
        const result = await request; if (!result.ok) { setError(result.error.message); return; } setView(result.value);
        if (result.value.noteOperation?.status === "conflict") { setError("笔记已更新，请核对当前内容后再保存。"); if (result.value.noteOperation.current) setNoteEdit({ id: result.value.noteOperation.current.noteId, revision: result.value.noteOperation.current.revision }); return; }
        setNoteDraft(""); setNoteEdit(null); }}>保存笔记</button>}{(view.sourceNotes ?? []).filter(n => !n.deleted || n.canUndo).map(n => <article key={n.noteId}>{n.sentence && <blockquote>{n.sentence.quote.exact}</blockquote>}<MarkdownContent text={n.content} />{host.changeSourceNote && <>{!n.deleted && <button onClick={() => { setNoteEdit({ id: n.noteId, revision: n.revision }); setNoteDraft(n.content); }}>编辑</button>}<button onClick={() => void apply(host.changeSourceNote!(sourceId, n.noteId, n.deleted ? "undo" : "delete", n.revision, createReaderId()))}>{n.deleted ? "撤销删除" : "删除"}</button></>}</article>)}{(view.sourceHighlights ?? []).filter(h => !h.deleted || h.canUndo).map(h => <article key={h.highlightId}><blockquote>{h.quote.exact}</blockquote>{host.changeHighlight && <button onClick={() => void apply(host.changeHighlight!(sourceId, h.highlightId, h.deleted ? "undo" : "delete", h.revision, createReaderId()))}>{h.deleted ? "撤销删除重点" : "取消重点"}</button>}</article>)}</aside>}
  </section>;
}
