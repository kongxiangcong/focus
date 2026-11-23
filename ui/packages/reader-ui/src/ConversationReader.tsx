import { forwardRef, memo, useCallback, useEffect, useImperativeHandle, useLayoutEffect, useMemo, useRef, useState, type CSSProperties } from "react";
import { createReaderId, type ReaderHost, type ReaderHostResult, type ReaderMessage, type ReadingDocument, type ReadingOpening, type ReadingWindow, type ValidatedAnswerEvidence } from "@focus/reader-contracts";
import { useEvidenceNavigation, type EvidenceNavigation, type EvidenceNavigationIntent } from "./evidence-navigation";
import type { ReadingSession } from "./reading-session";
import { MarkdownContent } from "./MarkdownContent";
import { ActiveSourceCitation, SourceAnswerChooser } from "./SourceEvidenceMarkers";
import { boxesForBlock, OriginalPaper, TranslatedPaper } from "./PaperViews";
import { locatePaperEvidence, matchesTranslationChunk } from "./paper-evidence";
import { citedMarkdown, messageEvidence, projectEvidence } from "./source-evidence";
import type { RenderMark } from "./rehype-annotations";
import { readingFontSizes } from "./typography";
import { AgentControls } from "./AgentControls";
import { AssetInstanceContext } from "./asset-context";
import { ArrowUp, Close, Collapse, Expand, ListOutline, Pin, StopSquare } from "./ReaderIcons";
import "./conversation-reader.css";

const safeRead = (key: string) => { try { return localStorage.getItem(key); } catch { return null; } };
const safeWrite = (key: string, value: string) => { try { localStorage.setItem(key, value); } catch { /* Session remains usable. */ } };
const reduced = () => window.document.documentElement.dataset.reducedMotion === "true" || typeof matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").matches;

type AnswerLocation = { messageId: string; evidenceId: string; origin?: HTMLButtonElement };

type FullscreenControls = { fullscreen?: boolean; onFullscreenChange?: (next: boolean) => void };

export function ConversationReader({ host, visible = true, fontSize = "standard", readingSession, evidenceNavigation, approvalManaged, ...fullscreenControls }: { host: ReaderHost; visible?: boolean; fontSize?: string; readingSession?: ReadingSession; evidenceNavigation?: EvidenceNavigation; approvalManaged?: boolean } & FullscreenControls) {
  const [localView, setView] = useState<ReadingWindow | null>(null), [error, setError] = useState("");
  const managed = !!readingSession;
  const view = readingSession ? readingSession.view : localView;
  const acceptView = useCallback((next: ReadingWindow) => setView(previous => previous && previous.workspace?.instanceId === next.workspace?.instanceId && (previous.revision ?? 0) > (next.revision ?? 0) ? previous : next), []);
  useEffect(() => {
    if (managed) return;
    let live = true;
    const receive = (r: ReaderHostResult<ReadingWindow>) => { if (live) { if (r.ok) { acceptView(r.value); setError(""); } else setError(r.error.message); } };
    void host.getReadingWindow().then(receive).catch(e => { if (live) setError(String(e)); });
    const off = host.subscribe?.(receive);
    return () => { live = false; off?.(); };
  }, [host, acceptView, managed]);
  if (!view) return <div className="conversation-reader" role="status" hidden={!visible}>{error || "加载中…"}</div>;
  if (!view.source.sourceId) return <div className="conversation-reader" hidden={!visible} />;
  return <AssetInstanceContext.Provider value={view.workspace?.instanceId}><ReadingSurface key={`${view.workspace?.instanceId}:${view.source.sourceId}:${view.sourceBundleVersion ?? ""}:${view.sourceGeneration ?? view.resetVersion ?? 0}:${readingSession?.generation ?? 0}`} {...fullscreenControls} host={host} view={view} setView={acceptView} readingSession={readingSession} evidenceNavigation={evidenceNavigation} approvalManaged={approvalManaged} visible={visible} fontSize={fontSize} /></AssetInstanceContext.Provider>;
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
  approvalManaged?: boolean;
  onSend: (content: string) => Promise<boolean>;
  onStop: () => void;
  onApprove: (input: Parameters<NonNullable<ReaderHost["approve"]>>[0]) => Promise<boolean>;
}

const ConversationComposer = memo(forwardRef<ComposerHandle, ComposerProps>(function ConversationComposer(
  { draftKey, running, sending, agent, approvalManaged, onSend, onStop, onApprove }, ref,
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

  const sharedApproval = approvalManaged && agent?.run?.status === "approval" && agent.run.approvals.some(approval => approval.status !== "expired");
  return <form className="source-composer focus-composer" onSubmit={e => { e.preventDefault(); void submit(); }}>
    {agent && !sharedApproval && running &&
      <AgentControls agent={agent} showApproval={!approvalManaged} showStop={false} onStop={onStop} onAnswer={onApprove} />}
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
      {running && !sharedApproval
        ? <button type="button" className="focus-primary focus-composer__send" onClick={onStop} aria-label="停止回复" title="停止回复"><StopSquare /></button>
        : <button type="submit" className="focus-primary focus-composer__send" disabled={sending || running || !draft.trim()} aria-label="发送" title="发送"><ArrowUp /></button>}
    </div>
  </form>;
}));

interface MessageItemProps {
  message: ReaderMessage;
  markdown: string;
  isSelected: boolean;
  activeCitation?: string;
  onSelect: (messageId: string) => void;
  onCite: (message: ReaderMessage, id: string, keyboard: boolean, origin: HTMLButtonElement) => void;
  onHoverCitation: (messageId: string, id: string | undefined) => void;
}

