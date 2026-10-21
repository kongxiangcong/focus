import { describe, expect, it } from "vitest";
import { groupReadingDiscussion } from "./FocusReader";
const reading = (chunkId: string) => ({ kind: "reading" as const, chunk: { chunkId } });
const message = (messageId: string) => ({ kind: "message" as const, messageId });
const entries = [message("leading"), reading("a"), message("first"), reading("b"), message("back"), reading("a"), message("repeat")];
const group = () => groupReadingDiscussion(entries, entries.map((_, i) => String(i)));
describe("chronological discussion grouping", () => {
  it("keeps messages before any reading at the top", () => {
    expect(group()[0]).toEqual({ id: "leading-discussion", chunk: null, indexes: [0] });
  });
  it("keeps replies in reading order, including after revisiting a paragraph", () => {
    expect(group().map(g => g.indexes)).toEqual([[0], [1, 2], [3, 4], [5, 6]]);
    expect(group().flatMap(g => g.indexes)).toEqual(entries.map((_, i) => i));
  });
  it("does not carry occurrences into a new session", () => {
    expect(groupReadingDiscussion([message("back")], ["back"])[0].chunk).toBeNull();
  });
});
