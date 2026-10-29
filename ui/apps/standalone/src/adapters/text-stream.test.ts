import { expect, it } from "vitest";
import type { ReadingWindow, ReaderMessage } from "@focus/reader-contracts";
import { mergeText } from "./text-stream";
const message: ReaderMessage = { messageId: "reply", chunkId: "", role: "assistant", content: "a", discussionId: "discussion" };
const baseline: ReadingWindow = { status: "empty", source: { sourceId: "paper", title: "Paper", topicId: null },
  current: null, history: [], conversation: [message], timeline: [{ kind: "message", messageId: "reply" }],
  workspace: { workspaceId: "w", instanceId: "instance", path: "/fixture" }, sessionId: "session", discussionId: "discussion", revision: 10,
  figures: [], sourceNotes: [], sourceHighlights: [] };
const update = { baseRevision: 10, revision: 15, sessionId: "session", instanceId: "instance", messages: [{ ...message, content: "完整答案🙂" }], run: null };
it("replaces absolute text, preserves stable projections and never duplicates timeline entries", () => {
  const result = mergeText(baseline, update);
  expect(result.conversation[0].content).toBe("完整答案🙂");
  for (const key of ["history", "current", "source", "figures", "sourceNotes", "sourceHighlights", "timeline"] as const) expect(result[key]).toBe(baseline[key]);
  expect(mergeText(result, {...update, baseRevision:15, revision:16}).conversation).toHaveLength(1);
});
it("adds a new visible message once while keeping unchanged historical objects", () => {
  const result = mergeText(baseline, {...update, messages:[{...message,messageId:"new"}]});
  expect(result.conversation[0]).toBe(message);
  expect(result.timeline).toHaveLength(2);
  expect(mergeText(result,{...update, baseRevision:15, revision:16,messages:[{...message,messageId:"new",content:"ab"}]}).timeline).toBe(result.timeline);
});
it.each([{sessionId:"cleared"}, {instanceId:"other-workspace"}, {baseRevision:9}, {revision:10}])("rejects stale sessions, instances and revisions %j", change => {
  expect(() => mergeText(baseline, {...update,...change})).toThrow();
});
it("filters output for another source discussion", () => {
  expect(mergeText(baseline,{...update,messages:[{...message,discussionId:"other"}]}).conversation[0]).toBe(message);
});
