import { cursorReceipt } from "@focus/reader-contracts";
import { describe, expect, it } from "vitest";

import { FixtureReaderHost } from "./fixture-reader-host";

describe("FixtureReaderHost", () => {
  it("reports an explicit annotation clear generation and revokes saved recovery receipts", async () => {
    const host = new FixtureReaderHost();
    const loaded = await host.getReadingWindow();
    if (!loaded.ok || !loaded.value.current) throw new Error("fixture did not load");
    const chunk = loaded.value.current;
    const selection = { layer: "source" as const, range: { start: 0, end: 7 }, quote: { exact: "Fixture", prefix: "", suffix: "" } };
    const highlight = { sourceId: chunk.sourceId, requestId: "clear-highlight", chunk: { planId: chunk.planId, chunkId: chunk.chunkId }, ...selection };
    const note = { sourceId: chunk.sourceId, requestId: "clear-note", content: "Remark", kind: "thought" as const,
      origin: "user" as const, chunk: highlight.chunk, sentence: selection };
    expect((await host.createHighlight(highlight)).ok).toBe(true);
    expect((await host.createSourceNote(note)).ok).toBe(true);
    const fresh = await host.newSession();
    if (!fresh.ok) throw new Error("fresh session failed");
    expect(fresh.value.noteClearVersion).toBe(0);
    expect(fresh.value.sourceHighlights).toHaveLength(1);
    const cleared = await host.clearSource(chunk.sourceId, "clear-operation");
    if (!cleared.ok) throw new Error("clear failed");
    expect(cleared.value.noteClearVersion).toBe(1);
    expect(cleared.value.sourceHighlights).toEqual([]);
    expect(cleared.value.sourceNotes).toEqual([]);
    expect(cleared.value.highlightOperation).toBeUndefined();
    expect(cleared.value.noteOperation).toBeUndefined();
    expect(await host.highlightRequestResult(chunk.sourceId, highlight.requestId)).toEqual({ ok: true, value: { status: "cancelled" } });
    expect(await host.sourceNoteRequestResult(chunk.sourceId, note.requestId)).toEqual({ ok: true, value: { status: "cancelled" } });
    expect((await host.createHighlight(highlight)).ok).toBe(false);
    const replay = await host.clearSource(chunk.sourceId, "clear-operation");
    if (!replay.ok) throw new Error("clear replay failed");
    expect(replay.value.noteClearVersion).toBe(1);
  });
  it("advances only with the current receipt", async () => {
    const host = new FixtureReaderHost();
    const initial = await host.getReadingWindow();
    expect(initial.ok).toBe(true);
    if (!initial.ok) return;

    const receipt = cursorReceipt(initial.value);
    expect(receipt).not.toBeNull();
    const advanced = await host.continueReading({ receipt: receipt! });
    expect(advanced.ok).toBe(true);
    if (!advanced.ok) return;
    expect(advanced.value.current?.chunkId).toBe("chunk-002");
    expect(advanced.value.history.map((chunk) => chunk.chunkId)).toEqual(["chunk-001"]);

    const stale = await host.continueReading({ receipt: receipt! });
    expect(stale).toEqual({
      ok: false,
      error: {
        code: "cursor-changed",
        message: "The Reading Cursor changed before Continue Reading completed.",
        retryable: false,
      },
    });
  });

  it("projects complete ordered history for the Reader UI", async () => {
    const host = new FixtureReaderHost();

    for (const expectedChunkId of ["chunk-002", "chunk-003", "chunk-004"]) {
      const before = await host.getReadingWindow();
      if (!before.ok) throw new Error("fixture failed to load");
      const receipt = cursorReceipt(before.value);
      if (receipt === null) throw new Error("fixture completed too early");
      const advanced = await host.continueReading({ receipt });
      if (!advanced.ok) throw new Error("fixture failed to advance");
      expect(advanced.value.current?.chunkId).toBe(expectedChunkId);
    }

    const current = await host.getReadingWindow();
    if (!current.ok) throw new Error("fixture failed to load");
    expect(current.value.history.map((chunk) => chunk.chunkId)).toEqual([
      "chunk-001",
      "chunk-002",
      "chunk-003",
    ]);
  });

  it("keeps questions on the current chunk without advancing", async () => {
    const host = new FixtureReaderHost();
    const initial = await host.getReadingWindow();
    if (!initial.ok) throw new Error("fixture failed to load");
    const receipt = cursorReceipt(initial.value)!;

    const result = await host.sendMessage({ receipt, content: "What remains authoritative?" });

    expect(result.ok).toBe(true);
    if (!result.ok) return;
    expect(result.value.current?.chunkId).toBe("chunk-001");
    expect(result.value.conversation.map((message) => message.role)).toEqual(["user", "assistant"]);
  });
});
