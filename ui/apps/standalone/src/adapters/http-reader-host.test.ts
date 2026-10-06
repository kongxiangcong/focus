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

it('clears status notifications through the bound Host and decodes inbox dismissal', async () => {
  const boundWindow = { ...completedWindow, workspace: { workspaceId: 'workspace', instanceId: 'instance', path: '/workspace' } };
  const fetch = vi.fn<typeof globalThis.fetch>()
    .mockResolvedValueOnce(new Response(JSON.stringify({ ok: true, value: boundWindow })))
    .mockResolvedValueOnce(new Response(JSON.stringify({ ok: true, value: [{
      item_id: 'item', file_name: 'paper.pdf', status: 'failed', topic_title: null,
      topic_id: null, source_id: null, document_status: 'failed', topic_status: 'not_started', dismissed: true,
    }] })));
  const host = new HttpReaderHost({ baseUrl: 'http://127.0.0.1:4317', fetch, instanceId: 'instance' });
  expect(await host.clearFinishedStatuses('clear-1')).toEqual({ ok: true, value: boundWindow });
  const [, request] = fetch.mock.calls[0];
  expect(request?.method).toBe('POST');
  expect(new Headers(request?.headers).get('X-FOCUS-Instance')).toBe('instance');
  expect(JSON.parse(request?.body as string)).toEqual({ requestId: 'clear-1' });
  expect(await host.listInbox()).toMatchObject({ ok: true, value: [{ itemId: 'item', dismissed: true }] });
});

it('accepts batches without an associated topic, including control responses', async () => {
  const batch = {
    batchId: 'deleted-topic-batch', topicId: null, status: 'partial', error: null,
    items: [{ itemId: 'deleted-item', fileName: 'paper.pdf', sourceId: null,
      status: 'deleted', ingestionStatus: 'cancelled', blog: null, error: null }],
  };
  const fetch = vi.fn<typeof globalThis.fetch>()
    .mockResolvedValueOnce(new Response(JSON.stringify({ ok: true, value: [batch] })))
    .mockResolvedValueOnce(new Response(JSON.stringify({ ok: true, value: batch })));
  const host = new HttpReaderHost({ baseUrl: 'http://127.0.0.1:4317', fetch });
  expect(await host.listBatches()).toEqual({ ok: true, value: [batch] });
  expect(await host.controlBatch(batch.batchId, 'stop', 'request-1')).toEqual({ ok: true, value: batch });
});

it.each([undefined, 123, {}])('rejects a malformed batch topic %j', async topicId => {
  const fetch = vi.fn<typeof globalThis.fetch>().mockResolvedValue(new Response(JSON.stringify({
    ok: true, value: [{ batchId: 'batch', topicId, status: 'partial', items: [], error: null }],
  })));
  const host = new HttpReaderHost({ baseUrl: '', fetch });
  expect(await host.listBatches()).toMatchObject({ ok: false, error: { code: 'invalid-response' } });
});

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
    await host.confirmIngestion("abc", true);
    await host.processIngestion("abc", "request-1");
    expect(fetch.mock.calls.map(([url]) => String(url))).toEqual([
      "http://127.0.0.1:4317/library/inbox?name=paper.pdf&topicId=systems",
      "http://127.0.0.1:4317/library/inbox/abc/confirm",
      "http://127.0.0.1:4317/library/inbox/abc/process",
    ]);
    expect(JSON.parse(fetch.mock.calls[1][1]!.body as string)).toEqual({ generateBlog: true });
  });

  it("sends generation and artifact retry as POST with the requested IDs", async () => {
    const status = {
      sourceId: "fixture-paper", generated: true, artifacts: {}, warnings: [],
    };
    const fetch = vi.fn<typeof globalThis.fetch>().mockImplementation(async () =>
      new Response(JSON.stringify({ ok: true, value: status })),
    );
    const host = new HttpReaderHost({ baseUrl: "http://127.0.0.1:4317", fetch });

    expect((await host.generateBlog("fixture-paper", "generate-1")).ok).toBe(true);
    expect((await host.regenerateBlog("fixture-paper", "retry-1", "value_analysis")).ok).toBe(true);
    expect((await host.cancelBlog("fixture-paper")).ok).toBe(true);
    expect(fetch.mock.calls).toEqual([
      ["http://127.0.0.1:4317/library/sources/fixture-paper/blog/generate", {
        method: "POST", headers: { "content-type": "application/json" },
        body: JSON.stringify({ requestId: "generate-1" }),
      }],
      ["http://127.0.0.1:4317/library/sources/fixture-paper/blog/regenerate", {
        method: "POST", headers: { "content-type": "application/json" },
        body: JSON.stringify({ requestId: "retry-1", artifact: "value_analysis" }),
      }],
      ["http://127.0.0.1:4317/library/sources/fixture-paper/blog/cancel", {
        method: "POST", headers: { "content-type": "application/json" }, body: "{}",
      }],
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


it("dismisses only the referenced preparation attempt through its dedicated endpoint", async () => {
  const fetch = vi.fn<typeof globalThis.fetch>().mockResolvedValue(new Response(JSON.stringify({ ok: true, value: completedWindow }), { status: 200 }));
  const host = new HttpReaderHost({ baseUrl: "http://127.0.0.1:4317", fetch });
  expect(await host.dismissPreparation("Model A-paper", "attempt-1")).toEqual({ ok: true, value: completedWindow });
  expect(fetch).toHaveBeenCalledWith("http://127.0.0.1:4317/library/sources/Model%20A-paper/preparation/dismiss", {
    method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ attempt: "attempt-1" }),
  });
});
