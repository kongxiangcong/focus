import { type CSSProperties, useEffect, useRef, useState } from "react";
import { createReaderId, type BlogArtifactName, type BlogArtifactStatus, type BlogRegenerationTarget, type BlogStatus, type IngestionItem, type ProcessingBatch, type SourceDeletionImpact, type LibrarySource, type LibraryTopic, type ReaderHost, type ReaderHostResult, type ReadingPreparation, type ReadingWindow } from "@focus/reader-contracts";
import { FocusReader, AgentControls, TaskProgress, readingFontSizes } from "@focus/reader-ui";
import { BackendSetupPanel } from "./BackendSetupPanel";

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

const preparationSteps: Record<string, string> = {
  context: "正在分析全文", plan: "正在生成计划", translate: "正在翻译", check: "正在检查", repair: "正在修订译文", ready: "已完成",
};
function preparationText(preparation: ReadingPreparation) {
  if (preparation.ready) return preparation.candidate ? "新计划已就绪；旧阅读仍保留，可手动打开新计划" : "阅读已准备好，可手动点击开始阅读";
  if (preparation.timed_out) return "准备超时";
  const subject = preparation.candidate ? "新计划" : "阅读";
  const step = preparationSteps[preparation.step] ?? "正在准备";
  if (preparation.status === "running") return `${subject}准备中 · ${step}${preparation.total > 0 ? ` · ${preparation.completed}/${preparation.total} 段` : ""}`;
  const status = ({ failed: "准备失败", interrupted: "准备已中断", cancelled: "准备已取消", bundle_changed: "原件已变化", commit_conflict: "提交冲突" } as Record<string, string>)[preparation.status] ?? "准备未完成";
  return `${subject}${status}${preparation.error ? ` · ${preparation.error}` : ""}`;
}

const blogArtifacts: readonly [BlogArtifactName, string][] = [["value_analysis", "价值分析"], ["reading_blog", "带读博客"], ["html", "HTML"]];
const blogStatusText: Record<BlogArtifactStatus, string> = {
  pending: "待生成", generating: "生成中", completed: "已完成", failed: "失败", not_applicable: "不适用",
};
/** Retry is named by granularity: only the failed document is re-run. */
const blogRetryLabel: Record<BlogArtifactName, string> = {
  value_analysis: "重新生成价值分析", reading_blog: "重新生成带读博客", html: "重新生成 HTML",
};

