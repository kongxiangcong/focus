import { cursorReceipt } from "@focus/reader-contracts";
import { describe, expect, it } from "vitest";

import { FixtureReaderHost } from "./fixture-reader-host";

describe("FixtureReaderHost", () => {
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
