import type { ReadingWindow } from "@focus/reader-contracts";
import { describe, expect, it, vi } from "vitest";

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
