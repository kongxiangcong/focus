import { forwardRef, memo, useCallback, useEffect, useImperativeHandle, useLayoutEffect, useMemo, useRef, useState, type CSSProperties } from "react";
import { createReaderId, type ReaderHost, type ReaderHostResult, type ReaderMessage, type ReadingDocument, type ReadingOpening, type ReadingWindow, type ValidatedAnswerEvidence } from "@focus/reader-contracts";
import { MarkdownContent } from "./MarkdownContent";
import { OriginalPaper, TranslatedPaper } from "./PaperViews";
import { projectEvidence } from "./source-evidence";
import type { RenderMark } from "./rehype-annotations";
import { readingFontSizes } from "./typography";
import { AgentControls } from "./AgentControls";
import { AssetInstanceContext } from "./asset-context";
import { ArrowUp, Close, Collapse, Expand, ListOutline, Pin, Plus, StopSquare } from "./ReaderIcons";
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
  }, [host, acceptView]);
  if (!view) return <div className="conversation-reader" role="status" hidden={!visible}>{error || "加载中…"}</div>;
  if (!view.source.sourceId) return <div className="conversation-reader" hidden={!visible} />;
  return <AssetInstanceContext.Provider value={view.workspace?.instanceId}><ReadingSurface key={`${view.workspace?.instanceId}:${view.source.sourceId}:${view.sourceBundleVersion ?? ""}:${view.sourceGeneration ?? view.resetVersion ?? 0}`} {...fullscreenControls} host={host} view={view} setView={acceptView} visible={visible} fontSize={fontSize} /></AssetInstanceContext.Provider>;
}

interface ComposerHandle {
  insertQuote: (quote: string) => void;
  focus: () => void;
}

interface ComposerProps {
  draftKey: string;
  running: boolean;
  sending: boolean;
  agent: ReadingWindow["agent"];
  onSend: (content: string) => Promise<boolean>;
  onStop: () => void;
  onApprove: (input: Parameters<NonNullable<ReaderHost["approve"]>>[0]) => Promise<boolean>;
}

const ConversationComposer = memo(forwardRef<ComposerHandle, ComposerProps>(function ConversationComposer(
  { draftKey, running, sending, agent, onSend, onStop, onApprove }, ref,
) {
  const [draft, setDraft] = useState(() => safeRead(draftKey) ?? "");
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const saveTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const prevKey = useRef(draftKey);

  useEffect(() => {
    if (prevKey.current !== draftKey) {
      prevKey.current = draftKey;
      if (saveTimer.current) { clearTimeout(saveTimer.current); saveTimer.current = null; }
      setDraft(safeRead(draftKey) ?? "");
    }
  }, [draftKey]);

  useEffect(() => () => { if (saveTimer.current) clearTimeout(saveTimer.current); }, []);

  const persistDraft = useCallback((value: string) => {
    if (saveTimer.current) clearTimeout(saveTimer.current);
    saveTimer.current = setTimeout(() => { safeWrite(draftKey, value); saveTimer.current = null; }, 250);
  }, [draftKey]);

  useImperativeHandle(ref, () => ({
    insertQuote(quote: string) {
      setDraft(current => {
        const next = `${current ? current + "\n\n" : ""}> ${quote.replace(/\n/g, "\n> ")}\n\n`;
        safeWrite(draftKey, next);
        return next;
      });
      requestAnimationFrame(() => textareaRef.current?.focus());
    },
    focus() { textareaRef.current?.focus(); },
  }), [draftKey]);

  async function submit() {
    const content = draft.trim();
    if (!content || sending || running) return;
    const sentDraft = draft;
    const ok = await onSend(content);
    if (ok && prevKey.current === draftKey && textareaRef.current?.value === sentDraft) {
      if (saveTimer.current) { clearTimeout(saveTimer.current); saveTimer.current = null; }
      safeWrite(draftKey, "");
      setDraft("");
    }
  }

  return <form className="source-composer focus-composer" onSubmit={e => { e.preventDefault(); void submit(); }}>
    {agent && (running || !!agent.run?.error) && <AgentControls agent={agent} onStop={onStop} onAnswer={onApprove} />}
    <textarea
      ref={textareaRef}
      rows={1}
      aria-label="输入消息"
      placeholder="问问这篇原文…"
      value={draft}
      onChange={e => { const val = e.target.value; setDraft(val); persistDraft(val); }}
      onKeyDown={e => { if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); void submit(); } }}
    />
    <div className="focus-composer__actions">
      {running
        ? <button type="button" className="focus-primary focus-composer__send" onClick={onStop} aria-label="停止回复" title="停止回复"><StopSquare /></button>
        : <button type="submit" className="focus-primary focus-composer__send" disabled={sending || running || !draft.trim()} aria-label="发送" title="发送"><ArrowUp /></button>}
    </div>
  </form>;
}));

