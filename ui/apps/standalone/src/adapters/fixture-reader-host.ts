import { createReaderId, type CreateSourceNoteInput, type SourceNote, type CreateHighlightInput, type ReadingHighlight, type HighlightOperation, type SentenceInput, type ReaderChunk, type ReaderSource, type SourceNoteOperation, type SourceNoteRequestResult,
  cursorReceipt,
  readerFailure,
  readerSuccess,
  type ContinueReadingInput,
  type CursorReceipt,
  type ReaderHost,
  type ReaderHostResult,
  type ReaderMessage,
  type ReadingWindow,
  type SendReaderMessageInput,
} from "@focus/reader-contracts";

import { fixtureChunks as sourceChunks, fixtureSource } from "../fixtures/reading-fixture";

const fixtureChunks = sourceChunks.map(chunk => ({ ...chunk, bundleVersion: "fixture-bundle-v1" }));

function sameReceipt(left: CursorReceipt | null, right: CursorReceipt): boolean {
  return (
    left !== null &&
    left.sourceId === right.sourceId &&
    left.planId === right.planId &&
    left.chunkId === right.chunkId
  );
}

export interface FixtureReaderHostOptions {
  source?: ReaderSource;
  chunks?: readonly ReaderChunk[];
  notes?: readonly SourceNote[];
  highlights?: readonly ReadingHighlight[];
}

type RequestEntry = { identity: string } & (
  { entity: "highlight"; operation: HighlightOperation } | { entity: "note"; operation: SourceNoteOperation }
);
const requestValid = (id: unknown): id is string => typeof id === "string" && /^[A-Za-z0-9-]{8,80}$/.test(id);
function hasKeys(value: unknown, keys: readonly string[]): value is Record<string, unknown> {
  return !!value && typeof value === "object" && !Array.isArray(value) &&
    Object.keys(value).length === keys.length && keys.every(key => Object.hasOwn(value, key));
}
function validSentence(value: unknown, chunk: ReaderChunk): value is SentenceInput {
  if (!hasKeys(value, ["layer", "range", "quote"]) || !["source", "translation"].includes(String(value.layer)) ||
    (value.layer === "translation" && !chunk.translation) || !hasKeys(value.range, ["start", "end"]) ||
    !hasKeys(value.quote, ["exact", "prefix", "suffix"])) return false;
  const { start, end } = value.range, { exact, prefix, suffix } = value.quote;
  return typeof start === "number" && typeof end === "number" && Number.isInteger(start) && Number.isInteger(end) &&
    start >= 0 && end > start && end - start <= 2000 && typeof exact === "string" &&
    Array.from(exact).length >= 1 && Array.from(exact).length <= 2000 && typeof prefix === "string" &&
    Array.from(prefix).length <= 64 && typeof suffix === "string" && Array.from(suffix).length <= 64;
}
function identity(value: unknown): string {
  return JSON.stringify(value, (_key, item) => item && typeof item === "object" && !Array.isArray(item)
    ? Object.fromEntries(Object.entries(item).sort(([a], [b]) => a.localeCompare(b))) : item);
}

export class FixtureReaderHost implements ReaderHost {
  /** Legacy direct-note fixture switch retained for existing consumers. */
  noteCreateOutcome: "success" | "failed" | "note_bundle_changed" = "success";
  writeOutcome: "success" | "failed" | "bundle_changed" = "success";
  private readonly notes: SourceNote[];
  private readonly highlights: ReadingHighlight[];
  private readonly requests = new Map<string, RequestEntry>();
  private readonly recovery = new Map<string, SourceNote | "create">();
  private readonly highlightRecovery = new Map<string, "create" | "delete">();
  private readonly failures = new Set<"highlight" | "note">();
  private readonly cancelledRequests = new Set<string>();
  private readonly clearRequests = new Set<string>();
  private noteClearVersion = 0;
  private noteOperation?: SourceNoteOperation;
  private highlightOperation?: HighlightOperation;
  private readonly source: ReaderSource;
  private readonly chunks: readonly ReaderChunk[];

  constructor(options: FixtureReaderHostOptions = {}) {
    this.source = options.source ?? fixtureSource;
    this.chunks = options.chunks ?? fixtureChunks;
    this.notes = structuredClone([...(options.notes ?? [])]);
    this.highlights = structuredClone([...(options.highlights ?? [])]);
    for (const note of this.notes) if (note.canUndo && !note.deleted) this.recovery.set(note.noteId, "create");
    for (const mark of this.highlights) if (mark.canUndo) this.highlightRecovery.set(mark.highlightId, mark.deleted ? "delete" : "create");
    this.timeline = this.chunks[0] ? [{ kind: "reading", chunk: this.chunks[0] }] : [];
  }

