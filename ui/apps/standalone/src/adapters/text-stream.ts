import type { ReadingWindow, ReaderMessage } from "@focus/reader-contracts";

/** Absolute message replacements tolerate coalesced tokens without replaying text. */
export function mergeText(view: ReadingWindow, update: {
  baseRevision: number; revision: number; sessionId: string; instanceId: string;
  messages: readonly ReaderMessage[]; run: NonNullable<ReadingWindow["agent"]>["run"];
}): ReadingWindow {
  if (update.sessionId !== view.sessionId || update.instanceId !== view.workspace?.instanceId ||
      update.baseRevision !== view.revision || !Number.isSafeInteger(update.revision) || update.revision <= update.baseRevision ||
      !Array.isArray(update.messages) || update.messages.some(m => typeof m.messageId !== "string" || typeof m.content !== "string")) {
    throw new Error("Stream baseline changed");
  }
  const visible = update.messages.filter(m => !view.discussionId || m.discussionId === view.discussionId || m.sourceDeleted);
  const replacements = new Map(visible.map(m => [m.messageId, m]));
  const conversation = view.conversation.map(m => { const next = replacements.get(m.messageId); replacements.delete(m.messageId); return next ?? m; });
  conversation.push(...replacements.values());
  const added = visible.filter(m => !(view.timeline ?? []).some(e => e.kind === "message" && e.messageId === m.messageId));
  return { ...view, revision: update.revision, conversation,
    timeline: added.length ? [...(view.timeline ?? []), ...added.map(m => ({ kind: "message" as const, messageId: m.messageId }))] : view.timeline,
    agent: view.agent ? { ...view.agent, run: update.run } : view.agent };
}
