import type { ReadingWindow } from "@focus/reader-contracts";
import { afterEach, describe, expect, it, vi } from "vitest";

import { HttpReaderHost } from "./http-reader-host";

const completedWindow: ReadingWindow = {
  status: "completed",
  source: { sourceId: "fixture-paper", title: "Fixture Paper", topicId: null },
  current: null,
  history: [],
  conversation: [],
};

describe("HttpReaderHost", () => {
  it("normalizes the HTTP host behind ReaderHost", async () => {
    const fetch = vi.fn<typeof globalThis.fetch>().mockResolvedValue(
      new Response(JSON.stringify({ ok: true, value: completedWindow }), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    );
    const host = new HttpReaderHost({ baseUrl: "http://127.0.0.1:4317/", fetch });

    const result = await host.getReadingWindow();

    expect(result).toEqual({ ok: true, value: completedWindow });
    expect(fetch).toHaveBeenCalledWith("http://127.0.0.1:4317/reader/window", {
      method: "GET",
      signal: undefined,
    });
  });

  it("rejects a successful HTTP envelope with an invalid body", async () => {
    const fetch = vi.fn<typeof globalThis.fetch>().mockResolvedValue(
      new Response(JSON.stringify({ ok: true, value: { status: "reading" } }), { status: 200 }),
    );
    const host = new HttpReaderHost({ baseUrl: "http://127.0.0.1:4317", fetch });

    const result = await host.getReadingWindow();

    expect(result).toEqual({
      ok: false,
      error: {
        code: "invalid-response",
        message: "The Focus host returned an invalid response.",
        retryable: false,
      },
    });
  });
});


afterEach(() => vi.unstubAllGlobals());
it("sends both HTTP actions without randomUUID and preserves supplied retry IDs", async () => {
  const getRandomValues = globalThis.crypto.getRandomValues.bind(globalThis.crypto);
  vi.stubGlobal("crypto", { getRandomValues });
  const fetch = vi.fn<typeof globalThis.fetch>().mockImplementation(async () =>
    new Response(JSON.stringify({ ok: true, value: completedWindow })));
  const host = new HttpReaderHost({ baseUrl: "http://192.168.1.10:4317", fetch });
  const receipt = { sourceId: "fixture-paper", planId: "plan-001", chunkId: "chunk-001" };
  expect((await host.continueReading({ receipt })).ok).toBe(true);
  expect((await host.sendMessage({ receipt, content: "解释这段" })).ok).toBe(true);
  const ids = fetch.mock.calls.map(([, init]) => JSON.parse(init!.body as string).requestId);
  expect(ids[0]).toMatch(/^[a-f0-9]{8}-[a-f0-9]{4}-4[a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12}$/);
  expect(ids[1]).toMatch(/^[a-f0-9-]{36}$/);
  expect(ids[1]).not.toBe(ids[0]);
  await host.continueReading({ receipt, requestId: ids[0] });
  expect(JSON.parse(fetch.mock.calls[2][1]!.body as string).requestId).toBe(ids[0]);
});
