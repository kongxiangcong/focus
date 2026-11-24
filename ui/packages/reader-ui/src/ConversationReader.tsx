import { forwardRef, memo, useCallback, useEffect, useImperativeHandle, useLayoutEffect, useMemo, useRef, useState, type CSSProperties, type KeyboardEvent as ReactKeyboardEvent } from "react";
import { createReaderId, type ReaderHost, type ReaderHostResult, type ReaderMessage, type ReadingDocument, type ReadingOpening, type ReadingWindow, type SourceTextSelectionInput } from "@focus/reader-contracts";
import { useEvidenceNavigation, type EvidenceNavigation, type EvidenceNavigationIntent } from "./evidence-navigation";
import type { ReadingSession } from "./reading-session";
import { MarkdownContent } from "./MarkdownContent";
import { ActiveSourceCitation } from "./SourceEvidenceMarkers";
import { TranslatedPaper } from "./TranslatedPaper";
import { locatePaperEvidence, overlapsSourceLines } from "./paper-evidence";
import { blockAtReadingLine, blockAtSourcePosition, fractionAtReadingLine, restoreReadingLine, sourceLinesAt, sourcePositionAt, type SourceLines, type SourcePosition } from "./source-position";
import { citedMarkdown, messageEvidence, projectEvidence, type EvidenceProjection } from "./source-evidence";
import type { RenderMark } from "./rehype-annotations";
import { captureSourceText, documentNoteMarks } from "./selected-source-note";
import { readingFontSizes } from "./typography";
import { AgentControls } from "./AgentControls";
import { AssetInstanceContext } from "./asset-context";
import { ArrowUp, Close, Collapse, Expand, ListOutline, Pin, StopSquare } from "./ReaderIcons";
import { canDismissReaderLayer } from "./reader-keyboard";
import "./conversation-reader.css";

const safeRead = (key: string) => { try { return localStorage.getItem(key); } catch { return null; } };
const safeWrite = (key: string, value: string) => { try { localStorage.setItem(key, value); } catch { /* Session remains usable. */ } };
const reduced = () => window.document.documentElement.dataset.reducedMotion === "true" || typeof matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").matches;
const scrollKeys = new Set(["PageDown", "PageUp", "ArrowDown", "ArrowUp", "Home", "End", " "]);

function isScrollKey(event: ReactKeyboardEvent) {
  const target = event.target as HTMLElement;
  return !event.defaultPrevented && !event.ctrlKey && !event.altKey && !event.metaKey && scrollKeys.has(event.key) &&
    !target.closest("input, textarea, select, [contenteditable=true]") && (event.key !== " " || !target.closest("button, a"));
}

function sourcePdfPage(pdf: ReadingDocument["pdf"], sourceLines: SourceLines, quoteOffsets?: SourceLines) {
  if (!pdf) return;
  const pages = new Set(pdf.blocks.filter(block => overlapsSourceLines(block.sourceLines, sourceLines) &&
    (!quoteOffsets || !block.offsets || block.offsets[0] < quoteOffsets[1] && quoteOffsets[0] < block.offsets[1]))
    .map(block => block.page)
    .filter(page => Number.isSafeInteger(page) && page > 0 && (!pdf.pages?.length || pdf.pages.some(item => item.page === page))));
  if (pages.size === 1) return [...pages][0];
}

function pdfOriginalHref(url: string, pdfHash?: string, page?: number) {
  const [path] = url.split("#", 1);
  const hash = pdfHash ? `${path.includes("?") ? "&" : "?"}pdfHash=${encodeURIComponent(pdfHash)}` : "";
  return `${path}${hash}${page ? `#page=${page}` : ""}`;
}

type AnswerLocation = { messageId: string; evidenceId: string; origin?: HTMLButtonElement };
type DiscussionCitation = AnswerLocation & { discussionId?: string };
type AnswerReturn = { messageId: string; evidenceId?: string; origin?: HTMLButtonElement; discussionId?: string };

function answerDestination(chat: HTMLElement | null, messageId: string, evidenceId?: string, origin?: HTMLButtonElement) {
  const answer = [...(chat?.querySelectorAll<HTMLElement>("[data-message-id]") ?? [])]
    .find(element => element.dataset.messageId === messageId);
  if (!evidenceId) return answer;
  if (origin && answer?.contains(origin)) return origin;
  return [...(answer?.querySelectorAll<HTMLButtonElement>("[data-citation]") ?? [])]
    .find(element => element.dataset.citation === evidenceId);
}

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
}

