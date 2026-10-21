import { AssetInstanceContext } from "./asset-context";
import { PanelLeft, Pin, Plus, Expand, Collapse, ArrowRight, ArrowUp, StopSquare, ChevronDown, Widen, Close } from "./ReaderIcons";
import { createReaderId, cursorReceipt, type ReaderChunk, type ReaderAttachment, type ReaderHost, type ReadingWindow,
  type ReaderHostResult, type SendReaderMessageInput, type ContinueReadingInput, type SourceNote, type ReadingProgressEntry } from "@focus/reader-contracts";
import { type CSSProperties, type ReactNode, useEffect, useLayoutEffect, useRef, useState } from "react";
import { AgentControls } from "./AgentControls";
import { ReadingChunk, ReaderConversation, chunkKey } from "./ReadingChunk";
import { readingFontSizes, readingMeasures, readingLayout, readReadingMeasure, effectiveReadingMeasure, measureWidth, drawerTranslation, type ReadingMeasure } from "./typography";
import "./reader-shell.css";
import "./mist-reader.css";
import "./reader-figures.css";
import { FigurePanel, FigureViewer, type ViewerRequest } from "./FigurePanel";
import { useReadingScroll } from "./reading-scroll";
import { useReadingLens } from "./reading-lens";
import { ArticleOverviewPanel } from "./ArticleOverviewPanel";
import { ArticleStructure } from "./ArticleStructure";
import "./article-structure.css";
import { chunkFigures, figureChunk, extractFigures, figureNumber, imageIdentity, mergeFigures, type Figure } from "./figures";

type DraftReference = ReaderChunk & { excerpt?: string };
type Upload = { id: string; file: File; state: "uploading" | "ready" | "failed"; attachment?: ReaderAttachment; error?: string };
type Failure = { message: string; label: string; retry: () => void };
export interface FocusReaderProps { host: ReaderHost; appearance?: "mist" | "conversation"; fontSize?: "small" | "standard" | "large" | "extra"; visible?: boolean; fullscreen?: boolean; onFullscreenChange?: (next: boolean) => void }

// Capture entry eligibility only on mount, never on streaming updates.
function TimelineEvent({ identity, fresh, current, streaming, children }: { identity: string; fresh: boolean; current: boolean; streaming?: boolean; children: ReactNode }) {
  const [enter] = useState(fresh);
  const [entered, setEntered] = useState(false);
  return <div data-streaming={streaming ? "true" : undefined} data-event-id={identity} className="focus-output" data-current-output={current} data-fresh={enter} data-entered={entered} onAnimationEnd={() => setEntered(true)}>{children}</div>;
}

/** Presentation projection; input order defines the current session. */
export function groupReadingDiscussion<C extends { chunkId: string }>(
  entries: readonly ({ kind: "reading"; chunk: C } | { kind: "message"; messageId: string })[],
  keys: readonly string[], messages: readonly { messageId: string; reference?: { chunkId: string | null } | null }[], attached: boolean,
) {
  const groups: { id: string; chunk: C | null; indexes: number[] }[] = [];
  const latest = new Map<string, typeof groups[number]>();
  const references = new Map(messages.map(m => [m.messageId, m.reference?.chunkId]));
  entries.forEach((entry, index) => {
    if (entry.kind === "reading") {
      const group = { id: keys[index], chunk: entry.chunk, indexes: [index] };
      groups.push(group); latest.set(entry.chunk.chunkId, group);
    } else {
      if (!groups.length) groups.push({ id: "leading-discussion", chunk: null, indexes: [] });
      const owner = attached ? latest.get(references.get(entry.messageId) ?? "") : undefined;
      (owner ?? groups[groups.length - 1]).indexes.push(index);
    }
  });
  return groups;
}