  failNext(entity: "highlight" | "note") { this.failures.add(entity); }

  private writeFailure(entity: "highlight" | "note"): ReaderHostResult<never> | undefined {
    if (this.failures.delete(entity) || this.writeOutcome === "failed") return readerFailure("unavailable", "保存失败，请重试", true);
    if (this.writeOutcome === "bundle_changed") return readerFailure(entity === "highlight" ? "highlight_bundle_changed" : "note_bundle_changed", "这段原文已更新，标注未保存");
  }

  private replay(entity: "highlight" | "note", requestId: string, payload: unknown): ReaderHostResult<ReadingWindow> | undefined {
    if (this.cancelledRequests.has(requestId)) return readerFailure("invalid-request", "此请求已随笔记清除");
    const prior = this.requests.get(requestId);
    if (!prior) return;
    if (prior.entity !== entity || prior.identity !== identity(payload)) return readerFailure(entity === "highlight" ? "highlight_request_conflict" : "invalid-request", "请求已用于不同内容");
    if (prior.entity === "highlight") this.highlightOperation = prior.operation;
    else this.noteOperation = prior.operation;
    return readerSuccess(this.snapshot());
  }

  async createHighlight(input: CreateHighlightInput): Promise<ReaderHostResult<ReadingWindow>> {
    const chunk = hasKeys(input.chunk, ["planId", "chunkId"])
      ? this.chunks.find(c => c.planId === input.chunk.planId && c.chunkId === input.chunk.chunkId) : undefined;
    if (input.sourceId !== this.source.sourceId || !chunk || !requestValid(input.requestId) ||
      !validSentence({ layer: input.layer, range: input.range, quote: input.quote }, chunk)) return readerFailure("highlight_invalid", "标注参数不正确");
    const prior = this.replay("highlight", input.requestId, input); if (prior) return prior;
    const failure = this.writeFailure("highlight"); if (failure) return failure;
    const highlight: ReadingHighlight = { highlightId: createReaderId().replaceAll("-", ""), sourceId: input.sourceId, revision: 1,
      ...input.chunk, layer: input.layer, range: { ...input.range }, quote: { ...input.quote }, bundle: chunk.bundleVersion ?? "fixture-bundle-v1",
      sourceLines: chunk.sourceLines, deleted: false, canUndo: true, sourceUpdated: false };
    this.highlights.push(highlight); this.highlightRecovery.set(highlight.highlightId, "create");
    this.highlightOperation = { sourceId: input.sourceId, status: "saved", highlight };
    this.requests.set(input.requestId, { entity: "highlight", identity: identity(input), operation: this.highlightOperation });
    return readerSuccess(this.snapshot());
  }

  async changeHighlight(sourceId: string, highlightId: string, operation: "delete" | "undo", expectedRevision: number, requestId: string): Promise<ReaderHostResult<ReadingWindow>> {
    if (sourceId !== this.source.sourceId || !requestValid(requestId) || !Number.isInteger(expectedRevision) || expectedRevision < 1 ||
      !["delete", "undo"].includes(operation)) return readerFailure("highlight_invalid", "标注操作不正确");
    const payload = { sourceId, highlightId, operation, expectedRevision };
    const prior = this.replay("highlight", requestId, payload); if (prior) return prior;
    const failure = this.writeFailure("highlight"); if (failure) return failure;
    const index = this.highlights.findIndex(h => h.highlightId === highlightId), current = this.highlights[index];
    if (!current) return readerFailure("highlight_not_found", "标注不存在");
    if (current.revision !== expectedRevision || (current.deleted && operation !== "undo") ||
      (operation === "undo" && !this.highlightRecovery.has(highlightId))) this.highlightOperation = { sourceId, status: "conflict", current };
    else {
      const deleted = operation === "delete" || this.highlightRecovery.get(highlightId) === "create";
      const highlight = { ...current, revision: current.revision + 1, deleted, canUndo: operation === "delete" };
      this.highlights[index] = highlight;
      if (operation === "delete") this.highlightRecovery.set(highlightId, "delete"); else this.highlightRecovery.delete(highlightId);
      this.highlightOperation = { sourceId, status: "changed", operation, highlight };
    }
    this.requests.set(requestId, { entity: "highlight", identity: identity(payload), operation: this.highlightOperation });
    return readerSuccess(this.snapshot());
  }

  async highlightRequestResult(sourceId: string, requestId: string): Promise<ReaderHostResult<HighlightOperation | { status: "cancelled" } | null>> {
    if (sourceId !== this.source.sourceId) return readerFailure("invalid-request", "标注来源不正确");
    if (this.cancelledRequests.has(requestId)) return readerSuccess({ status: "cancelled" });
    const prior = this.requests.get(requestId);
    return readerSuccess(prior?.entity === "highlight" ? prior.operation : null);
  }

