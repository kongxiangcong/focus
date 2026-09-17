import {
  type LibrarySource,
  type LibraryTopic,
  type ContinueReadingInput,
  type ReaderApprovalResponse,
  type ReaderAttachment,
  type ReaderFailureCode,
  type ReaderHost,
  type ReaderHostResult,
  type ReadingWindow,
  type SendReaderMessageInput,
} from "@focus/reader-contracts";

type Fetch = typeof fetch;

export interface HttpReaderHostOptions {
  baseUrl: string;
  fetch?: Fetch;
}

function isStringArray(value: unknown): value is readonly string[] {
  return Array.isArray(value) && value.every((item) => typeof item === "string");
}

function isReaderChunk(value: unknown): value is NonNullable<ReadingWindow["current"]> {
  if (typeof value !== "object" || value === null) {
    return false;
  }
  const chunk = value as Record<string, unknown>;
  return (
    typeof chunk.sourceId === "string" &&
    typeof chunk.planId === "string" &&
    typeof chunk.chunkId === "string" &&
    typeof chunk.index === "number" &&
    typeof chunk.total === "number" &&
    isStringArray(chunk.sectionPath) &&
    Array.isArray(chunk.sourceLines) &&
    chunk.sourceLines.length === 2 &&
    chunk.sourceLines.every((line) => typeof line === "number") &&
    typeof chunk.sourceMarkdown === "string" &&
    (chunk.translation === null || typeof chunk.translation === "string") &&
    Array.isArray(chunk.images) &&
    Array.isArray(chunk.relevantGlossary) &&
    ["source-ready", "translation-required", "presented"].includes(String(chunk.presentationStatus))
  );
}

function isReadingWindow(value: unknown): value is ReadingWindow {
  if (typeof value !== "object" || value === null) {
    return false;
  }
  const candidate = value as Partial<ReadingWindow>;
  return (
    (["empty", "reading", "completed"].includes(String(candidate.status))) &&
    typeof candidate.source === "object" &&
    candidate.source !== null &&
    typeof candidate.source.sourceId === "string" &&
    typeof candidate.source.title === "string" &&
    (candidate.source.topicId === null || typeof candidate.source.topicId === "string") &&
    (candidate.outline === undefined || (Array.isArray(candidate.outline) && candidate.outline.every(item =>
      item && typeof item.chunkId === "string" && typeof item.index === "number" && isStringArray(item.sectionPath)))) &&
    Array.isArray(candidate.history) &&
    candidate.history.every(isReaderChunk) &&
    Array.isArray(candidate.conversation) &&
    candidate.conversation.every(
      (message) =>
        typeof message === "object" &&
        message !== null &&
        typeof message.messageId === "string" &&
        typeof message.chunkId === "string" &&
        (message.role === "user" || message.role === "assistant") &&
        typeof message.content === "string",
    ) &&
    (candidate.current === null || isReaderChunk(candidate.current)) &&
    (((candidate.status === "completed" || candidate.status === "empty") && candidate.current === null) ||
      (candidate.status === "reading" && candidate.current !== null))
  );
}

function isFailureCode(value: unknown): value is ReaderFailureCode {
  return ["cursor-changed", "invalid-request", "invalid-response", "unavailable", "unknown"].includes(
    String(value),
  );
}

function decodeResult(value: unknown): ReaderHostResult<ReadingWindow> {
  if (typeof value !== "object" || value === null || !("ok" in value)) {
    return {
      ok: false,
      error: { code: "invalid-response", message: "The Focus host returned an invalid response.", retryable: false },
    };
  }
  const candidate = value as Record<string, unknown>;
  if (candidate.ok === true && isReadingWindow(candidate.value)) {
    return { ok: true, value: candidate.value };
  }
  if (candidate.ok === false && typeof candidate.error === "object" && candidate.error !== null) {
    const error = candidate.error as Record<string, unknown>;
    if (isFailureCode(error.code) && typeof error.message === "string" && typeof error.retryable === "boolean") {
      return {
        ok: false,
        error: { code: error.code, message: error.message, retryable: error.retryable },
      };
    }
  }
  return {
    ok: false,
    error: { code: "invalid-response", message: "The Focus host returned an invalid response.", retryable: false },
  };
}

export class HttpReaderHost implements ReaderHost {
  private readonly baseUrl: string;
  private readonly fetch: Fetch;

  constructor(options: HttpReaderHostOptions) {
    this.baseUrl = options.baseUrl.replace(/\/$/, "");
    this.fetch = options.fetch ?? globalThis.fetch.bind(globalThis);
  }

  async listTopics(): Promise<ReaderHostResult<readonly LibraryTopic[]>> {
    return this.libraryList<LibraryTopic>("/library/topics", item => typeof item.topicId === "string" && typeof item.title === "string" && isStringArray(item.sourceIds));
  }

  async listSources(): Promise<ReaderHostResult<readonly LibrarySource[]>> {
    return this.libraryList<LibrarySource>("/library/sources", item => {
      const progress = item.progress as LibrarySource["progress"] | undefined;
      return typeof item.sourceId === "string" && typeof item.title === "string" &&
        ["paper", "article"].includes(String(item.kind)) && ["ready", "invalid"].includes(String(item.parseStatus)) &&
        (item.error === null || typeof item.error === "string") && typeof item.noteCount === "number" &&
        isStringArray(item.topicIds) && !!progress && typeof progress.completed === "number" && typeof progress.total === "number" &&
        (progress.planId === null || typeof progress.planId === "string") && (progress.chunkId === null || typeof progress.chunkId === "string");
    });
  }