const ConversationMessage = memo(function ConversationMessage({
  message, markdown, isSelected, activeCitation, onSelect, onCite,
}: MessageItemProps) {
  const handleCitation = useCallback((id: string, keyboard: boolean, origin: HTMLButtonElement) => onCite(message, id, keyboard, origin), [onCite, message]);
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
  const languagePreference = `focus.sourceLanguage:${view.workspace?.workspaceId ?? "local"}:${sourceId}`;
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
  const [paperLanguage, setPaperLanguage] = useState(() => safeRead(languagePreference));
  const [currentPage, setCurrentPage] = useState<number>();
  const locatedPage = useRef<{ top: number; page?: number } | null>(null);
  const position = useRef<(SourcePosition & { fraction: number }) | null>(null);
  const restorePaperPosition = useRef(false);
  const scrollByLanguage = useRef({ original: 0, translation: 0 });
  const [selection, setSelection] = useState<{ text: string; range: Range } | null>(null);
  const [noteSelection, setNoteSelection] = useState<SourceTextSelectionInput>();
  const [noteEdit, setNoteEdit] = useState<{ id: string; revision: number } | null>(null);
  const [noteDraft, setNoteDraft] = useState("");
  const [savingNote, setSavingNote] = useState(false);
  const noteRequest = useRef<{ key: string; id: string; busy: boolean } | null>(null);
  const [activeMessage, setActiveMessage] = useState<string | null>(null), [activeEvidence, setActiveEvidence] = useState<string | undefined>();
  const [answerReturn, setAnswerReturn] = useState<AnswerReturn | null>(null);
  const [lastAnswerCitation, setLastAnswerCitation] = useState<DiscussionCitation | null>(null);
  const [mobile, setMobile] = useState("chat"), [guideOpen, setGuideOpen] = useState(false), [notesOpen, setNotesOpen] = useState(false);
  const notesButton = useRef<HTMLButtonElement>(null);
  const noteInput = useRef<HTMLTextAreaElement>(null);
  const notesOpener = useRef<HTMLElement | null>(null);
  function openNotes(opener: HTMLElement) {
    if (!notesOpen) notesOpener.current = opener;
    setNotesOpen(true);
  }
  const closeNotes = useCallback(() => {
    if (noteSelection) { setNoteSelection(undefined); setNoteDraft(""); }
    setNotesOpen(false);
  }, [noteSelection]);
  useEffect(() => {
    if (!visible || !notesOpen) return;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (!canDismissReaderLayer(event)) return;
      event.preventDefault();
      closeNotes();
    };
    globalThis.document.addEventListener("keydown", closeOnEscape);
    return () => globalThis.document.removeEventListener("keydown", closeOnEscape);
  }, [notesOpen, visible, closeNotes]);
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
  const sourceBody = useRef<HTMLDivElement>(null);
  useLayoutEffect(() => {
    setSelection(null);
    setNoteSelection(undefined);
    setNoteDraft("");
    setNoteEdit(null);
    setSavingNote(false);
    noteRequest.current = null;
  }, [draftKey]);
  const sendRequest = useRef<{ content: string; id: string } | null>(null);
  const sendBusy = useRef(false);
  const composer = useRef<ComposerHandle>(null);
  const pendingAnswerCitation = useRef<(DiscussionCitation & { nonce: string }) | null>(null);
  const [answerTarget, setAnswerTarget] = useState<(AnswerLocation & { discussionId: string }) | null>(null);
  const manual = useRef(false), followChat = useRef(true), turn = useRef<{ seen: Set<string>; cancelled: boolean; located: boolean } | null>(null);
  const localNavigation = useEvidenceNavigation();
  const { intent, start, isLatest, consume, cancel, isResettingDiscussion } = evidenceNavigation ?? localNavigation;
  const resettingDiscussion = isResettingDiscussion(sourceId, view.discussionId);
  const [focusedTurn, setFocusedTurn] = useState<number>(-1);
  const chatScrollTop = useRef(0);
  const restored = useRef(false), bookmark = document ? `focus.sourceBookmark:${scope}:${document.bundleVersion}` : "";
  useEffect(() => {
    setActiveMessage(safeRead(`focus.activeAnswer:${draftKey}`));
    setActiveEvidence(undefined);
    setAnswerTarget(target => target?.discussionId === view.discussionId ? target : null);
    pendingAnswerCitation.current = null;
    setLastAnswerCitation(current => current?.discussionId === view.discussionId ? current : null);
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
  const originalFormat = document?.original === undefined ? (document?.pdf ? "pdf" : undefined) : document.original?.format;
  const originalUrl = originalFormat ? host.sourceOriginalUrl?.(sourceId) : undefined;
  const originalHref = originalUrl && originalFormat === "pdf"
    ? pdfOriginalHref(originalUrl, document?.pdf?.pdfHash, currentPage) : originalUrl;
  const translation = document?.translation;
  const translationState = translation?.status;
  const modernDocument = document?.language !== undefined || translation?.segments !== undefined;
  const chineseSource = /^zh(?:[-_]|$)/i.test(document?.language ?? "") || translationState === "not_applicable";
  const translationReady = !chineseSource && translation?.status === "ready" &&
    (!translation.bundleVersion || translation.bundleVersion === document?.bundleVersion) &&
    !!(translation.segments ?? translation.chunks).length;
  const showingTranslation = translationReady && (paperLanguage === "zh" || modernDocument && paperLanguage !== "source");

  const updateOriginalPage = useCallback((pane: HTMLElement | null = original.current) => {
    if (!document?.pdf || !pane?.clientHeight) return;
    if (locatedPage.current?.top === pane.scrollTop) {
      setCurrentPage(locatedPage.current.page);
      return;
    }
    locatedPage.current = null;
    const block = blockAtReadingLine(pane);
    setCurrentPage(block ? sourcePdfPage(document.pdf, sourceLinesAt(block)) : undefined);
  }, [document?.pdf]);

  function switchPaper(next: boolean) {
    const pane = original.current;
    if (!pane || !document || showingTranslation === next) return;
    const cited = activeEvidence ? target(activeEvidence) : undefined;
    const citedBounds = cited?.getBoundingClientRect();
    const paneBounds = pane.getBoundingClientRect();
    const citedBlock = citedBounds && citedBounds.top < paneBounds.bottom && citedBounds.bottom > paneBounds.top
      ? cited?.closest<HTMLElement>("[data-source-line]") : undefined;
    const anchor = citedBlock ?? blockAtReadingLine(pane);
    const projection = citedBlock && active;
    const prior = position.current;
    if (citedBlock && projection && projection.kind !== "unavailable") {
      position.current = { lines: projection.sourceLines, offset: projection.quoteOffsets?.[0],
        fraction: fractionAtReadingLine(pane, citedBlock) };
    } else if (!anchor || manual.current || anchor.dataset.translationGranularity !== "group" || !prior || blockAtSourcePosition(pane, prior) !== anchor) {
      position.current = anchor ? { ...sourcePositionAt(anchor), fraction: fractionAtReadingLine(pane, anchor) } : null;
    }
    scrollByLanguage.current[showingTranslation ? "translation" : "original"] = pane.scrollTop;
    stopNavigation();
    restorePaperPosition.current = true;
    locatedPage.current = null;
    manual.current = false;
    setSelection(null);
    const language = next ? "zh" : "source";
    safeWrite(languagePreference, language);
    setPaperLanguage(language);
  }

  useLayoutEffect(() => {
    const anchor = position.current, pane = original.current;
    if (!pane || !restorePaperPosition.current) return;
    restorePaperPosition.current = false;
    manual.current = false;
    const node = anchor && blockAtSourcePosition(pane, anchor);
    if (node && anchor) {
      restoreReadingLine(pane, node, anchor.fraction);
    } else pane.scrollTop = scrollByLanguage.current[showingTranslation ? "translation" : "original"];
  }, [showingTranslation]);

  const messages = useMemo(() => view.conversation.filter(m => !m.sourceDeleted && (!m.sourceId || m.sourceId === sourceId)), [view.conversation, sourceId]);
  const turns = useMemo(() => groupIntoTurns(messages), [messages]);
  const answers = useMemo(() => messages.filter(m => m.role === "assistant"), [messages]);
  const latest = answers.at(-1);
  const selected = useMemo(() => messages.find(m => m.messageId === activeMessage) ?? latest, [messages, activeMessage, latest]);
  const selectedIdRef = useRef(selected?.messageId);
  selectedIdRef.current = selected?.messageId;

  const validated = useMemo(() => !resettingDiscussion && document ? answers.flatMap(message => messageEvidence(message, document, view.discussionId)) : [],
    [answers, document, view.discussionId, resettingDiscussion]);
  const evidenceKey = JSON.stringify(validated);
  const evidence = useMemo(() => validated, [evidenceKey]);
  // Keep the parsed document stable when the active citation changes.
  const sourceInput = useMemo(() => document ? { document, evidence } : undefined, [document, evidence]);
  const projections = useMemo(() => document ? projectEvidence(document, evidence) : [], [document, evidence]);
  const paperLocations = useMemo(() => document?.translation ? projections.map(projection => locatePaperEvidence(document, projection)) : [],
    [document, projections]);

  const annotationKey = JSON.stringify([view.sourceHighlights, view.sourceNotes]);
  const permanentMarks = useMemo(() => {
    if (!document) return [];
    const annotations = [
      ...(view.sourceHighlights ?? []).filter(h => !h.deleted && !h.sourceUpdated && h.layer === "source").map(h => ({ id: h.highlightId, quote: h.quote, lines: h.sourceLines, bundle: h.bundle, highlight: true })),
      ...(view.sourceNotes ?? []).filter(n => !n.deleted && !n.sourceUpdated && n.sentence?.layer === "source" && (n.anchor ?? n.placement)).map(n => ({ id: n.noteId, quote: n.sentence!.quote, lines: (n.anchor ?? n.placement)!.sourceLines, bundle: n.bundle, highlight: false })),
    ];
    const legacy = annotations.flatMap(a => {
      const projected = projectEvidence(document, [{ evidenceId: a.id, sourceId, bundleVersion: a.bundle, messageId: "", discussionId: "", answerRevision: "", displayNumber: 0, sourceLines: a.lines, quote: a.quote, relation: "context" }])[0];
      return projected.kind === "exact" ? [{ key: a.id, start: projected.start, end: projected.end, ...(a.highlight ? { highlightId: a.id } : { noteId: a.id }), ariaLabel: a.highlight ? "重点" : "备注" } satisfies RenderMark] : [];
    });
    return [...legacy, ...documentNoteMarks(document, view.sourceNotes ?? [])];
  }, [document, annotationKey, sourceId]);

  const active = projections.find(projection => projection.evidence.evidenceId === activeEvidence);
  const rememberedAnswer = !resettingDiscussion && lastAnswerCitation?.discussionId === view.discussionId ? lastAnswerCitation : null;
  const markerSelection = useMemo(() => ({
    messageId: selected?.messageId,
    evidenceId: rememberedAnswer?.messageId === selected?.messageId ? rememberedAnswer?.evidenceId : undefined,
  }), [selected?.messageId, rememberedAnswer]);
  const run = view.agent?.run?.sourceId === sourceId ? view.agent.run : null;
  const agent = run ? view.agent : undefined;
  const running = !!run && ["running", "approval", "stopping"].includes(run.status);

  // Highlight on the existing source DOM without reprocessing the entire document.
  useLayoutEffect(() => {
    const pane = original.current;
    if (!pane) return;
    pane.querySelectorAll("[data-evidence-ids].is-active, [data-evidence-block].is-active").forEach(el => el.classList.remove("is-active"));
    if (activeEvidence) {
      pane.querySelectorAll(`[data-evidence-ids~="${activeEvidence}"], [data-evidence="${activeEvidence}"], [data-evidence-block~="${activeEvidence}"]`)
        .forEach(el => el.classList.add("is-active"));
    }
  }, [activeEvidence, evidenceKey, document, showingTranslation, annotationKey]);

  // Keep latest turn focused when new turns arrive.
  useEffect(() => {
    if (turns.length > 0) setFocusedTurn(turns.length - 1);
    else setFocusedTurn(-1);
  }, [turns.length]);

  const stopNavigation = useCallback(() => {
    setAnswerTarget(null);
    cancel();
    pendingAnswerCitation.current = null;
    setAnswerReturn(null);
    if (turn.current) turn.current.cancelled = true;
  }, [cancel]);

  useLayoutEffect(() => {
    if (!resettingDiscussion) return;
    stopNavigation();
    setActiveEvidence(undefined);
    setLastAnswerCitation(null);
  }, [resettingDiscussion, stopNavigation]);

  useEffect(() => {
    setSelection(null);
    if (!visible) return;
    const selectText = () => {
      const picked = window.getSelection();
      const pane = original.current;
      if (!pane || !picked?.anchorNode || !picked.focusNode ||
          !pane.contains(picked.anchorNode) || !pane.contains(picked.focusNode)) return;
      const text = picked.toString().trim();
      if (!text || !picked.rangeCount) return;
      stopNavigation();
      setSelection({ text: text.slice(0, 4000), range: picked.getRangeAt(0).cloneRange() });
    };
    globalThis.document.addEventListener("selectionchange", selectText);
    return () => globalThis.document.removeEventListener("selectionchange", selectText);
  }, [document, showingTranslation, stopNavigation, visible]);

  const manualBrowse = useCallback(() => {
    stopNavigation();
    restorePaperPosition.current = false;
    restored.current = true;
    manual.current = true;
  }, [stopNavigation]);

  const target = (id: string) => original.current?.querySelector<HTMLElement>(
    `[data-evidence-ids~="${id}"], [data-evidence-block~="${id}"]`) ?? undefined;

  // Keep the previous return until the new jump reaches its source location.
  const rememberAnswerReturn = useCallback((navigationIntent: EvidenceNavigationIntent) => {
    const pending = pendingAnswerCitation.current;
    if (pending?.nonce !== navigationIntent.nonce) return;
    const { messageId, evidenceId, origin, discussionId } = pending;
    setLastAnswerCitation({ messageId, evidenceId, origin, discussionId });
  }, []);

  const moveTo = useCallback((projection: Exclude<EvidenceProjection, { kind: "unavailable" }>,
    { keyboard = false, navigationIntent }: { keyboard?: boolean; navigationIntent?: EvidenceNavigationIntent } = {}) => {
    const pane = original.current;
    const id = projection.evidence.evidenceId;
    if (!pane || !isCurrentSource()) return;
    const destinations = pane.querySelectorAll<HTMLElement>(`[data-evidence-ids~="${id}"], [data-evidence-block~="${id}"]`);
    if (!destinations.length || !pane.clientHeight) return;
    if (navigationIntent && !consume(navigationIntent)) return;
    if (navigationIntent) rememberAnswerReturn(navigationIntent);

    manual.current = false;
    const viewport = pane.getBoundingClientRect();
    const bounds = [...destinations].map(node => node.getBoundingClientRect());
    const top = Math.min(...bounds.map(rect => rect.top));
    const bottom = Math.max(...bounds.map(rect => rect.bottom));
    if (top < viewport.top || bottom > viewport.bottom) {
      const height = bottom - top;
      const inset = Math.min(pane.clientHeight * .32, Math.max(0, (pane.clientHeight - height) / 2));
      pane.scrollTo({ top: Math.max(0, pane.scrollTop + top - viewport.top - inset), behavior: "instant" });
    }
    if (document?.pdf) {
      const page = sourcePdfPage(document.pdf, projection.sourceLines, projection.quoteOffsets);
      locatedPage.current = { top: pane.scrollTop, page };
      setCurrentPage(page);
    }
    setActiveEvidence(id);
    if (keyboard) {
      const destination = destinations[0];
      destination.tabIndex = -1;
      destination.focus({ preventScroll: true });
    }
  }, [consume, document?.pdf, isCurrentSource, rememberAnswerReturn]);

  useLayoutEffect(() => {
    if (visible) return;
    manual.current = false;
    if (!readingSession) stopNavigation();
    turn.current = null;
    pendingAnswerCitation.current = null;
    setAnswerReturn(null);
    setAnswerTarget(null);
    setActiveEvidence(undefined);
  }, [visible, selectionGeneration, stopNavigation]);

  useLayoutEffect(() => {
    if (!visible || !intent || intent.sourceId !== sourceId || !isCurrentSource() || !isLatest(intent)) return;
    if (intent.discussionId !== view.discussionId || intent.selectionGeneration !== selectionGeneration) {
      consume(intent);
      return;
    }
    if (intent.destination === "answer") {
      if (intent.bundleVersion !== view.sourceBundleVersion || intent.sourceGeneration !== (view.sourceGeneration ?? view.resetVersion)) {
        consume(intent);
        return;
      }
      if (!document) return;
      const message = messages.find(item => item.messageId === intent.messageId);
      const cited = message && messageEvidence(message, document, view.discussionId).some(item => item.evidenceId === intent.evidenceId);
      if (!cited) { consume(intent); return; }
      if (mobile !== "chat") { setMobile("chat"); return; }
      const citation = answerDestination(chat.current, intent.messageId, intent.evidenceId);
      if (!consume(intent) || !citation) return;
      followChat.current = false;
      if (turn.current) turn.current.cancelled = true;
      setActiveEvidence(undefined);
      citation.scrollIntoView({ block: "nearest", behavior: "instant" });
      citation.focus({ preventScroll: true });
      safeWrite(`focus.activeAnswer:${draftKey}`, intent.messageId);
      setActiveMessage(intent.messageId);
      setAnswerTarget({ messageId: intent.messageId, evidenceId: intent.evidenceId, discussionId: intent.discussionId });
      return;
    }
    if (!document) return;
    const message = messages.find(item => item.messageId === intent.messageId);
    const cited = message && messageEvidence(message, document, view.discussionId).find(item => item.evidenceId === intent.evidenceId);
    const verified = cited && projections.find(item => item.evidence.evidenceId === intent.evidenceId);
    if (!verified || verified.kind === "unavailable" || !target(intent.evidenceId)) {
      consume(intent);
      return;
    }
    if (mobile !== "original") { setMobile("original"); return; }
    if (selected?.messageId !== intent.messageId) { setActiveMessage(intent.messageId); return; }
    restored.current = true;
    restorePaperPosition.current = false;
    moveTo(verified, { keyboard: intent.keyboard, navigationIntent: intent });
  }, [visible, intent, sourceId, selectionGeneration, isCurrentSource, isLatest, consume, document, messages, draftKey,
    view.discussionId, view.sourceBundleVersion, view.sourceGeneration, view.resetVersion,
    selected?.messageId, mobile, showingTranslation, projections, moveTo]);

  const cite = useCallback((message: ReaderMessage, id: string, keyboard: boolean, origin: HTMLButtonElement) => {
    if (!isCurrentSource() || resettingDiscussion) return;
    stopNavigation();
    manual.current = false;
    restored.current = true;
    restorePaperPosition.current = false;
    safeWrite(`focus.activeAnswer:${draftKey}`, message.messageId);
    setActiveMessage(message.messageId);
    const next = start({ sourceId, discussionId: view.discussionId, selectionGeneration, messageId: message.messageId, evidenceId: id,
      keyboard });
    pendingAnswerCitation.current = { nonce: next.nonce, messageId: message.messageId, evidenceId: id, origin, discussionId: view.discussionId };
  }, [stopNavigation, draftKey, isCurrentSource, resettingDiscussion, sourceId, view.discussionId, selectionGeneration, start]);

  const handleSelectMessage = useCallback((messageId: string) => {
    if (selectedIdRef.current !== messageId) {
      stopNavigation();
      safeWrite(`focus.activeAnswer:${draftKey}`, messageId);
      setActiveMessage(messageId);
      setActiveEvidence(undefined);
    }
  }, [stopNavigation, draftKey]);

  useLayoutEffect(() => {
    const pane = original.current;
    if (!document || !pane?.clientHeight || !visible || restored.current || intent) return;
    restored.current = true;
    try {
      const raw = safeRead(bookmark);
      const saved = raw ? JSON.parse(raw) : view.readingStarted && view.navigationCurrent?.bundleVersion === document.bundleVersion ? { line: view.navigationCurrent.sourceLines[0], offset: 0 } : null;
      if (saved && Number.isSafeInteger(saved.line)) {
        const node = blockAtSourcePosition(pane, { lines: [saved.line, saved.line], offset: saved.sourceOffset });
        if (node && Number.isFinite(saved.fraction)) restoreReadingLine(pane, node, saved.fraction);
        else if (node && Number.isFinite(saved.offset)) pane.scrollTop += node.getBoundingClientRect().top - pane.getBoundingClientRect().top + saved.offset;
      }
    } catch { /* Ignore malformed display bookmarks, never mutate the Cursor. */ }
  }, [document, bookmark, intent, visible, mobile]);

  useLayoutEffect(() => {
    const pane = original.current;
    if (!visible || !document?.pdf || !pane) return;
    updateOriginalPage(pane);
    const resize = typeof ResizeObserver === "function" ? new ResizeObserver(() => updateOriginalPage(pane)) : undefined;
    resize?.observe(pane);
    return () => resize?.disconnect();
  }, [document?.pdf, mobile, showingTranslation, updateOriginalPage, visible]);

  useEffect(() => {
    const pending = turn.current;
    if (!visible || intent || !pending || pending.located || pending.cancelled || !latest || pending.seen.has(latest.messageId) || !evidence.length) return;
    const first = projections.find((p): p is Exclude<EvidenceProjection, { kind: "unavailable" }> => p.evidence.messageId === latest.messageId && p.kind !== "unavailable");
    if (first && selected?.messageId === latest.messageId) { pending.located = true; if ((shell.current?.clientWidth ?? 0) >= 960) moveTo(first); }
  }, [visible, intent, latest, evidence, projections, selected, moveTo]);

  useLayoutEffect(() => {
    if (!chat.current) return;
    if (followChat.current) chat.current.scrollTop = chat.current.scrollHeight;
    chatScrollTop.current = chat.current.scrollTop;
  }, [messages.at(-1)?.content]);
  useLayoutEffect(() => { chatScrollTop.current = chat.current?.scrollTop ?? 0; }, [fullscreen, mobile]);

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

  function beginSelectedNote(opener: HTMLElement) {
    if (!selection || savingNote) return;
    let locator: SourceTextSelectionInput | undefined;
    if (!showingTranslation && document?.readingPlan) {
      locator = sourceBody.current ? captureSourceText(sourceBody.current, selection.range, document) : undefined;
      if (!locator) {
        showOperationError("note-save", "选文位置已失效，请重新选择。");
        return;
      }
    }
    showOperationError("note-save", "");
    setNoteEdit(null);
    setNoteSelection(locator);
    setNoteDraft(`「${selection.text}」\n`);
    openNotes(opener);
    setSelection(null);
    noteInput.current?.focus({ preventScroll: true });
  }

  async function saveCurrentNote() {
    const content = noteDraft.trim();
    if (!content || !host.createSourceNote || noteRequest.current?.busy) return;
    const key = JSON.stringify([noteEdit, noteSelection, content]);
    const request = noteRequest.current?.key === key ? noteRequest.current : { key, id: createReaderId(), busy: false };
    noteRequest.current = request;
    request.busy = true;
    setSavingNote(true);
    const write = Promise.resolve().then(() => noteEdit && host.changeSourceNote
      ? host.changeSourceNote(sourceId, noteEdit.id, "edit", noteEdit.revision, request.id, content)
      : host.createSourceNote!({ sourceId, requestId: request.id, content, kind: "thought", origin: "user", ...(noteSelection ? { selection: noteSelection } : {}) }));
    const ok = await apply("note-save", write, result => {
      if (noteRequest.current !== request) return;
      if (result.noteOperation?.status === "conflict") {
        showOperationError("note-save", "笔记已更新，请核对当前内容后再保存。");
        if (result.noteOperation.current) setNoteEdit({ id: result.noteOperation.current.noteId, revision: result.noteOperation.current.revision });
        return;
      }
      setNoteDraft("");
      setNoteEdit(null);
      setNoteSelection(undefined);
    });
    if (noteRequest.current === request) {
      setSavingNote(false);
      request.busy = false;
      if (ok) noteRequest.current = null;
    }
  }

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
    if (item) goToAnswer(item.messageId, evidenceId);
  }

  function goToAnswer(messageId: string, evidenceId?: string) {
    if (!isCurrentSource() || !evidence.some(item => item.messageId === messageId)) return;
    const openedFrom = [rememberedAnswer, pendingAnswerCitation.current].find(item =>
      item && item.discussionId === view.discussionId && item.messageId === messageId && item.evidenceId === evidenceId);
    stopNavigation();
    manual.current = false;
    followChat.current = false;
    safeWrite(`focus.activeAnswer:${draftKey}`, messageId);
    setActiveMessage(messageId);
    setActiveEvidence(evidenceId);
    setMobile("chat");
    setAnswerReturn({ messageId, evidenceId, origin: openedFrom?.origin, discussionId: view.discussionId });
  }

  useLayoutEffect(() => {
    if (!answerReturn) return;
    setAnswerReturn(null);
    if (!visible || mobile !== "chat" || !isCurrentSource() || answerReturn.discussionId !== view.discussionId) return;
    const { messageId, evidenceId, origin } = answerReturn;
    const destination = answerDestination(chat.current, messageId, evidenceId, origin);
    destination?.scrollIntoView({ block: evidenceId ? "nearest" : "start", behavior: "instant" });
    destination?.focus({ preventScroll: true });
  }, [answerReturn, isCurrentSource, mobile, view.discussionId, visible]);

  // Update focused turn smoothly on chat scroll (Mist Focus Lens for conversation).
  const updateChatFocus = useCallback(() => {
    const el = chat.current;
    if (!el) return;
    const previousTop = chatScrollTop.current;
    chatScrollTop.current = el.scrollTop;
    // Native scrollbar drags do not always dispatch pointer events to the scroller.
    const limit = Math.max(0, el.scrollHeight - el.clientHeight);
    if (intent && isLatest(intent) && previousTop !== el.scrollTop &&
        !(previousTop > limit && Math.abs(el.scrollTop - limit) <= 1)) stopNavigation();
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
  }, [intent, isLatest, stopNavigation, turns.length]);

  const translationInterrupted = ["failed", "cancelled", "interrupted"].includes(translationState ?? "");
  const showLanguageControls = !chineseSource && (translationReady || !!translation && !modernDocument);
  const activeFocusIndex = focusedTurn >= 0 && focusedTurn < turns.length ? focusedTurn : turns.length - 1;

  return <section ref={shell} className="conversation-reader" data-fullscreen={!!fullscreen} data-mobile={mobile} data-font-size={fontSize} hidden={!visible} style={{ "--source-share": `${share}%`, "--source-font-size": `${readingFontSizes[fontSize as keyof typeof readingFontSizes] ?? 18}px` } as CSSProperties}>
    {documentError && <div role="alert" className="source-reader-error">{documentError}<button onClick={() => setReloadDocument(v => v + 1)}>重试</button><button onClick={() => setDocumentError("")}>关闭</button></div>}
    {Object.entries(operationErrors).map(([key, message]) => <div key={key} role="alert" className="source-reader-error">{message}<button onClick={() => showOperationError(key, "")}>关闭</button></div>)}
    {!running && run?.error && dismissedRun !== run.runId && <div role="alert" className="source-reader-error">{run.error}<button onClick={() => setDismissedRun(run.runId)}>关闭</button></div>}
    <div className="source-reader-columns">
      <div className="source-original-pane">
        <button type="button" className="source-mobile-toggle source-mobile-return" onClick={() => { stopNavigation(); setMobile("chat"); }}>返回对话</button>
        {(showLanguageControls || originalHref) && <div className="source-original-toolbar">
          {showLanguageControls && <div className="paper-view-controls" role="group" aria-label="正文语言">
            <button aria-pressed={showingTranslation} disabled={!translationReady} onClick={() => switchPaper(true)}>{modernDocument ? "中文" : `中文译文${translationReady ? "" : translationState === "running" ? " · 准备中" : translationInterrupted ? " · 未完成" : " · 未就绪"}`}</button>
            <button aria-pressed={!showingTranslation} onClick={() => switchPaper(false)}>原文</button>
            {translationInterrupted && host.resumePreparation && <button onClick={() => void apply("translation", host.resumePreparation!(sourceId, createReaderId()))}>重试译文</button>}</div>}
          {originalHref && <a className="source-original-link" href={originalHref} target="_blank" rel="noreferrer">打开原件 ↗</a>}
        </div>}
        <div ref={original} className="source-original"
          aria-label="文章原文" tabIndex={0} onWheel={e => { if (!e.ctrlKey) manualBrowse(); }} onTouchStart={manualBrowse}
          onPointerDown={e => { if (e.target === e.currentTarget) manualBrowse(); }}
          onKeyDown={e => {
            if ((e.key === "Enter" || e.key === " ") && (e.target as HTMLElement).matches("[data-shared-note-ids][role=button]")) {
              e.preventDefault(); openNotes(e.target as HTMLElement);
            } else if (isScrollKey(e)) manualBrowse();
          }}
          onScroll={event => {
            const pane = event.currentTarget;
            updateOriginalPage(pane);
            if (!manual.current || !bookmark) return;
            const block = blockAtReadingLine(pane);
            if (block) {
              const { lines, offset } = sourcePositionAt(block);
              safeWrite(bookmark, JSON.stringify({ line: lines[0], sourceOffset: offset, fraction: fractionAtReadingLine(pane, block) }));
            }
          }}
          onClick={e => {
            const node = e.target as HTMLElement;
            const id = node.closest<HTMLElement>("[data-evidence]")?.dataset.evidence;
            if (id) backToAnswer(id);
            else {
              const mark = node.closest<HTMLElement>("[data-anno-key], [data-anno-bulb]");
              if (mark) openNotes(mark);
            }
          }}>
          <ActiveSourceCitation.Provider value={markerSelection}>
            {document ? showingTranslation ? <TranslatedPaper document={document} evidence={paperLocations} /> :
              <article><MarkdownContent text={document.markdown} sourceId={sourceId} marks={permanentMarks} sourceEvidence={sourceInput} bodyRef={sourceBody} /></article> :
              <span role="status" className="source-loading">加载中…</span>}
          </ActiveSourceCitation.Provider>
        </div>
        {selection && <div className="source-selection-actions">
          <button onClick={() => { composer.current?.insertQuote(selection.text); setSelection(null); setMobile("chat"); }}>引用</button>
          {host.createSourceNote && (showingTranslation || document?.readingPlan !== null) && <button disabled={savingNote} onClick={e => beginSelectedNote(e.currentTarget)}>记笔记</button>}
          <button aria-label="取消选择" onClick={() => { window.getSelection()?.removeAllRanges(); setSelection(null); }}>×</button>
        </div>}
      </div>
      <div className="source-splitter" role="separator" aria-label="调整原文宽度" aria-orientation="vertical" aria-valuemin={40} aria-valuemax={70} aria-valuenow={share} tabIndex={0}
        onKeyDown={e => { if (["ArrowLeft", "ArrowRight"].includes(e.key)) { e.preventDefault(); const v = Math.max(40, Math.min(70, share + (e.key === "ArrowLeft" ? -2 : 2))); setShare(v); safeWrite("focus.sourceShare", String(v)); } }}
        onPointerDown={e => { e.currentTarget.setPointerCapture(e.pointerId); }} onPointerMove={e => { if (!e.currentTarget.hasPointerCapture(e.pointerId) || !shell.current) return; const rect = shell.current.getBoundingClientRect(); const v = Math.max(40, Math.min(70, (e.clientX - rect.left) / rect.width * 100)); setShare(v); safeWrite("focus.sourceShare", String(v)); }} onPointerUp={e => e.currentTarget.releasePointerCapture(e.pointerId)} />
      <div className="source-chat-pane">
        <div ref={chat} className="source-chat" aria-label="文章对话" data-evidence-pending={intent ? "true" : undefined} onWheel={e => { if (!e.ctrlKey) stopNavigation(); }}
          onTouchStart={stopNavigation} onKeyDown={e => { if (isScrollKey(e)) stopNavigation(); }} onScroll={updateChatFocus}>
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
                const refs = !resettingDiscussion && document ? messageEvidence(message, document, view.discussionId) : [];
                const text = message.role === "assistant" ? citedMarkdown(message, refs, resettingDiscussion) : message.content;
                return <ConversationMessage
                  key={message.messageId}
                  message={message}
                  markdown={text}
                  isSelected={selected?.messageId === message.messageId}
                  activeCitation={answerTarget?.messageId === message.messageId ? answerTarget.evidenceId : undefined}
                  onSelect={handleSelectMessage}
                  onCite={cite}
                />;
              })}
            </div>;
          })}
        </div>
        <div className="source-composer-dock">
          <div className="source-composer-actions" role="toolbar" aria-label="对话操作">
            <button type="button" className="source-mobile-toggle" onClick={() => { stopNavigation(); setMobile("original"); }}>查看正文</button>
            <div className="source-composer-icons">
              {(view.discussions?.length ?? 0) > 1 && host.selectDiscussionSource && (
                <select className="source-discussion-select" aria-label="对话记录" value={view.discussionId ?? ""} disabled={running} onChange={e => { stopNavigation(); void apply("discussion", host.selectDiscussionSource!(sourceId, e.target.value)); }}>
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
      <textarea ref={noteInput} aria-label="笔记内容" placeholder="记录想法或结论…" value={noteDraft} readOnly={savingNote} onChange={e => setNoteDraft(e.target.value)} />
      {host.createSourceNote && <button className="source-notes-save" disabled={savingNote || !noteDraft.trim()} onClick={() => void saveCurrentNote()}>保存笔记</button>}
      {(view.sourceNotes ?? []).filter(n => !n.deleted || n.canUndo).map(n => <article key={n.noteId}>{n.sentence && <blockquote>{n.sentence.quote.exact}</blockquote>}<MarkdownContent text={n.content} />{host.changeSourceNote && <div className="source-note-actions">{!n.deleted && <button disabled={savingNote} onClick={() => { setNoteSelection(undefined); setNoteEdit({ id: n.noteId, revision: n.revision }); setNoteDraft(n.content); }}>编辑</button>}<button onClick={() => void apply(`note:${n.noteId}`, host.changeSourceNote!(sourceId, n.noteId, n.deleted ? "undo" : "delete", n.revision, createReaderId()))}>{n.deleted ? "撤销删除" : "删除"}</button></div>}</article>)}
      {(view.sourceHighlights ?? []).filter(h => !h.deleted || h.canUndo).map(h => <article key={h.highlightId}><blockquote>{h.quote.exact}</blockquote>{host.changeHighlight && <div className="source-note-actions"><button onClick={() => void apply(`highlight:${h.highlightId}`, host.changeHighlight!(sourceId, h.highlightId, h.deleted ? "undo" : "delete", h.revision, createReaderId()))}>{h.deleted ? "撤销删除重点" : "取消重点"}</button></div>}</article>)}
    </aside>}
  </section>;
}