  async createSourceNote(input: CreateSourceNoteInput): Promise<ReaderHostResult<ReadingWindow>> {
    if (this.noteCreateOutcome !== "success") return readerFailure(this.noteCreateOutcome === "failed" ? "unavailable" : "note_bundle_changed",
      this.noteCreateOutcome === "failed" ? "保存失败，请重试" : "这段原文已更新，可改存为整篇笔记");
    if (input.sourceId !== this.source.sourceId || typeof input.content !== "string" || !input.content.trim() || Array.from(input.content).length > 8000 || !requestValid(input.requestId) ||
      !["thought", "conclusion", "question"].includes(input.kind) || !["user", "dialogue"].includes(input.origin)) return readerFailure("invalid-request", "笔记内容或来源不正确");
    const chunk = input.chunk && hasKeys(input.chunk, ["planId", "chunkId"]) ? this.chunks.find(c => c.planId === input.chunk!.planId && c.chunkId === input.chunk!.chunkId) : undefined;
    if (input.chunk && !chunk) return readerFailure("invalid-request", "笔记段落不存在");
    if (input.sentence != null && (!chunk || input.kind !== "thought" || input.origin !== "user" || input.quote != null || !validSentence(input.sentence, chunk))) return readerFailure("note_sentence_invalid", "句子备注参数不正确");
    if (input.quote && chunk && !chunk.sourceMarkdown.includes(input.quote)) return readerFailure("invalid-request", "引文不匹配原文");
    const prior = this.replay("note", input.requestId, input); if (prior) return prior;
    const failure = this.writeFailure("note"); if (failure) return failure;
    const note: SourceNote = { noteId: createReaderId().replaceAll("-", ""), sourceId: input.sourceId, revision: 1,
      content: input.content.trim(), kind: input.kind, origin: input.origin, bundle: chunk?.bundleVersion ?? "fixture-bundle-v1",
      anchor: chunk ? { sourceId: input.sourceId, bundle: chunk.bundleVersion ?? "fixture-bundle-v1", sourceLines: chunk.sourceLines, ...(input.quote ? { quote: input.quote } : {}) } : null,
      sentence: input.sentence && chunk ? { ...structuredClone(input.sentence), ...input.chunk! } : null, placement: null,
      evidenceRole: input.kind === "question" ? "unresolved_question" : "explanation", deleted: false, canUndo: true,
      sourceUpdated: false, referenceStatus: "current" };
    this.notes.push(note); this.recovery.set(note.noteId, "create");
    this.noteOperation = { sourceId: input.sourceId, status: "saved", note };
    this.requests.set(input.requestId, { entity: "note", identity: identity(input), operation: this.noteOperation });
    return readerSuccess(this.snapshot());
  }

  async changeSourceNote(sourceId: string, noteId: string, operation: "edit" | "delete" | "undo", expectedRevision: number,
    requestId: string, content?: string): Promise<ReaderHostResult<ReadingWindow>> {
    if (sourceId !== this.source.sourceId || !requestValid(requestId) || !Number.isInteger(expectedRevision) || expectedRevision < 1 ||
      !["edit", "delete", "undo"].includes(operation) || (operation === "edit"
        ? typeof content !== "string" || !content.trim() || Array.from(content).length > 8000 : content !== undefined)) return readerFailure("invalid-request", "笔记操作不正确");
    const payload = { sourceId, noteId, operation, expectedRevision, content };
    const prior = this.replay("note", requestId, payload); if (prior) return prior;
    const failure = this.writeFailure("note"); if (failure) return failure;
    const index = this.notes.findIndex(note => note.noteId === noteId), current = this.notes[index];
    if (!current) return readerFailure("invalid-request", "笔记不存在");
    if (current.revision !== expectedRevision || (current.deleted && operation !== "undo") ||
      (operation === "undo" && !this.recovery.has(noteId))) this.noteOperation = { sourceId, status: "conflict", current, attemptedContent: content };
    else {
      const saved = this.recovery.get(noteId);
      const note = operation === "undo"
        ? { ...(saved && saved !== "create" ? saved : current), deleted: saved === "create" ? true : saved?.deleted ?? current.deleted, revision: current.revision + 1, canUndo: false }
        : { ...current, content: operation === "edit" ? content!.trim() : current.content, deleted: operation === "delete", revision: current.revision + 1, canUndo: true };
      this.notes[index] = note;
      if (operation === "undo") this.recovery.delete(noteId); else this.recovery.set(noteId, current);
      this.noteOperation = { sourceId, status: "changed", operation, note };
    }
    this.requests.set(requestId, { entity: "note", identity: identity(payload), operation: this.noteOperation });
    return readerSuccess(this.snapshot());
  }

