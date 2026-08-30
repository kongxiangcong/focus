export type ReaderStatus = "reading" | "completed";

export type ChunkPresentationStatus =
  | "source-ready"
  | "translation-required"
  | "presented";

export interface CursorReceipt {
  sourceId: string;
  planId: string;
  chunkId: string;
}

export interface SourceAnchor {
  sourceLines: readonly [number, number];
  quote?: string;
}

export interface ReaderImage {
  src: string;
  caption: string;
}

export interface GlossaryTerm {
  source: string;
  translation: string;
}

export interface ReaderChunk {
  sourceId: string;
  planId: string;
  chunkId: string;
  index: number;
  total: number;
  sectionPath: readonly string[];
  sourceLines: readonly [number, number];
  sourceMarkdown: string;
  translation: string | null;
  images: readonly ReaderImage[];
  relevantGlossary: readonly GlossaryTerm[];
  presentationStatus: ChunkPresentationStatus;
}

export interface ReaderSource {
  sourceId: string;
  title: string;
  topicId: string | null;
}

export type ReaderMessageRole = "user" | "assistant";

export interface ReaderMessage {
  messageId: string;
  chunkId: string;
  role: ReaderMessageRole;
  content: string;
}

export interface ReadingWindow {
  status: ReaderStatus;
  source: ReaderSource;
  current: ReaderChunk | null;
  /** Complete ordered Reading Chunks before `current`; the Reader UI does not cache a second history. */
  history: readonly ReaderChunk[];
  conversation: readonly ReaderMessage[];
}

export type ReaderNoteKind = "thought" | "emphasis" | "question" | "clarification";
export type ReaderNoteOrigin = "user" | "dialogue";

export interface ReaderNoteDraft {
  kind: ReaderNoteKind;
  origin: ReaderNoteOrigin;
  content: string;
  anchor?: SourceAnchor;
}

export interface ContinueReadingInput {
  receipt: CursorReceipt;
  pendingNotes?: readonly ReaderNoteDraft[];
}

export interface SendReaderMessageInput {
  receipt: CursorReceipt;
  content: string;
}

export type ReaderFailureCode =
  | "cursor-changed"
  | "invalid-request"
  | "invalid-response"
  | "unavailable"
  | "unknown";

export interface ReaderFailure {
  code: ReaderFailureCode;
  message: string;
  retryable: boolean;
}

export type ReaderHostResult<T> =
  | { ok: true; value: T }
  | { ok: false; error: ReaderFailure };

export interface ReaderHost {
  getReadingWindow(signal?: AbortSignal): Promise<ReaderHostResult<ReadingWindow>>;
  continueReading(
    input: ContinueReadingInput,
    signal?: AbortSignal,
  ): Promise<ReaderHostResult<ReadingWindow>>;
  sendMessage(
    input: SendReaderMessageInput,
    signal?: AbortSignal,
  ): Promise<ReaderHostResult<ReadingWindow>>;
}

export function cursorReceipt(window: ReadingWindow): CursorReceipt | null {
  const chunk = window.current;
  if (chunk === null) {
    return null;
  }
  return {
    sourceId: chunk.sourceId,
    planId: chunk.planId,
    chunkId: chunk.chunkId,
  };
}

export function readerSuccess<T>(value: T): ReaderHostResult<T> {
  return { ok: true, value };
}

export function readerFailure(
  code: ReaderFailureCode,
  message: string,
  retryable = false,
): ReaderHostResult<never> {
  return { ok: false, error: { code, message, retryable } };
}