export function FocusReader({ host, appearance = "conversation", fontSize = "standard", visible = true, fullscreen = false, onFullscreenChange }: FocusReaderProps) {
  const mist = appearance === "mist";
  const [attachDiscussion, setAttachDiscussion] = useState(() => {
    try { return localStorage.getItem("focus.attachDiscussion") === "true"; } catch { return false; }
  });
  const [preferredMeasure, setPreferredMeasure] = useState<ReadingMeasure>(() => {
    try { return readReadingMeasure(localStorage, readingFontSizes[fontSize]); } catch { return "standard"; }
  });
  const [widthOpen, setWidthOpen] = useState(false);
  const widthControl = useRef<HTMLDivElement>(null);
  const widthPanel = useRef<HTMLDivElement>(null);
  useLayoutEffect(() => {
    if (!widthOpen || !widthPanel.current || !widthControl.current) return;
    const panel = widthPanel.current;
    const position = () => {
      const box = widthControl.current!.getBoundingClientRect();
      panel.style.setProperty("--measure-bottom", `${window.innerHeight - box.top}px`);
      panel.style.setProperty("--measure-right", `${window.innerWidth - box.right}px`);
    };
    position();
    if (panel.showPopover) panel.showPopover(); else panel.removeAttribute("popover");
    window.addEventListener("resize", position); window.addEventListener("scroll", position, true);
    return () => { window.removeEventListener("resize", position); window.removeEventListener("scroll", position, true); };
  }, [widthOpen]);
  useEffect(() => {
    if (!widthOpen) return;
    const close = (event: PointerEvent) => { if (!widthControl.current?.contains(event.target as Node)) setWidthOpen(false); };
    document.addEventListener("pointerdown", close);
    return () => document.removeEventListener("pointerdown", close);
  }, [widthOpen]);
  const [readerShift, setReaderShift] = useState(0);
  const [availableWidth, setAvailableWidth] = useState(0);
  const [readingWidth, setReadingWidth] = useState(0);
  const measure = effectiveReadingMeasure(preferredMeasure, readingFontSizes[fontSize], availableWidth);
  const columnWidth = measureWidth(measure, readingFontSizes[fontSize]);
  const measureFits = (id: ReadingMeasure) => !availableWidth || measureWidth(id, readingFontSizes[fontSize]) + readingLayout.padding <= availableWidth;
  function selectMeasure(id: ReadingMeasure) {
    if (!measureFits(id) || preferredMeasure === id) return;
    preserveReading(() => setPreferredMeasure(id));
    try { localStorage.setItem("focus.readingMeasure", id); } catch { /* In-memory preference. */ }
  }
  const [collapsed, setCollapsed] = useState(false);
  const [structureOpen, setStructureOpen] = useState(false);
  const [reviewNoticeDismissed, setReviewNoticeDismissed] = useState(false);
  const [progressNoticeDismissed, setProgressNoticeDismissed] = useState<string | null>(null);
  const [viewportChunk, setViewportChunk] = useState<ReaderChunk | null>(null);
  const [view, setView] = useState<ReadingWindow | null>(null);
  const paintedTimingRuns = useRef(new Set<string>());
  const [draft, setDraft] = useState("");
  const [uploads, setUploads] = useState<Upload[]>([]);
  const [selection, setSelection] = useState<{ chunk: ReaderChunk; text: string; x: number; y: number } | null>(null);
  const highlightTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [reference, setReference] = useState<DraftReference | null | undefined>(undefined);
  const [sideMode, setSideMode] = useState<"figures" | "notes" | "progress" | "discussion" | null>(null);
  const materialsOpen = sideMode === "notes" || sideMode === "progress" || sideMode === "discussion";
  const lastSideMode = useRef(sideMode);
  useLayoutEffect(() => { if (sideMode) lastSideMode.current = sideMode; }, [sideMode]);
  const renderedSideMode = sideMode ?? lastSideMode.current;
  const materialTab = sideMode === "figures" ? null : sideMode;
  const [viewer, setViewer] = useState<ViewerRequest | null>(null);
  const [selectedFigure, setSelectedFigure] = useState<string | null>(null);
  const [figureSelectionVersion, setFigureSelectionVersion] = useState(0);
  const [figureLanguages, setFigureLanguages] = useState<Record<string, boolean>>({});
  const [textShare, setTextShare] = useState(() => {
    try { return Math.max(35, Math.min(75, Number(localStorage.getItem("focus.readerTextShare")) || 60)); } catch { return 60; }
  });
  const layout = useRef<HTMLDivElement>(null);
  const drafts = useRef<Record<string, { text: string; reference: DraftReference | null | undefined; noteId: string | null; note: string; noteRevision: number | null; progressId: string | null; progress: string; progressRevision: number | null }>>({});
  const mutationIds = useRef(new Map<string, string>());
  function mutationId(key: string) { if (!mutationIds.current.has(key)) mutationIds.current.set(key, createReaderId()); return mutationIds.current.get(key)!; }
  const draftOwner = useRef("");
  const [recoverDraft, setRecoverDraft] = useState(false);
  const [reviewChunk, setReviewChunk] = useState<ReaderChunk | null>(null);
  const [discussionFocus, setDiscussionFocus] = useState<string | null>(null);
  const [operation, setOperation] = useState("");
  const [failure, setFailure] = useState<Failure | null>(null);
  const [connection, setConnection] = useState("");
  const [panel, setPanel] = useState<"materials" | "contents" | "settings" | null>(null);
  const lastPanel = useRef(panel);
  useLayoutEffect(() => { if (panel) lastPanel.current = panel; }, [panel]);
  const renderedPanel = panel ?? lastPanel.current;
  const [largeText, setLargeText] = useState(false);
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
    setDraft(""); setUploads([]); setSelection(null); setViewer(null); setReference(undefined); setReviewChunk(null); setFailure(null); setPanel(null);
    setDiscussionFocus(null);
    setEditingNoteId(null); setEditDraft(""); setEditBaseRevision(null); setNoteError(""); setNoteConflict(null);
    setEditingProgressId(null); setProgressDraft(""); setProgressBaseRevision(null); setProgressConflict(null); setProgressError(""); follow.current = true;
  }
  const draftState = useRef({ reference, editingNoteId, editDraft, editBaseRevision, editingProgressId, progressDraft, progressBaseRevision });
  draftState.current = { reference, editingNoteId, editDraft, editBaseRevision, editingProgressId, progressDraft, progressBaseRevision };
  function accept(value: ReadingWindow) {
    if (!alive.current || (value.revision !== undefined && value.revision < revision.current)) return;
    const owner = `${value.source.sourceId}:${value.discussionId ?? value.sessionId}`;
    if (draftOwner.current && owner !== draftOwner.current) {
      drafts.current[draftOwner.current] = { text: draftRef.current, reference: draftState.current.reference, noteId: draftState.current.editingNoteId,
        note: draftState.current.editDraft, noteRevision: draftState.current.editBaseRevision, progressId: draftState.current.editingProgressId,
        progress: draftState.current.progressDraft, progressRevision: draftState.current.progressBaseRevision };
      try { sessionStorage.setItem("focus.drafts", JSON.stringify(drafts.current)); } catch { /* In-memory recovery remains available. */ }
      clearSessionUI();
      const prior = drafts.current[owner];
      if (prior) { setDraft(prior.text); setReference(prior.reference); setEditingNoteId(prior.noteId); setEditDraft(prior.note); setEditBaseRevision(prior.noteRevision); setEditingProgressId(prior.progressId); setProgressDraft(prior.progress); setProgressBaseRevision(prior.progressRevision); }
      setRecoverDraft(Object.values(drafts.current).some(d => !!d.text || !!d.note || !!d.progress));
    }
    draftOwner.current = owner;
    session.current = value.sessionId;
    displayedSource.current = value.source.sourceId;
    revision.current = value.revision ?? revision.current;
    if (value.reviewChunk) setReviewChunk(value.reviewChunk.chunkId === value.navigationCurrent?.chunkId ? null : value.reviewChunk);
    else if (value.readingOperation?.operation === "continue" || value.readingOperation?.operation === "open") setReviewChunk(null);
    setView(value);
    setConnection("");
  }
  // Browser-only first-response paint evidence. Client/server clocks may differ.
  useEffect(() => {
    const run = view?.agent?.run;
    const first = run?.phaseTiming?.firstOutput;
    if (!run || first === undefined || paintedTimingRuns.current.has(run.runId)) return;
    const frame = requestAnimationFrame(() => {
      paintedTimingRuns.current.add(run.runId);
      window.dispatchEvent(new CustomEvent('focus-discussion-timing', { detail: {
        runId: run.runId, serverFirstOutputAt: first,
        clientFirstPaintAt: Date.now(), clockSkewNotCalibrated: true,
      } }));
    });
    return () => cancelAnimationFrame(frame);
  }, [view?.agent?.run?.runId, view?.agent?.run?.phaseTiming?.firstOutput]);

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
    try { drafts.current = JSON.parse(sessionStorage.getItem("focus.drafts") ?? "{}"); } catch { /* malformed draft storage is ignored */ }
    setRecoverDraft(Object.values(drafts.current).some(d => !!d.text || !!d.note || !!d.progress));
  }, []);
  useEffect(() => {
    if (!draftOwner.current) return;
    drafts.current[draftOwner.current] = { text: draft, reference, noteId: editingNoteId, note: editDraft,
      noteRevision: editBaseRevision, progressId: editingProgressId, progress: progressDraft, progressRevision: progressBaseRevision };
    try { sessionStorage.setItem("focus.drafts", JSON.stringify(drafts.current)); } catch { /* memory fallback */ }
  }, [draft, reference, editingNoteId, editDraft, editingProgressId, progressDraft]);
  useEffect(() => {
    if (panel) dialog.current?.showModal(); else dialog.current?.close();
  }, [panel]);

  const resetVersions = useRef<Record<string, number>>((() => {
    try { return JSON.parse(sessionStorage.getItem("focus.draftResetVersions") ?? "{}"); } catch { return {}; }
  })());
  useEffect(() => {
    if (!view?.source.sourceId || view.resetVersion === undefined) return;
    const source = view.source.sourceId;
    const previous = resetVersions.current[source];
    resetVersions.current[source] = view.resetVersion;
    try { sessionStorage.setItem("focus.draftResetVersions", JSON.stringify(resetVersions.current)); } catch { /* memory fallback */ }
    if (previous !== undefined && previous !== view.resetVersion) {
      for (const key of Object.keys(drafts.current)) if (key.startsWith(`${source}:`)) delete drafts.current[key];
      clearSessionUI();
      try { sessionStorage.setItem("focus.drafts", JSON.stringify(drafts.current)); } catch { /* memory fallback */ }
    }
  }, [view?.source.sourceId, view?.resetVersion]);
  const current = view?.current ?? null;
  const frontier = view?.navigationCurrent ?? current;
  useEffect(() => { setReviewChunk(null); }, [view?.source.sourceId, view?.readingRevision]);
  const agent = view?.agent;
  const active = !!agent?.run && ["running", "approval", "stopping"].includes(agent.run.status);
  const uploading = uploads.some(u => u.state === "uploading");
  const blocked = active || !!operation;
  const chunks = view ? [...view.history, ...(current ? [current] : view.readingStarted && frontier ? [frontier] : [])] : [];
  const displayed = reviewChunk ?? current;
  const showStructure = !!view?.structure?.length && (!!view.structureIntro || structureOpen);
  const bodyScroll = useRef(0);
  useLayoutEffect(() => {
    if (!stream.current) return;
    if (showStructure) { bodyScroll.current = stream.current.scrollTop; stream.current.scrollTop = 0; }
    else stream.current.scrollTop = bodyScroll.current;
  }, [showStructure]);
  useEffect(() => { setStructureOpen(false); }, [view?.source.sourceId, frontier?.planId, view?.resetVersion]);
  useEffect(() => { setViewportChunk(null); }, [view?.source.sourceId, view?.readingRevision, reviewChunk, view?.sessionId]);
  useEffect(() => { setReviewNoticeDismissed(false); }, [reviewChunk, view?.source.sourceId, view?.sessionId]);
  const sourceId = view?.source.sourceId ?? "";
  const protectedImages = new Set(chunks.flatMap(c => [...extractFigures(c.sourceMarkdown, c.sourceId).protectedIds]));
  const allFigures = mergeFigures(sourceId, (view?.figures ?? []).filter(f => !protectedImages.has(imageIdentity(f.src, sourceId))),
    ...chunks.filter(c => c.sourceId === sourceId).map(c => chunkFigures(c, figureLanguages[chunkKey(c)] ?? false)));
  // Current-language captions override the original catalogue for loaded Chunks.
  const localized = new Map(chunks.filter(c => c.sourceId === sourceId).flatMap(c => chunkFigures(c, figureLanguages[chunkKey(c)] ?? false)).map(f => [f.id, f]));
  const sourceFigures = allFigures.map(f => {
    const local = localized.get(f.id);
    return local && (local.bodyCaption || figureNumber.test(local.caption) || !f.caption) ? { ...f, caption: local.caption, label: local.label } : f;
  }).sort((a, b) => {
    const aNumber = a.label.match(figureNumber)?.[1];
    const bNumber = b.label.match(figureNumber)?.[1];
    if (!aNumber || !bNumber) return aNumber ? -1 : bNumber ? 1 : 0;
    return aNumber.localeCompare(bNumber, undefined, { numeric: true });
  });
  const ordered = view?.timeline ?? [
    ...(view?.status === "completed" && !view.sessionFresh ? view.history.map(chunk => ({ kind: "reading" as const, chunk })) : displayed ? [{ kind: "reading" as const, chunk: displayed }] : []),
    ...(view?.conversation ?? []).map(message => ({ kind: "message" as const, messageId: message.messageId })),
  ];
  const entries = [...ordered, ...(view?.timeline ? (view.conversation ?? []).filter(m => !ordered.some(e => e.kind === "message" && e.messageId === m.messageId)).map(m => ({ kind: "message" as const, messageId: m.messageId })) : [])];
  const eventKeys = entries.map((e, index) => e.kind === "reading" ? ("eventId" in e && typeof e.eventId === "string" ? e.eventId : undefined) ?? `${chunkKey(e.chunk)}:${index}` : e.messageId);
  const eventScope = `${sourceId}:${view?.discussionId ?? view?.sessionId}`;
  const discussionAttached = mist && attachDiscussion && readingWidth >= 1240 && !sideMode && !showStructure;
  const attachTitle = !attachDiscussion ? "将讨论吸附到原文右侧" : sideMode
    ? "吸附已开启；资料打开时暂停，关闭资料后自动恢复" : readingWidth < 1240
    ? "吸附已开启；阅读区不足 1240px，宽度恢复后自动吸附" : "吸附已开启；点击恢复阅读流";
  const paragraphGroups = groupReadingDiscussion(entries, eventKeys, view?.conversation ?? [], discussionAttached);
  const readingGroups = paragraphGroups.filter(group => group.chunk !== null);
  const lens = useReadingLens(eventScope, readingGroups.map(group => group.id), mist && visible && !showStructure);
  const lensIndex = Math.max(0, readingGroups.findIndex(group => group.id === lens.activeId));
  const lensChunk = readingGroups.find(group => group.id === lens.activeId)?.chunk;
  const lensReview = !!(lensChunk && frontier && lensChunk.planId === frontier.planId && lensChunk.index < frontier.index);
  const latestReading = [...(view?.timeline ?? [])].reverse().find(e => e.kind === "reading");
  const locatedChunk = (mist ? lensChunk : null) ?? viewportChunk ?? reviewChunk ?? (latestReading?.kind === "reading" ? latestReading.chunk : displayed ?? frontier);
  const structurePlanId = frontier?.planId ?? view?.history.at(-1)?.planId;
  const structureChunkId = locatedChunk?.planId === structurePlanId ? locatedChunk?.chunkId : undefined;
  const structureNode = view?.structure?.find(n => n.id === view.outline?.find(c => c.chunkId === structureChunkId)?.nodeId);
  const structureParent = view?.structure?.find(n => n.id === structureNode?.parentId);
  const structureTitle = structureNode ? [structureParent?.title, structureNode.title].filter(Boolean).join(" › ") : locatedChunk?.sectionPath.slice(-2).join(" › ");
  const committedEvents = useRef<{ scope: string; ids: Set<string> } | null>(null);
  useLayoutEffect(() => {
    if (view) committedEvents.current = { scope: eventScope, ids: new Set(eventKeys) };
  });
  useEffect(() => { setFigureLanguages({}); setSelectedFigure(null); setSideMode(null); }, [sourceId]);
  useLayoutEffect(() => {
    const root = layout.current, column = lens.document.current;
    if (!root || !column) return;
    const measure = () => {
      const width = column.offsetWidth, area = root.clientWidth;
      const drawer = root.querySelector<HTMLElement>(".reader-left-drawer");
      const gap = parseFloat(getComputedStyle(root).getPropertyValue("--reader-gap-sm")) || 0;
      const shift = sideMode && mist && drawer ? drawerTranslation(area, width, drawer.offsetLeft + drawer.offsetWidth, gap) : 0;
      setReaderShift(shift);
    };
    measure();
    const observer = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(measure);
    observer?.observe(root); observer?.observe(column);
    return () => observer?.disconnect();
  }, [sideMode, mist, columnWidth]);
  function preserveReading(change: () => void) {
    scrolling.controller.current?.hold();
    change();
  }
  function showFigure(figure: Figure) {
    if (figure.sourceId !== sourceId) return;
    preserveReading(() => {
      setSelectedFigure(figure.id); setFigureSelectionVersion(old => old + 1); setSideMode("figures");
    });
  }
  function resizeColumns(share: number) {
    const available = (layout.current?.clientWidth ?? 1100) - (stream.current?.offsetLeft ?? 0) - 8;
    const bounded = Math.max(35, 340 / available * 100, Math.min(75, 100 - 280 / available * 100, share));
    preserveReading(() => setTextShare(bounded));
    try { localStorage.setItem("focus.readerTextShare", String(bounded)); } catch { /* UI still resizes */ }
  }
  const visibleChunks = entries.flatMap(e => e.kind === "reading" ? [e.chunk] : []);
  function locateVisibleChunk() {
    if (mist || showStructure || !stream.current) return;
    const bounds = stream.current.getBoundingClientRect();
    const cards = Array.from(stream.current.querySelectorAll<HTMLElement>("[data-chunk-key]"))
      .map(el => ({ el, box: el.getBoundingClientRect() }))
      .filter(({ box }) => box.height > 0 && box.bottom > bounds.top + 50 && box.top < bounds.bottom)
      .sort((a, b) => Math.abs(a.box.top - bounds.top - 60) - Math.abs(b.box.top - bounds.top - 60));
    const key = cards[0]?.el.dataset.chunkKey;
    const chunk = visibleChunks.find(c => chunkKey(c) === key);
    if (chunk) setViewportChunk(old => old && chunkKey(old) === key ? old : chunk);
  }
  const focusedIndex = view?.timeline ? entries.length - 1 : displayed && !active && discussionFocus !== chunkKey(displayed) ? 0 : entries.length - 1;
  const displayEmpty = entries.length === 0;
  const contentVersion = `${view?.sessionId}:${displayed?.chunkId}:${entries.length}:${view?.conversation.map(m => m.content).join('\n')}:${displayed?.translation?.length}`;
  const positioned = useRef<string | undefined>(undefined);
  const reviewLanding = useRef(false);
  const pendingQuestion = useRef<string | null | undefined>(undefined);
  const scrolling = useReadingScroll(stream, follow, eventScope, active, visible && !showStructure);
  useLayoutEffect(() => {
    const pane = stream.current;
    if (!pane || !mist) return;
    let previousWidth = 0;
    const measure = () => {
      setAvailableWidth((layout.current?.clientWidth ?? pane.offsetWidth) - (pane.offsetWidth - pane.clientWidth));
      if (pane.clientWidth === previousWidth) return;
      scrolling.controller.current?.hold();
      previousWidth = pane.clientWidth; setReadingWidth(previousWidth);
    };
    measure();
    const observer = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(measure);
    observer?.observe(pane);
    if (layout.current) observer?.observe(layout.current);
    return () => observer?.disconnect();
  }, [mist]);
  useLayoutEffect(() => {
    scrolling.controller.current?.sizeSpacer();
    scrolling.controller.current?.restore();
  }, [discussionAttached]);
  useLayoutEffect(() => {
    const control = scrolling.controller.current;
    const target = stream.current?.querySelector<HTMLElement>('[data-current-output="true"]');
    if (!control || !target) return;
    const question = Array.from(stream.current?.querySelectorAll<HTMLElement>('[data-role="user"]') ?? []).at(-1);
    if (pendingQuestion.current !== undefined && question && question.dataset.messageId !== pendingQuestion.current) {
      pendingQuestion.current = undefined; control.reveal(question);
    }
    if (!follow.current && !reviewLanding.current) { control.contentChanged(); return; }
    const identity = target.dataset.eventId;
    if (positioned.current !== identity) {
      positioned.current = identity;
      if (target.querySelector('.focus-reading')) {
        const group = target.closest<HTMLElement>('[data-reading-group]') ?? target;
        if (reviewLanding.current) { control.jump(group); reviewLanding.current = false; }
        else control.land(group);
      }
      else {
        const question = target.querySelector<HTMLElement>('[data-role="user"]');
        if (question) control.reveal(question);
      }
    }
  }, [contentVersion, focusedIndex, visible, showStructure]);
  function pauseFollow() { scrolling.controller.current?.userIntent(true); }
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
  function send(content = draft, clear = true, includeAttachments = true, explicitReference?: ReaderChunk) {
    if (!view || blocked || uploading || !content.trim()) return;
    pendingQuestion.current = view.conversation.filter(m => m.role === "user").at(-1)?.messageId ?? null;
    setDiscussionFocus(displayed ? chunkKey(displayed) : null);
    follow.current = true;
    // undefined uses the reading context; null is an explicitly removed reference.
    const selected = explicitReference ?? (reference === null ? null : reference ?? reviewChunk ?? displayed);
    const attachmentIds = (includeAttachments ? uploads : []).flatMap(u => u.attachment ? [u.attachment.attachmentId] : []);
    const sentUploads = (includeAttachments ? uploads : []).filter(u => u.state === "ready").map(u => u.id);
    const input: SendReaderMessageInput = {
      sessionId: view.sessionId, receipt: selected ? { sourceId: selected.sourceId, planId: selected.planId, chunkId: selected.chunkId } : reference === null ? null : visibleChunks.some(c => current && chunkKey(c) === chunkKey(current)) ? cursorReceipt(view) : null,
      content: clear && reference?.excerpt ? `> ${reference.excerpt.replace(/\n/g, "\n> ")}\n\n${content.trim()}` : content.trim(), attachmentIds,
      sourceId: selected?.sourceId ?? (view.source.sourceId || undefined),
    };
    void perform("发送", () => {
      input.requestId ??= createReaderId();
      return host.sendMessage(input);
    }, () => {
      if (clear && draftRef.current === content) setDraft("");
      setUploads(old => old.filter(u => !sentUploads.includes(u.id)));
      if (clear) setReference(undefined); setPanel(null);
    });
  }
  function next() {
    if (!view || !frontier || blocked) return;
    reviewLanding.current = false;
    const selected = reviewChunk ?? frontier;
    if (selected.index === selected.total) return;
    const input: ContinueReadingInput = { receipt: { sourceId: selected.sourceId, planId: selected.planId,
      chunkId: selected.chunkId, readingRevision: view.readingRevision }, sessionId: view.sessionId, requestId: createReaderId() };
    follow.current = true;
    void perform("下一段", () => host.continueReading(input), () => { setDiscussionFocus(null); });
  }
  function freshContinue() {
    if (!view || !frontier || blocked) return;
    reviewLanding.current = false;
    const input = { receipt: cursorReceipt(view)!, sessionId: view.sessionId, requestId: createReaderId(), beginBody: !!view.structureIntro };
    follow.current = true;
    void perform("下一段", () => host.continueReading(input));
  }
  function finishFresh() {
    if (!view || !frontier || !host.finishReading || blocked) return;
    const input = { receipt: cursorReceipt(view)!, sessionId: view.sessionId, requestId: createReaderId() };
    void perform("完成本篇", () => host.finishReading!(input));
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
    void perform("完成本篇", () => host.finishReading!(input), () => setReference(undefined));
  }
  function reread() {
    if (!view || blocked || !host.rereadReading || view.readingRevision === undefined) return;
    const chunk = current ?? view.history.at(-1);
    if (!chunk) return;
    const input = { receipt: { sourceId: chunk.sourceId, planId: chunk.planId,
      chunkId: current?.chunkId ?? null, readingRevision: view.readingRevision },
      sessionId: view.sessionId, requestId: createReaderId() };
    void perform("从头重读", () => host.rereadReading!(input), () => { setReviewChunk(null); setReference(undefined); });
  }
  async function changeNote(note: SourceNote, action: "edit" | "delete" | "undo", expectedRevision = note.revision) {
    if (!host.changeSourceNote || !view) return;
    const content = action === "edit" ? editDraft : undefined;
    const key = JSON.stringify([note.sourceId, note.noteId, action, expectedRevision, content]);
    const result = await host.changeSourceNote(note.sourceId, note.noteId, action, expectedRevision, mutationId(key), content);
    if (!result.ok) { setNoteError(result.error.message); return; }
    accept(result.value);
    mutationIds.current.delete(key);
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
    const key = JSON.stringify([entry.progress_id, action, expectedRevision, action === "edit" ? progressDraft : undefined]);
    const result = await host.changeReadingProgress(entry.progress_id, action, expectedRevision,
      mutationId(key), action === "edit" ? progressDraft : undefined);
    if (!result.ok) { setProgressError(result.error.message); return; }
    accept(result.value);
    mutationIds.current.delete(key);
    if (result.value.progressOperation?.status === "conflict") {
      setProgressConflict(result.value.progressOperation.current ?? null);
      setProgressError("阅读记录已改变；输入已保留，请查看当前版本后重新提交。");
    } else {
      setEditingProgressId(null); setProgressDraft(""); setProgressBaseRevision(null);
      setProgressConflict(null); setProgressError("");
    }
  }
  function referencedElement(chunk: ReaderChunk) {
    return Array.from(stream.current?.querySelectorAll<HTMLElement>("[data-chunk-key]") ?? []).reverse().find(el => el.dataset.chunkKey === chunkKey(chunk));
  }
  function clearHighlight() {
    if (highlightTimer.current) clearTimeout(highlightTimer.current);
    highlightTimer.current = null;
    globalThis.CSS?.highlights?.delete("reader-quote");
  }
  function highlight(chunk: ReaderChunk, excerpt: string, timed = false) {
    clearHighlight();
    const body = referencedElement(chunk)?.querySelector(".focus-markdown");
    if (!body || !globalThis.CSS?.highlights || typeof Highlight === "undefined") return;
    const walker = document.createTreeWalker(body, NodeFilter.SHOW_TEXT), nodes: Text[] = [];
    while (walker.nextNode()) nodes.push(walker.currentNode as Text);
    const full = nodes.map(n => n.data).join(""), start = full.indexOf(excerpt);
    if (start < 0 || !excerpt) return;
    const range = document.createRange(); let offset = 0;
    for (const node of nodes) {
      if (start >= offset && start < offset + node.length) range.setStart(node, start - offset);
      if (start + excerpt.length > offset && start + excerpt.length <= offset + node.length) { range.setEnd(node, start + excerpt.length - offset); break; }
      offset += node.length;
    }
    CSS.highlights.set("reader-quote", new Highlight(range));
    if (timed) highlightTimer.current = setTimeout(clearHighlight, 2400);
  }
  useEffect(() => () => clearHighlight(), [eventScope]);
  function jumpReference(chunk: ReaderChunk, excerpt = "") {
    const target = referencedElement(chunk);
    if (target) { scrolling.controller.current?.jump(target); highlight(chunk, excerpt, true); }
  }
  function readSelection() {
    const selected = window.getSelection();
    if (!selected?.rangeCount || selected.isCollapsed || !selected.toString().trim()) { setSelection(null); return; }
    const range = selected.getRangeAt(0);
    const element = (range.startContainer.nodeType === Node.ELEMENT_NODE ? range.startContainer : range.startContainer.parentElement) as Element | null;
    const article = element?.closest<HTMLElement>(".focus-reading");
    if (!article || !article.contains(range.endContainer) || !element?.closest(".focus-markdown")) { setSelection(null); return; }
    const chunk = visibleChunks.find(c => chunkKey(c) === article.dataset.chunkKey);
    const box = range.getBoundingClientRect();
    if (chunk) setSelection({ chunk, text: selected.toString().trim(), x: Math.max(8, Math.min(innerWidth - 160, box.left)), y: Math.max(8, box.top - 40) });
  }
  function referenceChunk(chunk: ReaderChunk, excerpt?: string) { setReference({ ...chunk, excerpt }); setCollapsed(false); requestAnimationFrame(() => composer.current?.focus({ preventScroll: true })); }
  function review(chunk: ReaderChunk) {
    setDiscussionFocus(null);
    setPanel(null);
    if (!host.reviewChunk) { reviewLanding.current = true; setReviewChunk(chunk); return; }
    const requestId = createReaderId();
    void perform("回看", () => host.reviewChunk!(chunk.sourceId, chunk.planId, chunk.chunkId, requestId), () => {
      reviewLanding.current = true;
      setReviewChunk(chunk.chunkId === frontier?.chunkId ? null : chunk); if (!draftRef.current) setReference(undefined); follow.current = true;
    });
  }

  const outline = view?.outline ?? Array.from({ length: current?.total ?? chunks.at(-1)?.total ?? 0 },
    (_, i) => ({ chunkId: `chunk-${String(i + 1).padStart(3, "0")}`, index: i + 1, sectionPath: [] as string[] }));
  const progressEntries = view?.readingProgress ?? [];
  const locationProgress = mist && lensReview ? <small>回看 {lensChunk!.index} · 进度 {frontier!.index}/{frontier!.total}</small> : <small>{view?.structureIntro ? 0 : locatedChunk?.index ?? frontier?.index ?? current?.index ?? 0} / {view?.outline?.length ?? frontier?.total ?? current?.total ?? 0}</small>;
  const locationPath = <span>{showStructure ? "文章结构" : structureTitle || (view?.status === "completed" ? "已完成本篇" : "准备阅读")}</span>;
  const readingLocation = !!(view?.structure?.length || view?.outline?.length || frontier || current) && (mist
    ? <button type="button" className="reader-location-badge" aria-label="当前阅读位置" aria-haspopup="dialog" title={structureTitle} onClick={() => setPanel("contents")}>{locationProgress}{locationPath}</button>
    : <div className="reader-structure-status" aria-label="当前阅读位置" title={structureTitle}>
      {locationPath}{locationProgress}
      {!view?.structureIntro && <button aria-expanded={showStructure} onClick={() => setStructureOpen(!structureOpen)}>{showStructure ? "返回阅读" : "文章结构"}</button>}
    </div>);
  const composerFeedback = recoverDraft || connection || failure || (operation && !active) || (agent && active) || uploads.length > 0;
  function toggleComposer(nextCollapsed: boolean) {
    scrolling.controller.current?.hold(nextCollapsed ? layout.current?.querySelector<HTMLElement>(".focus-bottom")?.offsetHeight ?? 0 : 0);
    setCollapsed(nextCollapsed);
    requestAnimationFrame(() => {
      if (nextCollapsed) layout.current?.querySelector<HTMLButtonElement>(".mist-reading-actions .mist-composer-toggle")?.focus({ preventScroll: true });
      else composer.current?.focus({ preventScroll: true });
    });
  }
  const continueLabel = view?.status === "completed" && (!reviewChunk || reviewChunk.index === reviewChunk.total) ? "已读完" : (view?.sessionFresh && view.readingStarted && frontier?.index === frontier?.total) || (!view?.sessionFresh && displayed?.index === displayed?.total && !reviewChunk) ? "完成本篇" : operation === "下一段" ? "打开中…" : "继续";
  return <AssetInstanceContext.Provider value={view?.workspace?.instanceId}><div ref={layout} data-reading-measure={measure} data-discussion-attached={discussionAttached} data-reading-narrow={readingWidth < 600} data-structure-open={showStructure} onKeyDown={event => { if (event.key === "Escape" && structureOpen) {
      setStructureOpen(false); layout.current?.querySelector<HTMLButtonElement>(".reader-location-badge")?.focus({ preventScroll: true });
    } else if (event.key === "Escape" && sideMode && !(event.target as HTMLElement).closest("dialog")) {
    preserveReading(() => setSideMode(null)); event.currentTarget.querySelector<HTMLButtonElement>(mist ? ".reader-side-toggle" : ".reader-figures-toggle")?.focus({ preventScroll: true });
  } }} data-materials-open={mist && materialsOpen && !showStructure} data-side-open={!!sideMode && !showStructure} className={`focus-reader reader-split${mist ? " focus-mist" : ""}`} data-font-size={fontSize} data-large-text={largeText || fontSize === "large" || fontSize === "extra"} data-composer-collapsed={collapsed}
    style={{ "--reader-column": `calc(${readingMeasures.find(m => m.id === measure)!.characters} * var(--reader-reading-size))`, "--reader-available-width": availableWidth ? `${availableWidth}px` : "100%", "--reader-shift": `${readerShift}px`, "--reader-reading-size": `${readingFontSizes[fontSize]}px`, "--reader-text-share": `${textShare}fr`, "--reader-side-share": `${100 - textShare}fr` } as CSSProperties}>
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
        {!mist && <nav className="reader-side-toolbar" aria-label="阅读侧栏">
          <button className="reader-figures-toggle" aria-controls="reader-side-space" aria-expanded={sideMode === "figures"} onClick={() => preserveReading(() => setSideMode(sideMode === "figures" ? null : "figures"))}>{sideMode === "figures" ? "隐藏图片区" : "展开图片区"}</button>
          <button className="reader-materials-toggle" aria-controls="reader-side-space" aria-expanded={materialsOpen} onClick={() => preserveReading(() => setSideMode(materialsOpen ? null : materialTab ?? "notes"))}>{materialsOpen ? "隐藏资料栏" : "笔记与记录"}</button>
        </nav>}
        {sideMode && !showStructure && !mist && <div className="reader-column-resizer" role="separator" aria-label="调整文字与侧栏宽度" aria-orientation="vertical" tabIndex={0} aria-valuemin={35} aria-valuemax={75} aria-valuenow={Math.round(textShare)} onKeyDown={event => {
          if (["ArrowLeft", "ArrowRight", "Home"].includes(event.key)) { event.preventDefault(); resizeColumns(event.key === "Home" ? 60 : textShare + (event.key === "ArrowRight" ? 2 : -2)); }
        }} onPointerDown={event => { event.currentTarget.setPointerCapture(event.pointerId); event.preventDefault(); }} onPointerMove={event => {
          if (!event.currentTarget.hasPointerCapture(event.pointerId) || !event.buttons || !layout.current) return;
          const box = layout.current.getBoundingClientRect(); const left = stream.current?.offsetLeft ?? 0;
          resizeColumns((event.clientX - box.left - left) / (box.width - left - 8) * 100);
        }} />}
        <section id="reader-side-space" className={`reader-side-space${mist ? " reader-left-drawer" : ""}`} data-side-placement={mist ? "left" : "right"} aria-label="阅读资料侧栏" data-open={!!sideMode && !showStructure} inert={!sideMode || showStructure} aria-hidden={!sideMode || showStructure} hidden={!mist && (!sideMode || showStructure)}>
        <header className="reader-side-heading" role="group" aria-label="资料分类"><button aria-label="图片" aria-pressed={renderedSideMode === "figures"} onClick={() => preserveReading(() => setSideMode("figures"))}>图片 <small>{sourceFigures.length}</small></button><button aria-label="笔记" aria-pressed={renderedSideMode === "notes"} onClick={() => preserveReading(() => setSideMode("notes"))}>笔记 <small>{view?.sourceNotes?.filter(note => !note.deleted).length ?? 0}</small></button><button aria-pressed={renderedSideMode === "progress"} onClick={() => preserveReading(() => setSideMode("progress"))}>进度</button><button aria-pressed={renderedSideMode === "discussion"} onClick={() => preserveReading(() => setSideMode("discussion"))}>讨论</button>{renderedSideMode && <button className="reader-side-close" aria-label="关闭阅读侧栏" onClick={() => preserveReading(() => setSideMode(null))}>×</button>}</header>
        {renderedSideMode === "figures" && <FigurePanel key={sourceId} figures={sourceFigures} selected={selectedFigure} selectionVersion={figureSelectionVersion} paragraph={f => figureChunk(f, visibleChunks)?.index} onParagraph={f => {
          const chunk = figureChunk(f, visibleChunks);
          const target = Array.from(stream.current?.querySelectorAll<HTMLElement>("[data-chunk-key]") ?? []).find(el => chunk && el.dataset.chunkKey === chunkKey(chunk));
          if (target) scrolling.controller.current?.jump(target);
        }} onZoom={(figure, origin) => setViewer({ figure, origin })} onSelect={figure => preserveReading(() => { setSelectedFigure(figure.id); setFigureSelectionVersion(old => old + 1); })} />}
        <aside id="reader-materials" role={mist ? "complementary" : "group"} className="reader-materials" hidden={renderedSideMode === "figures" || !renderedSideMode} aria-label="阅读资料">
        <div className="reader-panel" hidden={renderedSideMode !== "discussion"}>
        {view?.discussions?.length ? <section aria-label="历史讨论">{view.discussions.map((d, i) => <button key={d.discussionId} disabled={blocked} onClick={() => host.selectDiscussionSource && void perform("打开历史讨论", () => host.selectDiscussionSource!(d.sourceId, d.discussionId))}>讨论 {i + 1} · {d.sourceId}</button>)}</section>
          : <p className="reader-panel__empty">开始讨论后，历史会保存在这里。</p>}
        </div>

        <div className="reader-panel" hidden={renderedSideMode !== "notes"}>
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
                  {!note.deleted && <button onClick={() => void changeNote(note, "delete")}>删除</button>}
                  {note.canUndo && <button onClick={() => void changeNote(note, "undo")}>撤销</button>}

                </>}
            </li>)}</ol>}
        </details>}
        </div>
        <div className="reader-panel" hidden={renderedSideMode !== "progress"}>
        {view?.source.sourceId && view.readingProgress && <details className="focus-source-notes" open><summary>阅读记录 · {progressEntries.filter(entry => !entry.deleted).length}</summary>
          {progressError && <p role="alert">{progressError}</p>}
          {progressEntries.length === 0 ? <p>推进或完成本篇后，此处显示已读记录。</p> : <ol>{progressEntries.filter(entry => !entry.deleted).map(entry =>
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
                {!entry.deleted && <button onClick={() => { if (window.confirm("删除这条阅读记录？阅读位置不会改变。")) void changeProgress(entry, "delete"); }}>删除</button>}
                {!entry.deleted && ["pending", "failed", "interrupted"].includes(entry.status) && host.retryReadingProgress &&
                  <button onClick={() => { const requestId = createReaderId(); void perform("补记", () => host.retryReadingProgress!(entry.progress_id, requestId)); }}>补记</button>}
                {!entry.deleted && entry.status === "generating" && <small>整理中…</small>}
                {!entry.deleted && entry.status === "generating" && host.cancelReadingProgress &&
                  <button onClick={() => void perform("停止补记", () => host.cancelReadingProgress!(entry.progress_id))}>停止补记</button>}
                {!entry.deleted && (entry.status === "failed" || entry.status === "interrupted") && <small>生成未完成，已读位置不受影响。</small>}
              </>}
            </li>)}</ol>}
        </details>}
        </div>
        </aside>
        </section>
    <main className="focus-stream" ref={stream} aria-label="阅读与对话" tabIndex={0}
      onWheel={e => scrolling.controller.current?.userIntent(e.deltaY < 0)} onTouchStart={pauseFollow}
      onKeyDown={e => { if (["PageUp", "PageDown", "Home", "End", "ArrowUp", "ArrowDown", " "].includes(e.key)) scrolling.controller.current?.userIntent(["PageUp", "Home", "ArrowUp"].includes(e.key)); }}
      onMouseUp={readSelection} onKeyUp={readSelection} onScroll={() => { setSelection(null); locateVisibleChunk(); scrolling.controller.current?.onScroll(); }}>
      {!mist && readingLocation}
      <div className="focus-content">
        {showStructure && view && (host.getArticleOverview ? <ArticleOverviewPanel host={host} sourceId={sourceId} title={view.source.title} view={view}
          currentChunkId={view.structureIntro ? undefined : structureChunkId} blocked={blocked}
          onReview={id => { const chunk = chunks.find(c => c.chunkId === id); if (chunk) { setStructureOpen(false); review(chunk); } }}
          onBody={() => { if (view.structureIntro) freshContinue(); else setStructureOpen(false); }} /> : <ArticleStructure view={view} currentChunkId={view.structureIntro ? undefined : structureChunkId} blocked={blocked}
          onReview={id => { const chunk = chunks.find(c => c.chunkId === id); if (chunk) { setStructureOpen(false); review(chunk); } }}
          onBody={() => { if (view.structureIntro) freshContinue(); else setStructureOpen(false); }} />)}
        <div hidden={showStructure} className={mist ? "reading-lens-document" : undefined} ref={lens.document}>
        {mist && <div ref={lens.surface} className="reading-lens" data-review={lensReview} data-lens-active={lens.activeId ?? undefined} hidden={!lens.activeId} aria-hidden="true" />}
        {!view && <p role="status">{connection ? "暂时无法连接" : "正在打开…"}</p>}
        {reviewChunk && !reviewNoticeDismissed && <p className="focus-review-banner">正在回看第 {reviewChunk.index} 段 · 正式位置未改变 <button onClick={() => { if (frontier) review(frontier); }}>返回当前阅读</button><button aria-label="关闭回看提示" onClick={() => setReviewNoticeDismissed(true)}><Close /></button></p>}
        {view && displayEmpty && <section className="focus-start">
          <span className="focus-start__label" aria-hidden="true">▤</span>
          <h1>{view.readingUnavailable ? view.source.title : view.source.sourceId ? `讨论 ${view.source.title}` : "打开一份材料"}</h1>
          {view.readingUnavailable && <p role="status">{view.readingUnavailable}</p>}
          <div><button className="focus-primary" onClick={() => setPanel("materials")}>打开材料</button>
            {!mist && host.upload && <button onClick={() => fileInput.current?.click()}>上传</button>}
            {(current || view.history.length > 0) && host.resumeReading && <button onClick={resume} disabled={blocked}>恢复阅读</button>}</div>
        </section>}
        {paragraphGroups.map(group => {
          const groupIndex = readingGroups.findIndex(item => item.id === group.id);
          const state = group.id === lens.activeId ? "focus" : Math.abs(groupIndex - lensIndex) === 1 ? "near" : "far";
          return <div key={`${eventScope}:${group.id}`} className={mist ? "reading-lens-group" : undefined}
            data-reading-group={group.chunk ? group.id : undefined} data-lens-group={mist && group.chunk ? group.id : undefined} data-lens-index={group.chunk?.index}
            data-state={mist && group.chunk ? state : undefined} data-review={mist && group.id === lens.activeId && lensReview}>
          {([false, true] as const).map(discussion => <div key={String(discussion)} className={discussion ? "reading-group-discussion" : "reading-group-source"}>
          {group.indexes.filter(index => (entries[index].kind === "message") === discussion).map(index => {
          const e = entries[index];
          const message = e.kind === "message" ? view?.conversation.find(m => m.messageId === e.messageId) : null;
          const content = e.kind === "reading" ? <ReadingChunk chunk={e.chunk} onReference={referenceChunk} onFigure={showFigure} onZoom={(figure, origin) => setViewer({ figure, origin })} onLanguage={(chunk, original) => preserveReading(() => setFigureLanguages(old => ({ ...old, [chunkKey(chunk)]: original })))} /> : message ? <ReaderConversation messages={[message]} chunks={chunks} figures={view?.figures} figureSourceId={sourceId} sourceFigures={sourceFigures} onFigure={showFigure} onZoom={(figure, origin) => setViewer({ figure, origin })} streaming={active && message.messageId === view?.conversation.at(-1)?.messageId}
            onJump={jumpReference} onHighlight={highlight} onClearHighlight={() => { if (!highlightTimer.current) clearHighlight(); }} onSaveNote={(reply, chunk) => send(`请把下面的回答记下来：\n\n${reply.content}`, false, false, chunk)} /> : null;
          const identity = eventKeys[index];
          return <TimelineEvent key={`${eventScope}:${identity}`} identity={identity} current={index === focusedIndex} fresh={committedEvents.current?.scope === eventScope && !committedEvents.current.ids.has(identity)} streaming={active && message?.role === "assistant" && message.messageId === view?.conversation.at(-1)?.messageId}>{content}</TimelineEvent>;
          })}
          {discussion && discussionAttached && group.chunk && state === "focus" && group.indexes.length === 1 &&
            <button className="reading-group-ask" disabled={blocked} onClick={() => preserveReading(() => referenceChunk(group.chunk!))}>＋ 就这段提问</button>}
          </div>)}
          </div>;
        })}
        {view?.status === "completed" && !reviewChunk && <div className="focus-finished">已完成本篇 <button disabled={!host.clearSource || blocked} onClick={() => { if (view && window.confirm("将清除本篇讨论、笔记和阅读记录，并从第一段重新开始。原文、译文和博客保留。")) { const requestId = createReaderId(); void perform("重新阅读", () => host.clearSource!(view.source.sourceId, requestId)); } }}>重新阅读</button><button onClick={() => setPanel("contents")}>查看已读段落</button></div>}
        </div>
      </div>
      <div ref={scrolling.end} aria-hidden="true" />
      <div ref={scrolling.spacer} aria-hidden="true" style={{ height: 128, overflowAnchor: "none" }} />
    </main>
      {!showStructure && (scrolling.back || (scrolling.latest && (readingGroups.length > 1 || !!view?.conversation.length))) && <div className="focus-new-content">
        {scrolling.back && <span className="reader-scroll-notice"><button onClick={() => scrolling.controller.current?.goBack()}>↩ 返回刚才位置</button><button aria-label="关闭返回位置提示" onClick={() => scrolling.controller.current?.dismissBack()}><Close /></button></span>}
        {scrolling.latest && (readingGroups.length > 1 || !!view?.conversation.length) && <span className="reader-scroll-notice"><button onClick={() => scrolling.controller.current?.toLatest()}>{active ? "回答生成中 · " : ""}回到最新 ↓</button><button aria-label="关闭回到最新提示" onClick={() => scrolling.controller.current?.dismissLatest()}><Close /></button></span>}
      </div>}
    <div className="focus-bottom" hidden={showStructure} data-empty={mist && collapsed && !composerFeedback} role={mist ? "complementary" : undefined} aria-label={mist ? "阅读助手" : undefined}>
      <div className="focus-composer-wrap">
        <div className="focus-composer-notices">
        {recoverDraft && <details className="focus-recover"><summary>恢复草稿</summary>{Object.entries(drafts.current).filter(([, d]) => d.text || d.note || d.progress).map(([key, d]) => <div key={key}><p>{d.reference?.sourceId ?? key.split(":")[0]}：{d.text || d.note || d.progress}</p><button disabled={key.split(":")[0] !== view?.source.sourceId} onClick={() => { setDraft(d.text); setReference(d.reference); setEditingNoteId(d.noteId); setEditDraft(d.note); setEditBaseRevision(d.noteRevision); setEditingProgressId(d.progressId); setProgressDraft(d.progress); setProgressBaseRevision(d.progressRevision); setRecoverDraft(false); }}>恢复草稿</button></div>)}</details>}
        {connection && <div className="focus-error" role="alert">{connection}<button onClick={() => void reconnect()}>重新连接</button></div>}
        {failure && <div className="focus-error" role="alert">{failure.message}<button disabled={!!operation} onClick={failure.retry}>{failure.label}</button><button aria-label="关闭错误" onClick={() => setFailure(null)}>×</button></div>}
        {operation && !active && <p className="focus-operation" role="status">{operation === "下一段" ? "正在打开下一段…" : `${operation}中…`}</p>}
        {agent && active && <AgentControls agent={agent} showStop={false} onStop={() => void perform("停止", () => host.stop!())} onAnswer={async input => {
          const result = await host.approve?.(input);
          if (result?.ok) { accept(result.value); return true; } return false;
        }} />}
        </div>
        <div className="focus-composer-collapse" data-collapsed={mist && collapsed} inert={mist && collapsed} aria-hidden={mist && collapsed}><div className="focus-composer-row">
          <form id="focus-composer-form" className="focus-composer" data-busy={blocked || uploading ? "true" : undefined} onSubmit={e => { e.preventDefault(); send(); }}>
          {reference && <div className="focus-reference"><button type="button" onClick={() => jumpReference(reference, reference.excerpt ?? "")}>引用第 {reference.index} 段 · {reference.excerpt || reference.sectionPath.at(-1)}</button><button type="button" onClick={() => setReference(displayed)}>改为当前段落</button><button type="button" className="focus-reference-remove" aria-label="取消段落引用" title="取消段落引用" onClick={() => { setReference(null); composer.current?.focus({ preventScroll: true }); }}><Close /></button></div>}
          {uploads.length > 0 && <ul className="focus-attachments">{uploads.map(u => <li key={u.id}>
            <span title={u.file.name}>{u.file.name}</span><small>{u.state === "uploading" ? "上传中" : u.state === "failed" ? "上传失败" : "已上传"}</small>
            {u.state === "failed" && <button type="button" title={u.error} onClick={() => void upload(u.file, u.id)}>重试上传</button>}
            <button type="button" aria-label={`移除 ${u.file.name}`} onClick={() => setUploads(old => old.filter(v => v.id !== u.id))}>移除</button>
          </li>)}</ul>}
          <label className="focus-sr-only" htmlFor="focus-question">输入问题或阅读需求</label>
          <span id="focus-question-hint" className="focus-sr-only">Enter 发送，Shift+Enter 换行</span>
          <textarea id="focus-question" aria-describedby="focus-question-hint" ref={composer} rows={1} disabled={blocked} value={draft} placeholder="问问这段原文…"
            onChange={e => { if (!draft && e.target.value && reference === undefined) setReference(displayed); setDraft(e.target.value); }} onKeyDown={e => {
              if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing && e.nativeEvent.keyCode !== 229) { e.preventDefault(); send(); }
            }} />
          <div className="focus-composer__actions">
            {((!mist && host.upload) || uploads.some(u => u.state === "ready")) && <div className="focus-composer__tools">{!mist && host.upload && <><input ref={fileInput} className="focus-sr-only" aria-label="选择论文文件" type="file" accept=".pdf,.html" multiple onChange={e => {
              Array.from(e.target.files ?? []).forEach(f => void upload(f)); e.target.value = "";
            }} /><button type="button" onClick={() => fileInput.current?.click()} aria-label="添加附件">＋ 附件</button></>}
              {uploads.some(u => u.state === "ready") && <button type="button" disabled={blocked || uploading} onClick={() => send("请阅读附件", false)}>阅读附件</button>}
            </div>}
            {active && host.stop && !collapsed
              ? <button type="button" className="focus-primary focus-composer__send" aria-label="停止" title="停止" onClick={() => void perform("停止", () => host.stop!())} disabled={agent?.run?.status === "stopping"}><StopSquare /></button>
              : <button type="submit" className="focus-primary focus-composer__send" aria-label={operation === "发送" ? "发送中" : "发送"} title={operation === "发送" ? "发送中" : "发送"} disabled={!view || blocked || uploading || !draft.trim()}><ArrowUp /></button>}
          </div>
          </form>
        </div>
        </div>
        {!mist && view?.status !== "completed" && current && !reviewChunk && <div className="focus-next"><button disabled={blocked} onClick={current.index === current.total ? finish : next}>{current.index === current.total ? "完成本篇" : operation === "下一段" ? "正在打开…" : "下一段 →"}</button></div>}
      </div>
    </div>
    {mist && <nav className="mist-reading-actions" aria-label="阅读功能控制区">
      <button className="reader-side-toggle" aria-controls="reader-side-space" aria-expanded={!!sideMode} onClick={() => preserveReading(() => setSideMode(sideMode ? null : sourceFigures.length ? "figures" : materialTab ?? "notes"))}><PanelLeft /><span className="mist-action-label">{sideMode ? "收起资料" : "资料"}</span></button>

      {readingLocation}
      {lensReview && progressNoticeDismissed !== `${eventScope}:${lens.activeId}` && <span className="reader-scroll-notice"><button type="button" onClick={() => {
        const group = [...readingGroups].reverse().find(item => item.chunk && frontier && chunkKey(item.chunk) === chunkKey(frontier));
        const target = Array.from(lens.document.current?.querySelectorAll<HTMLElement>("[data-lens-group]") ?? []).find(el => el.dataset.lensGroup === group?.id);
        if (group && target && stream.current) {
          lens.focus(group.id);
          scrolling.controller.current?.jump(target);
        }
      }}>回到进度</button><button aria-label="关闭回到进度提示" onClick={() => setProgressNoticeDismissed(`${eventScope}:${lens.activeId}`)}><Close /></button></span>}
      <div className="reader-width-control" ref={widthControl} onKeyDown={event => {
        if (event.key === "Escape") { event.stopPropagation(); setWidthOpen(false); widthControl.current?.querySelector("button")?.focus(); }
      }}>
        <button className="reader-width-toggle" aria-label="行宽" title="行宽" aria-expanded={widthOpen} aria-controls="reader-width-panel" onClick={() => setWidthOpen(!widthOpen)}><Widen /><span className="mist-action-label">行宽</span></button>
        {widthOpen && <div ref={widthPanel} popover="manual" id="reader-width-panel" className="reader-width-panel" role="radiogroup" aria-label="阅读行宽" onKeyDown={event => {
          if (!["ArrowLeft", "ArrowRight"].includes(event.key)) return;
          event.preventDefault();
          const options = readingMeasures.filter(m => measureFits(m.id));
          if (!options.length) return;
          const index = options.findIndex(m => m.id === measure);
          const next = options[(index + (event.key === "ArrowRight" ? 1 : options.length - 1)) % options.length];
          selectMeasure(next.id); widthControl.current?.querySelector<HTMLButtonElement>(`[data-measure="${next.id}"]`)?.focus();
        }}>
          {readingMeasures.map(item => <button key={item.id} role="radio" data-measure={item.id} aria-checked={measure === item.id}
            disabled={!measureFits(item.id)} title={measureFits(item.id) ? `每行约 ${item.characters} 字` : "窗口宽度不足"}
            tabIndex={measure === item.id ? 0 : -1} autoFocus={measure === item.id} onClick={() => selectMeasure(item.id)}>{item.label}</button>)}
        </div>}

      </div>
      <button className="reader-attach-toggle" aria-pressed={attachDiscussion} title={attachTitle} onClick={() => preserveReading(() => {
        const next = !attachDiscussion; setAttachDiscussion(next);
        try { localStorage.setItem("focus.attachDiscussion", String(next)); } catch { /* In-memory fallback. */ }
      })}><Pin /><span className="mist-action-label">吸附讨论</span></button>
      <button aria-label="新会话" className="reader-new-session" disabled={!host.newSession || !view || blocked} onClick={reset}><Plus /><span className="mist-action-label">新会话</span></button>
      <button className="reader-fullscreen-toggle" aria-label={fullscreen ? "退出全屏" : "全屏"} aria-pressed={fullscreen} onClick={() => onFullscreenChange?.(!fullscreen)}>{fullscreen ? <Collapse /> : <Expand />}<span className="mist-action-label">{fullscreen ? "退出全屏" : "全屏"}</span></button>
      <button type="button" className="mist-composer-toggle" aria-expanded={!collapsed} aria-controls="focus-composer-form" onClick={() => toggleComposer(!collapsed)}><ChevronDown />{collapsed ? "提问" : "收起"}{collapsed && draft && <span aria-hidden="true" className="mist-composer-toggle__draft" />}</button>
      {collapsed && active && host.stop && <button className="focus-reader__stop" onClick={() => void perform("停止", () => host.stop!())}><StopSquare />停止</button>}
      {view?.status !== "completed" && <button className="focus-reader__continue" aria-label={continueLabel} disabled={showStructure || blocked || (!frontier && !reviewChunk)}
        onClick={() => { follow.current = true; view?.sessionFresh ? (view.readingStarted && frontier?.index === frontier?.total ? finishFresh() : freshContinue()) : displayed?.index === displayed?.total && !reviewChunk ? finish() : next(); }}>
        {continueLabel === "继续" ? `继续 · 第 ${view?.sessionFresh ? view.readingStarted ? (frontier?.index ?? 0) + 1 : frontier?.index ?? 1 : (displayed?.index ?? 0) + 1} 段` : continueLabel}<ArrowRight /></button>}
      {blocked && <span className="mist-reading-actions__status">{active ? "请等待回答完成，或停止此问答" : `${operation}中`}</span>}
    </nav>}

    {selection && <button className="reader-selection-quote" style={{ left: selection.x, top: selection.y }} onMouseDown={e => e.preventDefault()} onClick={() => { referenceChunk(selection.chunk, selection.text); setSelection(null); window.getSelection()?.removeAllRanges(); }}>引用所选提问</button>}
    {viewer && <FigureViewer request={viewer} figures={sourceFigures} onClose={() => setViewer(null)} />}
    <dialog ref={dialog} className="focus-dialog" data-panel={renderedPanel} onCancel={() => setPanel(null)} onClick={e => { if (e.target === dialog.current) setPanel(null); }}>
      <header><h2>{renderedPanel === "materials" ? "材料" : renderedPanel === "contents" ? "已加载段落" : "阅读设置"}</h2><button aria-label="关闭" onClick={() => setPanel(null)}>×</button></header>
      {renderedPanel === "materials" && <>
        {view?.source.sourceId && <p className="focus-full-title">{view.source.title}</p>}
        {!mist && host.upload && <button onClick={() => { setPanel(null); fileInput.current?.click(); }}>上传</button>}
        {agent?.catalog.sources.length ? <section><h3>来源</h3>{agent.catalog.sources.map(s => <button className="focus-material" disabled={blocked} key={s.sourceId} onClick={() => { follow.current = true; if (host.openSource) void perform("加载材料", () => host.openSource!(s.sourceId), () => setPanel(null)); else send(`开始阅读 Source ${s.sourceId}`, false, false); }}>{s.title}</button>)}</section> : <p>暂无已保存的材料。</p>}
        {!!agent?.catalog.topics.length && <section><h3>专题</h3>{agent.catalog.topics.map(t => <button className="focus-material" disabled={blocked} key={t.topicId} onClick={() => send(`开始阅读 Topic ${t.topicId}`, false, false)}>{t.title}</button>)}</section>}
      </>}
      {renderedPanel === "contents" && !!view?.structure?.length && !view.structureIntro && <button className="reader-structure-overview" onClick={() => { setPanel(null); setStructureOpen(true); requestAnimationFrame(() => stream.current?.querySelector<HTMLElement>(".article-structure h1")?.focus({ preventScroll: true })); }}>文章结构总览</button>}
      {renderedPanel === "contents" && <nav aria-label="已读段落">{outline.length ? outline.map(item => {
        const loaded = chunks.find(c => c.chunkId === item.chunkId);
        return <button className="focus-material" key={item.chunkId} disabled={!loaded} aria-current={displayed?.chunkId === item.chunkId ? "step" : undefined}
          onClick={() => { if (loaded) review(loaded); }}>第 {item.index} 段 · {loaded?.sectionPath.at(-1) ?? item.sectionPath.at(-1) ?? "未读段落"}</button>;
      }) : <p>打开材料后显示。</p>}</nav>}
      {renderedPanel === "settings" && <label><input type="checkbox" checked={largeText} onChange={e => setLargeText(e.target.checked)} /> 使用较大正文字号</label>}
    </dialog>
  </div></AssetInstanceContext.Provider>;
}