  async sourceNoteRequestResult(sourceId: string, requestId: string): Promise<ReaderHostResult<SourceNoteRequestResult | null>> {
    if (sourceId !== this.source.sourceId) return readerFailure("invalid-request", "笔记来源不正确");
    if (this.cancelledRequests.has(requestId)) return readerSuccess({ status: "cancelled" });
    const prior = this.requests.get(requestId);
    return readerSuccess(prior?.entity === "note" ? prior.operation : null);
  }

  async clearSource(sourceId: string, requestId: string): Promise<ReaderHostResult<ReadingWindow>> {
    if (sourceId !== this.source.sourceId || !requestValid(requestId)) return readerFailure("invalid-request", "清除来源或请求不正确");
    if (this.clearRequests.has(requestId)) return readerSuccess(this.snapshot());
    this.clearRequests.add(requestId);
    for (const id of this.requests.keys()) this.cancelledRequests.add(id);
    this.requests.clear(); this.recovery.clear(); this.highlightRecovery.clear(); this.failures.clear();
    this.notes.length = 0; this.highlights.length = 0;
    this.noteOperation = undefined; this.highlightOperation = undefined;
    this.messages.length = 0; this.timeline = []; this.chunkIndex = 0; this.fresh = true;
    this.noteClearVersion += 1;
    return readerSuccess(this.snapshot());
  }

  private chunkIndex = 0;
  private sessionId = createReaderId();
  private fresh = false;
  private timeline: NonNullable<ReadingWindow["timeline"]>[number][] = [];
  private readonly messages: ReaderMessage[] = [];
  private messageSequence = 0;

  async newSession(): Promise<ReaderHostResult<ReadingWindow>> {
    this.sessionId = createReaderId(); this.fresh = true; this.messages.length = 0; this.timeline = [];
    return readerSuccess(this.snapshot());
  }
  async resumeReading(): Promise<ReaderHostResult<ReadingWindow>> {
    this.fresh = false;
    const chunk = this.chunks[this.chunkIndex];
    if (chunk && !this.timeline.some(e => e.kind === "reading" && e.chunk.chunkId === chunk.chunkId)) this.timeline.push({ kind: "reading", chunk });
    return readerSuccess(this.snapshot());
  }
  async getReadingWindow(): Promise<ReaderHostResult<ReadingWindow>> {
    return readerSuccess(this.snapshot());
  }

  async continueReading(input: ContinueReadingInput): Promise<ReaderHostResult<ReadingWindow>> {
    const current = this.snapshot();
    if (input.receipt === null || !sameReceipt(cursorReceipt(current), input.receipt)) {
      return readerFailure("cursor-changed", "The Reading Cursor changed before Continue Reading completed.");
    }
    this.fresh = false;
    this.chunkIndex += 1;
    if (this.chunks[this.chunkIndex]) this.timeline.push({ kind: "reading", chunk: this.chunks[this.chunkIndex] });
    return readerSuccess(this.snapshot());
  }

  async sendMessage(input: SendReaderMessageInput): Promise<ReaderHostResult<ReadingWindow>> {
    if (input.receipt && !this.chunks.some(c => sameReceipt(c, input.receipt!))) {
      return readerFailure("invalid-request", "The referenced paragraph does not exist.");
    }
    const content = input.content.trim();
    if (content.length === 0) {
      return readerFailure("invalid-request", "A reader message cannot be empty.");
    }
    this.fresh = false;
    this.messages.push(
      this.message("user", input.receipt?.chunkId ?? "", content),
      this.message(
        "assistant",
        input.receipt?.chunkId ?? "",
        "这是 Fixture Adapter 生成的合成回答。真实宿主应在不移动 Reading Cursor 的前提下提供回答。",
      ),
    );
    this.timeline.push(...this.messages.slice(-2).map(m => ({ kind: "message" as const, messageId: m.messageId })));
    return readerSuccess(this.snapshot());
  }

  private message(role: ReaderMessage["role"], chunkId: string, content: string): ReaderMessage {
    this.messageSequence += 1;
    return {
      messageId: `fixture-message-${this.messageSequence}`,
      chunkId,
      role,
      content,
    };
  }

  private snapshot(): ReadingWindow {
    const current = this.chunks[this.chunkIndex] ?? null;
    return {
      sourceNotes: [...this.notes], noteOperation: this.noteOperation,
      sourceHighlights: [...this.highlights], highlightOperation: this.highlightOperation,
      sessionId: this.sessionId, sessionFresh: this.fresh,
      resetVersion: this.noteClearVersion, noteClearVersion: this.noteClearVersion,
      timeline: this.timeline,
      status: current === null ? "completed" : "reading",
      source: this.source,
      current,
      history: this.chunks.slice(0, this.chunkIndex),
      conversation: this.messages,
    };
  }
}
