import { createPortal } from "react-dom";
import { Fragment } from "react";
import { NavigationResize } from "./NavigationResize";
import { type CSSProperties, type ReactNode, useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { createReaderId, type BlogArtifactName, type BlogArtifactStatus, type BlogRegenerationTarget, type BlogStatus, type IngestionItem, type ProcessingBatch, type SourceDeletionImpact, type LibrarySource, type LibraryTopic, type ReaderHost, type ReaderHostResult, type ReadingWindow } from "@focus/reader-contracts";
import { FocusReader, AgentControls, readingFontSizes, preparationFailed as hasPreparationFailure, preparationStepText, preparationText, useEvidenceNavigation, BookOpen, ChatBubble, DocText, ReaderConfirmation, type ReaderConfirmationInput, type ReadingMode } from "@focus/reader-ui";
import { BackendSetupPanel } from "./BackendSetupPanel";
import { WorkspaceSelection } from './WorkspaceSelection';
import { UploadTopicPicker } from "./UploadTopicPicker";
import { readingFonts, readReadingFont, readingFontFamily, type ReadingFont } from "./reading-fonts";
import { applyAppearance, readPreference, type Theme, type Density } from "./appearance";

import { LibraryToolbar } from "./library/LibraryToolbar";
import { LibraryPage } from "./library/LibraryPage";
import { ingestionFormat } from "./library/ingestion-format";
import { matchesStatus, sourceStatus, type StatusFilter } from "./library/source-status";
import { UNFILED, sortingDisabledReason } from "./library/topic-view";

type Route = "/library" | "/reading" | "/settings";
type FontSize = "small" | "standard" | "large" | "extra";
const fontOptions: [FontSize, string][] = [["small", "紧凑"], ["standard", "标准"], ["large", "较大"], ["extra", "特大"]];
function readFont(): FontSize {
  try { const value = localStorage.getItem("focus.fontSize"); return fontOptions.some(([key]) => key === value) ? value as FontSize : "standard"; }
  catch { return "standard"; }
}
function routeFromLocation(): Route { return ["/library", "/reading", "/settings"].includes(location.pathname) ? location.pathname as Route : "/library"; }

const blogArtifacts: readonly [BlogArtifactName, string][] = [["reading_blog", "带读博客"], ["html", "HTML"]];
const blogStatusText: Record<BlogArtifactStatus, string> = {
  pending: "待生成", generating: "生成中", completed: "已完成", failed: "失败",
};
/** Retry is named by granularity: only the failed document is re-run. */
const blogRetryLabel: Record<BlogArtifactName, string> = {
  reading_blog: "重新生成带读博客", html: "重新生成 HTML",
};

export function WorkspaceApp({ host }: { host: ReaderHost }) {
  const [workbenchId] = useState(createReaderId);
  const [route, setRoute] = useState<Route>(routeFromLocation);
  const [fontSize, setFontSize] = useState<FontSize>(readFont);
  const [readingFont, setReadingFont] = useState<ReadingFont>(readReadingFont);
  const [theme, setTheme] = useState<Theme>(() => readPreference("focus.theme", ["light", "dark", "system"], "system"));
  const [reducedMotion, setReducedMotion] = useState(() => readPreference("focus.reducedMotion", ["true", "false"], "false") === "true");
  const [density, setDensity] = useState<Density>(() => readPreference("focus.density", ["compact", "comfortable"], "compact"));
  const [navCollapsed, setNavCollapsed] = useState(() => readPreference("focus.navigation", ["expanded", "collapsed"], globalThis.matchMedia?.("(max-width: 1180px)").matches ? "collapsed" : "expanded") === "collapsed");
  const [appearanceFeedback, setAppearanceFeedback] = useState("");
  const [moreSource, setMoreSource] = useState<string | null>(null);
  const savedAppearance = useRef({ fontSize, readingFont, theme, density, reducedMotion });
  useEffect(() => {
    applyAppearance(theme, density, reducedMotion);
    const media = globalThis.matchMedia?.("(prefers-color-scheme: dark)");
    const update = () => applyAppearance(theme, density, reducedMotion);
    media?.addEventListener?.("change", update);
    return () => media?.removeEventListener?.("change", update);
  }, [theme, density, reducedMotion]);
  const [readingBranchOpen, setReadingBranchOpen] = useState(true);
  const [branchSlot, setBranchSlot] = useState<HTMLDivElement | null>(null);
  const [pickerSlot, setPickerSlot] = useState<HTMLDivElement | null>(null);
  const [readingFullscreen, setReadingFullscreen] = useState(false);
  const [managementTopics, setManagementTopics] = useState<readonly string[]>([]);
  const [generateOnUpload, setGenerateOnUpload] = useState(true);
  const [connectionError, setConnectionError] = useState("");
  const connectionLost = !!connectionError;
  const connectionHealth = useRef(0);
  const markConnectionHealthy = useCallback(() => {
    connectionHealth.current++;
    setConnectionError("");
  }, []);
  const streamVersion = useRef(0);
  const [taskDetails, setTaskDetails] = useState(false);
  const [taskVisited, setTaskVisited] = useState(false);
  useEffect(() => { if (taskDetails) setTaskVisited(true); }, [taskDetails]);
  const [closingPreparations, setClosingPreparations] = useState<Readonly<Record<string, string>>>({});
  const [retryAction, setRetryAction] = useState<(() => void) | null>(null);
  const refreshing = useRef<Promise<void> | null>(null);
  const taskFrame = useRef<HTMLDivElement>(null);
  const [pendingTaskFocus, setPendingTaskFocus] = useState<readonly string[] | null>(null);
  const blogRefreshing = useRef(new Set<string>());
  const [dragging, setDragging] = useState(false);
  const [view, setView] = useState<ReadingWindow | null>(null);
  const viewRef = useRef<ReadingWindow | null>(null);
  const selection = useRef<{ sourceId: string | undefined; generation: number }>({ sourceId: undefined, generation: 0 });
  const [generation, setGeneration] = useState(0);
  const mounted = useRef(false);
  useLayoutEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  const unifiedReading = !!host.getSourceDocument;
  const evidenceNavigation = useEvidenceNavigation();
  const cancelEvidenceNavigation = evidenceNavigation.cancel;
  const changeSelection = useCallback((sourceId: string | undefined) => {
    const next = { sourceId, generation: selection.current.generation + 1 };
    selection.current = next;
    cancelEvidenceNavigation();
    setGeneration(next.generation);
    return next.generation;
  }, [cancelEvidenceNavigation]);
  const isCurrentSelection = useCallback((started: number, sourceId?: string) =>
    mounted.current && started === selection.current.generation && (sourceId === undefined || sourceId === selection.current.sourceId), []);
  const acceptView = useCallback((next: ReadingWindow, started = selection.current.generation, allowSourceChange = false) => {
    if (!isCurrentSelection(started)) return false;
    const previous = viewRef.current;
    const sourceId = next.source.sourceId;
    const selected = selection.current.sourceId;
    const newInstance = previous?.workspace?.instanceId && next.workspace?.instanceId && previous.workspace.instanceId !== next.workspace.instanceId;
    if (!newInstance && unifiedReading && selected && selected !== sourceId && !allowSourceChange) return false;
    if (!newInstance && previous?.revision !== undefined && next.revision !== undefined && previous.revision > next.revision) return false;
    if (newInstance || (unifiedReading && sourceId !== selected)) changeSelection(sourceId);
    viewRef.current = next;
    setView(next);
    return true;
  }, [changeSelection, isCurrentSelection, unifiedReading]);
  const [sources, setSources] = useState<readonly LibrarySource[]>([]);
  const [topics, setTopics] = useState<readonly LibraryTopic[]>([]);
  const [inbox, setInbox] = useState<readonly IngestionItem[]>([]);
  const [topic, setTopic] = useState("");
  const [management, setManagement] = useState<{ kind: "create" | "rename" | "delete" | "source"; id?: string } | null>(null);
  const [managementTitle, setManagementTitle] = useState("");
  const [managementDisplayTitle, setManagementDisplayTitle] = useState("");
  const [managementDisplayTitleEdited, setManagementDisplayTitleEdited] = useState(false);
  const managementDialog = useRef<HTMLDialogElement>(null);
  const [libraryView, setLibraryView] = useState<"cards" | "list">(() => {
    try { return localStorage.getItem("focus.libraryView") === "cards" ? "cards" : "list"; } catch { return "list"; }
  });
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [sourcesFailed, setSourcesFailed] = useState(false);
  const [libraryError, setLibraryError] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState("");
  const [deletionImpact, setDeletionImpact] = useState<SourceDeletionImpact | null>(null);
  const [deleteConfirmation, setDeleteConfirmation] = useState<LibrarySource | null>(null);
  const [resetConfirmation, setResetConfirmation] = useState<ReaderConfirmationInput | null>(null);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [selectedFiles, setSelectedFiles] = useState<readonly File[]>([]);
  const [batches, setBatches] = useState<readonly ProcessingBatch[]>([]);
  const [uploadTopic, setUploadTopic] = useState("");
  const [blogs, setBlogs] = useState<Readonly<Record<string, BlogStatus>>>({});
  const [blogViewer, setBlogViewer] = useState("");
  function closeBlogViewer() { blogDialog.current?.close(); setBlogViewer(""); }
  const uploadDialog = useRef<HTMLDialogElement>(null);
  const blogDialog = useRef<HTMLDialogElement>(null);
  const confirmation = useRef<HTMLDialogElement>(null);
  const locked = useRef(false);
  const requestVersion = useRef(0);
  const workPollKey = `${connectionLost}:${view?.configuration?.busy}:${(view?.workItems ?? []).map(item => `${item.kind}:${item.targetId}:${item.status}`).join("|")}`;
  const libraryReadingRevision = route === "/library" ? view?.readingRevision : undefined;
  const active = !!view?.agent?.run && ["running", "approval", "stopping"].includes(view.agent.run.status);
  const approval = view?.agent?.run?.status === "approval" && view.agent.run.approvals.some(item => item.status !== "expired") ? view.agent : null;

  const actionIds = useRef<Record<string, string>>({});
  async function identified<T>(key: string, task: (requestId: string) => Promise<ReaderHostResult<T>>) {
    const id = actionIds.current[key] ??= createReaderId();
    const result = await task(id);
    if (result.ok) delete actionIds.current[key];
    return result;
  }
  function saveAppearance() {
    try {
      const changes = { "focus.fontSize": fontSize, "focus.readingFont": readingFont, "focus.theme": theme, "focus.density": density, "focus.reducedMotion": String(reducedMotion) };
      const old = Object.keys(changes).map(key => [key, localStorage.getItem(key)] as const);
      try { for (const [key, value] of Object.entries(changes)) localStorage.setItem(key, value); }
      catch (e) { for (const [key, value] of old) { if (value !== null) localStorage.setItem(key, value); else localStorage.removeItem(key); } throw e; }
      savedAppearance.current = { fontSize, readingFont, theme, density, reducedMotion }; return true;
    } catch { return false; }
  }
  useEffect(() => {
    if (!moreSource) return;
    const close = (event: PointerEvent) => {
      const target = event.target as HTMLElement | null;
      if (target?.closest<HTMLElement>("[data-more-source]")?.dataset.moreSource === moreSource) return;
      setMoreSource(null);
      document.getElementById(`source-more-trigger-${moreSource}`)?.focus();
    };
    document.addEventListener("pointerdown", close);
    return () => document.removeEventListener("pointerdown", close);
  }, [moreSource]);
  const appearanceMounted = useRef(false);
  useEffect(() => {
    if (!appearanceMounted.current) { appearanceMounted.current = true; return; }
    const ok = saveAppearance();
    setAppearanceFeedback(ok ? "已自动保存" : "外观保存失败，请重试");
    if (!ok) return;
    const timer = setTimeout(() => setAppearanceFeedback(""), 1800);
    return () => clearTimeout(timer);
  }, [fontSize, readingFont, theme, density, reducedMotion]);
  function navigate(next: Route) {
    if (next !== "/reading") cancelEvidenceNavigation();
    history.pushState(null, "", next);
    setRoute(next); setError(""); setRetryAction(null);
  }
  async function refresh(afterCurrent = false): Promise<void> {
    if (!host.listSources || !host.listTopics) { setLoading(false); return; }
    if (refreshing.current) {
      await refreshing.current;
      if (afterCurrent) await refresh();
      return;
    }
    const version = ++requestVersion.current;
    const healthAtStart = connectionHealth.current;
    const request = (async () => {
      try {
        const [sourceResult, topicResult, inboxResult, batchResult] = await Promise.allSettled([
          Promise.resolve().then(() => host.listSources!()),
          Promise.resolve().then(() => host.listTopics!()),
          Promise.resolve().then(() => host.listInbox?.()),
          Promise.resolve().then(() => host.listBatches?.()),
        ]);
        if (version !== requestVersion.current) return;
        let listError = "";
        let offline = "";
        function value<T>(result: PromiseSettledResult<ReaderHostResult<T> | undefined>): T | undefined {
          if (result.status === "rejected") {
            offline ||= String(result.reason);
          } else if (result.value?.ok) {
            return result.value.value;
          } else if (result.value?.error.code === "unavailable" && result.value.error.retryable) {
            offline ||= result.value.error.message;
          } else if (result.value) {
            listError ||= result.value.error.message;
          }
        }
        const nextSources = value(sourceResult);
        const nextTopics = value(topicResult);
        const nextInbox = value(inboxResult);
        const nextBatches = value(batchResult);
        setSourcesFailed(nextSources === undefined);
        if (nextSources) setSources(nextSources);
        if (nextTopics) { setTopics(nextTopics); setTopic(current => current === UNFILED || nextTopics.some(t => t.topicId === current) ? current : ""); }
        if (nextInbox) setInbox(nextInbox);
        if (nextBatches) setBatches(nextBatches);
        setLibraryError(listError);
        if (offline && healthAtStart === connectionHealth.current) setConnectionError(current => current || offline);
      } catch (e) {
        if (version === requestVersion.current) setLibraryError(String(e));
      }
      finally { if (version === requestVersion.current) setLoading(false); }
    })();
    refreshing.current = request;
    try { await request; } finally { if (refreshing.current === request) refreshing.current = null; }
  }
  useEffect(() => {
    if (location.pathname !== routeFromLocation()) history.replaceState(null, "", "/library");
    const pop = () => {
      const next = routeFromLocation();
      if (next !== "/reading") cancelEvidenceNavigation();
      setRoute(next);
    };
    window.addEventListener("popstate", pop);
    let alive = true;
    const accept = (result: ReaderHostResult<ReadingWindow>, started: number) => {
      if (!alive) return;
      if (result.ok) {
        markConnectionHealthy();
        acceptView(result.value, started);
      } else setConnectionError(result.error.message);
    };
    const started = selection.current.generation;
    const initialStreamVersion = streamVersion.current;
    void (host.refreshBackendConfiguration ? host.refreshBackendConfiguration() : host.getReadingWindow())
      .then(result => { if (streamVersion.current === initialStreamVersion) accept(result, started); })
      .catch(failure => { if (alive && streamVersion.current === initialStreamVersion) setConnectionError(String(failure)); });
    const unsubscribe = host.subscribe?.(result => {
      streamVersion.current++;
      accept(result, selection.current.generation);
    });
    return () => { alive = false; unsubscribe?.(); window.removeEventListener("popstate", pop); requestVersion.current++; };
  }, [host, acceptView, isCurrentSelection, cancelEvidenceNavigation, markConnectionHealthy]);
  useEffect(() => {
    if (route !== "/settings" && !connectionLost) void refresh(route === "/library");
  }, [route, view?.agent?.run?.status, libraryReadingRevision, connectionLost, host]);
  useEffect(() => {
    if (!inbox.some(item => item.status === "processing") && !batches.some(b => b.executing || ["confirmed", "running"].includes(b.status))) return;
    const timer = window.setInterval(() => void refresh(), 1200);
    return () => window.clearInterval(timer);
  }, [inbox, batches, host]);
  useEffect(() => {
    if (!connectionLost && !view?.configuration?.busy && !(view?.workItems ?? []).some(item => ["running", "approval", "stopping", "processing", "confirmed", "pending", "generating"].includes(item.status))) return;
    let cancelled = false;
    let timer: number;
    async function poll() {
      const started = selection.current.generation;
      const streamAtStart = streamVersion.current;
      try { const result = await host.getReadingWindow();
        if (!cancelled && streamAtStart === streamVersion.current) {
          if (result.ok) {
            markConnectionHealthy();
            acceptView(result.value, started);
          } else setConnectionError(result.error.message);
        }
      } catch (failure) { if (!cancelled && streamAtStart === streamVersion.current) setConnectionError(String(failure)); }
      if (!cancelled) timer = window.setTimeout(() => void poll(), 1500);
    }
    timer = window.setTimeout(() => void poll(), 1500);
    return () => { cancelled = true; window.clearTimeout(timer); };
  }, [host, workPollKey, acceptView, isCurrentSelection, markConnectionHealthy]);
  useEffect(() => { if (blogViewer) blogDialog.current?.showModal(); else blogDialog.current?.close(); }, [blogViewer]);
  useEffect(() => { if (management) managementDialog.current?.showModal(); else managementDialog.current?.close(); }, [management]);
  useEffect(() => { if (deleteConfirmation) confirmation.current?.showModal(); else confirmation.current?.close(); }, [deleteConfirmation]);
  useEffect(() => { if (view?.blog) setBlogs(view.blog); }, [view?.blog]);
  useEffect(() => {
    const running = Object.values(blogs).filter(blog => blog.runStatus === "running" || blog.executing).map(blog => blog.sourceId);
    if (running.length === 0 || !host.blogStatus) return;
    const timer = window.setInterval(() => running.forEach(id => void refreshBlog(id)), 1500);
    return () => window.clearInterval(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [blogs, host]);

  useEffect(() => { if (uploadOpen) uploadDialog.current?.showModal(); else uploadDialog.current?.close(); }, [uploadOpen]);

  async function operate(label: string, operation: () => Promise<ReaderHostResult<ReadingWindow>>, read = false) {
    if (locked.current || (active && !label.startsWith("停止") && label !== '全部清空')) return;
    locked.current = true; setBusy(label); setError(""); setRetryAction(null);
    const started = selection.current.generation;
    try {
      const result = await operation();
      if (!isCurrentSelection(started)) return;
      if (!result.ok) { setError(result.error.message); setRetryAction(() => () => void operate(label, operation, read)); return; }
      setRetryAction(null); acceptView(result.value, started, read || label === "删除"); setDeleteConfirmation(null);
      if (read) navigate("/reading");
      if (label === "上传") { setUploadOpen(false); setSelectedFiles([]); }
      await refresh();
    } catch (e) { if (isCurrentSelection(started)) { setError(String(e)); setRetryAction(() => () => void operate(label, operation, read)); } }
    finally { locked.current = false; setBusy(""); }
  }
  async function discuss(sourceId: string) {
    if (!host.selectDiscussionSource || locked.current || active) return;
    const started = changeSelection(sourceId);
    setError(""); setRetryAction(null);
    function failed(message: string) {
      if (!isCurrentSelection(started, sourceId)) return;
      if (viewRef.current?.source.sourceId !== sourceId) changeSelection(viewRef.current?.source.sourceId);
      setError(message);
      setRetryAction(() => () => void discuss(sourceId));
    }
    try {
      const result = await host.selectDiscussionSource(sourceId, undefined, { workbenchId, generation: started });
      if (!isCurrentSelection(started, sourceId)) return;
      if (!result.ok) { failed(result.error.message); return; }
      acceptView(result.value, started);
      if (viewRef.current?.source.sourceId === sourceId) navigate("/reading");
    } catch (failure) { failed(String(failure)); }
  }
  function preparationHidden(sourceId: string) {
    const prepared = view?.preparations?.[sourceId];
    return !!prepared?.dismissed || !!(prepared?.attempt && closingPreparations[sourceId] === prepared.attempt);
  }
  function preparationFailed(sourceId: string) {
    return hasPreparationFailure(view?.preparations?.[sourceId]);
  }
  async function dismissPreparation(sourceId: string) {
    const attempt = view?.preparations?.[sourceId]?.attempt;
    if (!attempt || !host.dismissPreparation) return;
    setClosingPreparations(old => ({ ...old, [sourceId]: attempt }));
    const started = selection.current.generation;
    const restore = () => setClosingPreparations(old => { if (old[sourceId] !== attempt) return old; const next = { ...old }; delete next[sourceId]; return next; });
    try {
      const result = await host.dismissPreparation(sourceId, attempt);
      if (result.ok) acceptView(result.value, started);
      else { restore(); if (isCurrentSelection(started)) setError(result.error.message); }
    } catch { restore(); if (isCurrentSelection(started)) setError("关闭提示未保存，请检查连接后再次关闭。"); }
  }
  async function retryPreparation(sourceId: string) {
    const prepared = view?.preparations?.[sourceId];
    if (prepared && ["failed", "cancelled", "interrupted"].includes(prepared.status) && host.resumePreparation) {
      await operate("准备阅读", () => identified(`resume:${sourceId}`, id => host.resumePreparation!(sourceId, id)));
    } else if (host.replanSource) {
      await operate("准备阅读", () => identified(`replan:${sourceId}`, id => host.replanSource!(sourceId, id)));
    }
  }
  function preparationNotice(sourceId: string) {
    const prepared = view?.preparations?.[sourceId];
    if (!prepared || prepared.ready || preparationHidden(sourceId)) return null;
    return <section className="preparation-notice" aria-label="准备阅读状态">
      <div className="preparation-notice-heading">
        <p role="status">{preparationText(prepared)}</p>
        {preparationFailed(sourceId) && prepared.attempt && host.dismissPreparation && <button className="preparation-dismiss" aria-label="关闭准备阅读提示" title="关闭这次状态提示" onClick={() => void dismissPreparation(sourceId)}>×</button>}
      </div>
      {preparationFailed(sourceId) && (host.resumePreparation || host.replanSource) && <button disabled={!!busy || active} onClick={() => void retryPreparation(sourceId)}>重试</button>}
    </section>;
  }
  async function enterReading(sourceId: string) {
    if (host.getSourceDocument && host.selectDiscussionSource) {
      await discuss(sourceId);
      return;
    }
    if (!host.openSource) return;
    const prepared = view?.preparations?.[sourceId];
    if (prepared && !prepared.selected_ready && preparationFailed(sourceId)) {
      await retryPreparation(sourceId);
      return;
    }
    await operate("阅读", () => identified(`open:${sourceId}`, id => host.openSource!(sourceId, id)), !!(prepared?.ready || prepared?.selected_ready));
  }
  async function activateCandidate(sourceId: string) {
    const preparation = view?.preparations?.[sourceId];
    if (!host.activateReadingCandidate || !preparation?.candidate || !preparation.ready ||
        !preparation.plan_id || view?.readingRevision === undefined) return;
    await operate("打开新计划", () => host.activateReadingCandidate!(sourceId, preparation.plan_id!,
      view.readingRevision!, createReaderId()), true);
  }
  function duplicateNotice(item: IngestionItem) {
    const published = !!item.sourceId && ["published", "reused"].includes(item.documentStatus);
    return `${item.fileName}：该原件已有未完成任务。${published ? "文档已入库，仍有后续步骤未完成" : "原件已上传，文档尚未入库"}；已恢复原任务，请在任务面板查看或重试。不会自动重复解析。`;
  }
  async function revealIngestion(items: readonly IngestionItem[]) {
    setNotice(items.map(duplicateNotice).join("\n"));
    setTaskDetails(true);
    setPendingTaskFocus(items.map(item => item.itemId));
    // A poll started before staging may still contain dismissal receipts.
    // Wait for it, then fetch the persisted restored projections.
    await refresh(true);
  }
  function replaceInbox(item: IngestionItem) { setInbox(current => [item, ...current.filter(existing => existing.itemId !== item.itemId)]); }
  async function ingest(label: string, operation: () => Promise<ReaderHostResult<IngestionItem>>, closeUpload = false) {
    if (locked.current) return;
    locked.current = true; setBusy(label); setError(""); setNotice(""); setRetryAction(null);
    try {
      const result = await operation();
      if (!result.ok) { setError(result.error.message); setRetryAction(() => () => void ingest(label, operation, closeUpload)); return; }
      setRetryAction(null); replaceInbox(result.value);
      if (result.value.duplicate) await revealIngestion([result.value]);
      if (closeUpload) { setUploadOpen(false); setSelectedFiles([]); }
    } catch (e) { setError(String(e)); setRetryAction(() => () => void ingest(label, operation, closeUpload)); }
    finally { locked.current = false; setBusy(""); }
  }
  async function refreshBlog(sourceId: string) {
    if (!host.blogStatus || blogRefreshing.current.has(sourceId)) return;
    blogRefreshing.current.add(sourceId);
    try { const result = await host.blogStatus(sourceId);
      if (result.ok) setBlogs(current => ({ ...current, [sourceId]: result.value }));
    } finally { blogRefreshing.current.delete(sourceId); }
  }
  async function blogAction(sourceId: string, operation: () => Promise<ReaderHostResult<BlogStatus>>) {
    setError(""); setRetryAction(null);
    try {
      const result = await operation();
      if (!result.ok) { setError(result.error.message); setRetryAction(() => () => void blogAction(sourceId, operation)); return; }
      setBlogs(current => ({ ...current, [sourceId]: result.value }));
    } catch (e) { setError(String(e)); setRetryAction(() => () => void blogAction(sourceId, operation)); }
  }
  async function generateBlog(sourceId: string) {
    if (!host.generateBlog) return;
    setBusy("生成博客");
    try { await blogAction(sourceId, () => identified(`blog:${sourceId}`, id => host.generateBlog!(sourceId, id))); }
    finally { setBusy(""); }
  }
  async function regenerateBlog(sourceId: string, artifact: BlogRegenerationTarget) {
    if (!host.regenerateBlog) return;
    setBusy(artifact === "all" ? "重新生成" : blogRetryLabel[artifact]);
    try { await blogAction(sourceId, () => identified(`blog:${sourceId}:${artifact}`, id => host.regenerateBlog!(sourceId, id, artifact))); }
    finally { setBusy(""); }
  }
  async function cancelBlog(sourceId: string) {
    if (!host.cancelBlog) return;
    setBusy("取消博客生成");
    try { await blogAction(sourceId, () => host.cancelBlog!(sourceId)); }
    finally { setBusy(""); }
  }
  async function confirmAndStart(item: IngestionItem) {
    if (!host.startBatch || locked.current) return;
    locked.current = true; setBusy("确认"); setError(""); setNotice("");
    try {
      const started = await identified(`start:${item.itemId}`, id => ingestionFormat(item.fileName) === "Markdown"
        ? host.startBatch!([item.itemId], id, false)
        : host.startBatch!([item.itemId], id));
      if (!started.ok) { setError(started.error.message); return; }
      await refresh();
    } catch (e) { setError(String(e)); }
    finally { locked.current = false; setBusy(""); }
  }
  const selectedTopic = topics.find(t => t.topicId === topic);
  const managementBusy = !!busy || !!view?.configuration?.busy || active || batches.some(b => b.executing || ["confirmed", "running"].includes(b.status)) || Object.values(blogs).some(b => b.executing || b.runStatus === "running");
  const sortingReason = sortingDisabledReason({ managementBusy, query, statusFilter, libraryView, canManage: !!host.manageTopic });
  const unfiledCount = sources.filter(s => s.topicIds.length === 0).length;
  const statusFor = (source: LibrarySource) => sourceStatus(source, view?.preparations?.[source.sourceId], preparationHidden(source.sourceId));
  const completedCount = (ids: readonly string[]) => sources.filter(s => ids.includes(s.sourceId) && statusFor(s).phase === "completed").length;
  const scoped = sources.filter(s => (!topic || (topic === UNFILED ? s.topicIds.length === 0 : s.topicIds.includes(topic))) &&
    [s.title, s.displayTitle, s.shortName].filter(Boolean).join(" ").toLowerCase().includes(query.toLowerCase()));
  const filtered = scoped.filter(s => matchesStatus(statusFor(s), statusFilter, blogs[s.sourceId]));
  if (selectedTopic) filtered.sort((a, b) => selectedTopic.sourceIds.indexOf(a.sourceId) - selectedTopic.sourceIds.indexOf(b.sourceId));
  function openManagement(kind: "create" | "rename" | "delete" | "source", id?: string, title = "") {
    const source = sources.find(s => s.sourceId === id);
    setManagement({ kind, id }); setManagementTitle(title);
    setManagementDisplayTitle(source?.displayTitle || source?.title || "");
    setManagementDisplayTitleEdited(Boolean(source?.displayTitle));
    setManagementTopics(source?.topicIds ?? []); setError("");
  }
  async function manage(operation: () => Promise<ReaderHostResult<unknown>>, close = true) {
    if (locked.current) return;
    locked.current = true; setBusy("更新知识库"); setError(""); setRetryAction(null);
    try {
      const result = await operation();
      if (!result.ok) { setError(result.error.message); setRetryAction(() => () => void manage(operation, close)); return; }
      setRetryAction(null); if (close) setManagement(null);
      await refresh();
    } catch (e) { setError(String(e)); setRetryAction(() => () => void manage(operation, close)); }
    finally { locked.current = false; setBusy(""); }
  }
  function saveManagement() {
    if (!management) return;
    const { kind, id } = management;
    if (kind === "create" && host.createTopic) void manage(() => host.createTopic!(managementTitle));
    if (kind === "rename" && id && host.manageTopic) void manage(() => host.manageTopic!(id, "rename", { title: managementTitle }));
    if (kind === "delete" && id && host.manageTopic) void manage(() => host.manageTopic!(id, "delete", {}));
    if (kind === "source" && id && host.saveSourceDetails) { const requestId = createReaderId(); void manage(() => host.saveSourceDetails!(id, managementTitle, managementTopics, requestId, managementDisplayTitle)); }
  }
  function moveSource(sourceId: string, offset: number) {
    if (!selectedTopic || !host.manageTopic || sortingReason) return;
    const ids = [...selectedTopic.sourceIds], index = ids.indexOf(sourceId), target = index + offset;
    if (index < 0 || target < 0 || target >= ids.length) return;
    [ids[index], ids[target]] = [ids[target], ids[index]];
    void manage(() => host.manageTopic!(selectedTopic.topicId, "reorder", { sourceIds: ids }));
  }

  async function reorderTopic(topicId: string, sourceIds: readonly string[]) {
    if (!selectedTopic || selectedTopic.topicId !== topicId || !host.manageTopic || sortingReason) return false;
    let succeeded = false;
    await manage(async () => { const result = await host.manageTopic!(topicId, "reorder", { sourceIds: [...sourceIds] }); succeeded = result.ok; return result; });
    return succeeded;
  }

  function requestReadingReset(sourceId: string, opener: HTMLElement) {
    const reset = host.resetSourceReading?.bind(host);
    if (!reset) return;
    const storageKey = `focus.resetReading:${view?.workspace?.workspaceId ?? "local"}:${sourceId}`;
    setResetConfirmation({
      title: "重新阅读本篇？",
      description: "将清除精读进度、旧计划、小段笔记、句子备注和重点。整篇笔记会保留，旧对话归档，并开启新对话。",
      label: "确认重新阅读",
      opener,
      confirm: () => void operate("重新阅读", () => identified(storageKey, async fallbackId => {
        let requestId = fallbackId;
        try {
          requestId = sessionStorage.getItem(storageKey) ?? fallbackId;
          sessionStorage.setItem(storageKey, requestId);
        } catch { /* The in-memory identity still covers retries. */ }
        const result = await reset(sourceId, requestId);
        if (result.ok) {
          try { sessionStorage.removeItem(storageKey); } catch { /* Storage is optional. */ }
        }
        return result;
      })),
    });
  }
  async function confirmDelete(source: LibrarySource) {
    if (!host.deletionImpact || managementBusy) return;
    setBusy("读取删除影响"); setError(""); setDeletionImpact(null);
    try {
      const result = await host.deletionImpact(source.sourceId);
      if (!result.ok) { setError(result.error.message); return; }
      setDeletionImpact(result.value); setDeleteConfirmation(source);
    } finally { setBusy(""); }
  }
  async function controlBatch(batchId: string, action: Parameters<NonNullable<ReaderHost["controlBatch"]>>[1], itemId?: string, riskChoiceId?: string) {
    if (!host.controlBatch || locked.current) return;
    locked.current = true; setBusy("更新批次"); setError(""); setRetryAction(null);
    try {
      const result = await identified(`batch:${batchId}:${action}:${itemId}`, id => host.controlBatch!(batchId, action, id, itemId, riskChoiceId));
      if (!result.ok) { setError(result.error.message); setRetryAction(() => () => void controlBatch(batchId, action, itemId, riskChoiceId)); return; }
      await refresh();
    } catch (e) { setError(String(e)); setRetryAction(() => () => void controlBatch(batchId, action, itemId, riskChoiceId)); }
    finally { locked.current = false; setBusy(""); }
  }
  const includesPdf = selectedFiles.some(file => ingestionFormat(file.name) === "PDF");
  const markdownOnly = selectedFiles.length > 0 && selectedFiles.every(file => ingestionFormat(file.name) === "Markdown");
  const generateUploadBlog = !markdownOnly && (includesPdf || generateOnUpload);
  async function uploadAndStart() {
    if (locked.current || !selectedFiles.length || !host.stageIngestion || !host.startBatch) return;
    const files = [...selectedFiles], topicTitle = uploadTopic.trim();
    locked.current = true; setBusy("开始处理"); setError(""); setNotice("");
    try {
      const ids: string[] = [];
      const duplicates: IngestionItem[] = [];
      const failures: {file: File; message: string}[] = [];
      for (const file of files) {
        const staged = await host.stageIngestion(file, { ...(topicTitle ? { topicTitle } : {}) });
        if (!staged.ok) { failures.push({ file, message: staged.error.message }); continue; }
        replaceInbox(staged.value);
        const unsubmitted = staged.value.status === "awaiting_confirmation" && !staged.value.topicId &&
          (staged.value.topicTitle ?? "") === topicTitle;
        if (staged.value.duplicate && !unsubmitted) {
          duplicates.push(staged.value);
          continue;
        }
        if (!ids.includes(staged.value.itemId)) ids.push(staged.value.itemId);
      }
      if (ids.length) {
        const started = await identified(`upload:${ids.join(",")}`, id => host.startBatch!(ids, id, generateUploadBlog));
        if (!started.ok) { setError(started.error.message); return; }
      }
      if (failures.length) {
        setSelectedFiles(failures.map(failure => failure.file));
        await refresh();
        setError(failures.map(({ file, message }) => file.name + "：" + message).join("；"));
        return;
      }
      setUploadOpen(false); setSelectedFiles([]);
      if (duplicates.length) await revealIngestion(duplicates);
      else await refresh(true);
    } catch (e) { setError(String(e)); }
    finally { locked.current = false; setBusy(""); }
  }
  function selectUploadFiles(selected: readonly File[]) {
    if (selected.some(file => !ingestionFormat(file.name))) {
      setError("请选择 PDF、SingleFile HTML 或 Markdown");
      return false;
    }
    setSelectedFiles(selected);
    setError("");
    return true;
  }
  function chooseUpload(selected: readonly File[] = []) {
    if (!selectUploadFiles(selected)) return;
    setUploadTopic(selectedTopic?.title ?? "");
    setGenerateOnUpload(true); setUploadOpen(true);
  }
  const uploadDisabled = !!busy || active || !host.stageIngestion || !host.startBatch;
  const batchStatusText = { confirmed: "待处理", running: "处理中", paused: "已暂停", completed: "完成", partial: "部分完成" };
  const itemStatusText = { queued: "待处理", processing: "处理中", completed: "完成", partial: "部分完成", failed: "失败", cancelled: "已取消", deleted: "来源已删除" };
  const statusText: Record<IngestionItem["status"], string> = {
    awaiting_confirmation: "待确认", confirmed: "已确认，等待开始", processing: "处理中", status_check_required: "远端状态待核对",
    retry_waiting: "等待继续", failed: "处理失败，可继续", commit_conflict: "提交冲突，可继续", topic_attachment_pending: "文档已入库，专题关联待恢复",
    cancelled: "已取消，可继续", interrupted: "处理曾中断，可继续", completed: "入库完成",
  };
  const resumableStatuses: readonly IngestionItem["status"][] = ["retry_waiting", "failed", "commit_conflict", "topic_attachment_pending", "cancelled", "interrupted"];
  function continueInbox(item: IngestionItem) { if (host.continueIngestion) void ingest("继续", () => host.continueIngestion!(item.itemId, createReaderId())); }
  const work = (view?.workItems ?? []).filter(item => !item.dismissed && (item.kind !== "preparation" || !preparationHidden(item.targetId)));
  const uploadBatches = view?.taskBatches ?? batches;
  const taskBatches = uploadBatches.filter(batch => !batch.dismissed).map(batch => ({ ...batch,
    items: batch.items.filter(item => !item.dismissed && item.status !== "completed" && item.status !== "deleted"),
  })).filter(batch => batch.items.length > 0);
  const taskInbox = (view?.taskInbox ?? inbox).filter(item => !item.dismissed && item.status !== "completed" &&
    (view?.taskInbox !== undefined || !uploadBatches.some(batch => batch.items.some(entry => entry.itemId === item.itemId))));
  const taskWork = work.filter(item => {
    if (item.kind === "batch") return false;
    if (item.kind !== "ingestion") return true;
    return view?.taskInbox === undefined && !inbox.some(entry => entry.itemId === item.targetId) &&
      !uploadBatches.some(batch => batch.items.some(entry => entry.itemId === item.targetId));
  });
  useEffect(() => {
    if (!pendingTaskFocus || !taskDetails || uploadOpen || busy) return;
    const rows = Array.from(taskFrame.current?.querySelectorAll<HTMLElement>("[data-task-item-id]") ?? [])
      .filter(row => pendingTaskFocus.includes(row.dataset.taskItemId!));
    if (!rows.length) return;
    for (const row of rows) { const batch = row.closest("details"); if (batch) batch.open = true; }
    const row = rows[0];
    row.scrollIntoView({ block: "nearest" });
    (row.querySelector<HTMLElement>("[data-task-retry]:not(:disabled), button:not(:disabled)") ?? row).focus({ preventScroll: true });
    setPendingTaskFocus(null);
  }, [pendingTaskFocus, taskDetails, uploadOpen, busy, view?.taskInbox, view?.taskBatches, inbox, batches]);

  async function clearStatuses() {
    const tokens = view?.clearableStatusTokens;
    if (!host.clearFinishedStatuses || locked.current || !tokens?.length) return;
    const requestId = createReaderId();
    await operate('全部清空', () => host.clearFinishedStatuses!(requestId, tokens));
  }
  const runningWork = work.filter(w => w.phase === "running" || w.phase === "approval");
  const attention = work.filter(w => w.phase === "needs_action" || w.phase === "error");
  const primaryWork = runningWork.find(w => w.phase === "approval") ?? runningWork.find(w => w.kind === "ingestion") ?? runningWork[0];
  const workLabel = (item: (typeof work)[number]) => item.sourceTitle ? `${item.label} · ${item.sourceTitle}` : item.label;
  async function stopWork(item: (typeof work)[number]) {
    if (item.kind === "chat" && host.stop) await operate("停止问答", () => host.stop!());
    if (item.kind === "preparation" && host.cancelPreparation) await operate("取消准备", () => host.cancelPreparation!(item.targetId));
    if (item.kind === "progress" && host.cancelReadingProgress) await operate("停止补记", () => host.cancelReadingProgress!(item.targetId));
    if (item.kind === "blog") await cancelBlog(item.targetId);
    if (item.kind === "ingestion") {
      const batch = batches.find(b => b.items.some(i => i.itemId === item.targetId));
      if (batch) await controlBatch(batch.batchId, "cancel-item", item.targetId);
      else if (host.cancelIngestion) await ingest("取消解析", () => host.cancelIngestion!(item.targetId));
    }
  }
  async function retryOpening(sourceId: string) {
    if (!host.getSourceOpening) return;
    await operate("生成开篇导读", async () => {
      const result = await host.getSourceOpening!(sourceId, true);
      return result.ok ? host.getReadingWindow() : result;
    });
  }
  useEffect(() => {
    if (!readingFullscreen) return;
    const exit = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !event.defaultPrevented && !event.isComposing && event.keyCode !== 229 &&
          !document.querySelector("dialog[open]")) setReadingFullscreen(false);
    };
    window.addEventListener("keydown", exit);
    return () => window.removeEventListener("keydown", exit);
  }, [readingFullscreen]);
  useEffect(() => { if (route !== "/reading") setReadingFullscreen(false); }, [route]);
  const readingResetAction = route === "/reading" && view?.source.sourceId && host.resetSourceReading &&
    <button type="button" className={`workspace-task-toggle${readingFullscreen ? " reading-reset-fullscreen" : ""}`}
      disabled={!!busy || active || view.clearBusySources?.includes(view.source.sourceId)}
      onClick={event => requestReadingReset(view.source.sourceId, event.currentTarget)}>重新阅读</button>;
  return <div className="workspace-app" data-route={route} data-nav-collapsed={navCollapsed} data-reading-fullscreen={route === "/reading" && readingFullscreen} style={{ "--reader-body-font": readingFontFamily(readingFont) } as CSSProperties}>
    <NavigationResize enabled={!navCollapsed && !(route === "/reading" && readingFullscreen)} />
    <aside id="workspace-navigation" className="workspace-nav" aria-label="工作台导航">
      <div className="workspace-nav__head">
        <a className="workspace-logo" href="/library" onClick={e => { e.preventDefault(); navigate("/library"); }}>focus<span>.</span></a>
        <button type="button" className="workspace-nav-toggle" aria-label={navCollapsed ? "展开导航" : "收起导航"} aria-expanded={!navCollapsed} aria-controls="workspace-routes" onClick={() => { setNavCollapsed(!navCollapsed); try { localStorage.setItem("focus.navigation", navCollapsed ? "expanded" : "collapsed"); } catch { /* Navigation remains usable without persistence. */ } }}><span aria-hidden="true">☰</span></button>
      </div>
      <nav id="workspace-routes" aria-label="应用导航">{([
        ["/library", "知识库", <svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><rect x="2.5" y="2.5" width="4.5" height="11" rx="1"/><rect x="9" y="2.5" width="4.5" height="11" rx="1"/></svg>],
        ["/reading", "阅读", <BookOpen />],
        ["/settings", "设置", <svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><circle cx="8" cy="8" r="2.2"/><path d="M8 2.2v1.5M8 12.3v1.5M2.2 8h1.5M12.3 8h1.5M3.9 3.9l1.1 1.1M11 11l1.1 1.1M12.1 3.9 11 5M5 11l-1.1 1.1"/></svg>],
      ] as const).map(([path, title, icon]) =>
        <Fragment key={path}>
          <a href={path} aria-label={title} title={navCollapsed ? title : undefined} aria-current={route === path ? "page" : undefined}
            data-branch-active={path === "/reading" && route === "/reading" && readingBranchOpen && !!host.getSourceDocument ? "true" : undefined}
            onClick={e => { e.preventDefault(); if (path === "/reading") setReadingBranchOpen(true); navigate(path); }}>
            <span className="workspace-nav-icon" aria-hidden="true">{icon}</span><span className="workspace-nav-label">{title}</span>
          </a>
          {path === "/reading" && route === path && host.getSourceDocument && <div className="reading-branch" data-open={readingBranchOpen}>
            <button type="button" className="reading-branch-toggle" aria-label={readingBranchOpen ? "折叠阅读方式" : "展开阅读方式"}
              aria-expanded={readingBranchOpen} aria-controls="reading-children" onClick={() => setReadingBranchOpen(!readingBranchOpen)}>
              <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="m4 6 4 4 4-4" /></svg>
            </button>
            <div className="reading-branch-collapse" data-open={readingBranchOpen}>
              <div id="reading-children" ref={setBranchSlot} inert={!readingBranchOpen} aria-hidden={!readingBranchOpen} role="group" aria-label="阅读方式" />
            </div>
          </div>}
        </Fragment>)}</nav>
      {route === "/library" && <div className="workspace-topics" role="group" aria-label="专题">
        <h2>专题</h2>
        <button type="button" className="workspace-topics__new" disabled={managementBusy || !host.createTopic} onClick={() => openManagement("create")}>＋ 新建专题</button>
        <button type="button" aria-pressed={!topic} onClick={() => setTopic("")}>全部 <span>{sources.length}</span></button>
        {topics.map(t => <button type="button" key={t.topicId} aria-pressed={topic === t.topicId} onClick={() => setTopic(t.topicId)} title={`已读完 ${completedCount(t.sourceIds)} / ${t.sourceIds.length} 篇`}>{t.title}<span>{completedCount(t.sourceIds)}/{t.sourceIds.length}</span></button>)}
        {unfiledCount > 0 && <button type="button" aria-pressed={topic === UNFILED} onClick={() => setTopic(UNFILED)}>未归类<span>{unfiledCount}</span></button>}
      </div>}
    </aside>
    <header className="workspace-header">
      <div className={route === "/library" ? "workspace-toolbar library-toolbar" : "workspace-toolbar"}>
        {route === "/reading" ? <div className="reading-library-picker"><div className="reading-mode-picker" data-branch-open={readingBranchOpen} ref={setPickerSlot} /><span className="workspace-reading-title" title={view?.source.title}>{view?.source.title || "阅读"}</span></div> : route === "/library" ? <LibraryToolbar {...{ selectedTopic, topic, filtered, topics, unfiledCount, setTopic, libraryView, setLibraryView, setMoreSource, query, setQuery }} /> : <h1>设置</h1>}
        <div className="workspace-header-actions">
          {!readingFullscreen && readingResetAction}
          <section className="workspace-status" aria-label="当前工作">
            <span className="workspace-sr-only" role="status">{connectionLost ? "连接中断，正在恢复" : !view ? "正在连接" : primaryWork ? `${workLabel(primaryWork)} · ${runningWork.length} 项进行中` : attention.length ? `${attention.length} 项需查看` : "当前无工作"}{primaryWork && attention.length > 0 ? ` · ${attention.length} 项需查看` : ""}</span>
            <button className="workspace-task-toggle" aria-label="任务详情" aria-controls="workspace-tasks" aria-expanded={taskDetails} onClick={() => setTaskDetails(!taskDetails)}>
              <span className="workspace-status-dot" data-active={runningWork.length > 0} data-attention={connectionLost || attention.length > 0} aria-hidden="true" />
              <span>{connectionLost ? "连接中断" : !view ? "连接中" : runningWork.length ? `${runningWork.length} 项进行中` : attention.length ? `${attention.length} 项需查看` : "任务"}</span>
              <svg className="workspace-chevron" aria-hidden="true" width="16" height="16" viewBox="0 0 16 16"><path d="m4 6 4 4 4-4" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" /></svg>
            </button>
          </section>
          {route === "/library" && <button className="workspace-primary" disabled={uploadDisabled} onClick={() => chooseUpload()}>上传</button>}
        </div>
      </div>
      {(taskDetails || taskVisited) && <div ref={taskFrame} className="workspace-task-frame" id="workspace-tasks" role="region" aria-label="任务框" data-open={taskDetails} aria-hidden={!taskDetails} inert={!taskDetails} onKeyDown={event => { if (event.key === "Escape") { event.stopPropagation(); setTaskDetails(false); document.querySelector<HTMLButtonElement>(".workspace-task-toggle")?.focus(); } }}>
        <div className="workspace-task-actions"><span>任务状态</span><button disabled={!!busy || !host.clearFinishedStatuses || !view?.clearableStatusTokens?.length} onClick={() => void clearStatuses()}>全部清空</button></div>
        <small>清空已结束的失败提示，保留仍需操作的任务。</small>
        {taskWork.length === 0 && taskBatches.length === 0 && taskInbox.length === 0 && <p>没有进行中或待处理的任务。</p>}
        {taskWork.map(item => <div key={item.id}><span>{workLabel(item)}{item.kind === "preparation" && preparationFailed(item.targetId) ? "" : ` · ${{ running: "进行中", approval: "待确认", needs_action: "待处理", error: "待查看" }[item.phase]}`}</span>
          {item.stage && <small>{item.kind === "preparation" ? preparationStepText(item.stage) : item.kind === "blog" ? (item.stage === "html" ? "生成 HTML" : "生成带读博客") : item.stage}</small>}
          {typeof item.percent === "number" && <progress aria-label={workLabel(item)} max={100} value={item.percent} />}
          {item.error && (item.kind !== "preparation" || !view?.preparations?.[item.targetId]) && <p role="alert">{item.error}</p>}
          {item.cancellable && item.phase !== "approval" && <button disabled={!!busy} onClick={() => void stopWork(item)}>{item.kind === "preparation" ? "取消准备" : "停止此任务"}</button>}
          {item.kind === "preparation" && preparationFailed(item.targetId) && preparationNotice(item.targetId)}
          {item.retryable && item.kind === "progress" && host.retryReadingProgress && <button disabled={!!busy} onClick={() => void operate("补记", () => identified(`progress:${item.targetId}`, id => host.retryReadingProgress!(item.targetId, id)))}>补记</button>}
          {item.retryable && item.kind === "opening" && host.getSourceOpening && <button disabled={!!busy} onClick={() => void retryOpening(item.targetId)}>重试导读</button>}
          {item.retryable && (item.kind === "ingestion" || item.kind === "blog") && <button onClick={() => navigate("/library")}>查看并恢复</button>}
          {item.retryable && item.kind === "chat" && <button onClick={() => item.sourceId ? void enterReading(item.sourceId) : navigate("/reading")}>查看并重新提问</button>}
        </div>)}
      {taskBatches.length > 0 && <section className="library-inbox" aria-label="处理任务"><h2>上传任务</h2>{taskBatches.map(batch => <details key={batch.batchId}><summary>当前任务 / 待处理</summary><article>
        <h3>{topics.find(t => t.topicId === batch.topicId)?.title ?? batch.topicId ?? '未关联专题'} · {batchStatusText[batch.status]}</h3>
        {["confirmed", "running"].includes(batch.status) && <button disabled={!!busy || !host.controlBatch} onClick={() => void controlBatch(batch.batchId, "stop")}>停止整批</button>}
        {["paused", "partial"].includes(batch.status) && <button disabled={!!busy || batch.executing || !host.controlBatch} onClick={() => void controlBatch(batch.batchId, "continue")}>继续剩余工作</button>}
        {batch.error && <p role="status">{batch.error.message}</p>}
        {batch.items.map(item => <div className="library-inbox-item" data-task-item-id={item.itemId} tabIndex={-1} data-status={item.ingestionStatus === "failed" ? "failed" : item.status} key={item.itemId}>
          <strong>{item.fileName}</strong><span>{itemStatusText[item.status]}</span>{item.sourceTitle && <small>{item.sourceTitle}</small>}
          <small>{item.status === "deleted" ? "原处理授权已失效" : item.ingestionStatus === "completed" ? "解析完成" : "解析：" + (statusText[item.ingestionStatus as IngestionItem["status"]] ?? "待处理")}{item.blog ? " · 博客：" + ({ running: "生成中", completed: "已完成", failed: "失败", cancelled: "已取消", interrupted: "已中断" }[item.blog.runStatus ?? ""] ?? "待生成") : ""}</small>
          {item.parserBackend && <small>{item.parserBackend === "local-mineru" ? "本地 MinerU" : "远端 MinerU API"}{item.selectionReason ? ` · ${item.selectionReason}` : ""}{item.parserProgress?.status ? ` · ${item.parserProgress.status === "queued" ? "排队中" : "解析中"}` : ""}{typeof item.parserProgress?.percent === "number" ? ` · ${Math.round(item.parserProgress.percent)}%` : ""}</small>}
          {item.error && <p>{item.error.message}</p>}
          {item.status === "processing" && <button disabled={!!busy || !host.controlBatch} onClick={() => void controlBatch(batch.batchId, "cancel-item", item.itemId)}>取消此项</button>}
          {item.status === "queued" && <button disabled={!!busy || !host.controlBatch} onClick={() => void controlBatch(batch.batchId, "remove-item", item.itemId)}>移出队列</button>}
          {["failed", "partial", "cancelled"].includes(item.status) && !item.resubmitRisk && <button data-task-retry disabled={!!busy || batch.executing || !host.controlBatch} onClick={() => void controlBatch(batch.batchId, "retry-item", item.itemId)}>重试未完成步骤</button>}
          {item.resubmitRisk && <div><p>上次提交结果未知，重新提交可能重复解析。</p>
            {item.remoteReference && <button disabled={!!busy || batch.executing || !host.controlBatch} onClick={() => void controlBatch(batch.batchId, "retry-item", item.itemId)}>查询并续接原任务</button>}
            <button disabled={!!busy || batch.executing || !host.controlBatch} onClick={() => void controlBatch(batch.batchId, "resubmit-item", item.itemId, item.resubmitRisk!.choice_id)}>重新提交</button>
          </div>}
          {item.sourceId && <div className="inbox-links">{host.sourceOriginalUrl && <a href={host.sourceOriginalUrl(item.sourceId)} target="_blank" rel="noreferrer">原件</a>}{host.sourceContentUrl && <a href={host.sourceContentUrl(item.sourceId)} target="_blank" rel="noreferrer">正文</a>}</div>}
        </div>)}
      </article></details>)}</section>}
      {taskInbox.length > 0 && <section className="library-inbox" aria-label="Inbox"><div className="library-inbox-heading"><h2>单项上传</h2><button disabled={!!busy} onClick={() => void refresh()}>刷新状态</button></div>{taskInbox.map(item => <article key={item.itemId} className="library-inbox-item" data-task-item-id={item.itemId} tabIndex={-1} data-status={item.status}>
        <div><strong>{item.fileName}</strong><span>{statusText[item.status]}</span>{item.sourceTitle && <small>{item.sourceTitle}</small>}<small>{item.topicTitle ?? topics.find(t => t.topicId === item.topicId)?.title ?? "不关联专题"}</small></div>
        {item.parserBackend && <p role="status">{item.parserBackend === "local-mineru" ? "本地 MinerU" : "远端 MinerU API"}{item.selectionReason ? ` · ${item.selectionReason}` : ""}{item.parserProgress?.status ? ` · ${item.parserProgress.status === "queued" ? "排队中" : item.parserProgress.status === "running" ? "解析中" : item.parserProgress.status}` : ""}{typeof item.parserProgress?.percent === "number" ? ` · ${Math.round(item.parserProgress.percent)}%` : ""}</p>}
        {item.status === "awaiting_confirmation" && <div className="inbox-confirmation"><p>PDF 由服务器自动选择本地 MinerU 或远端 MinerU API。HTML 和 Markdown 在本地解析。</p>
          <button className="workspace-primary" disabled={!!busy} onClick={() => void confirmAndStart(item)}>{ingestionFormat(item.fileName) === "Markdown" ? "仅解析入库" : "开始解析并生成博客"}</button></div>}
        {item.status === "processing" && <button disabled={!!busy || !host.cancelIngestion} onClick={() => host.cancelIngestion && void ingest("取消", () => host.cancelIngestion!(item.itemId))}>取消</button>}
        {(item.status === "status_check_required" || (item.status === "cancelled" && item.resubmitRisk)) && <div className="inbox-confirmation inbox-resubmission">
          <p>上次提交结果未知，重新提交可能重复解析。</p>
          <div className="inbox-resubmission-actions">
            {item.remoteReference && <button disabled={!!busy || !host.continueIngestion} onClick={() => host.continueIngestion && void ingest("查询", () => host.continueIngestion!(item.itemId, createReaderId()))}>查询并续接原任务</button>}
            <button className="workspace-primary" disabled={!!busy || !host.resubmitIngestion || !item.resubmitRisk} onClick={() => host.resubmitIngestion && item.resubmitRisk && void ingest("重新提交", () => host.resubmitIngestion!(item.itemId, createReaderId(), item.resubmitRisk!.choiceId))}>重新提交</button>
          </div>
        </div>}
        {["retry_waiting", "failed", "commit_conflict", "topic_attachment_pending", "interrupted"].includes(item.status) && <button data-task-retry disabled={!!busy || !host.continueIngestion} onClick={() => continueInbox(item)}>{item.status === "failed" ? "重试解析" : "继续"}</button>}
        {item.status === "cancelled" && !item.resubmitRisk && <button data-task-retry disabled={!!busy || !host.continueIngestion} onClick={() => continueInbox(item)}>继续</button>}
        {["status_check_required", ...resumableStatuses].includes(item.status) && <button disabled={!!busy || !host.confirmIngestion || !host.processIngestion} onClick={() => void confirmAndStart(item)}>重新确认并开始</button>}
        {item.sourceId && <div className="inbox-links">{host.sourceOriginalUrl && <a href={host.sourceOriginalUrl(item.sourceId)} target="_blank" rel="noreferrer">原件</a>}{host.sourceContentUrl && <a href={host.sourceContentUrl(item.sourceId)} target="_blank" rel="noreferrer">正文</a>}</div>}
        {(item.error || item.topicError) && <p className="inbox-error">{item.topicError?.message ?? item.error?.message}</p>}
      </article>)}</section>}
      {managementBusy && <p role="status">部分操作暂不可用：当前任务正在使用材料。可在任务详情停止对应任务后重试。</p>}
      </div>}
      {approval && <div className="workspace-approval">
        <AgentControls agent={approval} showStop={!!host.stop} onStop={() => host.stop && void host.stop().then(result => { if (result.ok) acceptView(result.value); })} onAnswer={async input => {
        const result = await host.approve?.(input); if (result?.ok) { acceptView(result.value); return true; } return false;
      }} /></div>}
      {connectionError && <div className="workspace-error" role="alert">{connectionError}</div>}
      {route === "/library" && libraryError && <div className="workspace-error" role="alert">{libraryError}<button onClick={() => void refresh()}>刷新列表</button></div>}
      {!uploadOpen && error && <div className="workspace-error" role="alert">{error}<button onClick={() => { setError(""); if (retryAction) retryAction(); else void refresh(); }}>{retryAction ? "重试此操作" : "刷新状态"}</button></div>}
      {!error && notice && <div className="workspace-notice" role="status">{notice}<button onClick={() => setNotice("")}>关闭</button></div>}
    </header>
    {readingFullscreen && readingResetAction}
    {route === "/reading" && readingFullscreen && <button type="button" className="reading-fullscreen-exit"
      aria-label="关闭全屏模式" title="退出全屏" onClick={() => setReadingFullscreen(false)}>×</button>}
    <div className="workspace-reading" hidden={route !== "/reading"}>
      <FocusReader
        renderModeNavigation={(mode, select, disabled) => <>
          {branchSlot && createPortal(([
            ["chunks", "精读", <BookOpen />],
            ["chat", "对话", <ChatBubble />],
            ...(host.blogUrl ? [["blog", "带读博客", <DocText />] as const] : []),
          ] as readonly (readonly [ReadingMode, string, ReactNode])[]).map(([value, label, icon]) =>
            <button type="button" key={value} className="reading-branch-item" aria-pressed={mode === value} disabled={disabled}
              onClick={() => select(value)}>
              <span className="reading-branch-item__icon" aria-hidden="true">{icon}</span>
              <span>{label}</span>
            </button>), branchSlot)}
          {pickerSlot && createPortal(<select aria-label="阅读方式" value={mode} disabled={disabled}
            onChange={event => { const v = event.target.value; select(v === "chunks" || v === "blog" ? v : "chat"); }}>
            <option value="chunks">精读</option>
            <option value="chat">对话</option>
            {host.blogUrl && <option value="blog">带读博客</option>}
          </select>, pickerSlot)}
        </>}
        renderBlog={host.blogUrl ? (blogSourceId) => {
          const blog = blogs[blogSourceId];
          const htmlReady = blog?.artifacts?.html?.status === "completed";
          const isRunning = blog?.runStatus === "running" || blog?.executing;
          const isFailed = blog?.runStatus === "failed" || blog?.runStatus === "interrupted" || blog?.runStatus === "cancelled";
          if (htmlReady) {
            return <div className="reading-blog-view">
              <div className="reading-blog-floating">
                <a href={host.blogUrl!(blogSourceId)} target="_blank" rel="noreferrer" title="在新窗口打开带读博客">新窗口打开 ↗</a>
              </div>
              <iframe className="reading-blog-frame" title="带读博客阅读" src={host.blogUrl!(blogSourceId)} />
            </div>;
          }
          return <div className="reading-blog-empty">
            <div className="reading-blog-empty__card">
              <h2>带读博客</h2>
              <p>{isRunning ? "正在生成带读博客，完成后将自动在此呈现。" : isFailed ? (blog?.error?.message || "带读博客生成未完成，可重新生成。") : "为这篇文章生成以问题为线索的深度带读长文，方便系统理解核心方法与脉络。"}</p>
              <div className="reading-blog-empty__actions">
                {isRunning
                  ? (host.cancelBlog && <button type="button" disabled={!!busy} onClick={() => void cancelBlog(blogSourceId)}>取消生成</button>)
                  : (host.generateBlog && <button type="button" className="workspace-primary" disabled={!!busy || managementBusy} onClick={() => void (isFailed && host.regenerateBlog ? regenerateBlog(blogSourceId, "all") : generateBlog(blogSourceId))}>{isFailed ? "重新生成带读博客" : "生成带读博客"}</button>)}
              </div>
            </div>
          </div>;
        } : undefined}
        host={host} approvalManaged appearance="mist" fontSize={fontSize} visible={route === "/reading"}
        evidenceNavigation={unifiedReading ? evidenceNavigation : undefined}
        readingSession={{
          view: !unifiedReading || view?.source.sourceId === selection.current.sourceId ? view : null,
          generation, isCurrent: isCurrentSelection, accept: acceptView,
        }} fullscreen={readingFullscreen} onFullscreenChange={setReadingFullscreen} /></div>
    {route === "/library" && <LibraryPage {...{ scoped, statusFilter, setStatusFilter, sourcesFailed, refresh, statusFor, taskInbox, taskBatches, statusText, itemStatusText, continueInbox, controlBatch, sources, unfiledCount, sortingReason, reorderTopic, dragging, setDragging, uploadDisabled, chooseUpload, selectedTopic, managementBusy, host, openManagement, topics, topic, filtered, libraryView, setLibraryView, query, setQuery, setTopic, loading, view, preparationHidden, blogs, setBlogViewer, busy, active, enterReading, preparationFailed, retryPreparation, refreshBlog, moreSource, setMoreSource, moveSource, requestReadingReset, confirmDelete, preparationNotice, activateCandidate, blogArtifacts, blogStatusText, generateBlog, cancelBlog, regenerateBlog, blogRetryLabel }} onTasks={() => setTaskDetails(true)} />}
    {route === "/settings" && <main className="settings-page">
      <div className="settings-shell">
        <nav className="settings-toc" aria-label="设置分组">
          <a href="#settings-appearance">外观与阅读</a>
          <a href="#settings-backend">模型与后端</a>
          <a href="#settings-workspace">工作区</a>
        </nav>
        <div className="settings-sections">
          <section id="settings-appearance" className="focus-reader__appearance-panel" aria-label="外观与阅读">
            <div className="settings-section-head">
              <div>
                <h2>外观与阅读</h2>
                <p className="appearance-hint">所有外观调整实时生效并自动保存至本机浏览器。</p>
              </div>
              {appearanceFeedback && <span className="settings-saved-pill" role="status">{appearanceFeedback}</span>}
            </div>
            <div className="settings-appearance-grid">
              <div className="settings-appearance-controls">
                <div className="settings-row"><label htmlFor="focus-theme">主题</label><select id="focus-theme" value={theme} onChange={e => setTheme(e.target.value as Theme)}><option value="system">跟随系统</option><option value="light">浅色</option><option value="dark">深色</option></select></div>
                <div className="settings-row"><label htmlFor="focus-density">界面密度</label><select id="focus-density" value={density} onChange={e => setDensity(e.target.value as Density)}><option value="compact">紧凑</option><option value="comfortable">舒适</option></select></div>
                <div className="settings-row"><label htmlFor="font-size">字号</label><input id="font-size" type="range" min="0" max="3" step="1" value={fontOptions.findIndex(([key]) => key === fontSize)} aria-valuetext={fontOptions.find(([key]) => key === fontSize)?.[1]} onChange={e => { const value = fontOptions[Number(e.target.value)][0]; setFontSize(value); }} /><output htmlFor="font-size">{readingFontSizes[fontSize]}px</output></div>
                <div className="settings-row"><label htmlFor="reading-font">正文字体</label><select id="reading-font" value={readingFont} onChange={e => setReadingFont(e.target.value as ReadingFont)}>
                  {readingFonts.map(font => <option key={font.id} value={font.id}>{font.label}</option>)}
                </select></div>
                <div className="settings-row"><label htmlFor="focus-reduced-motion">低动态模式</label><input id="focus-reduced-motion" type="checkbox" checked={reducedMotion} onChange={e => setReducedMotion(e.target.checked)} /></div>
              </div>
              <div className="settings-font-preview" aria-label="阅读字体预览" style={{ fontSize: `${readingFontSizes[fontSize]}px` }}>
                <span className="settings-preview-badge">实时预览</span>
                <p>阅读让我们看见问题的来处，也理解方法成立的原因。保留疑问，沿着证据继续探索。</p>
                <p lang="en">Reading brings ideas into focus. Follow the evidence, ask clear questions, and keep exploring.</p>
                <p><strong>重要结论</strong> · Focus 2026 · 0123456789</p>
              </div>
            </div>
            <details className="settings-font-licenses"><summary>字体许可</summary>
              <p><a href="/fonts/SourceHanSerif-LICENSE.txt" target="_blank" rel="noreferrer">思源宋体</a> · <a href="/fonts/SourceHanSans-LICENSE.txt" target="_blank" rel="noreferrer">思源黑体</a> · <a href="/fonts/NeoZhiSong-IPA-LICENSE.txt" target="_blank" rel="noreferrer">新致宋屏幕阅读版</a></p>
              <p>新致宋可恢复为 IPA 原始字体：从 <a href="https://moji.or.jp/ipafont/ipafontdownload/" target="_blank" rel="noreferrer">IPA 官方下载页</a>下载并安装 IPAex 明朝，重启浏览器后选择“新致宋屏幕阅读版”，将优先使用本机 IPAexMincho（或 IPAmjMincho）。卸载原始字体后恢复使用内置屏幕阅读版。</p>
            </details>
          </section>
          <div id="settings-backend">
            <BackendSetupPanel host={host} configuration={view?.configuration} onSaved={acceptView} />
          </div>
          <div id="settings-workspace">
            <WorkspaceSelection />
          </div>
        </div>
      </div>
    </main>}
    <dialog className="workspace-confirm" ref={managementDialog} onCancel={() => setManagement(null)}>
      <form onSubmit={e => { e.preventDefault(); saveManagement(); }}>
        <h2>{management?.kind === "source" ? "管理来源" : management?.kind === "delete" ? "删除专题" : management?.kind === "rename" ? "重命名专题" : "新建专题"}</h2>
        {management?.kind === "delete" ? <p>删除“{managementTitle}”专题。全部来源、博客、笔记和阅读进度会保留。</p> : <>
          {management?.kind === "source" && <label>知识库显示标题<input aria-label="知识库显示标题" required maxLength={240}
            value={managementDisplayTitle} onChange={e => { setManagementDisplayTitle(e.target.value); setManagementDisplayTitleEdited(true); }} /></label>}
          <label>{management?.kind === "source" ? "来源原题" : "专题名称"}<input aria-label={management?.kind === "source" ? "来源原题" : "专题名称"} required maxLength={management?.kind === "source" ? 1000 : 120} value={managementTitle}
            onChange={e => { setManagementTitle(e.target.value); if (management?.kind === "source" && !managementDisplayTitleEdited) setManagementDisplayTitle(e.target.value); }} /></label>
          </>}
        {management?.kind === "source" && <fieldset><legend>所属专题</legend>{topics.map(t => <label key={t.topicId}><input type="checkbox" checked={managementTopics.includes(t.topicId)} disabled={managementBusy || !host.saveSourceDetails} onChange={e => { const checked = e.target.checked; setManagementTopics(old => checked ? [...old, t.topicId] : old.filter(id => id !== t.topicId)); }} />{t.title}</label>)}</fieldset>}
        {management?.kind === 'source' && <button type="button" disabled={managementBusy || !managementTopics.length} onClick={() => setManagementTopics([])}>不关联专题</button>}
        {error && <p role="alert">{error}</p>}
        <button type="button" disabled={!!busy} onClick={() => setManagement(null)}>取消</button>
        <button type="submit" disabled={managementBusy || (management?.kind !== "delete" && (!managementTitle.trim() || (management?.kind === "source" && !managementDisplayTitle.trim())))}>{management?.kind === "delete" ? "确认删除专题" : "保存"}</button>
      </form>
    </dialog>
    <dialog className="workspace-confirm workspace-upload" ref={uploadDialog} onCancel={() => setUploadOpen(false)}>
      <form onSubmit={e => { e.preventDefault(); void uploadAndStart(); }}>
        <h2>上传材料</h2>
        <UploadTopicPicker topics={topics} value={uploadTopic} onChange={setUploadTopic} disabled={!!busy} />
        {!includesPdf && !markdownOnly && <label className="upload-parse-only"><input type="checkbox" disabled={!!busy} checked={!generateOnUpload} onChange={e => setGenerateOnUpload(!e.target.checked)} />仅解析入库</label>}
        <label className="upload-file">{selectedFiles.map(f => f.name).join("、") || "PDF / HTML / Markdown"}<input aria-label="上传材料" type="file" multiple disabled={!!busy} accept=".pdf,.html,.md,.markdown,application/pdf,text/html,text/markdown" onChange={e => selectUploadFiles(Array.from(e.target.files ?? []))} /></label>
        {error && <p role="alert">{error}</p>}
        <div className="upload-actions"><button type="button" disabled={!!busy} onClick={() => setUploadOpen(false)}>取消</button><button type="submit" className="workspace-primary" disabled={uploadDisabled || !selectedFiles.length}>{busy ? "开始中…" : includesPdf ? "上传并准备阅读" : generateUploadBlog ? "开始解析并生成博客" : "仅解析入库"}</button></div>
      </form>
    </dialog>
    {blogViewer && host.blogUrl && <dialog className="workspace-blog-viewer" ref={blogDialog} aria-labelledby="blog-viewer-title" onCancel={e => { e.preventDefault(); closeBlogViewer(); }}>
      <div className="blog-viewer-head"><h2 id="blog-viewer-title">博客：{sources.find(s => s.sourceId === blogViewer)?.displayTitle || sources.find(s => s.sourceId === blogViewer)?.title}</h2>
        <div><a href={host.blogUrl(blogViewer)} target="_blank" rel="noreferrer">新窗口打开</a><button onClick={closeBlogViewer}>关闭</button></div></div>
      <iframe title="博客" src={host.blogUrl(blogViewer)} />
    </dialog>}
    {resetConfirmation && <ReaderConfirmation input={resetConfirmation} onClose={() => setResetConfirmation(null)} />}
    <dialog className="workspace-confirm" ref={confirmation} onCancel={() => setDeleteConfirmation(null)}><h2>删除材料？</h2><p>{deleteConfirmation?.title}</p><p>原件、正文、图片、博客、计划、笔记和阅读进度将永久删除。历史聊天保留并标记来源已删除。</p>{deleteConfirmation && deletionImpact && <div aria-label="删除影响"><p>受影响专题：{deletionImpact.topics.map(t => t.title).join("、") || "无"}</p><ul>
      <li>原件与解析正文（Bundle）：{deletionImpact.assets.bundle ? "将删除" : "未建立"}</li>
      <li>博客（Blog）：{deletionImpact.assets.blog ? "将删除" : "未生成"}</li>
      <li>笔记（Notes）：{deletionImpact.assets.notes ? "将删除" : "未建立"}</li>
      <li>阅读计划（Plan）：{deletionImpact.assets.plans} 份</li>
      <li>阅读进度：{deletionImpact.assets.progress ? "将清理" : "未建立"}</li>
    </ul></div>}<div><button disabled={!!busy} onClick={() => setDeleteConfirmation(null)}>取消</button><button className="workspace-primary" disabled={!!busy || active || managementBusy || !deletionImpact} onClick={() => {
      if (deleteConfirmation && host.deleteSource) void operate("删除", () => host.deleteSource!(deleteConfirmation.sourceId));
    }}>{busy || "永久删除"}</button></div>{error && <p role="alert">{error}</p>}</dialog>
    {view?.configuration?.startupError && route !== "/settings" && <aside role="alert" className="configuration-notice">
      <p>{view.configuration.startupError}</p>
      <button onClick={() => navigate("/settings")}>模型与后端设置</button>
    </aside>}
    {view?.configuration?.pending && <aside role="status" className="configuration-notice"
      >
      <p>{view.configuration.refreshBlocked ? "任务运行中，完成后请刷新以应用配置" : "配置更改，需要刷新页面"}</p>
      <button onClick={() => window.location.reload()}>Reload</button>
    </aside>}
  </div>;
}
