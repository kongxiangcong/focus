import { describe, expect, it } from "vitest";
import { groupReadingDiscussion } from "./FocusReader";
const reading = (chunkId: string) => ({kind: "reading" as const, chunk: {chunkId}});
const message = (messageId: string) => ({kind: "message" as const, messageId});
const entries = [message("leading"), reading("a"), message("first"), reading("b"), message("back"), message("none"), message("missing"), reading("a"), message("repeat"), message("b-ref")];
const messages = [ {messageId:"leading", reference:{chunkId:"a"}}, {messageId:"first", reference:{chunkId:"a"}}, {messageId:"back", reference:{chunkId:"a"}}, {messageId:"none"}, {messageId:"missing", reference:{chunkId:"future"}}, {messageId:"repeat", reference:{chunkId:"a"}}, {messageId:"b-ref", reference:{chunkId:"b"}} ];
const group = (attached: boolean) => groupReadingDiscussion(entries, entries.map((_,i)=>String(i)), messages, attached);
describe("manual discussion grouping", () => {
 it("keeps messages before any reading at the top, even with a future reference", () => { expect(group(true)[0]).toEqual({id:"leading-discussion", chunk:null, indexes:[0]}); });
 it("uses the nearest preceding occurrence, never a later revisit", () => { expect(group(true).map(g=>g.indexes)).toEqual([[0],[1,2,4],[3,5,6,9],[7,8]]); });
 it("falls back to the chronological previous group for absent or unknown references", () => { expect(group(true)[2].indexes).toContain(5); expect(group(true)[2].indexes).toContain(6); });
 it("restores chronological order in flow mode without mutating inputs", () => { group(true); expect(group(false).map(g=>g.indexes)).toEqual([[0],[1,2],[3,4,5,6],[7,8,9]]); });
 it("does not carry occurrences into a new session", () => { expect(groupReadingDiscussion([message("back")],["back"],messages,true)[0].chunk).toBeNull(); });
});
