import { createReaderId, type CreateSourceNoteInput, type SourceNote,
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

export class FixtureReaderHost implements ReaderHost {
  noteCreateOutcome: "success" | "failed" | "note_bundle_changed" = "success";
  private readonly notes: SourceNote[] = [];
  private readonly noteRequests = new Map<string, { input: string; note: SourceNote }>();
  private noteOperation?: ReadingWindow["noteOperation"];

  async createSourceNote(input: CreateSourceNoteInput): Promise<ReaderHostResult<ReadingWindow>> {
    if (this.noteCreateOutcome !== "success") return readerFailure(this.noteCreateOutcome === "failed" ? "unavailable" : "note_bundle_changed",
      this.noteCreateOutcome === "failed" ? "保存失败，请重试" : "这段原文已更新，可改存为整篇笔记");
    if (input.sourceId !== fixtureSource.sourceId || !input.content.trim() || input.content.length > 8000 || !input.requestId ||
      !["thought", "conclusion", "question"].includes(input.kind) || !["user", "dialogue"].includes(input.origin)) return readerFailure("invalid-request", "笔记内容或来源不正确");
    const prior = this.noteRequests.get(input.requestId), identity = JSON.stringify(input);
    if (prior && prior.input !== identity) return readerFailure("invalid-request", "请求已用于不同内容");
    const chunk = input.chunk ? fixtureChunks.find(c => c.planId === input.chunk!.planId && c.chunkId === input.chunk!.chunkId) : undefined;
    if (input.chunk && !chunk) return readerFailure("invalid-request", "笔记段落不存在");
    if (input.quote && chunk && !chunk.sourceMarkdown.includes(input.quote)) return readerFailure("invalid-request", "引文不匹配原文");
    const note: SourceNote = prior?.note ?? { noteId: createReaderId(), sourceId: input.sourceId, revision: 1,
      content: input.content.trim(), kind: input.kind, origin: input.origin, bundle: "fixture-bundle-v1",
      anchor: chunk ? { sourceId: input.sourceId, bundle: chunk.bundleVersion, sourceLines: chunk.sourceLines, ...(input.quote ? { quote: input.quote } : {}) } : null,
      evidenceRole: input.kind === "question" ? "unresolved_question" : "explanation", deleted: false, canUndo: true,
      sourceUpdated: false, referenceStatus: "current" };
    if (!prior) { this.notes.push(note); this.noteRequests.set(input.requestId, { input: identity, note }); }
    this.noteOperation = { sourceId: input.sourceId, status: "saved", note };
    return readerSuccess(this.snapshot());
  }

  private chunkIndex = 0;
  private sessionId = createReaderId();
  private fresh = false;
  private timeline: NonNullable<ReadingWindow["timeline"]>[number][] = [{ kind: "reading", chunk: fixtureChunks[0] }];
  private readonly messages: ReaderMessage[] = [];
  private messageSequence = 0;

  async newSession(): Promise<ReaderHostResult<ReadingWindow>> {
    this.sessionId = createReaderId(); this.fresh = true; this.messages.length = 0; this.timeline = [];
    return readerSuccess(this.snapshot());
  }
  async resumeReading(): Promise<ReaderHostResult<ReadingWindow>> {
    this.fresh = false;
    const chunk = fixtureChunks[this.chunkIndex];
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
    if (fixtureChunks[this.chunkIndex]) this.timeline.push({ kind: "reading", chunk: fixtureChunks[this.chunkIndex] });
    return readerSuccess(this.snapshot());
  }

  async sendMessage(input: SendReaderMessageInput): Promise<ReaderHostResult<ReadingWindow>> {
    if (input.receipt && !fixtureChunks.some(c => sameReceipt(c, input.receipt!))) {
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
    const current = fixtureChunks[this.chunkIndex] ?? null;
    return {
      sourceNotes: [...this.notes], noteOperation: this.noteOperation,
      sessionId: this.sessionId, sessionFresh: this.fresh,
      timeline: this.timeline,
      status: current === null ? "completed" : "reading",
      source: fixtureSource,
      current,
      history: fixtureChunks.slice(0, this.chunkIndex),
      conversation: this.messages,
    };
  }
}