interface MessageItemProps {
  message: ReaderMessage;
  markdown: string;
  isSelected: boolean;
  onSelect: (messageId: string) => void;
  onCite: (message: ReaderMessage, id: string, keyboard: boolean) => void;
  onHoverCitation: (messageId: string, id: string | undefined) => void;
}

const ConversationMessage = memo(function ConversationMessage({
  message, markdown, isSelected, onSelect, onCite, onHoverCitation,
}: MessageItemProps) {
  const handleCitation = useCallback((id: string, keyboard: boolean) => onCite(message, id, keyboard), [onCite, message]);
  const handleHover = useCallback((id: string | undefined) => onHoverCitation(message.messageId, id), [onHoverCitation, message.messageId]);
  return <section
    data-message-id={message.messageId}
    data-role={message.role}
    data-selected={isSelected ? "true" : undefined}
    tabIndex={-1}
    className="source-message"
    onClick={() => { if (message.role === "assistant") onSelect(message.messageId); }}
  >
    <MarkdownContent
      text={markdown}
      onCitation={message.role === "assistant" ? handleCitation : undefined}
      onCitationHover={message.role === "assistant" ? handleHover : undefined}
    />
  </section>;
});

interface TurnGroup {
  id: string;
  messages: ReaderMessage[];
}

function groupIntoTurns(messages: readonly ReaderMessage[]): TurnGroup[] {
  const turns: TurnGroup[] = [];
  for (const m of messages) {
    if (m.role === "user" || turns.length === 0) {
      turns.push({ id: m.messageId, messages: [m] });
    } else {
      const last = turns[turns.length - 1];
      if (last.messages.every(item => item.role === "user")) last.messages.push(m);
      else turns.push({ id: m.messageId, messages: [m] });
    }
  }
  return turns;
}