export function WorkspaceApp({ host }: { host: ReaderHost }) {
  const [route, setRoute] = useState<Route>(routeFromLocation);
  const [fontSize, setFontSize] = useState<FontSize>(readFont);
  const [brightness, setBrightness] = useState(() => { try { return Math.max(85, Math.min(110, Number(localStorage.getItem("focus.brightness") ?? 100) || 100)); } catch { return 100; } });
  const savedAppearance = useRef({ fontSize, brightness });
  const [readingTopic, setReadingTopic] = useState("");
  const [managementTopics, setManagementTopics] = useState<readonly string[]>([]);
  const [generateOnUpload, setGenerateOnUpload] = useState(true);
  const [connectionLost, setConnectionLost] = useState(false);
  const [taskDetails, setTaskDetails] = useState(false);
  const [closingPreparations, setClosingPreparations] = useState<Readonly<Record<string, string>>>({});
  const [retryAction, setRetryAction] = useState<(() => void) | null>(null);
  const refreshing = useRef(false);
  const blogRefreshing = useRef(new Set<string>());
  const [dragging, setDragging] = useState(false);
  const [view, setView] = useState<ReadingWindow | null>(null);
  function acceptView(next: ReadingWindow) {
    setView(old => old?.revision !== undefined && next.revision !== undefined && old.revision > next.revision ? old : next);
  }
  const [sources, setSources] = useState<readonly LibrarySource[]>([]);
  const [topics, setTopics] = useState<readonly LibraryTopic[]>([]);
  const [inbox, setInbox] = useState<readonly IngestionItem[]>([]);
  const [topic, setTopic] = useState("");
  const [management, setManagement] = useState<{ kind: "create" | "rename" | "delete" | "source"; id?: string } | null>(null);
  const [managementTitle, setManagementTitle] = useState("");
  const managementDialog = useRef<HTMLDialogElement>(null);
  const [libraryView, setLibraryView] = useState<"cards" | "list">(() => {
    try { return localStorage.getItem("focus.libraryView") === "list" ? "list" : "cards"; } catch { return "cards"; }
  });
  const [expandedSources, setExpandedSources] = useState<ReadonlySet<string>>(new Set());
  function toggleDetails(id: string) {
    setExpandedSources(current => { const next = new Set(current); if (next.has(id)) next.delete(id); else next.add(id); return next; });
    if (!blogs[id]) void refreshBlog(id);
  }
  const [query, setQuery] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [readyNotice, setReadyNotice] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState("");
  const [deletionImpact, setDeletionImpact] = useState<SourceDeletionImpact | null>(null);
  const [confirm, setConfirm] = useState<{ source: LibrarySource; action: "delete" | "reread" | "replan" | "clear"; requestId?: string } | null>(null);
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
  const seenPreparation = useRef<Record<string, string>>({});
  const workPollKey = `${connectionLost}:${view?.configuration?.busy}:${(view?.workItems ?? []).map(item => `${item.kind}:${item.targetId}:${item.status}`).join("|")}`;
  const active = !!view?.agent?.run && ["running", "approval", "stopping"].includes(view.agent.run.status);

  const actionIds = useRef<Record<string, string>>({});
  async function identified<T>(key: string, task: (requestId: string) => Promise<ReaderHostResult<T>>) {
    const id = actionIds.current[key] ??= createReaderId();
    const result = await task(id);
    if (result.ok) delete actionIds.current[key];
    return result;
  }
  function saveAppearance() {
    try {
      const old = { fontSize: localStorage.getItem("focus.fontSize"), brightness: localStorage.getItem("focus.brightness") };
      try { localStorage.setItem("focus.fontSize", fontSize); localStorage.setItem("focus.brightness", String(brightness)); }
      catch (e) { if (old.fontSize !== null) localStorage.setItem("focus.fontSize", old.fontSize); else localStorage.removeItem("focus.fontSize"); if (old.brightness !== null) localStorage.setItem("focus.brightness", old.brightness); else localStorage.removeItem("focus.brightness"); throw e; }
      savedAppearance.current = { fontSize, brightness }; return true;
    } catch { return false; }
  }
  function navigate(next: Route) { history.pushState(null, "", next); setRoute(next); setError(""); setRetryAction(null); }
  async function refresh() {
    if (!host.listSources || !host.listTopics) { setLoading(false); return; }
    if (refreshing.current) return;
    refreshing.current = true;
    const version = ++requestVersion.current;
    try {
      const [sourceResult, topicResult, inboxResult, batchResult] = await Promise.all([host.listSources(), host.listTopics(), host.listInbox?.(), host.listBatches?.()]);
      if (version !== requestVersion.current) return;
      if (sourceResult.ok) {
        setSources(sourceResult.value);

      } else setError(sourceResult.error.message);
      if (topicResult.ok) { setTopics(topicResult.value); setTopic(current => topicResult.value.some(t => t.topicId === current) ? current : ""); } else setError(topicResult.error.message);
      if (batchResult) { if (batchResult.ok) setBatches(batchResult.value); else setError(batchResult.error.message); }
      if (inboxResult) { if (inboxResult.ok) setInbox(inboxResult.value); else setError(inboxResult.error.message); }
    } catch (e) { if (version === requestVersion.current) setError(String(e)); }
    finally { refreshing.current = false; if (version === requestVersion.current) setLoading(false); }
  }
  useEffect(() => {
    if (location.pathname !== routeFromLocation()) history.replaceState(null, "", "/library");
    const pop = () => setRoute(routeFromLocation()); window.addEventListener("popstate", pop);
    let alive = true;
    const accept = (result: ReaderHostResult<ReadingWindow>) => {
      if (!alive) return;
      if (result.ok) { acceptView(result.value); setConnectionLost(false); }
      else { setConnectionLost(true); setError(result.error.message); }
    };
    void (host.refreshBackendConfiguration ? host.refreshBackendConfiguration() : host.getReadingWindow()).then(accept);
    const unsubscribe = host.subscribe?.(accept);
    return () => { alive = false; unsubscribe?.(); window.removeEventListener("popstate", pop); requestVersion.current++; };
  }, [host]);
  useEffect(() => { if (route !== "/settings") void refresh(); }, [route, view?.agent?.run?.status, host]);
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
      try { const result = await host.getReadingWindow();
        if (!cancelled) { if (result.ok) { acceptView(result.value); setConnectionLost(false); } else setConnectionLost(true); }
      } catch { if (!cancelled) setConnectionLost(true); }
      if (!cancelled) timer = window.setTimeout(() => void poll(), 1500);
    }
    timer = window.setTimeout(() => void poll(), 1500);
    return () => { cancelled = true; window.clearTimeout(timer); };
  }, [host, workPollKey]);
  useEffect(() => { if (blogViewer) blogDialog.current?.showModal(); else blogDialog.current?.close(); }, [blogViewer]);
  useEffect(() => { if (management) managementDialog.current?.showModal(); else managementDialog.current?.close(); }, [management]);
  useEffect(() => { if (confirm) confirmation.current?.showModal(); else confirmation.current?.close(); }, [confirm]);
  useEffect(() => { if (view?.blog) setBlogs(view.blog); }, [view?.blog]);
  useEffect(() => {
    if (!view?.preparations) return;
    for (const [sourceId, preparation] of Object.entries(view.preparations)) {
      if (preparation.ready && seenPreparation.current[sourceId] === "running") {
        setReadyNotice(`${sources.find(source => source.sourceId === sourceId)?.shortName ?? sourceId} 已就绪`);
      }
      seenPreparation.current[sourceId] = preparation.status;
    }
  }, [view?.preparations, sources]);
  useEffect(() => {
    const running = Object.values(blogs).filter(blog => blog.runStatus === "running" || blog.executing).map(blog => blog.sourceId);
    if (running.length === 0 || !host.blogStatus) return;
    const timer = window.setInterval(() => running.forEach(id => void refreshBlog(id)), 1500);
    return () => window.clearInterval(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [blogs, host]);

  useEffect(() => { if (uploadOpen) uploadDialog.current?.showModal(); else uploadDialog.current?.close(); }, [uploadOpen]);

  async function operate(label: string, operation: () => Promise<ReaderHostResult<ReadingWindow>>, read = false) {
    if (locked.current || (active && !label.startsWith("停止"))) return;
    locked.current = true; setBusy(label); setError(""); setRetryAction(null);
    try {
      const result = await operation();
      if (!result.ok) { setError(result.error.message); setRetryAction(() => () => void operate(label, operation, read)); return; }
      setRetryAction(null); acceptView(result.value); setConfirm(null);
      if (read) navigate("/reading");
      if (label === "上传") { setUploadOpen(false); setSelectedFiles([]); }
      await refresh();
    } catch (e) { setError(String(e)); setRetryAction(() => () => void operate(label, operation, read)); }
    finally { locked.current = false; setBusy(""); }
  }
  async function discuss(sourceId: string) {
    if (!host.selectDiscussionSource) return;
    const result = await host.selectDiscussionSource(sourceId);
    if (!result.ok) { setError(result.error.message); return; }
    acceptView(result.value);
    navigate("/reading");
  }
  function preparationHidden(sourceId: string) {
    const prepared = view?.preparations?.[sourceId];
    return !!prepared?.dismissed || !!(prepared?.attempt && closingPreparations[sourceId] === prepared.attempt);
  }
  function preparationFailed(sourceId: string) {
    return ["failed", "cancelled", "interrupted", "bundle_changed", "commit_conflict"].includes(view?.preparations?.[sourceId]?.status ?? "");
  }
  async function dismissPreparation(sourceId: string) {
    const attempt = view?.preparations?.[sourceId]?.attempt;
    if (!attempt || !host.dismissPreparation) return;
    setClosingPreparations(old => ({ ...old, [sourceId]: attempt }));
    const restore = () => setClosingPreparations(old => { if (old[sourceId] !== attempt) return old; const next = { ...old }; delete next[sourceId]; return next; });
    try {
      const result = await host.dismissPreparation(sourceId, attempt);
      if (result.ok) acceptView(result.value);
      else { restore(); setError(result.error.message); }
    } catch { restore(); setError("关闭提示未保存，请检查连接后再次关闭。"); }
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
    if (!prepared || preparationHidden(sourceId)) return null;
    return <section className="preparation-notice" aria-label="准备阅读状态">
      <div className="preparation-notice-heading">
        <p role="status">{preparationText(prepared)}</p>
        {preparationFailed(sourceId) && prepared.attempt && host.dismissPreparation && <button className="preparation-dismiss" aria-label="关闭准备阅读提示" title="关闭这次状态提示" onClick={() => void dismissPreparation(sourceId)}>×</button>}
      </div>
      {preparationFailed(sourceId) && (host.resumePreparation || host.replanSource) && <button disabled={!!busy || active} onClick={() => void retryPreparation(sourceId)}>重试</button>}
    </section>;
  }
  async function enterReading(sourceId: string) {
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
  function replaceInbox(item: IngestionItem) { setInbox(current => [item, ...current.filter(existing => existing.itemId !== item.itemId)]); }
  async function ingest(label: string, operation: () => Promise<ReaderHostResult<IngestionItem>>, closeUpload = false) {
    if (locked.current) return;
    locked.current = true; setBusy(label); setError(""); setNotice(""); setRetryAction(null);
    try {
      const result = await operation();
      if (!result.ok) { setError(result.error.message); setRetryAction(() => () => void ingest(label, operation, closeUpload)); return; }
      setRetryAction(null); replaceInbox(result.value);
      if (result.value.duplicate) setNotice("该原件已有未完成任务，已回到原任务；不会重复解析。");
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
      const started = await identified(`start:${item.itemId}`, id => host.startBatch!([item.itemId], id));
      if (!started.ok) { setError(started.error.message); return; }
      await refresh();
    } catch (e) { setError(String(e)); }
    finally { locked.current = false; setBusy(""); }
  }
  const selectedTopic = topics.find(t => t.topicId === topic);
  const managementBusy = !!busy || !!view?.configuration?.busy || active || batches.some(b => b.executing || ["confirmed", "running"].includes(b.status)) || Object.values(blogs).some(b => b.executing || b.runStatus === "running");
  const filtered = sources.filter(s => (!topic || s.topicIds.includes(topic)) && (s.title + " " + (s.shortName ?? "")).toLowerCase().includes(query.toLowerCase()));
  if (selectedTopic) filtered.sort((a, b) => selectedTopic.sourceIds.indexOf(a.sourceId) - selectedTopic.sourceIds.indexOf(b.sourceId));
  function openManagement(kind: "create" | "rename" | "delete" | "source", id?: string, title = "") {
    setManagement({ kind, id }); setManagementTitle(title); setManagementTopics(sources.find(s => s.sourceId === id)?.topicIds ?? []); setError("");
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
    if (kind === "source" && id && host.saveSourceDetails) { const requestId = createReaderId(); void manage(() => host.saveSourceDetails!(id, managementTitle, managementTopics, requestId)); }
  }
  function moveSource(sourceId: string, offset: number) {
    if (!selectedTopic || !host.manageTopic) return;
    const ids = [...selectedTopic.sourceIds], index = ids.indexOf(sourceId), target = index + offset;
    if (index < 0 || target < 0 || target >= ids.length) return;
    [ids[index], ids[target]] = [ids[target], ids[index]];
    void manage(() => host.manageTopic!(selectedTopic.topicId, "reorder", { sourceIds: ids }));
  }

  function rereadReceipt(sourceId: string) {
    if (!view || view.source.sourceId !== sourceId || view.readingRevision === undefined) return null;
    const chunk = view.current ?? view.history.at(-1);
    return chunk ? { sourceId, planId: chunk.planId, chunkId: view.current?.chunkId ?? null,
      readingRevision: view.readingRevision } : null;
  }
  async function confirmDelete(source: LibrarySource) {
    if (!host.deletionImpact || managementBusy) return;
    setBusy("读取删除影响"); setError(""); setDeletionImpact(null);
    try {
      const result = await host.deletionImpact(source.sourceId);
      if (!result.ok) { setError(result.error.message); return; }
      setDeletionImpact(result.value); setConfirm({ source, action: "delete" });
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
  async function uploadAndStart() {
    if (locked.current || !selectedFiles.length || !host.stageIngestion || !host.startBatch) return;
    const files = [...selectedFiles], topicTitle = uploadTopic.trim();
    locked.current = true; setBusy("开始处理"); setError("");
    try {
      const ids: string[] = [];
      for (const file of files) {
        const staged = await host.stageIngestion(file, { ...(topicTitle ? { topicTitle } : {}) });
        if (!staged.ok) { setError(staged.error.message); return; }
        replaceInbox(staged.value);
        if (staged.value.duplicate && !["awaiting_confirmation", "confirmed"].includes(staged.value.status)) {
          setNotice("该原件已有未完成任务，已回到原任务；不会重复解析。");
          continue;
        }
        ids.push(staged.value.itemId);
      }
      if (ids.length) {
        const started = await identified(`upload:${ids.join(",")}`, id => host.startBatch!(ids, id, generateOnUpload));
        if (!started.ok) { setError(started.error.message); return; }
      }
      setUploadOpen(false); setSelectedFiles([]); await refresh();
    } catch (e) { setError(String(e)); }
    finally { locked.current = false; setBusy(""); }
  }
  function chooseUpload(selected: readonly File[] = []) {
    if (selected.some(f => !/\.(pdf|html)$/i.test(f.name))) { setError("请选择 PDF 或 SingleFile HTML"); return; }
    setSelectedFiles(selected);
    setUploadTopic(topics.find(t => t.topicId === topic)?.title ?? "");
    setGenerateOnUpload(true); setError(""); setUploadOpen(true);
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
  const runningStatuses = ["running", "approval", "stopping", "processing", "confirmed", "pending", "generating"];
  const work = (view?.workItems ?? []).filter(item => item.kind !== "preparation" || !preparationHidden(item.targetId));
  const runningWork = work.filter(w => runningStatuses.includes(w.status));
  const attention = work.filter(w => !runningStatuses.includes(w.status));
  const primaryWork = runningWork.find(w => w.status === "approval") ?? runningWork.find(w => w.kind === "ingestion") ?? runningWork[0];
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
  return <div className="workspace-app" style={{ "--reader-brightness": brightness / 100 } as CSSProperties}>
    <header className="workspace-nav">
      <a className="workspace-logo" href="/library" onClick={e => { e.preventDefault(); navigate("/library"); }}>focus<span>.</span></a>
      <nav aria-label="应用导航">{([["/library", "知识库", "▤"], ["/reading", "阅读", "☷"], ["/settings", "设置", "☼"]] as const).map(([path, title, icon]) =>
        <a key={path} href={path} aria-current={route === path ? "page" : undefined} onClick={e => { e.preventDefault(); navigate(path); }}><span aria-hidden="true">{icon}</span>{title}</a>)}</nav>
    </header>
    <header className="workspace-header">
      <div className="workspace-toolbar">
        {route === "/reading" ? <div className="reading-library-picker">
          <label><span className="workspace-sr-only">专题</span><select aria-label="阅读专题" value={readingTopic} onChange={e => setReadingTopic(e.target.value)}><option value="">全部专题</option>{topics.map(t => <option key={t.topicId} value={t.topicId}>{t.title}</option>)}</select></label>
          <label><span className="workspace-sr-only">材料</span><select aria-label="选择阅读材料" title={view?.source.title} value={view?.source.sourceId || ""} disabled={!!busy || active} onChange={e => { if (e.target.value) void enterReading(e.target.value); }}><option value="">选择材料</option>{sources.filter(s => s.sourceId === view?.source.sourceId || !readingTopic || s.topicIds.includes(readingTopic)).map(s => <option key={s.sourceId} value={s.sourceId}>{s.shortName || s.title}</option>)}</select></label>
        </div> : <h1>{route === "/library" ? "知识库" : "设置"}</h1>}
        <div className="workspace-header-actions">
          <section className="workspace-status" aria-label="当前工作">
            <span className="workspace-sr-only" role="status">{connectionLost ? "连接中断，正在恢复" : !view ? "正在连接" : primaryWork ? `${primaryWork.label} · ${runningWork.length} 项进行中` : "当前无工作"}{attention.length > 0 ? ` · ${attention.length} 项需查看` : ""}</span>
            <button className="workspace-task-toggle" aria-label="任务详情" aria-controls="workspace-tasks" aria-expanded={taskDetails} onClick={() => setTaskDetails(!taskDetails)}>
              <span className="workspace-status-dot" data-active={runningWork.length > 0} data-attention={connectionLost || attention.length > 0} aria-hidden="true" />
              <span>{connectionLost ? "连接中断" : !view ? "连接中" : runningWork.length ? `${runningWork.length} 项进行中` : attention.length ? `${attention.length} 项需查看` : "任务"}</span>
              <svg className="workspace-chevron" aria-hidden="true" width="16" height="16" viewBox="0 0 16 16"><path d="m4 6 4 4 4-4" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" /></svg>
            </button>
          </section>
          {route === "/library" && <button className="workspace-primary" disabled={uploadDisabled} onClick={() => chooseUpload()}>上传</button>}
        </div>
      </div>
      {taskDetails && <div className="workspace-task-frame" id="workspace-tasks" aria-label="任务框">
        {work.length === 0 && batches.length === 0 && inbox.length === 0 && <p>没有进行中或待处理的任务。</p>}
        {work.filter(item => item.kind !== "ingestion" || (!inbox.some(entry => entry.itemId === item.targetId) && !batches.some(batch => batch.items.some(entry => entry.itemId === item.targetId)))).map(item => <div key={`${item.kind}:${item.targetId}`}><span>{item.label}{item.kind === "preparation" && preparationFailed(item.targetId) ? "" : ` · ${runningStatuses.includes(item.status) ? "进行中" : "待处理"}`}</span>
          {item.error && (item.kind !== "preparation" || !view?.preparations?.[item.targetId]) && <p role="alert">{item.error}</p>}
          {runningStatuses.includes(item.status) && item.status !== "pending" && <button disabled={!!busy} onClick={() => void stopWork(item)}>{item.kind === "preparation" ? "取消准备" : "停止此任务"}</button>}
          {item.kind === "preparation" && preparationFailed(item.targetId) && preparationNotice(item.targetId)}
          {!runningStatuses.includes(item.status) && item.kind === "progress" && host.retryReadingProgress && <button disabled={!!busy} onClick={() => void operate("补记", () => identified(`progress:${item.targetId}`, id => host.retryReadingProgress!(item.targetId, id)))}>补记</button>}
          {!runningStatuses.includes(item.status) && (item.kind === "ingestion" || item.kind === "blog") && <button onClick={() => navigate("/library")}>查看并恢复</button>}
          {!runningStatuses.includes(item.status) && item.kind === "chat" && <button onClick={() => navigate("/reading")}>查看并重新提问</button>}
        </div>)}
      {batches.length > 0 && <section className="library-inbox" aria-label="处理任务"><h2>上传任务</h2>{batches.map(batch => <details key={batch.batchId}><summary>{batch.status === "completed" ? "已完成任务" : "当前任务 / 待处理"}</summary><article>
        <h3>{topics.find(t => t.topicId === batch.topicId)?.title ?? batch.topicId} · {batchStatusText[batch.status]}</h3>
        {["confirmed", "running"].includes(batch.status) && <button disabled={!!busy || !host.controlBatch} onClick={() => void controlBatch(batch.batchId, "stop")}>停止整批</button>}
        {["paused", "partial"].includes(batch.status) && <button disabled={!!busy || batch.executing || !host.controlBatch} onClick={() => void controlBatch(batch.batchId, "continue")}>继续剩余工作</button>}
        {batch.error && <p role="status">{batch.error.message}</p>}
        {batch.items.map(item => <div className="library-inbox-item" data-status={item.ingestionStatus === "failed" ? "failed" : item.status} key={item.itemId}>
          <strong>{item.fileName}</strong><span>{itemStatusText[item.status]}</span>
          <small>{item.status === "deleted" ? "原处理授权已失效" : item.ingestionStatus === "completed" ? "解析完成" : "解析：" + (statusText[item.ingestionStatus as IngestionItem["status"]] ?? "待处理")}{item.blog ? " · 博客：" + ({ running: "生成中", completed: "已完成", failed: "失败", cancelled: "已取消", interrupted: "已中断" }[item.blog.runStatus ?? ""] ?? "待生成") : ""}</small>
          {item.parserBackend && <small>{item.parserBackend === "local-mineru" ? "本地 MinerU" : "远端 MinerU API"}{item.selectionReason ? ` · ${item.selectionReason}` : ""}{item.parserProgress?.status ? ` · ${item.parserProgress.status === "queued" ? "排队中" : "解析中"}` : ""}{typeof item.parserProgress?.percent === "number" ? ` · ${Math.round(item.parserProgress.percent)}%` : ""}</small>}
          {item.error && <p>{item.error.message}</p>}
          {item.status === "processing" && <button disabled={!!busy || !host.controlBatch} onClick={() => void controlBatch(batch.batchId, "cancel-item", item.itemId)}>取消此项</button>}
          {item.status === "queued" && <button disabled={!!busy || !host.controlBatch} onClick={() => void controlBatch(batch.batchId, "remove-item", item.itemId)}>移出队列</button>}
          {["failed", "partial", "cancelled"].includes(item.status) && !item.resubmitRisk && <button disabled={!!busy || batch.executing || !host.controlBatch} onClick={() => void controlBatch(batch.batchId, "retry-item", item.itemId)}>重试未完成步骤</button>}
          {item.resubmitRisk && <div><p>上次提交结果未知，重新提交可能重复解析。</p>
            {item.remoteReference && <button disabled={!!busy || batch.executing || !host.controlBatch} onClick={() => void controlBatch(batch.batchId, "retry-item", item.itemId)}>查询并续接原任务</button>}
            <button disabled={!!busy || batch.executing || !host.controlBatch} onClick={() => void controlBatch(batch.batchId, "resubmit-item", item.itemId, item.resubmitRisk!.choice_id)}>重新提交</button>
          </div>}
          {item.sourceId && <div className="inbox-links">{host.sourceOriginalUrl && <a href={host.sourceOriginalUrl(item.sourceId)} target="_blank" rel="noreferrer">原件</a>}{host.sourceContentUrl && <a href={host.sourceContentUrl(item.sourceId)} target="_blank" rel="noreferrer">正文</a>}</div>}
        </div>)}
      </article></details>)}</section>}
      {inbox.some(item => !batches.some(batch => batch.items.some(entry => entry.itemId === item.itemId))) && <section className="library-inbox" aria-label="Inbox"><div className="library-inbox-heading"><h2>单项上传</h2><button disabled={!!busy} onClick={() => void refresh()}>刷新状态</button></div>{inbox.filter(item => !batches.some(batch => batch.items.some(entry => entry.itemId === item.itemId))).map(item => <article key={item.itemId} className="library-inbox-item" data-status={item.status}>
        <div><strong>{item.fileName}</strong><span>{statusText[item.status]}</span><small>{item.topicTitle ?? topics.find(t => t.topicId === item.topicId)?.title ?? "不关联专题"}</small></div>
        {item.parserBackend && <p role="status">{item.parserBackend === "local-mineru" ? "本地 MinerU" : "远端 MinerU API"}{item.selectionReason ? ` · ${item.selectionReason}` : ""}{item.parserProgress?.status ? ` · ${item.parserProgress.status === "queued" ? "排队中" : item.parserProgress.status === "running" ? "解析中" : item.parserProgress.status}` : ""}{typeof item.parserProgress?.percent === "number" ? ` · ${Math.round(item.parserProgress.percent)}%` : ""}</p>}
        {item.status === "awaiting_confirmation" && <div className="inbox-confirmation"><p>PDF 由运行 FOCUS 后端的服务器自动选择本地 MinerU 或远端 MinerU API；HTML 使用本地解析。解析仅用于建立 Source 并关联专题，不会自动进入阅读。</p>
          <button className="workspace-primary" disabled={!!busy} onClick={() => void confirmAndStart(item)}>开始解析并生成博客</button></div>}
        {item.status === "processing" && <button disabled={!!busy || !host.cancelIngestion} onClick={() => host.cancelIngestion && void ingest("取消", () => host.cancelIngestion!(item.itemId))}>取消</button>}
        {(item.status === "status_check_required" || (item.status === "cancelled" && item.resubmitRisk)) && <div className="inbox-confirmation inbox-resubmission">
          <p>上次提交结果未知，重新提交可能重复解析。</p>
          <div className="inbox-resubmission-actions">
            {item.remoteReference && <button disabled={!!busy || !host.continueIngestion} onClick={() => host.continueIngestion && void ingest("查询", () => host.continueIngestion!(item.itemId, createReaderId()))}>查询并续接原任务</button>}
            <button className="workspace-primary" disabled={!!busy || !host.resubmitIngestion || !item.resubmitRisk} onClick={() => host.resubmitIngestion && item.resubmitRisk && void ingest("重新提交", () => host.resubmitIngestion!(item.itemId, createReaderId(), item.resubmitRisk!.choiceId))}>重新提交</button>
          </div>
        </div>}
        {["retry_waiting", "failed", "commit_conflict", "topic_attachment_pending", "interrupted"].includes(item.status) && <button disabled={!!busy || !host.continueIngestion} onClick={() => host.continueIngestion && void ingest("继续", () => host.continueIngestion!(item.itemId, createReaderId()))}>继续</button>}
        {item.status === "cancelled" && !item.resubmitRisk && <button disabled={!!busy || !host.continueIngestion} onClick={() => host.continueIngestion && void ingest("继续", () => host.continueIngestion!(item.itemId, createReaderId()))}>继续</button>}
        {["status_check_required", ...resumableStatuses].includes(item.status) && <button disabled={!!busy || !host.confirmIngestion || !host.processIngestion} onClick={() => void confirmAndStart(item)}>重新确认并开始</button>}
        {item.sourceId && <div className="inbox-links">{host.sourceOriginalUrl && <a href={host.sourceOriginalUrl(item.sourceId)} target="_blank" rel="noreferrer">原件</a>}{host.sourceContentUrl && <a href={host.sourceContentUrl(item.sourceId)} target="_blank" rel="noreferrer">正文</a>}</div>}
        {(item.error || item.topicError) && <p className="inbox-error">{item.topicError?.message ?? item.error?.message}</p>}
      </article>)}</section>}
      {managementBusy && <p role="status">部分操作暂不可用：当前任务正在使用材料。可在任务详情停止对应任务后重试。</p>}
      </div>}
      {view?.agent?.run?.status === "approval" && <AgentControls agent={view.agent} onStop={() => host.stop && void host.stop().then(result => { if (result.ok) acceptView(result.value); })} onAnswer={async input => {
        const result = await host.approve?.(input); if (result?.ok) { acceptView(result.value); return true; } return false;
      }} />}
      {!uploadOpen && error && <div className="workspace-error" role="alert">{error}<button onClick={() => { setError(""); if (retryAction) retryAction(); else void refresh(); }}>{retryAction ? "重试此操作" : "刷新状态"}</button></div>}
      {!error && (notice || readyNotice) && <div className="workspace-notice" role="status">{readyNotice || notice}<button onClick={() => { setNotice(""); setReadyNotice(""); }}>关闭</button></div>}
    </header>
    <div className="workspace-reading" hidden={route !== "/reading"}>
      <FocusReader host={host} appearance="mist" fontSize={fontSize} visible={route === "/reading"} /></div>
    {route === "/library" && <main className="library-page" data-dragging={dragging}
      onDragOver={e => { e.preventDefault(); if (!uploadDisabled) setDragging(true); }}
      onDragLeave={e => { if (!e.currentTarget.contains(e.relatedTarget as Node | null)) setDragging(false); }}
      onDrop={e => { e.preventDefault(); setDragging(false); if (!uploadDisabled) chooseUpload(Array.from(e.dataTransfer.files)); }}>
      <div className="library-layout"><aside className="library-topics" aria-label="专题"><h2>专题</h2><button disabled={managementBusy || !host.createTopic} onClick={() => openManagement("create")}>新建专题</button><button aria-pressed={!topic} onClick={() => setTopic("")}>全部 <span>{sources.length}</span></button>{topics.map(t => <button key={t.topicId} aria-pressed={topic === t.topicId} onClick={() => setTopic(t.topicId)}>{t.title}<span>{t.sourceIds.length}</span></button>)}</aside>
        <section className="library-sources" aria-label="材料列表">{selectedTopic && <div>
          <button disabled={managementBusy || !host.manageTopic} onClick={() => openManagement("rename", selectedTopic.topicId, selectedTopic.title)}>重命名专题</button>
          <button disabled={managementBusy || !host.manageTopic} onClick={() => openManagement("delete", selectedTopic.topicId, selectedTopic.title)}>删除专题</button>
        </div>}<div className="library-toolbar"><h2>{topics.find(t => t.topicId === topic)?.title ?? "全部材料"}<small>{filtered.length}</small></h2><div className="library-view-switch" role="group" aria-label="显示方式">{([["cards", "卡片显示"], ["list", "列表显示"]] as const).map(([mode, label]) => <button key={mode} aria-pressed={libraryView === mode} onClick={() => { setLibraryView(mode); try { localStorage.setItem("focus.libraryView", mode); } catch { /* The current view remains usable without storage. */ } }}>{label}</button>)}</div><input type="search" aria-label="搜索材料" placeholder="搜索标题" value={query} onChange={e => setQuery(e.target.value)} /></div>
          {loading ? <p role="status" className="library-empty">读取中…</p> : filtered.length === 0 ? <div className="library-empty"><span aria-hidden="true">▤</span><p>{query || topic ? "暂无匹配材料" : "放入第一份材料"}</p><button className="workspace-primary" disabled={uploadDisabled} onClick={() => { if (query || topic) { setQuery(""); setTopic(""); } else chooseUpload(); }}>{query || topic ? "重置" : "上传"}</button></div> : <div className="library-cards" data-view={libraryView}>{filtered.map(s => <article className="library-card" data-reading-status={readingStatus(s)} data-status={s.parseStatus !== "ready" ? "failed" : readingStatus(s) === "completed" ? "completed" : s.progress.completed > 0 ? "reading" : "unread"} key={s.sourceId}>
            <div className="library-overview">
              <h3 title={s.title}>{s.shortName || s.title}</h3>
              <p className="library-summary">{s.parseStatus !== "ready" ? "解析失败" : readingStatus(s) === "completed" ? "阅读完成" : s.progress.completed > 0 ? "阅读中" : "未阅读"}</p>
              <div className="library-progress"><progress aria-label={`${s.title} 阅读进度`} value={s.progress.completed} max={s.progress.total || 1} /><span>{s.progress.completed} / {s.progress.total}</span></div>
            </div>
            <div className="library-card-actions">
              <button disabled={!host.blogUrl || !blogs[s.sourceId]?.generated || blogs[s.sourceId]?.artifacts?.html?.status !== "completed"} onClick={() => setBlogViewer(s.sourceId)}>打开博客</button>
              <button title={active ? "请先完成或停止当前问答" : busy ? `${busy}中` : undefined} disabled={!!busy || active || !host.openSource || s.parseStatus !== "ready" || (view?.preparations?.[s.sourceId]?.status === "running" && !view.preparations[s.sourceId].selected_ready)} onClick={() => void enterReading(s.sourceId)}>{view?.preparations?.[s.sourceId]?.status === "running" && !view.preparations[s.sourceId].selected_ready ? "阅读准备中…" : preparationFailed(s.sourceId) && !view?.preparations?.[s.sourceId]?.selected_ready ? preparationHidden(s.sourceId) ? "准备阅读" : "重试准备" : readingStatus(s) === "completed" ? "查看已读" : s.progress.completed > 0 ? "继续阅读" : view?.preparations?.[s.sourceId]?.selected_ready || view?.preparations?.[s.sourceId]?.ready ? "开始阅读" : "准备阅读"}</button>
              {preparationHidden(s.sourceId) && preparationFailed(s.sourceId) && view?.preparations?.[s.sourceId]?.selected_ready && <button disabled={!!busy || active || (!host.resumePreparation && !host.replanSource)} onClick={() => void retryPreparation(s.sourceId)}>准备阅读</button>}
              <button aria-expanded={expandedSources.has(s.sourceId)} aria-controls={`source-details-${s.sourceId}`} onClick={() => toggleDetails(s.sourceId)}>详细</button>
            </div>

            {expandedSources.has(s.sourceId) && <div className="library-details" id={`source-details-${s.sourceId}`}>
            {preparationNotice(s.sourceId)}
            <p className="library-parse-status">解析：{s.parseStatus === "ready" ? "已完成" : "失败"}{s.error ? ` · ${s.error}` : ""}</p>
            <div><button disabled={managementBusy || !host.saveSourceDetails} onClick={() => openManagement("source", s.sourceId, s.title)}>管理来源</button>
              {selectedTopic && <><button aria-label={`${s.title} 上移`} disabled={managementBusy || selectedTopic.sourceIds.indexOf(s.sourceId) === 0} onClick={() => moveSource(s.sourceId, -1)}>上移</button><button aria-label={`${s.title} 下移`} disabled={managementBusy || selectedTopic.sourceIds.indexOf(s.sourceId) === selectedTopic.sourceIds.length - 1} onClick={() => moveSource(s.sourceId, 1)}>下移</button></>}
            </div>
            <div className="library-card-top"><span className="source-badge">{s.format ?? (s.kind === "paper" ? "PDF" : "HTML")}</span>{s.parseStatus !== "ready" && <span title={s.error ?? undefined}>需检查</span>}</div>
            <p className="library-metadata" title={s.title}>{[s.publishedAt, s.venue].filter(Boolean).join(" · ")}</p>
            <div className="library-card-bottom"><small>{({ ready: "待阅读", reading: "阅读中", completed: "已读完", unplanned: "待规划" })[readingStatus(s)]}</small><div className="library-row-actions">{host.sourceOriginalUrl && <a href={host.sourceOriginalUrl(s.sourceId)} target="_blank" rel="noreferrer">原件</a>}{host.sourceContentUrl && <a href={host.sourceContentUrl(s.sourceId)} target="_blank" rel="noreferrer">正文</a>}<button disabled={!!busy || active || !host.replanSource || s.parseStatus !== "ready"} onClick={() => setConfirm({ source: s, action: "replan" })}>重新规划</button><button disabled={!!busy || !host.clearSource || view?.clearBusySources?.includes(s.sourceId)} onClick={() => setConfirm({ source: s, action: "clear", requestId: createReaderId() })}>重新阅读</button><button disabled={managementBusy || !host.deleteSource || !host.deletionImpact} onClick={() => void confirmDelete(s)}>删除</button></div></div>
            {view?.preparations?.[s.sourceId]?.candidate && view.preparations[s.sourceId].ready && <button className="workspace-primary" disabled={!!busy || active || !host.activateReadingCandidate || view.readingRevision === undefined} onClick={() => void activateCandidate(s.sourceId)}>打开新计划</button>}
            <div className="library-tags" aria-label="专题标签"><span>属于专题：{s.topicIds.length === 0 ? "未分类" : ""}</span>{s.topicIds.map(id => <button key={id} onClick={() => setTopic(id)}>{topics.find(t => t.topicId === id)?.title ?? id}</button>)}</div>
            <section className="library-blog" aria-label={`${s.title} 博客`}>
              {!blogs[s.sourceId]?.generated ? <button disabled={!!busy || !host.generateBlog || s.parseStatus !== "ready"} onClick={() => void generateBlog(s.sourceId)}>生成博客</button> : <>
                <ul className="blog-statuses">{blogArtifacts.map(([name, label]) => <li key={name} data-status={blogs[s.sourceId].artifacts?.[name]?.status ?? "pending"}><span>{label}</span><small>{blogStatusText[(blogs[s.sourceId].artifacts?.[name]?.status ?? "pending") as BlogArtifactStatus]}</small></li>)}</ul>
                {blogs[s.sourceId].valueAnalysis.applicable === false && <p className="blog-note">架构价值分析不适用：{blogs[s.sourceId].valueAnalysis.reason}</p>}
                {blogs[s.sourceId].error && <p className="blog-note" role="alert">{blogs[s.sourceId].error?.message}</p>}
                <div className="blog-actions">
                  {blogs[s.sourceId].runStatus === "running" && <button disabled={!!busy || !host.cancelBlog} onClick={() => void cancelBlog(s.sourceId)}>取消生成</button>}
                  {blogArtifacts.filter(([name]) => blogs[s.sourceId].artifacts?.[name]?.status === "failed").map(([name]) => <button key={name} disabled={!!busy || blogs[s.sourceId]?.executing || !host.regenerateBlog} onClick={() => void regenerateBlog(s.sourceId, name)}>{blogRetryLabel[name]}</button>)}
                  {blogArtifacts.every(([name]) => blogs[s.sourceId].artifacts?.[name]?.status !== "failed") && <button disabled={!!busy || blogs[s.sourceId]?.executing || !host.regenerateBlog} onClick={() => void regenerateBlog(s.sourceId, "all")}>重新生成</button>}
                </div>
              </>}
            </section>
            </div>}
          </article>)}</div>}
        </section></div>
      {busy && <p role="status">{busy}中…</p>}
    </main>}
    {route === "/settings" && <main className="settings-page">
      <BackendSetupPanel host={host} configuration={view?.configuration}
        onSaved={acceptView} onSaveAppearance={saveAppearance} onCancelAppearance={() => { setFontSize(savedAppearance.current.fontSize); setBrightness(savedAppearance.current.brightness); }} />
      <section className="focus-reader__appearance-panel">
      <div className="settings-row"><label htmlFor="brightness">亮度</label><input id="brightness" type="range" min="85" max="110" value={brightness} onChange={e => { setBrightness(Number(e.target.value)); }} /></div>
      <div className="settings-row"><label htmlFor="font-size">字号</label><input id="font-size" type="range" min="0" max="3" step="1" value={fontOptions.findIndex(([key]) => key === fontSize)} aria-valuetext={fontOptions.find(([key]) => key === fontSize)?.[1]} onChange={e => { const value = fontOptions[Number(e.target.value)][0]; setFontSize(value); }} /></div>
      <p className="settings-font-preview" style={{ fontSize: `${readingFontSizes[fontSize]}px` }}>阅读字号预览 · {fontOptions.find(([key]) => key === fontSize)?.[1]}</p>
</section>
    </main>}
    <dialog className="workspace-confirm" ref={managementDialog} onCancel={() => setManagement(null)}>
      <form onSubmit={e => { e.preventDefault(); saveManagement(); }}>
        <h2>{management?.kind === "source" ? "管理来源" : management?.kind === "delete" ? "删除专题" : management?.kind === "rename" ? "重命名专题" : "新建专题"}</h2>
        {management?.kind === "delete" ? <p>删除“{managementTitle}”专题。全部来源、博客、笔记和阅读进度会保留。</p> : <label>{management?.kind === "source" ? "来源原题" : "专题名称"}<input aria-label={management?.kind === "source" ? "来源原题" : "专题名称"} required maxLength={management?.kind === "source" ? 1000 : 120} value={managementTitle} onChange={e => setManagementTitle(e.target.value)} /></label>}
        {management?.kind === "source" && <fieldset><legend>所属专题</legend>{topics.map(t => <label key={t.topicId}><input type="checkbox" checked={managementTopics.includes(t.topicId)} disabled={managementBusy || !host.saveSourceDetails} onChange={e => { const checked = e.target.checked; setManagementTopics(old => checked ? [...old, t.topicId] : old.filter(id => id !== t.topicId)); }} />{t.title}</label>)}</fieldset>}
        {error && <p role="alert">{error}</p>}
        <button type="button" disabled={!!busy} onClick={() => setManagement(null)}>取消</button>
        <button type="submit" disabled={managementBusy || (management?.kind !== "delete" && !managementTitle.trim())}>{management?.kind === "delete" ? "确认删除专题" : "保存"}</button>
      </form>
    </dialog>
    <dialog className="workspace-confirm workspace-upload" ref={uploadDialog} onCancel={() => setUploadOpen(false)}>
      <form onSubmit={e => { e.preventDefault(); void uploadAndStart(); }}>
        <h2>解析并生成博客</h2>
        <label>专题<input list="upload-topics" disabled={!!busy} maxLength={120} value={uploadTopic} onChange={e => setUploadTopic(e.target.value)} placeholder="可选；留空进入未分类" /></label>
        <label><input type="checkbox" checked={generateOnUpload} onChange={e => setGenerateOnUpload(e.target.checked)} />解析后生成博客</label>
        <datalist id="upload-topics">{topics.map(t => <option key={t.topicId} value={t.title} />)}</datalist>
        <label className="upload-file">{selectedFiles.map(f => f.name).join("、") || "PDF / HTML"}<input aria-label="上传材料" type="file" multiple disabled={!!busy} accept=".pdf,.html,application/pdf,text/html" onChange={e => setSelectedFiles(Array.from(e.target.files ?? []))} /></label>
        <p>PDF 在服务器端优先使用本地 MinerU，可用能力缺失时使用已配置的远端 MinerU API；HTML 使用本地 HTML 解析器（不上传原件）。博客由当前生效的 {view?.agent?.backend === "deepseek" ? "DeepSeek" : "Codex"} 模型服务生成。点击开始即确认文件、专题和服务范围，不自动进入精读。</p>
        {error && <p role="alert">{error}</p>}
        <div className="upload-actions"><button type="button" disabled={!!busy} onClick={() => setUploadOpen(false)}>取消</button><button type="submit" className="workspace-primary" disabled={uploadDisabled || !selectedFiles.length}>{busy ? "开始中…" : generateOnUpload ? "开始解析并生成博客" : "仅解析入库"}</button></div>
      </form>
    </dialog>
    {blogViewer && host.blogUrl && <dialog className="workspace-blog-viewer" ref={blogDialog} aria-labelledby="blog-viewer-title" onCancel={e => { e.preventDefault(); closeBlogViewer(); }}>
      <div className="blog-viewer-head"><h2 id="blog-viewer-title">博客：{sources.find(s => s.sourceId === blogViewer)?.shortName || sources.find(s => s.sourceId === blogViewer)?.title}</h2>
        <div><a href={host.blogUrl(blogViewer)} target="_blank" rel="noreferrer">新窗口打开</a><button onClick={closeBlogViewer}>关闭</button></div></div>
      <iframe title="博客" src={host.blogUrl(blogViewer)} />
    </dialog>}
    <dialog className="workspace-confirm" ref={confirmation} onCancel={() => setConfirm(null)}><h2>{confirm?.action === "clear" ? "重新阅读本篇？" : confirm?.action === "delete" ? "删除材料？" : confirm?.action === "replan" ? "重新规划？" : "从头阅读？"}</h2><p>{confirm?.source.title}</p><p>{confirm?.action === "clear" ? "将清除本篇讨论、笔记和阅读记录，并从第一段重新开始。原文、译文和博客保留。" : confirm?.action === "delete" ? "原件、正文、图片、博客、计划、笔记和阅读进度将永久删除。历史聊天保留并标记来源已删除。" : confirm?.action === "replan" ? "重新分段并准备译文；保留旧计划、译文和笔记，不重复解析。" : "回到第一段，保留现有分段、译文和笔记。"}</p>{confirm?.action === "delete" && deletionImpact && <div aria-label="删除影响"><p>受影响专题：{deletionImpact.topics.map(t => t.title).join("、") || "无"}</p><ul>
      <li>原件与解析正文（Bundle）：{deletionImpact.assets.bundle ? "将删除" : "未建立"}</li>
      <li>博客（Blog）：{deletionImpact.assets.blog ? "将删除" : "未生成"}</li>
      <li>笔记（Notes）：{deletionImpact.assets.notes ? "将删除" : "未建立"}</li>
      <li>阅读计划（Plan）：{deletionImpact.assets.plans} 份</li>
      <li>阅读进度：{deletionImpact.assets.progress ? "将清理" : "未建立"}</li>
    </ul></div>}<div><button disabled={!!busy} onClick={() => setConfirm(null)}>取消</button><button className="workspace-primary" disabled={!!busy || (confirm?.action === "clear" ? !!view?.clearBusySources?.includes(confirm.source.sourceId) : active) || (confirm?.action === "delete" && (managementBusy || !deletionImpact))} onClick={() => {
      if (!confirm) return;
      const { source, action } = confirm;
      const receipt = rereadReceipt(source.sourceId);
      if (action === "reread" && (!receipt || !host.rereadReading)) { setError("阅读位置已变化，请先打开这篇材料。"); return; }
      void operate(action === "clear" ? "重新阅读" : action === "delete" ? "删除" : action === "replan" ? "重新规划" : "从头阅读", () => action === "clear" ? host.clearSource!(source.sourceId, confirm.requestId!) : action === "delete" ? host.deleteSource!(source.sourceId) : action === "replan" ? identified(`replan:${source.sourceId}`, id => host.replanSource!(source.sourceId, id)) : host.rereadReading!({ receipt: receipt!, requestId: createReaderId(), sessionId: view?.sessionId }), action === "reread");
    }}>{busy || (confirm?.action === "clear" ? "确认重新阅读" : confirm?.action === "delete" ? "永久删除" : confirm?.action === "replan" ? "确认重新规划" : "确认从头阅读")}</button></div>{error && <p role="alert">{error}</p>}</dialog>
    {view?.configuration?.pending && <aside role="status" className="configuration-notice"
      >
      <p>{view.configuration.refreshBlocked ? "任务运行中，完成后请刷新以应用配置" : "配置更改，需要刷新页面"}</p>
      <button onClick={() => window.location.reload()}>Reload</button>
    </aside>}
  </div>;
}
