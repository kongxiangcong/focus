import { createReaderId,
  type BackendSetupAction, type BackendSetupInput, type BackendSetupResult,
  type BlogRegenerationTarget,
  type BlogStatus,
  type LibrarySource,
  type IngestionItem,
  type ProcessingBatch,
  type SourceDeletionImpact,
  type IngestionTarget,
  type LibraryTopic,
  type ContinueReadingInput,
  type FinishReadingInput,
  type RereadReadingInput,
  type ReaderApprovalResponse,
  type ReaderAttachment,
  type ReaderFailureCode,
  type ReaderHost,
  type ReaderHostResult,
  type ReadingWindow,
  type SendReaderMessageInput,
  type SourceNoteRequestResult,
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

function isRiskChoice(value: unknown): value is { choice_id: string } {
  return typeof value === "object" && value !== null && typeof (value as Record<string, unknown>).choice_id === "string";
}

function decodeIngestionItem(value: unknown): IngestionItem | null {
  if (value === null || typeof value !== "object") return null;
  const item = value as Record<string, unknown>;
  if (!(typeof item.item_id === "string" && typeof item.file_name === "string" &&
    typeof item.status === "string" && (item.topic_title === null || typeof item.topic_title === "string") &&
    (item.topic_id === null || typeof item.topic_id === "string") &&
    (item.source_id === null || typeof item.source_id === "string") &&
    typeof item.document_status === "string" && typeof item.topic_status === "string")) return null;
  const error = item.error as Record<string, unknown> | undefined;
  const topicError = item.topic_error as Record<string, unknown> | undefined;
  return {
    itemId: item.item_id, fileName: item.file_name, status: item.status as IngestionItem["status"],
    topicTitle: item.topic_title as string | null, topicId: item.topic_id as string | null,
    sourceId: item.source_id as string | null, documentStatus: item.document_status,
    topicStatus: item.topic_status,
    services: isStringArray(item.services) ? item.services : undefined,
    confirmation: item.confirmation as IngestionItem["confirmation"],
    ...(item.duplicate === true ? { duplicate: true } : {}),
    ...(typeof item.remote_reference === "boolean" ? { remoteReference: item.remote_reference } : {}),
    ...(isRiskChoice(item.resubmit_risk) ? { resubmitRisk: { choiceId: item.resubmit_risk.choice_id } } : {}),
    ...(error && typeof error.message === "string" ? { error: { errorId: String(error.error_id), message: error.message } } : {}),
    ...(topicError && typeof topicError.message === "string" ? { topicError: { errorId: String(topicError.error_id), message: topicError.message } } : {}),
  };
}

function isBatch(value: unknown): value is ProcessingBatch {
  if (!value || typeof value !== "object") return false;
  const b = value as Record<string, unknown>;
  return typeof b.batchId === "string" && typeof b.topicId === "string" &&
    ["confirmed", "running", "paused", "completed", "partial"].includes(String(b.status)) &&
    Array.isArray(b.items) && b.items.every(i => i && typeof i.itemId === "string" &&
      typeof i.fileName === "string" && (i.sourceId === null || typeof i.sourceId === "string") &&
      ["queued", "processing", "completed", "failed", "cancelled", "partial", "deleted"].includes(i.status));
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

  listBatches(): Promise<ReaderHostResult<readonly ProcessingBatch[]>> {
    return this.libraryList<ProcessingBatch>("/library/batches", isBatch);
  }

  createTopic(title: string): Promise<ReaderHostResult<unknown>> {
    return this.managementRequest('/library/topics', { title });
  }
  manageTopic(topicId: string, action: 'rename' | 'delete' | 'attach' | 'detach' | 'reorder', input: { title?: string; sourceId?: string; sourceIds?: readonly string[] }): Promise<ReaderHostResult<unknown>> {
    return this.managementRequest(`/library/topics/${encodeURIComponent(topicId)}/${action}`, input);
  }
  renameSource(sourceId: string, title: string): Promise<ReaderHostResult<unknown>> {
    return this.managementRequest(`/library/sources/${encodeURIComponent(sourceId)}/title`, { title });
  }
  async deletionImpact(sourceId: string): Promise<ReaderHostResult<SourceDeletionImpact>> {
    try {
      const response = await this.fetch(this.baseUrl + `/library/sources/${encodeURIComponent(sourceId)}/deletion-impact`);
      const body = await response.json();
      if (body.ok === false) return body;
      if (body.ok && body.value?.sourceId === sourceId && Array.isArray(body.value.topics) && body.value.assets) return body;
      return { ok: false, error: { code: 'invalid-response', message: '删除摘要响应格式错误', retryable: false } };
    } catch {
      return { ok: false, error: { code: 'unavailable', message: '无法读取删除影响', retryable: true } };
    }
  }
  private async managementRequest(path: string, input: unknown): Promise<ReaderHostResult<unknown>> {
    try {
      const response = await this.fetch(this.baseUrl + path, {
        method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(input),
      });
      const body = await response.json();
      if (body.ok === true || body.ok === false) return body;
      return { ok: false, error: { code: 'invalid-response', message: '管理响应格式错误', retryable: false } };
    } catch {
      return { ok: false, error: { code: 'unavailable', message: '无法连接知识库', retryable: true } };
    }
  }

  async startBatch(itemIds: readonly string[], requestId: string): Promise<ReaderHostResult<ProcessingBatch>> {
    return this.batchRequest('/library/batches', { itemIds, requestId });
  }

  controlBatch(batchId: string, action: Parameters<NonNullable<ReaderHost['controlBatch']>>[1], requestId: string, itemId?: string, riskChoiceId?: string): Promise<ReaderHostResult<ProcessingBatch>> {
    return this.batchRequest(`/library/batches/${encodeURIComponent(batchId)}/${action}`, { requestId, itemId, riskChoiceId });
  }

  private async batchRequest(path: string, payload: unknown): Promise<ReaderHostResult<ProcessingBatch>> {
    try {
      const response = await this.fetch(this.baseUrl + path, {
        method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(payload),
      });
      const body = await response.json();
      if (body.ok === false) return body;
      if (body.ok && isBatch(body.value)) return { ok: true, value: body.value };
      return { ok: false, error: { code: "invalid-response", message: "Invalid batch response", retryable: false } };
    } catch {
      return { ok: false, error: { code: "unavailable", message: "无法连接材料处理服务", retryable: true } };
    }
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

  async listInbox(): Promise<ReaderHostResult<readonly IngestionItem[]>> {
    try {
      const response = await this.fetch(`${this.baseUrl}/library/inbox`);
      const body = await response.json();
      const items = Array.isArray(body.value) ? body.value.map(decodeIngestionItem) : null;
      if (response.ok && body.ok === true && items !== null && items.every(Boolean)) return { ok: true, value: items as IngestionItem[] };
      return { ok: false, error: { code: "invalid-response", message: body.error?.message ?? "Inbox 响应格式错误", retryable: false } };
    } catch (e) { return { ok: false, error: { code: "unavailable", message: String(e), retryable: true } }; }
  }
  stageIngestion(file: File, target: IngestionTarget): Promise<ReaderHostResult<IngestionItem>> {
    const query = new URLSearchParams({ name: file.name });
    if (target.topicTitle) query.set("topic", target.topicTitle);
    if (target.topicId) query.set("topicId", target.topicId);
    return this.ingestionRequest(`/library/inbox?${query}`, { method: "POST", body: file });
  }
  confirmIngestion(itemId: string, generateBlog = false): Promise<ReaderHostResult<IngestionItem>> {
    return this.ingestionRequest(`/library/inbox/${encodeURIComponent(itemId)}/confirm`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ generateBlog }) });
  }
  startIngestion(itemId: string, requestId: string): Promise<ReaderHostResult<IngestionItem>> {
    return this.ingestionRequest(`/library/inbox/${encodeURIComponent(itemId)}/start`, {
      method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ requestId }),
    });
  }
  blogStatus(sourceId: string): Promise<ReaderHostResult<BlogStatus>> {
    return this.blogRequest(`/library/sources/${encodeURIComponent(sourceId)}/blog`, { method: "GET" });
  }
  generateBlog(sourceId: string, requestId: string): Promise<ReaderHostResult<BlogStatus>> {
    return this.blogRequest(`/library/sources/${encodeURIComponent(sourceId)}/blog/generate`,
      { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ requestId }) });
  }
  regenerateBlog(sourceId: string, requestId: string, artifact: BlogRegenerationTarget): Promise<ReaderHostResult<BlogStatus>> {
    return this.blogRequest(`/library/sources/${encodeURIComponent(sourceId)}/blog/regenerate`,
      { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ requestId, artifact }) });
  }
  cancelBlog(sourceId: string): Promise<ReaderHostResult<BlogStatus>> {
    return this.blogRequest(`/library/sources/${encodeURIComponent(sourceId)}/blog/cancel`,
      { method: "POST", headers: { "content-type": "application/json" }, body: "{}" });
  }
  blogUrl(sourceId: string): string {
    return `${this.baseUrl}/library/sources/${encodeURIComponent(sourceId)}/blog/html`;
  }

  private async blogRequest(path: string, init: RequestInit): Promise<ReaderHostResult<BlogStatus>> {
    try {
      const response = await this.fetch(`${this.baseUrl}${path}`, init);
      const body = await response.json();
      const value = body?.value as Partial<BlogStatus> | undefined;
      if (response.ok && body.ok === true && value && typeof value.sourceId === "string" && typeof value.generated === "boolean" &&
        value.artifacts && typeof value.artifacts === "object" && Array.isArray(value.warnings)) {
        // The Host reports failures in the Core's snake_case shape; the contract is camelCase.
        const error = value.error as { error_id?: unknown; errorId?: unknown; message?: unknown } | null | undefined;
        const normalized = { ...value } as Record<string, unknown>;
        if (error && typeof error === "object") {
          normalized.error = {
            errorId: String(error.errorId ?? error.error_id ?? "blog_failed"),
            message: typeof error.message === "string" ? error.message : "博客生成失败",
          };
        }
        return { ok: true, value: normalized as unknown as BlogStatus };
      }
      return { ok: false, error: { code: "invalid-response", message: body?.error?.message ?? "博客状态响应格式错误", retryable: false } };
    } catch (e) { return { ok: false, error: { code: "unavailable", message: String(e), retryable: true } }; }
  }
  processIngestion(itemId: string, requestId: string): Promise<ReaderHostResult<IngestionItem>> {
    return this.ingestionRequest(`/library/inbox/${encodeURIComponent(itemId)}/process`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ requestId }) });
  }
  continueIngestion(itemId: string, requestId: string): Promise<ReaderHostResult<IngestionItem>> {
    return this.ingestionRequest(`/library/inbox/${encodeURIComponent(itemId)}/continue`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ requestId }) });
  }
  resubmitIngestion(itemId: string, requestId: string, riskChoiceId: string): Promise<ReaderHostResult<IngestionItem>> {
    return this.ingestionRequest(`/library/inbox/${encodeURIComponent(itemId)}/resubmit`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ requestId, riskChoiceId }) });
  }
  cancelIngestion(itemId: string): Promise<ReaderHostResult<IngestionItem>> {
    return this.ingestionRequest(`/library/inbox/${encodeURIComponent(itemId)}/cancel`, { method: "POST", headers: { "content-type": "application/json" }, body: "{}" });
  }
  sourceOriginalUrl(sourceId: string): string {
    return `${this.baseUrl}/library/sources/${encodeURIComponent(sourceId)}/original`;
  }
  sourceContentUrl(sourceId: string): string {
    return `${this.baseUrl}/library/sources/${encodeURIComponent(sourceId)}/content`;
  }
  deleteSource(sourceId: string): Promise<ReaderHostResult<ReadingWindow>> {
    return this.request(`/library/sources/${encodeURIComponent(sourceId)}`, { method: "DELETE" });
  }
  replanSource(sourceId: string): Promise<ReaderHostResult<ReadingWindow>> {
    return this.request(`/library/sources/${encodeURIComponent(sourceId)}/replan`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ requestId: createReaderId() }) });
  }
  rereadSource(sourceId: string): Promise<ReaderHostResult<ReadingWindow>> {
    return this.request(`/library/sources/${encodeURIComponent(sourceId)}/reread`, { method: "POST", headers: { "content-type": "application/json" }, body: "{}" });
  }
  openSource(sourceId: string): Promise<ReaderHostResult<ReadingWindow>> {
    return this.request(`/library/sources/${encodeURIComponent(sourceId)}/open`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ requestId: createReaderId() }) });
  }
  activateReadingCandidate(sourceId: string, planId: string, readingRevision: number, requestId: string): Promise<ReaderHostResult<ReadingWindow>> {
    return this.request(`/library/sources/${encodeURIComponent(sourceId)}/activate`, { method: "POST",
      headers: { "content-type": "application/json" }, body: JSON.stringify({ planId, readingRevision, requestId }) });
  }

  resumePreparation(sourceId: string, requestId: string): Promise<ReaderHostResult<ReadingWindow>> {
    return this.request(`/library/sources/${encodeURIComponent(sourceId)}/preparation/resume`,
      { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ requestId }) });
  }

  cancelPreparation(sourceId: string): Promise<ReaderHostResult<ReadingWindow>> {
    return this.request(`/library/sources/${encodeURIComponent(sourceId)}/preparation/cancel`,
      { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ requestId: createReaderId() }) });
  }

  selectDiscussionSource(sourceId: string): Promise<ReaderHostResult<ReadingWindow>> {
    return this.request(`/library/sources/${encodeURIComponent(sourceId)}/discuss`, { method: "POST", headers: { "content-type": "application/json" }, body: "{}" });
  }

  changeSourceNote(sourceId: string, noteId: string, operation: "edit" | "delete" | "undo",
    expectedRevision: number, requestId: string, content?: string): Promise<ReaderHostResult<ReadingWindow>> {
    return this.request(`/library/sources/${encodeURIComponent(sourceId)}/notes/${encodeURIComponent(noteId)}/${operation}`,
      { method: "POST", headers: { "content-type": "application/json" },
        body: JSON.stringify({ expectedRevision, requestId, ...(content === undefined ? {} : { content }) }) });
  }

  async sourceNoteRequestResult(sourceId: string, requestId: string): Promise<ReaderHostResult<SourceNoteRequestResult | null>> {
    try {
      const response = await this.fetch(`${this.baseUrl}/library/sources/${encodeURIComponent(sourceId)}/notes/requests/${encodeURIComponent(requestId)}`);
      const body = await response.json();
      if (response.ok && body?.ok === true) return { ok: true, value: body.value ?? null };
      return { ok: false, error: { code: "invalid-request", message: body?.error?.message ?? "笔记请求结果不可用", retryable: false } };
    } catch (error) {
      return { ok: false, error: { code: "unavailable", message: String(error), retryable: true } };
    }
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
      body: JSON.stringify({ ...input, requestId: input.requestId ?? createReaderId() }),
      signal,
    });
  }

  finishReading(input: FinishReadingInput): Promise<ReaderHostResult<ReadingWindow>> {
    return this.request("/reader/finish", { method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ ...input, requestId: input.requestId ?? createReaderId() }) });
  }

  rereadReading(input: RereadReadingInput): Promise<ReaderHostResult<ReadingWindow>> {
    return this.request("/reader/reread", { method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ ...input, requestId: input.requestId ?? createReaderId() }) });
  }

  retryReadingProgress(progressId: string, requestId: string): Promise<ReaderHostResult<ReadingWindow>> {
    return this.request(`/reader/progress/${encodeURIComponent(progressId)}/retry`, { method: "POST",
      headers: { "content-type": "application/json" }, body: JSON.stringify({ requestId }) });
  }

  cancelReadingProgress(progressId: string): Promise<ReaderHostResult<ReadingWindow>> {
    return this.request(`/reader/progress/${encodeURIComponent(progressId)}/cancel`, { method: "POST",
      headers: { "content-type": "application/json" }, body: "{}" });
  }

  changeReadingProgress(progressId: string, operation: "edit" | "delete", expectedRevision: number,
    requestId: string, content?: string): Promise<ReaderHostResult<ReadingWindow>> {
    return this.request(`/reader/progress/${encodeURIComponent(progressId)}/${operation}`, { method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ expectedRevision, requestId, content }) });
  }

  reviewChunk(sourceId: string, planId: string, chunkId: string): Promise<ReaderHostResult<ReadingWindow>> {
    return this.request(`/reader/review/${encodeURIComponent(sourceId)}/${encodeURIComponent(planId)}/${encodeURIComponent(chunkId)}`,
      { method: "GET" });
  }

  async readingRequestResult(requestId: string): Promise<ReaderHostResult<ReadingWindow["readingOperation"]>> {
    try {
      const response = await this.fetch(`${this.baseUrl}/reader/requests/${encodeURIComponent(requestId)}`);
      const body = await response.json();
      if (response.ok && body?.ok === true) return { ok: true, value: body.value ?? null };
      return { ok: false, error: { code: "invalid-request", message: body?.error?.message ?? "阅读请求结果不可用", retryable: false } };
    } catch (error) {
      return { ok: false, error: { code: "unavailable", message: String(error), retryable: true } };
    }
  }

  sendMessage(
    input: SendReaderMessageInput,
    signal?: AbortSignal,
  ): Promise<ReaderHostResult<ReadingWindow>> {
    return this.request("/reader/messages", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ ...input, requestId: input.requestId ?? createReaderId() }),
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

  async backendSetup(action: BackendSetupAction, input: BackendSetupInput): Promise<ReaderHostResult<BackendSetupResult>> {
    try {
      const response = await this.fetch(this.baseUrl + '/reader/backend/setup', { method: 'POST', headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ ...input, action }) });
      const body = await response.json();
      if (body.ok === false) return body;
      const value = body.value;
      if (response.ok && body.ok === true && value && typeof value.backend === 'string' &&
          typeof value.status === 'string' && typeof value.message === 'string' &&
          (value.runtimePath === null || typeof value.runtimePath === 'string')) return { ok: true, value };
      return { ok: false, error: { code: 'invalid-response', message: '后端设置响应格式错误', retryable: false } };
    } catch {
      return { ok: false, error: { code: 'unavailable', message: '无法连接后端设置服务', retryable: true } };
    }
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

  private async ingestionRequest(path: string, init: RequestInit): Promise<ReaderHostResult<IngestionItem>> {
    try {
      const response = await this.fetch(`${this.baseUrl}${path}`, init);
      const body = await response.json();
      const item = decodeIngestionItem(body.value);
      if (response.ok && body.ok === true && item) return { ok: true, value: item };
      if (body?.ok === false && typeof body.error?.message === "string") return { ok: false, error: { code: isFailureCode(body.error.code) ? body.error.code : "unknown", message: body.error.message, retryable: body.error.retryable === true } };
      return { ok: false, error: { code: "invalid-response", message: "Inbox 响应格式错误", retryable: false } };
    } catch (error) {
      return { ok: false, error: { code: "unavailable", message: String(error), retryable: true } };
    }
  }
}
