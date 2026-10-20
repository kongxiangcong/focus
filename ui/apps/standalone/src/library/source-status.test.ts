import { expect, it } from "vitest";
import type { BlogStatus, LibrarySource, ReadingPreparation } from "@focus/reader-contracts";
import { blogSummary, matchesStatus, needsAttention, primaryAction, sourceStatus } from "./source-status";
const source: LibrarySource = { sourceId: "a", title: "A", kind: "paper", parseStatus: "ready", error: null, noteCount: 0, topicIds: [], progress: { completed: 0, total: 4, planId: null, chunkId: null } };
const prep: ReadingPreparation = { source_id: "a", status: "running", step: "translate", total: 4, completed: 2, ready: false, error: null, plan_id: "p" };
const planned = { ...source, progress: { ...source.progress, planId: "p", chunkId: "c" } };
it.each([
  ["invalid", { ...source, parseStatus: "invalid" as const }, prep, false, "解析失败", "danger", ""],
  ["preparing", planned, prep, false, "准备中", "accent", "2/4 段"],
  ["prepFailed", planned, { ...prep, status: "failed" as const }, false, "准备失败", "warning", ""],
  ["completed", { ...planned, readingStatus: "completed" as const }, undefined, false, "已读完", "success", "4 段"],
  ["reading", { ...planned, progress: { ...planned.progress, completed: 1 } }, undefined, false, "阅读中", "accent", "1/4"],
  ["ready", planned, undefined, false, "可阅读", "muted", "4 段"],
  ["ready", source, { ...prep, status: "ready" as const, ready: true }, false, "可阅读", "muted", "4 段"],
  ["ready", planned, { ...prep, status: "failed" as const }, true, "可阅读", "muted", "4 段"],
  ["ready", planned, { ...prep, selected_ready: true }, false, "可阅读", "muted", "4 段"],
  ["unplanned", source, undefined, false, "待准备", "muted", ""],
])("maps %s with ordered preparation precedence", (phase, s, p, hidden, label, tone, detail) => {
  expect(sourceStatus(s, p, hidden)).toMatchObject({ phase, label, tone, detail });
});
it("preserves every valid-source primary label and lock from the original card expression", () => {
  for (const readingStatus of [undefined, "unplanned", "ready", "reading", "completed"] as const)
    for (const completed of [0, 1, 4]) for (const p of [undefined, ...["running", "ready", "failed", "cancelled", "interrupted", "bundle_changed", "commit_conflict"].flatMap(status => [false, true].flatMap(selected_ready => [false, true].map(ready => ({ ...prep, status, selected_ready, ready } as ReadingPreparation))))])
      for (const hidden of [false, true]) for (const busy of ["", "上传"]) for (const active of [false, true]) for (const canOpen of [false, true]) {
        const s = { ...planned, readingStatus, progress: { ...planned.progress, completed } };
        const originalStatus = s.readingStatus ?? (s.progress.planId && s.progress.chunkId === null ? "completed" : s.progress.completed ? "reading" : s.progress.planId ? "ready" : "unplanned");
        const failed = ["failed", "cancelled", "interrupted", "bundle_changed", "commit_conflict"].includes(p?.status ?? "");
        const label = p?.status === "running" && !p.selected_ready ? "阅读准备中…" : failed && !p?.selected_ready ? hidden ? "准备阅读" : "重试准备" : originalStatus === "completed" ? "查看已读" : s.progress.completed > 0 ? "继续阅读" : p?.selected_ready || p?.ready ? "开始阅读" : "准备阅读";
        expect(primaryAction(s, p, hidden, { busy, active, canOpen })).toEqual({ kind: "read", label, disabled: !!busy || active || !canOpen || (p?.status === "running" && !p.selected_ready), title: active ? "请先完成或停止当前问答" : busy ? `${busy}中` : undefined });
      }
});
it("invalid only inspects and never requires an available Host", () => {
  expect(primaryAction({ ...source, parseStatus: "invalid" }, prep, false, { busy: "上传", active: true, canOpen: false })).toMatchObject({ kind: "inspect", label: "查看问题", disabled: false });
});
it("filters phases and blog failures without extra data requests", () => {
  const status = sourceStatus(source);
  expect(matchesStatus(status, "all")).toBe(true); expect(matchesStatus(status, "unstarted")).toBe(true);
  expect(matchesStatus(status, "reading")).toBe(false); expect(matchesStatus(status, "completed")).toBe(false);
  const blog = { generated: true, artifacts: { html: { status: "failed" } } } as BlogStatus;
  expect(needsAttention(status, blog)).toBe(true); expect(matchesStatus(status, "attention", blog)).toBe(true);
  expect(needsAttention(status, { ...blog, artifacts: {}, error: { errorId: "x", message: "failure" } } as BlogStatus)).toBe(true);
});
it("summarizes missing, pending, generating, failed and completed blogs", () => {
  expect(blogSummary().tone).toBe("muted");
  const blog = { generated: false, artifacts: {} } as BlogStatus;
  expect(blogSummary(blog).label).toBe("未生成");
  expect(blogSummary({ ...blog, executing: true }).label).toBe("生成中");
  expect(blogSummary({ ...blog, error: { errorId: "x", message: "failure" } }).label).toBe("部分失败");
  expect(blogSummary({ ...blog, generated: true, artifacts: { html: { status: "completed" }, reading_blog: { status: "completed" } } } as BlogStatus).label).toBe("已完成");
});