function ReadingSurface({ host, view, setView, visible, fontSize, fullscreen, onFullscreenChange }: { host: ReaderHost; view: ReadingWindow; setView: (v: ReadingWindow) => void; visible: boolean; fontSize: string } & FullscreenControls) {
  const sourceId = view.source.sourceId!;
  const [document, setDocument] = useState<ReadingDocument | null>(null), [opening, setOpening] = useState<ReadingOpening | null>(null);
  const [error, setError] = useState(""), [reload, setReload] = useState(0), [sending, setSending] = useState(false);
  const [translated, setTranslated] = useState(false);
  const [pdfRevision, setPdfRevision] = useState(0);
  const pdfReady = useCallback(() => setPdfRevision(v => v + 1), []);
  const position = useRef<{line: number; block?: string; fraction: number} | null>(null);
  const movedSinceSwitch = useRef(false);
  const lastPdfScroll = useRef(0);
  const [positionNotice, setPositionNotice] = useState("");
  const pointerX = useRef<number | undefined>(undefined);
  const [selection, setSelection] = useState("");
  const [noteEdit, setNoteEdit] = useState<{ id: string; revision: number } | null>(null);
  const [noteDraft, setNoteDraft] = useState("");
  const [hoverEvidence, setHoverEvidence] = useState<string | undefined>();
  const [activeMessage, setActiveMessage] = useState<string | null>(null), [activeEvidence, setActiveEvidence] = useState<string | undefined>();
  const [mobile, setMobile] = useState("chat"), [guideOpen, setGuideOpen] = useState(false), [notesOpen, setNotesOpen] = useState(false);
  const [share, setShare] = useState(() => Math.max(40, Math.min(70, Number(safeRead("focus.sourceShare")) || 60)));
  const scope = `${view.workspace?.workspaceId ?? "local"}:${sourceId}:${view.sourceGeneration ?? view.resetVersion ?? 0}`;
  const draftKey = `focus.sourceDraft:${scope}:${view.discussionId ?? ""}`;
  const original = useRef<HTMLDivElement>(null), chat = useRef<HTMLDivElement>(null), shell = useRef<HTMLDivElement>(null);
  const sendRequest = useRef<{ content: string; id: string } | null>(null);
  const sendBusy = useRef(false);
  const composer = useRef<ComposerHandle>(null), returnFocus = useRef<{ messageId: string; evidenceId: string } | null>(null);
  const manual = useRef(false), followChat = useRef(true), turn = useRef<{ seen: Set<string>; cancelled: boolean; located: boolean } | null>(null);
  const jumpOrigin = useRef<number | null>(null);
  const [cardAtTop, setCardAtTop] = useState(false);
  const [returnPosition, setReturnPosition] = useState<number | null>(null);
  const [focusedTurn, setFocusedTurn] = useState<number>(-1);
  const scrollAnimation = useRef<number | null>(null);
  useEffect(() => () => { if (scrollAnimation.current !== null) cancelAnimationFrame(scrollAnimation.current); }, []);
  const restored = useRef(false), bookmark = document ? `focus.sourceBookmark:${scope}:${document.bundleVersion}` : "";
  useEffect(() => { setActiveMessage(safeRead(`focus.activeAnswer:${draftKey}`)); setActiveEvidence(undefined); turn.current = null; }, [draftKey]);

  useEffect(() => {
    let live = true, timer: ReturnType<typeof setTimeout>;
    setError("");
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

  const prep = view.preparations?.[sourceId];
  useEffect(() => {
    let live = true;
    void host.getSourceDocument!(sourceId).then(r => { if (live) { if (r.ok) setDocument(r.value); else setError(r.error.message); } }).catch(e => { if (live) setError(String(e)); });
    return () => { live = false; };
  }, [host, sourceId, reload, prep?.status, prep?.selected_plan_id, prep?.plan_id, prep?.ready]);
  const originalUrl = document?.pdf && host.sourceOriginalUrl?.(sourceId);
  const pdfUrl = originalUrl && originalUrl + (originalUrl.includes("?") ? "&" : "?") + "pdfHash=" + document!.pdf!.pdfHash +
    (view.workspace?.instanceId ? "&instance=" + encodeURIComponent(view.workspace.instanceId) : "");
  function switchPaper(next: boolean) {
    const pane = original.current;
    if (!pane || translated === next) return;
    const rect = pane.getBoundingClientRect(), y = rect.top + rect.height * .32;
    const x = pointerX.current ?? rect.left + rect.width / 2;
    const pages = [...pane.querySelectorAll<HTMLElement>("[data-pdf-page]")];
    const page = pages.find(el => el.getBoundingClientRect().bottom >= y) ?? pages.at(-1);
    const anchors = [...(page ?? pane).querySelectorAll<HTMLElement>("[data-source-line]")].filter(el => el.getClientRects().length);
    setPositionNotice("");
    if (next) lastPdfScroll.current = pane.scrollTop;
    const dist = (el: HTMLElement) => {
      const r = el.getBoundingClientRect();
      return Math.max(r.top-y, y-r.bottom, 0) + Math.max(r.left-x, x-r.right, 0);
    };
    const cited = !manual.current && activeEvidence ?
      pane.querySelectorAll<HTMLElement>(`[data-evidence-block~="${activeEvidence}"]`)[regionNumber] : null;
    const current = cited || anchors.sort((a,b) => dist(a)-dist(b))[0];
    if (current && (next || movedSinceSwitch.current)) {
      const r = current.getBoundingClientRect();
      const line = Number(current.dataset.sourceLine);
      const remembered = position.current;
      position.current = next || !remembered || remembered.line < line || remembered.line > Number(current.dataset.sourceEnd)
        ? { line, block: current.dataset.blockId, fraction: Math.max(0, Math.min(1, (y-r.top)/Math.max(1,r.height))) } : remembered;
    } else if (!current) {
      position.current = null;
      if (next && page) setPositionNotice(`第 ${page.dataset.pdfPage} 页暂无对应译块`);
    }
    cancelAuto(); movedSinceSwitch.current = false; setSelection(""); setTranslated(next);
  }
  useLayoutEffect(() => {
    const anchor = position.current, pane = original.current;
    if (!pane) return;
    if (!anchor) {
      if (!translated && pdfRevision) pane.scrollTop = lastPdfScroll.current;
      return;
    }
    const candidates = [...pane.querySelectorAll<HTMLElement>("[data-source-line]")].filter(el => el.getClientRects().length);
    const node = candidates.find(el => anchor.block && el.dataset.blockId === anchor.block) ??
      candidates.find(el => Number(el.dataset.sourceLine) <= anchor.line && Number(el.dataset.sourceEnd) >= anchor.line);
    if (node) {
      const r = node.getBoundingClientRect();
      pane.scrollTop += r.top - pane.getBoundingClientRect().top + anchor.fraction*r.height - pane.clientHeight*.32;
    } else if (!translated && pane.querySelector("[data-pdf-page]")) {
      pane.scrollTop = lastPdfScroll.current;
      setPositionNotice("此译块暂无可靠版面位置，已返回上次 PDF 阅读处");
    }
  }, [translated, pdfRevision]);

  const messages = useMemo(() => view.conversation.filter(m => !m.sourceDeleted && (!m.sourceId || m.sourceId === sourceId)), [view.conversation, sourceId]);
  const turns = useMemo(() => groupIntoTurns(messages), [messages]);
  const latest = useMemo(() => messages.filter(m => m.role === "assistant").at(-1), [messages]);
  const selected = useMemo(() => messages.find(m => m.messageId === activeMessage) ?? latest, [messages, activeMessage, latest]);
  const selectedIdRef = useRef(selected?.messageId);
  selectedIdRef.current = selected?.messageId;

  const validated = useMemo(() => document && selected ? messageEvidence(selected, document, view.discussionId) : [], [document, selected, view.discussionId]);
  const evidenceKey = JSON.stringify(validated.map(e => [e.evidenceId, e.sourceId, e.bundleVersion, e.sourceLines, e.quote, e.displayNumber, e.layoutVersion, e.blockIds]));
  const evidence = useMemo(() => validated, [evidenceKey]);
  // Do NOT include hoverEvidence/activeEvidence here; toggling active highlight via DOM avoids reparsing the full document.
  const sourceInput = useMemo(() => document ? { document, evidence } : undefined, [document, evidence]);
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
  }, [document, annotationKey, sourceId]);

  const active = projections.find(p => p.evidence.evidenceId === activeEvidence);
  const highlightedEvidenceId = hoverEvidence ?? activeEvidence;
  const running = !!view.agent?.run && ["running", "approval", "stopping"].includes(view.agent.run.status);

  // Imperatively toggle active evidence class on the original DOM — < 0.2ms, zero Markdown reparse!
  useLayoutEffect(() => {
    const pane = original.current;
    if (!pane) return;
    pane.querySelectorAll(".is-active").forEach(el => el.classList.remove("is-active"));
    if (highlightedEvidenceId) {
      pane.querySelectorAll(`[data-evidence-ids~="${highlightedEvidenceId}"], [data-evidence="${highlightedEvidenceId}"], [data-evidence-block~="${highlightedEvidenceId}"]`)
        .forEach(el => el.classList.add("is-active"));
    }
  }, [highlightedEvidenceId, evidenceKey, document, translated, pdfRevision]);

  // Keep latest turn focused when new turns arrive.
  useEffect(() => {
    if (turns.length > 0) setFocusedTurn(turns.length - 1);
    else setFocusedTurn(-1);
  }, [turns.length]);

  const cancelAuto = useCallback(() => {
    movedSinceSwitch.current = true;
    pendingJump.current = null;
    jumpOrigin.current = null; setReturnPosition(null);
    if (scrollAnimation.current !== null) { cancelAnimationFrame(scrollAnimation.current); scrollAnimation.current = null; }
    manual.current = true;
    if (turn.current) turn.current.cancelled = true;
    original.current?.scrollTo({ top: original.current.scrollTop, behavior: "instant" });
  }, []);

  const target = (id: string) => original.current?.querySelector<HTMLElement>(`[data-evidence-ids~="${id}"], [data-evidence-block~="${id}"]`);

  const moveTo = useCallback((id: string, keyboard = false, automatic = false) => {
    const el = target(id), pane = original.current;
    if (!el || !pane) return;
    if (jumpOrigin.current === null) { jumpOrigin.current = pane.scrollTop; setReturnPosition(pane.scrollTop); }
    movedSinceSwitch.current = true;
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
  }, []);

  const pendingJump = useRef<{ id: string; keyboard: boolean } | null>(null);
  const wasFullscreen = useRef(fullscreen);
  useLayoutEffect(() => {
    const exitedFullscreen = wasFullscreen.current && !fullscreen;
    wasFullscreen.current = fullscreen;
    if (visible && !exitedFullscreen) return;
    pendingJump.current = null;
    turn.current = null;
    returnFocus.current = null;
    jumpOrigin.current = null;
    if (scrollAnimation.current !== null) {
      cancelAnimationFrame(scrollAnimation.current);
      scrollAnimation.current = null;
    }
    setActiveEvidence(undefined);
    setHoverEvidence(undefined);
    setReturnPosition(null);
  }, [visible, fullscreen]);
  const finishJump = useCallback(() => {
    const jump = pendingJump.current;
    if (jump && target(jump.id)) {
      pendingJump.current = null;
      moveTo(jump.id, jump.keyboard);
    }
  }, [moveTo]);
  useLayoutEffect(finishJump, [evidence, mobile, pdfRevision, finishJump]);

  const cite = useCallback((message: ReaderMessage, id: string, keyboard: boolean) => {
    cancelAuto(); returnFocus.current = { messageId: message.messageId, evidenceId: id };
    pendingJump.current = { id, keyboard }; safeWrite(`focus.activeAnswer:${draftKey}`, message.messageId); setActiveMessage(message.messageId); setActiveEvidence(id); setMobile("original");
    if (selectedIdRef.current === message.messageId) requestAnimationFrame(finishJump);
  }, [cancelAuto, draftKey, finishJump]);

  const handleSelectMessage = useCallback((messageId: string) => {
    if (selectedIdRef.current !== messageId) {
      cancelAuto();
      safeWrite(`focus.activeAnswer:${draftKey}`, messageId);
      setActiveMessage(messageId);
      setActiveEvidence(undefined);
    }
  }, [cancelAuto, draftKey]);

  const handleHoverCitation = useCallback((messageId: string, id: string | undefined) => {
    if (messageId === selectedIdRef.current) setHoverEvidence(id);
  }, []);

  useLayoutEffect(() => {
    if (!document || !original.current || restored.current || (pdfUrl && !pdfRevision)) return;
    restored.current = true;
    try {
      const raw = safeRead(bookmark);
      const saved = raw ? JSON.parse(raw) : view.readingStarted && view.navigationCurrent?.bundleVersion === document.bundleVersion ? { line: view.navigationCurrent.sourceLines[0], offset: 0 } : null;
      if (saved && Number.isSafeInteger(saved.line) && Number.isFinite(saved.offset)) {
        const el = original.current.querySelector<HTMLElement>(`[data-source-line="${saved.line}"]`);
        if (el) original.current.scrollTop += el.getBoundingClientRect().top - original.current.getBoundingClientRect().top + saved.offset;
      }
    } catch { /* Ignore malformed display bookmarks, never mutate the Cursor. */ }
  }, [document, bookmark, pdfUrl, pdfRevision]);

  useEffect(() => {
    const pending = turn.current;
    if (!visible || !pending || pending.located || pending.cancelled || !latest || pending.seen.has(latest.messageId) || !evidence.length) return;
    const first = projections.find(p => p.kind !== "unavailable");
    if (first && selected?.messageId === latest.messageId) { pending.located = true; if ((shell.current?.clientWidth ?? 0) >= 960) moveTo(first.evidence.evidenceId, false, true); }
  }, [visible, latest, evidence, projections, selected, moveTo]);

  useLayoutEffect(() => { if (followChat.current && chat.current) chat.current.scrollTop = chat.current.scrollHeight; }, [messages.at(-1)?.content]);

  const apply = useCallback(async (operation: Promise<ReaderHostResult<ReadingWindow>>) => {
    try { const r = await operation; if (r.ok) { setView(r.value); return true; } setError(r.error.message); } catch (e) { setError(String(e)); }
    return false;
  }, [setView]);

  const sendMessage = useCallback(async (content: string) => {
    if (!content || sendBusy.current || sending || running) return false;
    sendBusy.current = true;
    safeWrite(`focus.activeAnswer:${draftKey}`, ""); setSending(true); setError(""); setActiveMessage(null); setActiveEvidence(undefined);
    followChat.current = true; turn.current = { seen: new Set(messages.map(m => m.messageId)), cancelled: false, located: false };
    if (sendRequest.current?.content !== content) sendRequest.current = { content, id: createReaderId() };
    const ok = await apply(host.sendMessage({ sourceId, sessionId: view.sessionId, receipt: null, content, requestId: sendRequest.current.id }));
    if (ok) { sendRequest.current = null; } else turn.current = null;
    sendBusy.current = false; setSending(false);
    return ok;
  }, [apply, draftKey, host, messages, running, sending, sourceId, view.sessionId]);

  const handleStop = useCallback(() => { if (host.stop) void apply(host.stop()); }, [apply, host]);
  const handleApprove = useCallback((input: Parameters<NonNullable<ReaderHost["approve"]>>[0]) => host.approve ? apply(host.approve(input)) : Promise.resolve(false), [apply, host]);

  function backToAnswer(id: string) {
    cancelAuto(); setMobile("chat"); setActiveEvidence(id);
    requestAnimationFrame(() => { const el = chat.current?.querySelector<HTMLElement>(`[data-message-id="${selected?.messageId}"] [data-citation="${id}"]`); el?.scrollIntoView({ block: "nearest", behavior: reduced() ? "instant" : "smooth" }); el?.focus({ preventScroll: true }); });
  }

  // Update focused turn smoothly on chat scroll (Mist Focus Lens for conversation).
  const updateChatFocus = useCallback(() => {
    const el = chat.current;
    if (!el) return;
    followChat.current = el.scrollHeight - el.clientHeight - el.scrollTop < 64;
    if (!followChat.current && turn.current) turn.current.cancelled = true;
    if (turns.length <= 1) return;
    const turnEls = el.querySelectorAll<HTMLElement>(".source-turn");
    if (!turnEls.length) return;
    const rect = el.getBoundingClientRect();
    const readingLine = rect.top + rect.height * 0.45;
    let best = turns.length - 1;
    let bestDist = Infinity;
    turnEls.forEach((node, idx) => {
      const r = node.getBoundingClientRect();
      const center = (r.top + r.bottom) / 2;
      const dist = Math.abs(center - readingLine);
      if (dist < bestDist) { bestDist = dist; best = idx; }
    });
    setFocusedTurn(prev => (prev === best ? prev : best));
  }, [turns.length]);

  const [regionNumber, setRegionNumber] = useState(0);
  useEffect(() => { setRegionNumber(0); }, [activeEvidence, translated]);
  function nextRegion() {
    if (!activeEvidence || !original.current) return;
    const regions = original.current.querySelectorAll<HTMLElement>(`[data-evidence-block~="${activeEvidence}"]`);
    if (!regions.length) return;
    const next = (regionNumber + 1) % regions.length;
    manual.current = false; movedSinceSwitch.current = true;
    regions[next].scrollIntoView({ block: "center", behavior: reduced() ? "instant" : "smooth" });
    setRegionNumber(next);
  }
  const translationState = document?.translation?.status;
  const translationInterrupted = ["failed", "cancelled", "interrupted"].includes(translationState ?? "");
  const translationReady = document?.translation?.status === "ready";
  const showingTranslation = translated && translationReady;
  const activeBlocks = document?.pdf?.blocks.filter(b => active?.evidence.layoutVersion === document.pdf?.version && active?.evidence.blockIds?.includes(b.blockId)) ?? [];
  const locationLabel = pdfUrl && !showingTranslation ? (activeBlocks.length ?
    ` · 第 ${[...new Set(activeBlocks.map(b => b.page))].join("、")} 页 · ${activeBlocks.some(b => b.bbox) ? "段落定位" : "页定位"}` : " · 版面位置暂不可用") :
    showingTranslation ? " · 译块定位" : active?.kind === "block" ? " · 段落定位" : active?.kind === "unavailable" ? " · 不可定位" : "";
  const partCount = showingTranslation ? document?.translation?.chunks.filter(c => active && c.sourceLines[0] <= active.evidence.sourceLines[1] && active.evidence.sourceLines[0] <= c.sourceLines[1]).length ?? 0 :
    new Set(activeBlocks.map(b => b.blockId)).size;
  const activeFocusIndex = focusedTurn >= 0 && focusedTurn < turns.length ? focusedTurn : turns.length - 1;

  return <section ref={shell} className="conversation-reader" data-fullscreen={!!fullscreen} data-mobile={mobile} data-font-size={fontSize} hidden={!visible} style={{ "--source-share": `${share}%`, "--source-font-size": `${readingFontSizes[fontSize as keyof typeof readingFontSizes] ?? 18}px` } as CSSProperties}
    onKeyDown={e => { if (e.key === "Escape") { setActiveEvidence(undefined); const previous = returnFocus.current; if (previous) requestAnimationFrame(() => chat.current?.querySelector<HTMLElement>(`[data-message-id="${previous.messageId}"] [data-citation="${previous.evidenceId}"]`)?.focus({ preventScroll: true })); } }}>
    {error && <div role="alert" className="source-reader-error">{error}<button onClick={() => setReload(v => v + 1)}>重试</button></div>}
    <div className="source-reader-columns">
      <div className="source-original-pane" data-paper={!!pdfUrl}>
        {pdfUrl && <div className="paper-view-controls"><button aria-pressed={!showingTranslation} onClick={() => switchPaper(false)}>原版 PDF</button>
          <button aria-pressed={!!showingTranslation} disabled={!translationReady} onClick={() => switchPaper(true)}>中文译文{translationReady ? "" : translationState === "running" ? " · 准备中" : translationInterrupted ? " · 未完成" : " · 未就绪"}</button>
          {translationInterrupted && host.resumePreparation && <button onClick={() => void apply(host.resumePreparation!(sourceId, createReaderId()))}>重试译文</button>}</div>}
        {pdfUrl && positionNotice && <span role="status">{positionNotice}</span>}
        <div ref={original} className="source-original" data-evidence-focus={activeEvidence ? "true" : undefined} aria-label="文章原文" tabIndex={0} onPointerMove={e => { pointerX.current = e.clientX; }} onWheel={cancelAuto} onTouchStart={cancelAuto} onPointerDown={cancelAuto} onKeyDown={e => { if (["PageDown", "PageUp", "ArrowDown", "ArrowUp", "Home", "End", " "].includes(e.key)) cancelAuto(); }}
          onScroll={() => { if (manual.current && bookmark && original.current) {
            const top = original.current.getBoundingClientRect().top;
            const block = [...original.current.querySelectorAll<HTMLElement>("[data-source-line]")].find(el => el.getBoundingClientRect().bottom > top);
            if (block) safeWrite(bookmark, JSON.stringify({ line: Number(block.dataset.sourceLine), offset: top - block.getBoundingClientRect().top }));
          } }}
          onMouseUp={() => { const selectedText = window.getSelection()?.toString().trim() ?? ""; if (selectedText) { cancelAuto(); setSelection(selectedText.slice(0, 4000)); } }}
          onClick={e => { const id = (e.target as HTMLElement).closest<HTMLElement>("[data-evidence]")?.dataset.evidence; if (id) backToAnswer(id); else if ((e.target as HTMLElement).closest("[data-anno-key], [data-anno-bulb]")) setNotesOpen(true); }}>
          {document?.pdf && pdfUrl ? showingTranslation ? <TranslatedPaper document={document} evidence={evidence} /> :
            <OriginalPaper pdf={document.pdf} url={pdfUrl} evidence={evidence} active={highlightedEvidenceId} onReady={pdfReady} /> : document ? <article><MarkdownContent text={document.markdown} sourceId={sourceId} marks={permanentMarks} sourceEvidence={sourceInput} /></article> : <span role="status" className="source-loading">加载中…</span>}
        </div>
        {selection && <div className="source-selection-actions"><button onClick={() => { composer.current?.insertQuote(selection); setSelection(""); setMobile("chat"); }}>引用</button><button onClick={() => { setNoteDraft(`「${selection}」\n`); setNotesOpen(true); setSelection(""); }}>记笔记</button><button aria-label="取消选择" onClick={() => setSelection("")}>×</button></div>}
        {active && <aside className="source-evidence-card" data-top={cardAtTop} aria-label="原文证据"><button aria-label="关闭证据" onClick={() => setActiveEvidence(undefined)}>×</button><button onClick={() => backToAnswer(active.evidence.evidenceId)}>证据 {active.evidence.displayNumber}{locationLabel}</button><p>{active.evidence.quote.exact}</p>{partCount > 1 && <button onClick={nextRegion}>下一处（{regionNumber + 1}/{partCount}）</button>}{returnPosition !== null && <button onClick={() => { if (original.current && jumpOrigin.current !== null) { manual.current = false; original.current.scrollTo({ top: jumpOrigin.current, behavior: "instant" }); } jumpOrigin.current = null; setReturnPosition(null); setActiveEvidence(undefined); }}>返回阅读位置</button>}</aside>}
      </div>
      <div className="source-splitter" role="separator" aria-label="调整原文宽度" aria-orientation="vertical" aria-valuemin={40} aria-valuemax={70} aria-valuenow={share} tabIndex={0}
        onKeyDown={e => { if (["ArrowLeft", "ArrowRight"].includes(e.key)) { e.preventDefault(); const v = Math.max(40, Math.min(70, share + (e.key === "ArrowLeft" ? -2 : 2))); setShare(v); safeWrite("focus.sourceShare", String(v)); } }}
        onPointerDown={e => { e.currentTarget.setPointerCapture(e.pointerId); }} onPointerMove={e => { if (!e.currentTarget.hasPointerCapture(e.pointerId) || !shell.current) return; const rect = shell.current.getBoundingClientRect(); const v = Math.max(40, Math.min(70, (e.clientX - rect.left) / rect.width * 100)); setShare(v); safeWrite("focus.sourceShare", String(v)); }} onPointerUp={e => e.currentTarget.releasePointerCapture(e.pointerId)} />
      <div className="source-chat-pane">
        <div ref={chat} className="source-chat" aria-label="文章对话" onWheel={() => { if (turn.current) turn.current.cancelled = true; }} onScroll={updateChatFocus}>
          {opening?.status === "ready" && opening.bundleVersion === document?.bundleVersion && (
            <section className="source-opening" data-open={guideOpen}>
              <div className="source-opening__head">
                <button type="button" className="source-guide-toggle" onClick={() => setGuideOpen(!guideOpen)} aria-expanded={guideOpen}>
                  <ListOutline />
                  <span>文章导读{opening.structure?.length ? ` · ${opening.structure.length} 节` : ""}</span>
                  <span className="source-guide-toggle__hint">{guideOpen ? "收起" : "展开"}</span>
                </button>
              </div>
              {opening.guide && <p className="source-opening__summary">{opening.guide}</p>}
              {guideOpen && opening.structure && <ul className="source-opening__list">{opening.structure.map(n => <li key={n.id} data-child={!!n.parentId}><button onClick={() => { cancelAuto(); setMobile("original"); requestAnimationFrame(() => { const blocks = [...(original.current?.querySelectorAll<HTMLElement>("[data-source-line]") ?? [])]; const el = blocks.find(b => Number(b.dataset.sourceLine) >= n.sourceLines[0]); el?.scrollIntoView({ block: "start", behavior: reduced() ? "instant" : "smooth" }); }); }}>{n.title}</button></li>)}</ul>}
            </section>
          )}
          {opening?.status === "running" && <div className="source-opening-skeleton" aria-label="正在准备导读" role="status"><i /><i /><i /></div>}
          {opening?.status === "failed" && <p role="alert" className="source-opening-error">{opening.error}<button onClick={() => setReload(v => v + 1)}>重试导读</button></p>}
          {turns.map((group, idx) => {
            const dist = Math.abs(idx - activeFocusIndex);
            const focusBand = turns.length <= 1 || dist === 0 ? "0" : dist === 1 ? "1" : "far";
            return <div key={group.id} className="source-turn" data-focus-distance={focusBand} onClick={() => setFocusedTurn(idx)}>
              {group.messages.map(message => {
                const refs = document ? messageEvidence(message, document, view.discussionId) : [];
                const text = message.role === "assistant" ? citedMarkdown(message, refs) : message.content;
                return <ConversationMessage
                  key={message.messageId}
                  message={message}
                  markdown={text}
                  isSelected={selected?.messageId === message.messageId}
                  onSelect={handleSelectMessage}
                  onCite={cite}
                  onHoverCitation={handleHoverCitation}
                />;
              })}
            </div>;
          })}
        </div>
        <div className="source-composer-dock">
          <div className="source-composer-actions" role="toolbar" aria-label="对话操作">
            <button type="button" className="source-mobile-toggle" onClick={() => setMobile(mobile === "chat" ? "original" : "chat")}>{mobile === "chat" ? "查看原文" : "返回对话"}</button>
            <div className="source-composer-icons">
              {(view.discussions?.length ?? 0) > 1 && host.selectDiscussionSource && (
                <select className="source-discussion-select" aria-label="对话记录" value={view.discussionId ?? ""} disabled={running} onChange={e => void apply(host.selectDiscussionSource!(sourceId, e.target.value))}>
                  {view.discussions!.map((d, i) => <option key={d.discussionId} value={d.discussionId}>对话 {i + 1}</option>)}
                </select>
              )}
              {opening?.status === "ready" && (
                <button type="button" className="source-icon-btn" aria-label={guideOpen ? "收起导读" : "展开导读"} title={guideOpen ? "收起导读" : "展开导读"} aria-pressed={guideOpen} onClick={() => setGuideOpen(!guideOpen)}>
                  <ListOutline />
                </button>
              )}
              <button type="button" className="source-icon-btn" aria-label="笔记" title="笔记" aria-pressed={notesOpen} onClick={() => setNotesOpen(!notesOpen)}>
                <Pin />
              </button>
              {host.newSession && view.sessionId && (
                <button type="button" className="source-icon-btn" aria-label="新会话" title="新会话" disabled={running} onClick={() => void apply(host.newSession!(view.sessionId!))}>
                  <Plus />
                </button>
              )}
              {onFullscreenChange && (
                <button type="button" className="source-icon-btn" aria-label={fullscreen ? "退出全屏" : "对话全屏"} title={fullscreen ? "退出全屏" : "对话全屏"} aria-pressed={!!fullscreen} onClick={() => { if (!fullscreen) setMobile("chat"); onFullscreenChange(!fullscreen); }}>
                  {fullscreen ? <Collapse /> : <Expand />}
                </button>
              )}
            </div>
          </div>
          <ConversationComposer
            ref={composer}
            draftKey={draftKey}
            running={running}
            sending={sending}
            agent={view.agent}
            onSend={sendMessage}
            onStop={handleStop}
            onApprove={handleApprove}
          />
        </div>
      </div>
    </div>
    {notesOpen && <aside className="source-notes-drawer" aria-label="来源笔记">
      <div className="source-notes-drawer__head">
        <h3>笔记</h3>
        <button type="button" className="source-icon-btn" onClick={() => setNotesOpen(false)} aria-label="关闭笔记"><Close /></button>
      </div>
      <textarea aria-label="笔记内容" placeholder="记录想法或结论…" value={noteDraft} onChange={e => setNoteDraft(e.target.value)} />
      {host.createSourceNote && <button className="source-notes-save" disabled={!noteDraft.trim()} onClick={async () => { const request = noteEdit && host.changeSourceNote ? host.changeSourceNote(sourceId, noteEdit.id, "edit", noteEdit.revision, createReaderId(), noteDraft.trim()) : host.createSourceNote!({ sourceId, requestId: createReaderId(), content: noteDraft.trim(), kind: "thought", origin: "user" });
        const result = await request; if (!result.ok) { setError(result.error.message); return; } setView(result.value);
        if (result.value.noteOperation?.status === "conflict") { setError("笔记已更新，请核对当前内容后再保存。"); if (result.value.noteOperation.current) setNoteEdit({ id: result.value.noteOperation.current.noteId, revision: result.value.noteOperation.current.revision }); return; }
        setNoteDraft(""); setNoteEdit(null); }}>保存笔记</button>}
      {(view.sourceNotes ?? []).filter(n => !n.deleted || n.canUndo).map(n => <article key={n.noteId}>{n.sentence && <blockquote>{n.sentence.quote.exact}</blockquote>}<MarkdownContent text={n.content} />{host.changeSourceNote && <div className="source-note-actions">{!n.deleted && <button onClick={() => { setNoteEdit({ id: n.noteId, revision: n.revision }); setNoteDraft(n.content); }}>编辑</button>}<button onClick={() => void apply(host.changeSourceNote!(sourceId, n.noteId, n.deleted ? "undo" : "delete", n.revision, createReaderId()))}>{n.deleted ? "撤销删除" : "删除"}</button></div>}</article>)}
      {(view.sourceHighlights ?? []).filter(h => !h.deleted || h.canUndo).map(h => <article key={h.highlightId}><blockquote>{h.quote.exact}</blockquote>{host.changeHighlight && <div className="source-note-actions"><button onClick={() => void apply(host.changeHighlight!(sourceId, h.highlightId, h.deleted ? "undo" : "delete", h.revision, createReaderId()))}>{h.deleted ? "撤销删除重点" : "取消重点"}</button></div>}</article>)}
    </aside>}
  </section>;
}
