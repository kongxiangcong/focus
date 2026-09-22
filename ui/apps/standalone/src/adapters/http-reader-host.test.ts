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

  it("uses the Inbox API and keeps staging separate from confirmation and processing", async () => {
    const item = { item_id: "abc", file_name: "paper.pdf", status: "awaiting_confirmation", topic_title: null, topic_id: "systems", source_id: null, document_status: "not_started", topic_status: "not_started" };
    const fetch = vi.fn<typeof globalThis.fetch>().mockResolvedValue(new Response(JSON.stringify({ ok: true, value: item })));
    const host = new HttpReaderHost({ baseUrl: "http://127.0.0.1:4317", fetch });
    const pdf = new File(["%PDF"], "paper.pdf", { type: "application/pdf" });
    await host.stageIngestion(pdf, { topicId: "systems" });
    await host.confirmIngestion("abc");
    await host.processIngestion("abc", "request-1");
    expect(fetch.mock.calls.map(([url]) => String(url))).toEqual([
      "http://127.0.0.1:4317/library/inbox?name=paper.pdf&topicId=systems",
      "http://127.0.0.1:4317/library/inbox/abc/confirm",
      "http://127.0.0.1:4317/library/inbox/abc/process",
    ]);
  });

  it("rejects a successful Inbox envelope whose value is not an array", async () => {
    const fetch = vi.fn<typeof globalThis.fetch>().mockResolvedValue(
      new Response(JSON.stringify({ ok: true, value: { item_id: "not-a-list" } })),
    );
    const host = new HttpReaderHost({ baseUrl: "http://127.0.0.1:4317", fetch });

    const result = await host.listInbox();

    expect(result).toEqual({
      ok: false,
      error: { code: "invalid-response", message: "Inbox 响应格式错误", retryable: false },
    });
  });

  it("sends an explicit resubmission with its risk choice and decodes the risk state", async () => {
    const item = {
      item_id: "abc", file_name: "paper.pdf", status: "status_check_required",
      topic_title: null, topic_id: "systems", source_id: null,
      document_status: "not_started", topic_status: "not_started",
      remote_reference: false, resubmit_risk: { choice_id: "choice-1" },
    };
    const fetch = vi.fn<typeof globalThis.fetch>().mockResolvedValue(
      new Response(JSON.stringify({ ok: true, value: item })),
    );
    const host = new HttpReaderHost({ baseUrl: "http://127.0.0.1:4317", fetch });

    const result = await host.resubmitIngestion("abc", "request-1", "choice-1");

    expect(result).toEqual({
      ok: true,
      value: {
        itemId: "abc", fileName: "paper.pdf", status: "status_check_required",
        topicTitle: null, topicId: "systems", sourceId: null,
        documentStatus: "not_started", topicStatus: "not_started",
        remoteReference: false, resubmitRisk: { choiceId: "choice-1" },
      },
    });
    expect(fetch).toHaveBeenCalledWith("http://127.0.0.1:4317/library/inbox/abc/resubmit", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ requestId: "request-1", riskChoiceId: "choice-1" }),
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
