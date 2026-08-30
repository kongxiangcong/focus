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
  private readonly messages: ReaderMessage[] = [];
  private messageSequence = 0;

  async getReadingWindow(): Promise<ReaderHostResult<ReadingWindow>> {
    return readerSuccess(this.snapshot());
  }

  async continueReading(input: ContinueReadingInput): Promise<ReaderHostResult<ReadingWindow>> {
    const current = this.snapshot();
    if (!sameReceipt(cursorReceipt(current), input.receipt)) {
      return readerFailure("cursor-changed", "The Reading Cursor changed before Continue Reading completed.");
    }
    this.chunkIndex += 1;
    return readerSuccess(this.snapshot());
  }

  async sendMessage(input: SendReaderMessageInput): Promise<ReaderHostResult<ReadingWindow>> {
    const current = this.snapshot();
    if (!sameReceipt(cursorReceipt(current), input.receipt)) {
      return readerFailure("cursor-changed", "The Reading Cursor changed before the message was sent.");
    }
    const content = input.content.trim();
    if (content.length === 0) {
      return readerFailure("invalid-request", "A reader message cannot be empty.");
    }
    this.messages.push(
      this.message("user", input.receipt.chunkId, content),
      this.message(
        "assistant",
        input.receipt.chunkId,
        "这是 Fixture Adapter 生成的合成回答。真实宿主应在不移动 Reading Cursor 的前提下提供回答。",
      ),
    );
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
    const activeChunkId = current?.chunkId ?? fixtureChunks.at(-1)?.chunkId;
    return {
      status: current === null ? "completed" : "reading",
      source: fixtureSource,
      current,
      history: fixtureChunks.slice(0, this.chunkIndex),
      conversation:
        activeChunkId === undefined
          ? []
          : this.messages.filter((message) => message.chunkId === activeChunkId),
    };
  }
}