const ConversationMessage = memo(function ConversationMessage({
  message, markdown, isSelected, activeCitation, onSelect, onCite, onHoverCitation,
}: MessageItemProps) {
  const handleCitation = useCallback((id: string, keyboard: boolean, origin: HTMLButtonElement) => onCite(message, id, keyboard, origin), [onCite, message]);
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
      activeCitation={activeCitation}
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

function ReadingSurface({ host, view, setView, visible, fontSize, fullscreen, onFullscreenChange, readingSession, evidenceNavigation, approvalManaged }: { host: ReaderHost; view: ReadingWindow; setView: (v: ReadingWindow) => void; visible: boolean; fontSize: string; readingSession?: ReadingSession; evidenceNavigation?: EvidenceNavigation; approvalManaged?: boolean } & FullscreenControls) {
  const sourceId = view.source.sourceId!;
  const selectionGeneration = readingSession?.generation;
  const isCurrentSelection = readingSession?.isCurrent;
  const mounted = useRef(false);
  useLayoutEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  const isCurrentSource = useCallback(() => mounted.current && (
    selectionGeneration === undefined || !!isCurrentSelection?.(selectionGeneration, sourceId)
  ), [selectionGeneration, isCurrentSelection, sourceId]);
  const [document, setDocument] = useState<ReadingDocument | null>(null), [opening, setOpening] = useState<ReadingOpening | null>(null);
  const [documentError, setDocumentError] = useState("");
  const [openingError, setOpeningError] = useState("");
  const [reloadDocument, setReloadDocument] = useState(0), [reloadOpening, setReloadOpening] = useState(0);
  const [sending, setSending] = useState(false);
  const [operationErrors, setOperationErrors] = useState<Readonly<Record<string, string>>>({});
  const attempts = useRef(new Map<string, symbol>());
  const [dismissedRun, setDismissedRun] = useState("");
  const showOperationError = useCallback((operation: string, message: string) => {
    setOperationErrors(errors => {
      const next = { ...errors };
      if (message) next[operation] = message;
      else delete next[operation];
      return next;
    });
  }, []);
  const [translated, setTranslated] = useState(false);
  const [pdfRevision, setPdfRevision] = useState(0);
  const [settledPdf, setSettledPdf] = useState<{ url: string; available: boolean }>();
  const mountedPdfUrl = useRef<string | false | undefined>(undefined);
  const position = useRef<{ block?: string; chunk?: string; fraction: number } | null>(null);
  const movedSinceSwitch = useRef(false);
  const restorePaperPosition = useRef(false);
  const lastPdfScroll = useRef(0), lastTranslationScroll = useRef(0);
  const [positionNotice, setPositionNotice] = useState("");
  useEffect(() => {
    if (!positionNotice) return;
    const timer = setTimeout(() => setPositionNotice(""), 3000);
    return () => clearTimeout(timer);
  }, [positionNotice]);
  const pointerX = useRef<number | undefined>(undefined);
  const [selection, setSelection] = useState("");
  const [noteEdit, setNoteEdit] = useState<{ id: string; revision: number } | null>(null);
  const [noteDraft, setNoteDraft] = useState("");
  const [hoverEvidence, setHoverEvidence] = useState<string | undefined>();
  const [activeMessage, setActiveMessage] = useState<string | null>(null), [activeEvidence, setActiveEvidence] = useState<string | undefined>();
  const [answerChoices, setAnswerChoices] = useState<{ ids: readonly string[]; opener: HTMLElement; discussionId?: string } | null>(null);
  const [answerReturn, setAnswerReturn] = useState<(AnswerLocation & { discussionId?: string }) | null>(null);
  const [mobile, setMobile] = useState("chat"), [guideOpen, setGuideOpen] = useState(false), [notesOpen, setNotesOpen] = useState(false);
  const notesButton = useRef<HTMLButtonElement>(null);
  const noteInput = useRef<HTMLTextAreaElement>(null);
  const notesOpener = useRef<HTMLElement | null>(null);
  function openNotes(opener: HTMLElement) {
    if (!notesOpen) notesOpener.current = opener;
    setNotesOpen(true);
  }
  function closeNotes() { setNotesOpen(false); }
  useLayoutEffect(() => {
    if (notesOpen && visible) noteInput.current?.focus({ preventScroll: true });
    else if (notesOpener.current) {
      const opener = notesOpener.current;
      notesOpener.current = null;
      if (visible) (opener.isConnected ? opener : notesButton.current)?.focus({ preventScroll: true });
    }
  }, [notesOpen, visible]);
  const [share, setShare] = useState(() => Math.max(40, Math.min(70, Number(safeRead("focus.sourceShare")) || 60)));
  const scope = `${view.workspace?.workspaceId ?? "local"}:${sourceId}:${view.sourceGeneration ?? view.resetVersion ?? 0}`;
  const draftKey = `focus.sourceDraft:${scope}:${view.discussionId ?? ""}`;
  const original = useRef<HTMLDivElement>(null), chat = useRef<HTMLDivElement>(null), shell = useRef<HTMLDivElement>(null);
  const sendRequest = useRef<{ content: string; id: string } | null>(null);
  const sendBusy = useRef(false);
  const composer = useRef<ComposerHandle>(null), returnFocus = useRef<AnswerLocation | null>(null);
  const [answerTarget, setAnswerTarget] = useState<(AnswerLocation & { discussionId: string }) | null>(null);
  const manual = useRef(false), followChat = useRef(true), turn = useRef<{ seen: Set<string>; cancelled: boolean; located: boolean } | null>(null);
  const jumpOrigin = useRef<number | null>(null);
  const jumpFromPdf = useRef(false);
  const localNavigation = useEvidenceNavigation();
  const { intent, start, isLatest, consume, cancel } = evidenceNavigation ?? localNavigation;
  const waitingPosition = useRef<{ nonce: string; scrollTop: number } | null>(null);
  const [cardAtTop, setCardAtTop] = useState(false);
  const [returnPosition, setReturnPosition] = useState<number | null>(null);
  const [focusedTurn, setFocusedTurn] = useState<number>(-1);
  const scrollAnimation = useRef<number | null>(null);
  useEffect(() => () => { if (scrollAnimation.current !== null) cancelAnimationFrame(scrollAnimation.current); }, []);
  const restored = useRef(false), bookmark = document ? `focus.sourceBookmark:${scope}:${document.bundleVersion}` : "";
  useEffect(() => {
    setActiveMessage(safeRead(`focus.activeAnswer:${draftKey}`));
    setActiveEvidence(undefined);
    setAnswerChoices(null);
    setAnswerTarget(target => target?.discussionId === view.discussionId ? target : null);
    returnFocus.current = null;
    turn.current = null;
  }, [draftKey, view.discussionId]);

  const openingWork = view.workItems?.find(item => item.kind === "opening" && item.sourceId === sourceId);
  const lastOpeningRetry = useRef(0);
  useEffect(() => {
    let live = true, timer: ReturnType<typeof setTimeout>;
    async function loadOpening(prepare: boolean, prepareIfMissing = false) {
      try {
        const result = await host.getSourceOpening?.(sourceId, prepare);
        if (!live || !isCurrentSource() || !result) return;
        if (!result.ok) { setOpening(null); setOpeningError(result.error.message); return; }
        if (result.value.sourceId !== sourceId) return;
        if (result.value.status === "missing" && prepareIfMissing) {
          await loadOpening(true);
          return;
        }
        setOpening(result.value);
        setOpeningError(result.value.status === "failed" ? result.value.error ?? "导读准备失败" : "");
        if (result.value.status === "running") timer = setTimeout(() => void loadOpening(false), 1500);
      } catch (e) { if (live && isCurrentSource()) setOpeningError(String(e)); }
    }
    const retry = lastOpeningRetry.current !== reloadOpening;
    lastOpeningRetry.current = reloadOpening;
    void loadOpening(retry, !openingWork);
    return () => { live = false; clearTimeout(timer); };
  }, [host, sourceId, reloadOpening, isCurrentSource, openingWork?.id, openingWork?.phase]);

  const prep = view.preparations?.[sourceId];
  useEffect(() => {
    let live = true;
    void host.getSourceDocument!(sourceId).then(result => {
      if (!live || !isCurrentSource()) return;
      if (!result.ok) setDocumentError(result.error.message);
      else if (result.value.sourceId === sourceId && (!view.sourceBundleVersion || result.value.bundleVersion === view.sourceBundleVersion)) {
        setDocument(result.value);
        setDocumentError("");
      }
    }).catch(e => { if (live && isCurrentSource()) setDocumentError(String(e)); });
    return () => { live = false; };
  }, [host, sourceId, reloadDocument, isCurrentSource, view.sourceBundleVersion, prep?.status, prep?.selected_plan_id, prep?.plan_id, prep?.ready]);
  const originalUrl = document?.pdf && host.sourceOriginalUrl?.(sourceId);
  const pdfUrl = originalUrl && originalUrl + (originalUrl.includes("?") ? "&" : "?") + "pdfHash=" + document!.pdf!.pdfHash +
    (view.workspace?.instanceId ? "&instance=" + encodeURIComponent(view.workspace.instanceId) : "");
  const translationState = document?.translation?.status;
  const translationReady = translationState === "ready";
  const showingTranslation = translated && translationReady;
  const activePdfUrl = !showingTranslation && pdfUrl;
  useLayoutEffect(() => {
    mountedPdfUrl.current = activePdfUrl;
    setSettledPdf(undefined);
    return () => { mountedPdfUrl.current = undefined; };
  }, [activePdfUrl]);
  const settlePdf = useCallback((available: boolean) => {
    if (!activePdfUrl || activePdfUrl !== mountedPdfUrl.current || !isCurrentSource()) return;
    setSettledPdf({ url: activePdfUrl, available });
    setPdfRevision(revision => revision + 1);
  }, [activePdfUrl, isCurrentSource]);
  const pdfReady = useCallback(() => settlePdf(true), [settlePdf]);
  const pdfUnavailable = useCallback(() => settlePdf(false), [settlePdf]);
  function switchPaper(next: boolean) {
    const pane = original.current;
    if (!pane || !document?.pdf || translated === next) return;
    const rect = pane.getBoundingClientRect(), y = rect.top + rect.height * .32;
    const x = pointerX.current ?? rect.left + rect.width / 2;
    const pages = [...pane.querySelectorAll<HTMLElement>("[data-pdf-page]")];
    const page = pages.find(el => el.getBoundingClientRect().bottom >= y) ?? pages.at(-1);
    const bounds = (el: HTMLElement) => (el.closest("[data-page-only]") ?? el).getBoundingClientRect();
    const dist = (el: HTMLElement) => {
      const r = bounds(el);
      return Math.max(r.top - y, y - r.bottom, 0) + Math.max(r.left - x, x - r.right, 0);
    };
    const anchors = [...(page ?? pane).querySelectorAll<HTMLElement>(next ? "[data-block-id]" : "[data-translation-chunk]")]
      .filter(el => (el.closest("[data-page-only]") ?? el).getClientRects().length);
    const cited = !manual.current && activeEvidence ?
      pane.querySelectorAll<HTMLElement>(`[data-evidence-block~="${activeEvidence}"]`)[regionNumber] : null;
    const citedBlock = cited?.matches("[data-block-id], [data-translation-chunk]") ? cited :
      [...(cited?.querySelectorAll<HTMLElement>("[data-block-id]") ?? [])].find(el =>
        activePaper?.pdfBlocks.some(block => block.blockId === el.dataset.blockId));
    const current = citedBlock ?? anchors.sort((a, b) => dist(a) - dist(b))[0];
    const previous = position.current;
    const chunks = document.translation?.chunks ?? [];
    const block = document.pdf.blocks.find(item => item.blockId === current?.dataset.blockId &&
      item.page === Number(current?.closest<HTMLElement>("[data-pdf-page]")?.dataset.pdfPage));
    const chunk = next ? chunks.find(item => block && matchesTranslationChunk(item, block.sourceLines, [block.blockId])) :
      chunks.find(item => item.id === current?.dataset.translationChunk);
    const linkedBlocks = chunk ? document.pdf.blocks.filter(item => matchesTranslationChunk(chunk, item.sourceLines, [item.blockId])) : [];
    const linkedBlock = !movedSinceSwitch.current ? linkedBlocks.find(item => item.blockId === previous?.block) : undefined;
    const r = current && bounds(current);
    const fraction = r ? Math.max(0, Math.min(1, (y - r.top) / Math.max(1, r.height))) : 0;
    position.current = chunk ? { chunk: chunk.id, block: (block ?? linkedBlock ?? linkedBlocks[0])?.blockId, fraction } : null;
    if (next) lastPdfScroll.current = pane.scrollTop;
    else lastTranslationScroll.current = pane.scrollTop;
    setPositionNotice(next && !chunk && page ? `第 ${page.dataset.pdfPage} 页暂无对应译块` : "");
    stopNavigation(); restorePaperPosition.current = true; movedSinceSwitch.current = false;
    manual.current = false; setSelection(""); setTranslated(next);
  }
  useLayoutEffect(() => {
    const anchor = position.current, pane = original.current;
    if (!pane || !restorePaperPosition.current) return;
    if (!translated && pdfUrl && settledPdf?.url !== pdfUrl) return;
    restorePaperPosition.current = false;
    manual.current = false;
    const node = translated ? [...pane.querySelectorAll<HTMLElement>("[data-translation-chunk]")]
      .find(el => el.dataset.translationChunk === anchor?.chunk) :
      [...pane.querySelectorAll<HTMLElement>("[data-block-id]")].find(el => el.dataset.blockId === anchor?.block);
    if (node && anchor) {
      const r = (node.closest("[data-page-only]") ?? node).getBoundingClientRect();
      pane.scrollTop += r.top - pane.getBoundingClientRect().top + anchor.fraction * r.height - pane.clientHeight * .32;
    } else {
      pane.scrollTop = translated ? lastTranslationScroll.current : lastPdfScroll.current;
      if (!translated && settledPdf?.available && anchor?.chunk) {
        setPositionNotice("此译块暂无可靠版面位置，已返回上次 PDF 阅读处");
      }
    }
  }, [translated, settledPdf, pdfUrl]);

  const messages = useMemo(() => view.conversation.filter(m => !m.sourceDeleted && (!m.sourceId || m.sourceId === sourceId)), [view.conversation, sourceId]);
  const turns = useMemo(() => groupIntoTurns(messages), [messages]);
  const answers = useMemo(() => messages.filter(m => m.role === "assistant"), [messages]);
  const latest = answers.at(-1);
  const selected = useMemo(() => messages.find(m => m.messageId === activeMessage) ?? latest, [messages, activeMessage, latest]);
  const selectedIdRef = useRef(selected?.messageId);
  selectedIdRef.current = selected?.messageId;

  const validated = useMemo(() => document ? answers.flatMap(message => messageEvidence(message, document, view.discussionId)) : [],
    [answers, document, view.discussionId]);
  const evidenceKey = JSON.stringify(validated);
  const evidence = useMemo(() => validated, [evidenceKey]);
  // Do NOT include hoverEvidence/activeEvidence here; toggling active highlight via DOM avoids reparsing the full document.
  const sourceInput = useMemo(() => document ? { document, evidence } : undefined, [document, evidence]);
  const projections = useMemo(() => document ? projectEvidence(document, evidence) : [], [document, evidence]);
  const paperLocations = useMemo(() => document?.pdf ? projections.map(projection => locatePaperEvidence(document, projection)) : [],
    [document, projections]);

  const annotationKey = JSON.stringify([view.sourceHighlights, view.sourceNotes]);
  const permanentMarks = useMemo(() => {
    if (!document) return [];
    const annotations = [
      ...(view.sourceHighlights ?? []).filter(h => !h.deleted && !h.sourceUpdated && h.layer === "source").map(h => ({ id: h.highlightId, quote: h.quote, lines: h.sourceLines, bundle: h.bundle, highlight: true })),
      ...(view.sourceNotes ?? []).filter(n => !n.deleted && !n.sourceUpdated && n.sentence?.layer === "source" && (n.anchor ?? n.placement)).map(n => ({ id: n.noteId, quote: n.sentence!.quote, lines: (n.anchor ?? n.placement)!.sourceLines, bundle: n.bundle, highlight: false })),
    ];
    return annotations.flatMap(a => {
      const projected = projectEvidence(document, [{ evidenceId: a.id, sourceId, bundleVersion: a.bundle, messageId: "", discussionId: "", answerRevision: "", displayNumber: 0, sourceLines: a.lines, quote: a.quote, relation: "context" }])[0];
      return projected.kind === "exact" ? [{ key: a.id, start: projected.start, end: projected.end, ...(a.highlight ? { highlightId: a.id } : { noteId: a.id }), ariaLabel: a.highlight ? "重点" : "备注" } satisfies RenderMark] : [];
    });
  }, [document, annotationKey, sourceId]);

  const active = projections.find(p => p.evidence.evidenceId === activeEvidence);
  const highlightedEvidenceId = hoverEvidence ?? activeEvidence;
  const run = view.agent?.run?.sourceId === sourceId ? view.agent.run : null;
  const agent = run ? view.agent : undefined;
  const running = !!run && ["running", "approval", "stopping"].includes(run.status);

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

  const stopNavigation = useCallback(() => {
    setAnswerTarget(null);
    cancel();
    setAnswerReturn(null);
    setAnswerChoices(null);
    jumpOrigin.current = null;
    jumpFromPdf.current = false;
    setReturnPosition(null);
    if (scrollAnimation.current !== null) {
      cancelAnimationFrame(scrollAnimation.current);
      scrollAnimation.current = null;
    }
    if (turn.current) turn.current.cancelled = true;
  }, [cancel]);

  const manualBrowse = useCallback(() => {
    stopNavigation();
    setPositionNotice("");
    restorePaperPosition.current = false;
    restored.current = true;
    movedSinceSwitch.current = true;
    manual.current = true;
  }, [stopNavigation]);

  const target = (id: string) => {
    const pane = original.current;
    const selector = `[data-evidence-block~="${id}"]`;
    return pane?.querySelector<HTMLElement>(`[data-evidence-ids~="${id}"], ${selector}:not([data-page-only=true])`)
      ?? pane?.querySelector<HTMLElement>(selector);
  };

  const moveTo = useCallback((id: string, keyboard = false, automatic = false, navigationIntent?: EvidenceNavigationIntent) => {
    const el = target(id), pane = original.current;
    if (!el || !pane || !isCurrentSource()) return;
    const current = () => isCurrentSource() && (!navigationIntent || isLatest(navigationIntent));
    if (!current()) return;
    if (jumpOrigin.current === null) jumpOrigin.current = pane.scrollTop;
    setReturnPosition(jumpOrigin.current);
    movedSinceSwitch.current = true;
    manual.current = false; setActiveEvidence(id);
    if (!automatic) setMobile("original");
    if (scrollAnimation.current !== null) {
      cancelAnimationFrame(scrollAnimation.current);
      scrollAnimation.current = null;
    }
    const targetRect = el.getBoundingClientRect(), paneRect = pane.getBoundingClientRect();
    const cardClearance = 200;
    let { top, bottom } = targetRect;
    let inset = pane.clientHeight * .32;
    const pdfPage = el.closest("[data-pdf-page]");
    const regions = pdfPage?.querySelectorAll(`[data-evidence-block~="${id}"]:not([data-page-only=true])`);
    if (regions && regions.length > 1) {
      const boxes = Array.from(regions, region => region.getBoundingClientRect());
      const pageTop = Math.min(...boxes.map(box => box.top));
      const pageBottom = Math.max(...boxes.map(box => box.bottom));
      const height = pageBottom - pageTop;
      if (height <= pane.clientHeight) {
        top = pageTop;
        bottom = pageBottom;
        inset = Math.min(inset, Math.max(0, pane.clientHeight - height - cardClearance));
      }
    }
    const visibleTarget = top >= paneRect.top && bottom <= paneRect.bottom;
    setCardAtTop(automatic && visibleTarget && bottom > paneRect.bottom - cardClearance);
    if (automatic && visibleTarget) return;
    const from = pane.scrollTop;
    const to = Math.max(0, Math.min(pane.scrollHeight - pane.clientHeight, from + top - paneRect.top - inset));
    if (keyboard || reduced() || Math.abs(to - from) > pane.clientHeight * 1.2) pane.scrollTo({ top: to, behavior: "instant" });
    else {
      const started = performance.now();
      const duration = parseFloat(getComputedStyle(pane).getPropertyValue("--reader-duration-move")) || 240;
      const tick = (now: number) => {
        if (!current()) { scrollAnimation.current = null; return; }
        const t = Math.min(1, (now - started) / duration);
        pane.scrollTop = from + (to - from) * (1 - Math.pow(1 - t, 3));
        scrollAnimation.current = t < 1 ? requestAnimationFrame(tick) : null;
      };
      scrollAnimation.current = requestAnimationFrame(tick);
    }
    if (keyboard) { el.tabIndex = -1; el.focus({ preventScroll: true }); }
  }, [isCurrentSource, isLatest]);

  useLayoutEffect(() => {
    if (visible) return;
    manual.current = false;
    if (!readingSession) stopNavigation();
    turn.current = null;
    returnFocus.current = null;
    jumpOrigin.current = null;
    setAnswerChoices(null);
    setAnswerReturn(null);
    setAnswerTarget(null);
    setActiveEvidence(undefined);
    setHoverEvidence(undefined);
    setReturnPosition(null);
  }, [visible, selectionGeneration, stopNavigation]);

  useLayoutEffect(() => {
    if (!visible || !intent || intent.sourceId !== sourceId || !isCurrentSource() || !isLatest(intent)) return;
    if (intent.destination === "answer") {
      if (intent.discussionId !== view.discussionId || intent.bundleVersion !== view.sourceBundleVersion ||
          intent.sourceGeneration !== (view.sourceGeneration ?? view.resetVersion)) {
        consume(intent);
        return;
      }
      if (!document) return;
      const message = messages.find(item => item.messageId === intent.messageId);
      const cited = message && messageEvidence(message, document, view.discussionId).some(item => item.evidenceId === intent.evidenceId);
      if (!cited) { consume(intent); return; }
      if (mobile !== "chat") { setMobile("chat"); return; }
      const answer = [...(chat.current?.querySelectorAll<HTMLElement>("[data-message-id]") ?? [])]
        .find(element => element.dataset.messageId === intent.messageId);
      const citation = [...(answer?.querySelectorAll<HTMLButtonElement>("[data-citation]") ?? [])]
        .find(element => element.dataset.citation === intent.evidenceId);
      if (!consume(intent) || !citation) return;
      followChat.current = false;
      if (turn.current) turn.current.cancelled = true;
      setActiveEvidence(undefined);
      citation.scrollIntoView({ block: "nearest", behavior: "instant" });
      citation.focus({ preventScroll: true });
      setHoverEvidence(undefined);
      safeWrite(`focus.activeAnswer:${draftKey}`, intent.messageId);
      setActiveMessage(intent.messageId);
      setAnswerTarget({ messageId: intent.messageId, evidenceId: intent.evidenceId, discussionId: intent.discussionId });
      return;
    }
    manual.current = false;
    restored.current = true;
    restorePaperPosition.current = false;
    if (mobile !== "original") { setMobile("original"); return; }
    if (original.current && waitingPosition.current?.nonce !== intent.nonce) {
      waitingPosition.current = { nonce: intent.nonce, scrollTop: original.current.scrollTop };
    }
    if (!document) return;
    const message = messages.find(item => item.messageId === intent.messageId);
    const cited = message && messageEvidence(message, document, view.discussionId).find(item => item.evidenceId === intent.evidenceId);
    if (!cited) { consume(intent); return; }
    if (selected?.messageId !== intent.messageId) {
      setActiveMessage(intent.messageId);
      return;
    }
    const verified = projections.find(item => item.evidence.evidenceId === intent.evidenceId);
    if (!verified || verified.kind === "unavailable") {
      if (consume(intent)) setActiveEvidence(intent.evidenceId);
      return;
    }
    const paper = paperLocations.find(item => item.evidence.evidenceId === intent.evidenceId);
    if (activePdfUrl) {
      const pdfTarget = !!paper?.pdfPages.length;
      const wantsTranslation = intent.preferredView === "translation";
      if (!wantsTranslation && pdfTarget && settledPdf?.url !== activePdfUrl) return;
      const needsTranslation = wantsTranslation || !pdfTarget || !target(intent.evidenceId);
      if (needsTranslation && translationReady) {
        const pane = original.current;
        if (pane) {
          lastPdfScroll.current = pane.scrollTop;
          if (paper?.translationChunks.length) {
            jumpOrigin.current = pane.scrollTop;
            jumpFromPdf.current = true;
          }
        }
        waitingPosition.current = null;
        setSelection("");
        setTranslated(true);
        return;
      }
      if (needsTranslation && (translationState === "running" || prep?.status === "running")) return;
    }
    if (!consume(intent)) return;
    if (target(intent.evidenceId)) moveTo(intent.evidenceId, intent.keyboard, false, intent);
    else {
      if (showingTranslation && intent.preferredView !== "translation" && original.current) {
        original.current.scrollTop = lastTranslationScroll.current;
      }
      setActiveEvidence(intent.evidenceId);
    }
  }, [visible, intent, sourceId, isCurrentSource, isLatest, consume, document, messages, draftKey, view.discussionId,
    view.sourceBundleVersion, view.sourceGeneration, view.resetVersion,
    selected?.messageId, mobile, prep?.status, translationState, translationReady, showingTranslation, projections, paperLocations, activePdfUrl, settledPdf, pdfRevision, moveTo]);

  const cite = useCallback((message: ReaderMessage, id: string, keyboard: boolean, origin: HTMLButtonElement) => {
    if (!isCurrentSource()) return;
    stopNavigation();
    manual.current = false;
    restored.current = true;
    restorePaperPosition.current = false;
    setPositionNotice("");
    returnFocus.current = { messageId: message.messageId, evidenceId: id, origin };
    setHoverEvidence(undefined);
    safeWrite(`focus.activeAnswer:${draftKey}`, message.messageId);
    setActiveMessage(message.messageId);
    setActiveEvidence(undefined);
    start({ sourceId, messageId: message.messageId, evidenceId: id, preferredView: showingTranslation ? "translation" : pdfUrl ? "pdf" : "source", keyboard });
  }, [stopNavigation, draftKey, isCurrentSource, sourceId, showingTranslation, pdfUrl, start]);

  const handleSelectMessage = useCallback((messageId: string) => {
    if (selectedIdRef.current !== messageId) {
      stopNavigation();
      safeWrite(`focus.activeAnswer:${draftKey}`, messageId);
      setActiveMessage(messageId);
      setActiveEvidence(undefined);
    }
  }, [stopNavigation, draftKey]);

  const handleHoverCitation = useCallback((messageId: string, id: string | undefined) => {
    if (messageId === selectedIdRef.current) setHoverEvidence(id);
  }, []);

  useLayoutEffect(() => {
    if (!document || !original.current || restored.current || intent || (pdfUrl && !pdfRevision)) return;
    restored.current = true;
    try {
      const raw = safeRead(bookmark);
      const saved = raw ? JSON.parse(raw) : view.readingStarted && view.navigationCurrent?.bundleVersion === document.bundleVersion ? { line: view.navigationCurrent.sourceLines[0], offset: 0 } : null;
      if (saved && Number.isSafeInteger(saved.line) && Number.isFinite(saved.offset)) {
        const el = original.current.querySelector<HTMLElement>(`[data-source-line="${saved.line}"]`);
        if (el) original.current.scrollTop += el.getBoundingClientRect().top - original.current.getBoundingClientRect().top + saved.offset;
      }
    } catch { /* Ignore malformed display bookmarks, never mutate the Cursor. */ }
  }, [document, bookmark, pdfUrl, pdfRevision, intent]);

  useEffect(() => {
    const pending = turn.current;
    if (!visible || !pending || pending.located || pending.cancelled || !latest || pending.seen.has(latest.messageId) || !evidence.length) return;
    const first = projections.find(p => p.evidence.messageId === latest.messageId && p.kind !== "unavailable");
    if (first && selected?.messageId === latest.messageId) { pending.located = true; if ((shell.current?.clientWidth ?? 0) >= 960) moveTo(first.evidence.evidenceId, false, true); }
  }, [visible, latest, evidence, projections, selected, moveTo]);

  useLayoutEffect(() => { if (followChat.current && chat.current) chat.current.scrollTop = chat.current.scrollHeight; }, [messages.at(-1)?.content]);

  const acceptSession = readingSession?.accept;
  const apply = useCallback(async (key: string, operation: Promise<ReaderHostResult<ReadingWindow>>, success?: (value: ReadingWindow) => void) => {
    const attempt = Symbol(key);
    attempts.current.set(key, attempt);
    const current = () => isCurrentSource() && attempts.current.get(key) === attempt;
    try {
      const result = await operation;
      if (!current()) return false;
      if (!result.ok) showOperationError(key, result.error.message);
      else if (result.value.source.sourceId === sourceId) {
        if (selectionGeneration !== undefined) acceptSession?.(result.value, selectionGeneration);
        else setView(result.value);
        showOperationError(key, "");
        success?.(result.value);
        return true;
      }
    } catch (failure) { if (current()) showOperationError(key, String(failure)); }
    finally { if (attempts.current.get(key) === attempt) attempts.current.delete(key); }
    return false;
  }, [setView, acceptSession, isCurrentSource, selectionGeneration, sourceId, showOperationError]);

  const sendMessage = useCallback(async (content: string) => {
    if (!content || sendBusy.current || sending || running) return false;
    sendBusy.current = true;
    stopNavigation();
    safeWrite(`focus.activeAnswer:${draftKey}`, ""); setSending(true); showOperationError("send", ""); if (run) setDismissedRun(run.runId); setActiveMessage(null); setActiveEvidence(undefined);
    followChat.current = true; turn.current = { seen: new Set(messages.map(m => m.messageId)), cancelled: false, located: false };
    if (sendRequest.current?.content !== content) sendRequest.current = { content, id: createReaderId() };
    const ok = await apply("send", host.sendMessage({ sourceId, sessionId: view.sessionId,
      discussionId: view.discussionId, receipt: null, content, requestId: sendRequest.current.id }));
    if (ok) { sendRequest.current = null; } else turn.current = null;
    sendBusy.current = false; setSending(false);
    return ok;
  }, [apply, draftKey, host, messages, run, running, sending, showOperationError, sourceId, stopNavigation, view.sessionId]);

  const handleStop = useCallback(() => { if (host.stop) void apply("stop", host.stop()); }, [apply, host]);
  const handleApprove = useCallback((input: Parameters<NonNullable<ReaderHost["approve"]>>[0]) => host.approve ? apply("approval", host.approve(input)) : Promise.resolve(false), [apply, host]);

  function backToAnswer(evidenceId: string) {
    const item = evidence.find(entry => entry.evidenceId === evidenceId);
    if (!item || !isCurrentSource()) return;
    stopNavigation();
    manual.current = false;
    followChat.current = false;
    safeWrite(`focus.activeAnswer:${draftKey}`, item.messageId);
    setActiveMessage(item.messageId);
    setActiveEvidence(evidenceId);
    setMobile("chat");
    const openedFrom = returnFocus.current;
    const origin = openedFrom?.messageId === item.messageId && openedFrom.evidenceId === evidenceId ? openedFrom.origin : undefined;
    setAnswerReturn({ messageId: item.messageId, evidenceId, origin, discussionId: view.discussionId });
  }

  useLayoutEffect(() => {
    if (!answerReturn) return;
    setAnswerReturn(null);
    if (!visible || mobile !== "chat" || !isCurrentSource() || answerReturn.discussionId !== view.discussionId) return;
    const { messageId, evidenceId, origin } = answerReturn;
    const citation = origin && chat.current?.contains(origin) ? origin :
      chat.current?.querySelector<HTMLElement>(`[data-message-id="${messageId}"] [data-citation="${evidenceId}"]`);
    citation?.scrollIntoView({ block: "nearest", behavior: "instant" });
    citation?.focus({ preventScroll: true });
  }, [answerReturn, isCurrentSource, mobile, view.discussionId, visible]);

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
  const translationInterrupted = ["failed", "cancelled", "interrupted"].includes(translationState ?? "");
  const activePaper = paperLocations.find(item => item.evidence.evidenceId === activeEvidence);
  const activeBlocks = activePaper?.pdfBlocks ?? [];
  const activePages = activePaper?.pdfPages ?? [];
  const activeChunks = activePaper?.translationChunks ?? [];
  const locationLabel = active?.kind === "unavailable" ? " · 历史引文" : showingTranslation ?
    activeChunks.length ? " · 译块定位" : " · 译块位置暂不可用" : pdfUrl ?
    settledPdf?.available && activePages.length && activeEvidence && target(activeEvidence) ?
      ` · 第 ${activePages.join("、")} 页 · ${activeBlocks.some(b => boxesForBlock(b).length) ? "段落定位" : "页定位"}` : " · 版面位置暂不可用" :
    active?.kind === "block" ? " · 段落定位" : "";
  const partCount = showingTranslation ? activeChunks.length : new Set([
    ...activeBlocks.flatMap(block => boxesForBlock(block).map(box => `${block.blockId}:${box.join(",")}`)),
    ...activePages.filter(page => !activeBlocks.some(block => block.page === page) ||
      activeBlocks.some(block => block.page === page && !boxesForBlock(block).length)).map(page => `page:${page}`),
  ]).size;
  function returnToReading() {
    const top = jumpOrigin.current;
    const backToPdf = jumpFromPdf.current;
    stopNavigation();
    manual.current = false;
    if (top !== null && backToPdf) {
      lastPdfScroll.current = top;
      position.current = null;
      restorePaperPosition.current = true;
      setPositionNotice("");
      setTranslated(false);
    } else if (top !== null) original.current?.scrollTo({ top, behavior: "instant" });
    setActiveEvidence(undefined);
  }
  const choiceItems = answerChoices && answerChoices.discussionId === view.discussionId
    ? evidence.filter(item => answerChoices.ids.includes(item.evidenceId)) : [];
  function closeAnswerChooser() {
    setAnswerChoices(null);
    answerChoices?.opener.focus({ preventScroll: true });
  }
  const activeFocusIndex = focusedTurn >= 0 && focusedTurn < turns.length ? focusedTurn : turns.length - 1;

  return <section ref={shell} className="conversation-reader" data-fullscreen={!!fullscreen} data-mobile={mobile} data-font-size={fontSize} hidden={!visible} style={{ "--source-share": `${share}%`, "--source-font-size": `${readingFontSizes[fontSize as keyof typeof readingFontSizes] ?? 18}px` } as CSSProperties}
    onKeyDown={e => {
      if (e.key !== "Escape" || e.defaultPrevented || e.nativeEvent.isComposing || e.keyCode === 229 || globalThis.document.querySelector("dialog[open]")) return;
      if (notesOpen) { e.stopPropagation(); closeNotes(); return; }
      if (choiceItems.length) { e.stopPropagation(); closeAnswerChooser(); return; }
      if (!activeEvidence || fullscreen) return;
      if (returnFocus.current?.evidenceId === activeEvidence) backToAnswer(activeEvidence);
      else stopNavigation();
      setActiveEvidence(undefined);
    }}>
    {documentError && <div role="alert" className="source-reader-error">{documentError}<button onClick={() => setReloadDocument(v => v + 1)}>重试</button><button onClick={() => setDocumentError("")}>关闭</button></div>}
    {Object.entries(operationErrors).map(([key, message]) => <div key={key} role="alert" className="source-reader-error">{message}<button onClick={() => showOperationError(key, "")}>关闭</button></div>)}
    {!running && run?.error && dismissedRun !== run.runId && <div role="alert" className="source-reader-error">{run.error}<button onClick={() => setDismissedRun(run.runId)}>关闭</button></div>}
    <div className="source-reader-columns">
      <div className="source-original-pane" data-paper={!!pdfUrl}>
        {pdfUrl && <div className="paper-view-controls"><button aria-pressed={!showingTranslation} onClick={() => switchPaper(false)}>原版 PDF</button>
          <button aria-pressed={!!showingTranslation} disabled={!translationReady} onClick={() => switchPaper(true)}>中文译文{translationReady ? "" : translationState === "running" ? " · 准备中" : translationInterrupted ? " · 未完成" : " · 未就绪"}</button>
          {translationInterrupted && host.resumePreparation && <button onClick={() => void apply("translation", host.resumePreparation!(sourceId, createReaderId()))}>重试译文</button>}</div>}
        {pdfUrl && positionNotice && <span role="status">{positionNotice}</span>}
        <div ref={original} className="source-original" data-evidence-focus={activeEvidence ? "true" : undefined} aria-label="文章原文" tabIndex={0} onPointerMove={e => { pointerX.current = e.clientX; }} onWheel={manualBrowse} onTouchStart={manualBrowse}
          onPointerDown={e => { if (e.target === e.currentTarget) manualBrowse(); }}
          onKeyDown={e => { if (!(e.target as HTMLElement).closest("button, input, textarea, select") && ["PageDown", "PageUp", "ArrowDown", "ArrowUp", "Home", "End", " "].includes(e.key)) manualBrowse(); }}
          onScroll={event => {
            const pane = event.currentTarget;
            const waiting = waitingPosition.current;
            if (intent && waiting?.nonce === intent.nonce && waiting.scrollTop !== pane.scrollTop && consume(intent)) manualBrowse();
            if (!manual.current || !bookmark) return;
            const top = pane.getBoundingClientRect().top;
            const block = [...pane.querySelectorAll<HTMLElement>("[data-source-line]")].find(el => el.getBoundingClientRect().bottom > top);
            if (block) safeWrite(bookmark, JSON.stringify({ line: Number(block.dataset.sourceLine), offset: top - block.getBoundingClientRect().top }));
          }}
          onMouseUp={() => { const selectedText = window.getSelection()?.toString().trim() ?? ""; if (selectedText) { stopNavigation(); setSelection(selectedText.slice(0, 4000)); } }}
          onClick={e => {
            const node = e.target as HTMLElement;
            const choices = node.closest<HTMLElement>("[data-evidence-choices]");
            const id = node.closest<HTMLElement>("[data-evidence]")?.dataset.evidence;
            if (id) backToAnswer(id);
            else if (choices?.dataset.evidenceChoices && isCurrentSource()) {
              stopNavigation();
              setAnswerChoices({ ids: choices.dataset.evidenceChoices.split(" "), opener: choices, discussionId: view.discussionId });
            } else {
              const mark = node.closest<HTMLElement>("[data-anno-key], [data-anno-bulb]");
              if (mark) openNotes(mark);
            }
          }}>
          <ActiveSourceCitation.Provider value={returnFocus.current?.evidenceId === activeEvidence ? activeEvidence : undefined}>
            {document?.pdf && pdfUrl ? showingTranslation ? <TranslatedPaper document={document} evidence={paperLocations} /> :
              <OriginalPaper key={pdfUrl} pdf={document.pdf} url={pdfUrl} evidence={paperLocations} active={highlightedEvidenceId} onReady={pdfReady} onUnavailable={pdfUnavailable} /> : document ? <article><MarkdownContent text={document.markdown} sourceId={sourceId} marks={permanentMarks} sourceEvidence={sourceInput} /></article> : <span role="status" className="source-loading">加载中…</span>}
          </ActiveSourceCitation.Provider>
        </div>
        {selection && <div className="source-selection-actions"><button onClick={() => { composer.current?.insertQuote(selection); setSelection(""); setMobile("chat"); }}>引用</button><button onClick={e => { setNoteDraft(`「${selection}」\n`); openNotes(e.currentTarget); setSelection(""); }}>记笔记</button><button aria-label="取消选择" onClick={() => setSelection("")}>×</button></div>}
        {choiceItems.length > 0 && <SourceAnswerChooser items={choiceItems} answers={answers} onChoose={backToAnswer} onClose={closeAnswerChooser} />}
        {active && !choiceItems.length && <aside className="source-evidence-card" data-top={cardAtTop} aria-label="原文证据"><button aria-label="关闭证据" onClick={() => { stopNavigation(); setActiveEvidence(undefined); }}>×</button><button onClick={() => backToAnswer(active.evidence.evidenceId)}>证据 {active.evidence.displayNumber}{locationLabel}</button><p>{active.evidence.quote.exact}</p>{partCount > 1 && <button onClick={nextRegion}>下一处（{regionNumber + 1}/{partCount}）</button>}{returnPosition !== null && <button onClick={returnToReading}>返回阅读位置</button>}</aside>}
      </div>
      <div className="source-splitter" role="separator" aria-label="调整原文宽度" aria-orientation="vertical" aria-valuemin={40} aria-valuemax={70} aria-valuenow={share} tabIndex={0}
        onKeyDown={e => { if (["ArrowLeft", "ArrowRight"].includes(e.key)) { e.preventDefault(); const v = Math.max(40, Math.min(70, share + (e.key === "ArrowLeft" ? -2 : 2))); setShare(v); safeWrite("focus.sourceShare", String(v)); } }}
        onPointerDown={e => { e.currentTarget.setPointerCapture(e.pointerId); }} onPointerMove={e => { if (!e.currentTarget.hasPointerCapture(e.pointerId) || !shell.current) return; const rect = shell.current.getBoundingClientRect(); const v = Math.max(40, Math.min(70, (e.clientX - rect.left) / rect.width * 100)); setShare(v); safeWrite("focus.sourceShare", String(v)); }} onPointerUp={e => e.currentTarget.releasePointerCapture(e.pointerId)} />
      <div className="source-chat-pane">
        <div ref={chat} className="source-chat" aria-label="文章对话" onWheel={stopNavigation} onTouchStart={stopNavigation} onScroll={updateChatFocus}>
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
              {guideOpen && opening.structure && <ul className="source-opening__list">{opening.structure.map(n => <li key={n.id} data-child={!!n.parentId}><button onClick={() => { stopNavigation(); manual.current = false; setMobile("original"); requestAnimationFrame(() => { const blocks = [...(original.current?.querySelectorAll<HTMLElement>("[data-source-line]") ?? [])]; const el = blocks.find(b => Number(b.dataset.sourceLine) >= n.sourceLines[0]); el?.scrollIntoView({ block: "start", behavior: reduced() ? "instant" : "smooth" }); }); }}>{n.title}</button></li>)}</ul>}
            </section>
          )}
          {opening?.status === "running" && <div className="source-opening-skeleton" aria-label="正在准备导读" role="status"><i /><i /><i /></div>}
          {openingError && <p role="alert" className="source-opening-error">{openingError}<button onClick={() => setReloadOpening(v => v + 1)}>重试导读</button><button onClick={() => setOpeningError("")}>关闭</button></p>}
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
                  activeCitation={answerTarget?.messageId === message.messageId ? answerTarget.evidenceId : undefined}
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
                <select className="source-discussion-select" aria-label="对话记录" value={view.discussionId ?? ""} disabled={running} onChange={e => void apply("discussion", host.selectDiscussionSource!(sourceId, e.target.value))}>
                  {view.discussions!.map((d, i) => <option key={d.discussionId} value={d.discussionId}>对话 {i + 1}</option>)}
                </select>
              )}
              {opening?.status === "ready" && (
                <button type="button" className="source-icon-btn" aria-label={guideOpen ? "收起导读" : "展开导读"} title={guideOpen ? "收起导读" : "展开导读"} aria-pressed={guideOpen} onClick={() => setGuideOpen(!guideOpen)}>
                  <ListOutline />
                </button>
              )}
              <button ref={notesButton} type="button" className="source-icon-btn" aria-label="笔记" title="笔记" aria-pressed={notesOpen} onClick={e => notesOpen ? closeNotes() : openNotes(e.currentTarget)}>
                <Pin />
              </button>
              {onFullscreenChange && (
                <button type="button" className="source-icon-btn" aria-label={fullscreen ? "退出全屏" : "对话全屏"} title={fullscreen ? "退出全屏" : "对话全屏"} aria-pressed={!!fullscreen} onClick={() => onFullscreenChange(!fullscreen)}>
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
            agent={agent}
            approvalManaged={approvalManaged}
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
        <button type="button" className="source-icon-btn" onClick={closeNotes} aria-label="关闭笔记"><Close /></button>
      </div>
      <textarea ref={noteInput} aria-label="笔记内容" placeholder="记录想法或结论…" value={noteDraft} onChange={e => setNoteDraft(e.target.value)} />
      {host.createSourceNote && <button className="source-notes-save" disabled={!noteDraft.trim()} onClick={async () => { const request = noteEdit && host.changeSourceNote ? host.changeSourceNote(sourceId, noteEdit.id, "edit", noteEdit.revision, createReaderId(), noteDraft.trim()) : host.createSourceNote!({ sourceId, requestId: createReaderId(), content: noteDraft.trim(), kind: "thought", origin: "user" });
        await apply("note-save", request, result => {
          if (result.noteOperation?.status === "conflict") {
            showOperationError("note-save", "笔记已更新，请核对当前内容后再保存。");
            if (result.noteOperation.current) setNoteEdit({ id: result.noteOperation.current.noteId, revision: result.noteOperation.current.revision });
            return;
          }
          setNoteDraft(""); setNoteEdit(null);
        }); }}>保存笔记</button>}
      {(view.sourceNotes ?? []).filter(n => !n.deleted || n.canUndo).map(n => <article key={n.noteId}>{n.sentence && <blockquote>{n.sentence.quote.exact}</blockquote>}<MarkdownContent text={n.content} />{host.changeSourceNote && <div className="source-note-actions">{!n.deleted && <button onClick={() => { setNoteEdit({ id: n.noteId, revision: n.revision }); setNoteDraft(n.content); }}>编辑</button>}<button onClick={() => void apply(`note:${n.noteId}`, host.changeSourceNote!(sourceId, n.noteId, n.deleted ? "undo" : "delete", n.revision, createReaderId()))}>{n.deleted ? "撤销删除" : "删除"}</button></div>}</article>)}
      {(view.sourceHighlights ?? []).filter(h => !h.deleted || h.canUndo).map(h => <article key={h.highlightId}><blockquote>{h.quote.exact}</blockquote>{host.changeHighlight && <div className="source-note-actions"><button onClick={() => void apply(`highlight:${h.highlightId}`, host.changeHighlight!(sourceId, h.highlightId, h.deleted ? "undo" : "delete", h.revision, createReaderId()))}>{h.deleted ? "撤销删除重点" : "取消重点"}</button></div>}</article>)}
    </aside>}
  </section>;
}
