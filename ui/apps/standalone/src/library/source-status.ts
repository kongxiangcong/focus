import type { BlogStatus, LibrarySource, ReadingPreparation } from "@focus/reader-contracts";

export type Phase = "unstarted" | "reading" | "completed";
export type Tone = "danger" | "accent" | "warning" | "success" | "muted";
type SourceOperation = { kind: "parseFailed" | "preparing" | "prepFailed"; label: string; tone: Tone; detail?: string };
export type SourceStatus = {
  phase: Phase; label: string; tone: Tone;
  progress: { completed: number; total: number };
  operation?: SourceOperation;
};

function readingPhase(source: LibrarySource): Phase {
  const { completed, total, planId, chunkId } = source.progress;
  if (!planId || total <= 0) return "unstarted";
  // Older adapters may still report an independent source completion.
  if (chunkId === null && completed === total) return "completed";
  return completed > 0 || source.readingStatus === "reading" ? "reading" : "unstarted";
}

export function preparationFailed(preparation: ReadingPreparation | undefined) {
  return ["failed", "cancelled", "interrupted", "bundle_changed", "commit_conflict"].includes(preparation?.status ?? "");
}

const phases: Record<Phase, { label: string; tone: Tone }> = {
  unstarted: { label: "未开始", tone: "muted" },
  reading: { label: "阅读中", tone: "accent" },
  completed: { label: "已读完", tone: "success" },
};

export function sourceStatus(source: LibrarySource, preparation?: ReadingPreparation, hidden = false): SourceStatus {
  const phase = readingPhase(source);
  const total = source.progress.planId ? source.progress.total : 0;
  const completed = phase === "completed" ? total : Math.max(0, Math.min(total - 1, source.progress.completed));
  const operation: SourceOperation | undefined = source.parseStatus !== "ready" ? { kind: "parseFailed", label: "解析失败", tone: "danger" }
    : preparation?.status === "running" && !preparation.selected_ready
      ? { kind: "preparing", label: "准备中", tone: "accent", detail: `${preparation.completed}/${preparation.total} 段` }
    : preparationFailed(preparation) && !preparation?.selected_ready && !hidden ? { kind: "prepFailed", label: "准备失败", tone: "warning" }
    : undefined;
  return { phase, ...phases[phase], progress: { completed, total }, operation };
}

export function primaryAction(source: LibrarySource, preparation: ReadingPreparation | undefined, hidden: boolean, options: { busy: string; active: boolean; canOpen: boolean; direct?: boolean }) {
  const { busy, active, canOpen } = options;
  const title = active ? "请先完成或停止当前问答" : busy ? `${busy}中` : undefined;
  if (source.parseStatus !== "ready") return { kind: "inspect" as const, label: "查看问题", disabled: false, title: undefined };
  if (options.direct) return { kind: "read" as const, label: "阅读", disabled: !!busy || active || !canOpen, title };
  const running = preparation?.status === "running" && !preparation.selected_ready;
  const phase = readingPhase(source);
  const label = running ? "阅读准备中…"
    : preparationFailed(preparation) && !preparation?.selected_ready ? hidden ? "准备阅读" : "重试准备"
    : phase === "completed" ? "查看已读"
    : phase === "reading" ? "继续阅读"
    : preparation?.selected_ready || preparation?.ready ? "开始阅读" : "准备阅读";
  return { kind: "read" as const, label, disabled: !!busy || active || !canOpen || running, title };
}

export type StatusFilter = "all" | Phase | "attention";
export const statusFilters: readonly [StatusFilter, string][] = [["all", "全部"], ["reading", phases.reading.label], ["unstarted", phases.unstarted.label], ["completed", phases.completed.label], ["attention", "需处理"]];
export function needsAttention(status: SourceStatus, blog?: BlogStatus) {
  return status.operation?.kind === "parseFailed" || status.operation?.kind === "prepFailed" || !!blog?.error || Object.values(blog?.artifacts ?? {}).some(artifact => artifact.status === "failed");
}
export function matchesStatus(status: SourceStatus, filter: StatusFilter, blog?: BlogStatus) {
  return filter === "all" || (filter === "attention" ? needsAttention(status, blog) : status.phase === filter);
}
export function blogSummary(blog?: BlogStatus): { label: string; tone: Tone } {
  if (!blog) return { label: "博客状态未载入", tone: "muted" };
  const artifacts = Object.values(blog.artifacts ?? {});
  if (blog.executing || blog.runStatus === "running" || artifacts.some(a => a.status === "generating")) return { label: "生成中", tone: "accent" };
  if (blog.error || artifacts.some(a => a.status === "failed")) return { label: "部分失败", tone: "danger" };
  if (blog.generated && artifacts.length > 0 && artifacts.every(a => a.status === "completed")) return { label: "已完成", tone: "success" };
  return { label: "未生成", tone: "muted" };
}
