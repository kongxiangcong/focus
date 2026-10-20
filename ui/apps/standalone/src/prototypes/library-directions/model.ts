import type { DemoSource } from "./data";

/* One status vocabulary for every surface (row, card, inspector, filters).
   Replaces the two parallel mappings in WorkspaceApp (summary vs details). */

export type Phase = "invalid" | "preparing" | "prepFailed" | "unplanned" | "ready" | "reading" | "completed";

export function phaseOf(s: DemoSource): Phase {
  if (s.parseStatus !== "ready") return "invalid";
  if (s.preparing?.failed) return "prepFailed";
  if (s.preparing) return "preparing";
  if (s.progress.planId && s.progress.chunkId === null) return "completed";
  return s.readingStatus ?? (s.progress.completed > 0 ? "reading" : s.progress.planId ? "ready" : "unplanned");
}

export const phaseLabel: Record<Phase, string> = {
  invalid: "解析失败", preparing: "准备中", prepFailed: "准备失败", unplanned: "待准备", ready: "可阅读", reading: "阅读中", completed: "已读完",
};

/** Tone drives the small status mark only; text always carries the meaning. */
export const phaseTone: Record<Phase, "accent" | "muted" | "warning" | "danger" | "success"> = {
  invalid: "danger", preparing: "accent", prepFailed: "warning", unplanned: "muted", ready: "muted", reading: "accent", completed: "success",
};

export function statusDetail(s: DemoSource): string {
  const p = phaseOf(s);
  if (p === "preparing") return `${s.preparing!.completed}/${s.preparing!.total} 段`;
  if (p === "reading") return `${s.progress.completed}/${s.progress.total}`;
  if (p === "ready") return `${s.progress.total} 段`;
  if (p === "completed") return `${s.progress.total} 段`;
  return "";
}

export function progressRatio(s: DemoSource): number {
  const p = phaseOf(s);
  if (p === "preparing" || p === "prepFailed") return s.preparing!.completed / Math.max(1, s.preparing!.total);
  if (!s.progress.total) return 0;
  return s.progress.completed / s.progress.total;
}

/** Exactly one row-level action, named by the real state. */
export function primaryAction(s: DemoSource): { label: string; disabled?: boolean } {
  switch (phaseOf(s)) {
    case "invalid": return { label: "查看问题" };
    case "preparing": return { label: "准备中…", disabled: true };
    case "prepFailed": return { label: "重试准备" };
    case "unplanned": return { label: "准备阅读" };
    case "ready": return { label: "开始阅读" };
    case "reading": return { label: "继续阅读" };
    case "completed": return { label: "查看已读" };
  }
}

export type StatusFilter = "all" | "reading" | "unstarted" | "completed" | "attention";
export const statusFilters: [StatusFilter, string][] = [
  ["all", "全部"], ["reading", "阅读中"], ["unstarted", "未开始"], ["completed", "已读完"], ["attention", "需处理"],
];

export function needsAttention(s: DemoSource) {
  const p = phaseOf(s);
  return p === "invalid" || p === "prepFailed" || Object.values(s.blog.artifacts).includes("failed");
}

export function matchesStatus(s: DemoSource, f: StatusFilter) {
  const p = phaseOf(s);
  if (f === "all") return true;
  if (f === "reading") return p === "reading";
  if (f === "unstarted") return p === "ready" || p === "unplanned" || p === "preparing";
  if (f === "completed") return p === "completed";
  return needsAttention(s);
}

export function matchesQuery(s: DemoSource, q: string) {
  if (!q.trim()) return true;
  return [s.displayTitle, s.title, s.shortName, s.venue].filter(Boolean).join(" ").toLowerCase().includes(q.trim().toLowerCase());
}

export type BlogSummary = { tone: "none" | "running" | "done" | "failed"; label: string };
export function blogSummary(s: DemoSource): BlogSummary {
  const values = Object.values(s.blog.artifacts);
  if (!s.blog.generated) return { tone: "none", label: "未生成博客" };
  if (s.blog.running || values.includes("generating")) return { tone: "running", label: "博客生成中" };
  if (values.includes("failed")) return { tone: "failed", label: "博客部分失败" };
  return { tone: "done", label: "博客已完成" };
}

export function title(s: DemoSource) { return s.displayTitle || s.title; }

/** Presentation-only: "未归类" is not a Topic and has no manifest. */
export const UNFILED = "__unfiled__";