  private async libraryList<T>(path: string, validate: (item: Record<string, unknown>) => boolean): Promise<ReaderHostResult<readonly T[]>> {
    try {
      const response = await this.fetch(`${this.baseUrl}${path}`);
      const body = await response.json();
      if (response.ok && body.ok === true && Array.isArray(body.value) && body.value.every((x: unknown) =>
        x !== null && typeof x === "object" && validate(x as Record<string, unknown>))) return { ok: true, value: body.value };
      return { ok: false, error: { code: "invalid-response", message: body.error?.message ?? "知识库响应格式错误", retryable: false } };
    } catch (e) { return { ok: false, error: { code: "unavailable", message: String(e), retryable: true } }; }
  }

  uploadSource(file: File): Promise<ReaderHostResult<ReadingWindow>> {
    return this.request(`/library/sources?name=${encodeURIComponent(file.name)}`, { method: "POST", body: file });
  }
  deleteSource(sourceId: string): Promise<ReaderHostResult<ReadingWindow>> {
    return this.request(`/library/sources/${encodeURIComponent(sourceId)}`, { method: "DELETE" });
  }
  rereadSource(sourceId: string): Promise<ReaderHostResult<ReadingWindow>> {
    return this.request(`/library/sources/${encodeURIComponent(sourceId)}/reread`, { method: "POST", headers: { "content-type": "application/json" }, body: "{}" });
  }
  openSource(sourceId: string): Promise<ReaderHostResult<ReadingWindow>> {
    return this.request(`/library/sources/${encodeURIComponent(sourceId)}/open`, { method: "POST", headers: { "content-type": "application/json" }, body: "{}" });
  }

  getReadingWindow(signal?: AbortSignal): Promise<ReaderHostResult<ReadingWindow>> {
    return this.request("/reader/window", { method: "GET", signal });
  }

  continueReading(
    input: ContinueReadingInput,
    signal?: AbortSignal,
  ): Promise<ReaderHostResult<ReadingWindow>> {
    return this.request("/reader/continue", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ ...input, requestId: input.requestId ?? crypto.randomUUID() }),
      signal,
    });
  }

  sendMessage(
    input: SendReaderMessageInput,
    signal?: AbortSignal,
  ): Promise<ReaderHostResult<ReadingWindow>> {
    return this.request("/reader/messages", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ ...input, requestId: input.requestId ?? crypto.randomUUID() }),
      signal,
    });
  }

  newSession(sessionId: string): Promise<ReaderHostResult<ReadingWindow>> {
    return this.request("/reader/session", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ sessionId }) });
  }

  selectBackend(backend: string, sessionId: string): Promise<ReaderHostResult<ReadingWindow>> {
    return this.request('/reader/backend', { method: 'POST', headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ backend, sessionId }) });
  }

  resumeReading(sessionId: string): Promise<ReaderHostResult<ReadingWindow>> {
    return this.request("/reader/resume", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ sessionId }) });
  }

  stop(): Promise<ReaderHostResult<ReadingWindow>> {
    return this.request("/reader/stop", { method: "POST", headers: { "content-type": "application/json" }, body: "{}" });
  }

  approve(input: ReaderApprovalResponse): Promise<ReaderHostResult<ReadingWindow>> {
    return this.request("/reader/approval", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(input) });
  }

  async upload(file: File): Promise<ReaderHostResult<ReaderAttachment>> {
    try {
      const response = await this.fetch(`${this.baseUrl}/reader/upload?name=${encodeURIComponent(file.name)}`, {
        method: "POST", body: file,
      });
      const result = await response.json();
      if (result.ok && typeof result.value?.attachmentId === "string" && typeof result.value?.name === "string") return result;
      return { ok: false, error: { code: "invalid-request", message: result.error?.message ?? "上传失败", retryable: false } };
    } catch (error) {
      return { ok: false, error: { code: "unavailable", message: String(error), retryable: true } };
    }
  }

  subscribe(listener: (result: ReaderHostResult<ReadingWindow>) => void): () => void {
    const stream = new EventSource(`${this.baseUrl}/reader/events`);
    stream.addEventListener("snapshot", (event) => {
      try { listener(decodeResult(JSON.parse((event as MessageEvent).data))); }
      catch { listener({ ok: false, error: { code: "invalid-response", message: "任务状态流格式错误", retryable: true } }); }
    });
    stream.onerror = () => listener({ ok: false, error: { code: "unavailable", message: "连接中断，正在恢复；后台任务可能仍在运行。", retryable: true } });
    return () => stream.close();
  }

  private async request(path: string, init: RequestInit): Promise<ReaderHostResult<ReadingWindow>> {
    try {
      const response = await this.fetch(`${this.baseUrl}${path}`, init);
      if (!response.ok) {
        const body = await response.json().catch(() => null);
        if (body?.ok === false) return decodeResult(body);
        return {
          ok: false,
          error: {
            code: "unavailable",
            message: `The Focus host request failed with HTTP ${response.status}.`,
            retryable: response.status >= 500,
          },
        };
      }
      return decodeResult(await response.json());
    } catch (error) {
      if (init.signal?.aborted) {
        return {
          ok: false,
          error: { code: "unavailable", message: "The Focus host request was cancelled.", retryable: true },
        };
      }
      return {
        ok: false,
        error: {
          code: "unavailable",
          message: error instanceof Error ? error.message : "The Focus host is unavailable.",
          retryable: true,
        },
      };
    }
  }
}
