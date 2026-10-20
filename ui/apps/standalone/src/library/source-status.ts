import type { BlogStatus, LibrarySource, ReadingPreparation } from "@focus/reader-contracts";

export type Phase = "invalid" | "preparing" | "prepFailed" | "completed" | "reading" | "ready" | "unplanned";
export type Tone = "danger" | "accent" | "warning" | "success" | "muted";
export type SourceStatus = { phase: Phase; label: string; tone: Tone; detail: string; ratio: number };
export function readingStatus(source: LibrarySource) {
  return source.readingStatus ?? (source.progress.planId && source.progress.chunkId === null ? "completed" : source.progress.completed ? "reading" : source.progress.planId ? "ready" : "unplanned");
}
export function preparationFailed(preparation: ReadingPreparation | undefined) {
  return ["failed", "cancelled", "interrupted", "bundle_changed", "commit_conflict"].includes(preparation?.status ?? "");
}
const labels: Record<Phase, string> = { invalid: "解析失败", preparing: "准备中", prepFailed: "准备失败", completed: "已读完", reading: "阅读中", ready: "可阅读", unplanned: "待准备" };
const tones: Record<Phase, Tone> = { invalid: "danger", preparing: "accent", prepFailed: "warning", completed: "success", reading: "accent", ready: "muted", unplanned: "muted" };
export function sourceStatus(source: LibrarySource, preparation?: ReadingPreparation, hidden = false): SourceStatus {
  const phase: Phase = source.parseStatus !== "ready" ? "invalid"
    : preparation?.status === "running" && !preparation.selected_ready ? "preparing"
    : preparationFailed(preparation) && !preparation?.selected_ready && !hidden ? "prepFailed"
    : readingStatus(source) === "completed" ? "completed"
    : source.progress.completed > 0 ? "reading"
    : preparation?.ready || preparation?.selected_ready || readingStatus(source) === "ready" ? "ready" : "unplanned";
  const progress = phase === "preparing" || phase === "prepFailed" ? preparation! : source.progress;
  const detail = phase === "preparing" ? `${progress.completed}/${progress.total} 段` : phase === "reading" ? `${progress.completed}/${progress.total}` : phase === "ready" || phase === "completed" ? `${source.progress.total} 段` : "";
  return { phase, label: labels[phase], tone: tones[phase], detail, ratio: phase === "completed" ? 1 : Math.max(0, Math.min(1, progress.completed / Math.max(1, progress.total))) };
}
export function primaryAction(source: LibrarySource, preparation: ReadingPreparation | undefined, hidden: boolean, options: { busy: string; active: boolean; canOpen: boolean }) {
  const { busy, active, canOpen } = options;
  const title = active ? "请先完成或停止当前问答" : busy ? `${busy}中` : undefined;
  if (source.parseStatus !== "ready") return { kind: "inspect" as const, label: "查看问题", disabled: false, title: undefined };
  const running = preparation?.status === "running" && !preparation.selected_ready;
  const label = running ? "阅读准备中…" : preparationFailed(preparation) && !preparation?.selected_ready ? hidden ? "准备阅读" : "重试准备" : readingStatus(source) === "completed" ? "查看已读" : source.progress.completed > 0 ? "继续阅读" : preparation?.selected_ready || preparation?.ready ? "开始阅读" : "准备阅读";
  return { kind: "read" as const, label, disabled: !!busy || active || !canOpen || running, title };
}
export type StatusFilter = "all" | "reading" | "unstarted" | "completed" | "attention";
export const statusFilters: readonly [StatusFilter, string][] = [["all", "全部"], ["reading", "阅读中"], ["unstarted", "未开始"], ["completed", "已读完"], ["attention", "需处理"]];
export function needsAttention(status: SourceStatus, blog?: BlogStatus) {
  return status.phase === "invalid" || status.phase === "prepFailed" || !!blog?.error || Object.values(blog?.artifacts ?? {}).some(artifact => artifact.status === "failed");
}
export function matchesStatus(status: SourceStatus, filter: StatusFilter, blog?: BlogStatus) {
  return filter === "all" || (filter === "attention" ? needsAttention(status, blog) : filter === "unstarted" ? ["ready", "unplanned", "preparing"].includes(status.phase) : status.phase === filter);
}
export function blogSummary(blog?: BlogStatus): { label: string; tone: Tone } {
  if (!blog) return { label: "博客状态未载入", tone: "muted" };
  const artifacts = Object.values(blog.artifacts ?? {});
  if (blog.executing || blog.runStatus === "running" || artifacts.some(a => a.status === "generating")) return { label: "生成中", tone: "accent" };
  if (blog.error || artifacts.some(a => a.status === "failed")) return { label: "部分失败", tone: "danger" };
  if (blog.generated && artifacts.length > 0 && artifacts.every(a => a.status === "completed")) return { label: "已完成", tone: "success" };
  return { label: "未生成", tone: "muted" };
}
