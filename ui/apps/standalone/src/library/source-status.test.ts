import { expect, it } from "vitest";
import type { BlogStatus, LibrarySource, ReadingPreparation } from "@focus/reader-contracts";
import { blogSummary, matchesStatus, needsAttention, primaryAction, sourceStatus } from "./source-status";
const source: LibrarySource = { sourceId: "a", title: "A", kind: "paper", parseStatus: "ready", error: null, noteCount: 0, topicIds: [], progress: { completed: 0, total: 4, planId: null, chunkId: null } };
const prep: ReadingPreparation = { source_id: "a", status: "running", step: "translate", total: 4, completed: 2, ready: false, error: null, plan_id: "p" };
const planned = { ...source, progress: { ...source.progress, planId: "p", chunkId: "c" } };
it.each([
  ["unselected", source, undefined, false, "unstarted", 0, 0, undefined],
  ["selected", planned, undefined, false, "unstarted", 0, 4, undefined],
  ["prepared", source, { ...prep, status: "ready" as const, ready: true }, false, "unstarted", 0, 0, undefined],
  ["entered", { ...planned, readingStatus: "reading" as const }, undefined, false, "reading", 0, 4, undefined],
  ["advanced", { ...planned, progress: { ...planned.progress, completed: 1 } }, undefined, false, "reading", 1, 4, undefined],
  ["completed", { ...planned, progress: { ...planned.progress, completed: 4, chunkId: null } }, undefined, false, "completed", 4, 4, undefined],
  ["legacy completion", { ...planned, readingStatus: "completed" as const }, undefined, false, "unstarted", 0, 4, undefined],
  ["preparing", planned, prep, false, "unstarted", 0, 4, "准备中"],
  ["failed", planned, { ...prep, status: "failed" as const }, false, "unstarted", 0, 4, "准备失败"],
  ["dismissed failure", planned, { ...prep, status: "failed" as const }, true, "unstarted", 0, 4, undefined],
  ["invalid", { ...source, parseStatus: "invalid" as const }, prep, false, "unstarted", 0, 0, "解析失败"],
])("projects reading and operational status for %s", (_name, s, p, hidden, phase, completed, total, operation) => {
  const status = sourceStatus(s, p, hidden);
  expect(status).toMatchObject({ phase, progress: { completed, total } });
  expect(status.operation?.label).toBe(operation);
});

it.each([
  [source, undefined, false, "准备阅读", false],
  [planned, prep, false, "阅读准备中…", true],
  [planned, { ...prep, status: "failed" as const }, false, "重试准备", false],
  [planned, { ...prep, status: "failed" as const }, true, "准备阅读", false],
  [planned, { ...prep, status: "ready" as const, ready: true }, false, "开始阅读", false],
  [{ ...planned, readingStatus: "reading" as const }, undefined, false, "继续阅读", false],
  [{ ...planned, progress: { ...planned.progress, completed: 4, chunkId: null } }, undefined, false, "查看已读", false],
])("offers the appropriate primary action for the reading state (%#)", (s, p, hidden, label, disabled) => {
  expect(primaryAction(s, p, hidden, { busy: "", active: false, canOpen: true })).toMatchObject({ kind: "read", label, disabled });
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
