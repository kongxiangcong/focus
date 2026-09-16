import {
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

import { fixtureChunks, fixtureSource } from "../fixtures/reading-fixture";

function sameReceipt(left: CursorReceipt | null, right: CursorReceipt): boolean {
  return (
    left !== null &&
    left.sourceId === right.sourceId &&
    left.planId === right.planId &&
    left.chunkId === right.chunkId
  );
}

export class FixtureReaderHost implements ReaderHost {
  private chunkIndex = 0;
  private sessionId = crypto.randomUUID();
  private fresh = false;
  private timeline: NonNullable<ReadingWindow["timeline"]>[number][] = [{ kind: "reading", chunk: fixtureChunks[0] }];
  private readonly messages: ReaderMessage[] = [];
  private messageSequence = 0;

  async newSession(): Promise<ReaderHostResult<ReadingWindow>> {
    this.sessionId = crypto.randomUUID(); this.fresh = true; this.messages.length = 0; this.timeline = [];
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
