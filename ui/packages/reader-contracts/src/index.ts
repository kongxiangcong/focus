export type ReaderStatus = "empty" | "reading" | "completed";

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
  reference?: CursorReceipt | null;
  chunkId: string;
  role: ReaderMessageRole;
  content: string;
}

export interface ReadingWindow {
  revision?: number;
  sessionId?: string;
  sessionFresh?: boolean;
  timeline?: readonly ({ kind: "reading"; chunk: ReaderChunk } | { kind: "message"; messageId: string })[];
  status: ReaderStatus;
  source: ReaderSource;
  current: ReaderChunk | null;
  /** Complete ordered Reading Chunks before `current`; the Reader UI does not cache a second history. */
  history: readonly ReaderChunk[];
  conversation: readonly ReaderMessage[];
  agent?: ReaderAgentState;
}

export interface ReaderApproval {
  id: string;
  title: string;
  detail: string;
  kind: "approval" | "continue" | "input";
  choices: readonly string[];
  questions: readonly { id: string; question: string; options?: readonly { label: string; description: string }[] }[];
}

export interface ReaderAgentState {
  run: null | {
    runId: string;
    status: "running" | "approval" | "stopping" | "completed" | "failed" | "interrupted";
    error: string | null;
    approvals: readonly ReaderApproval[];
    activity: readonly { id: string; title: string; status: string; detail: string }[];
  };
  catalog: {
    sources: readonly { sourceId: string; title: string }[];
    topics: readonly { topicId: string; title: string }[];
  };
}

export interface ReaderApprovalResponse {
  approvalId: string;
  decision?: string;
  answers?: Record<string, { answers: string[] }>;
}

export interface ReaderAttachment { attachmentId: string; name: string }

export type ReaderNoteKind = "thought" | "emphasis" | "question" | "clarification";
export type ReaderNoteOrigin = "user" | "dialogue";

export interface ReaderNoteDraft {
  kind: ReaderNoteKind;
  origin: ReaderNoteOrigin;
  content: string;
  anchor?: SourceAnchor;
}

export interface ContinueReadingInput {
  sessionId?: string;
  receipt: CursorReceipt;
  requestId?: string;
  pendingNotes?: readonly ReaderNoteDraft[];
}

export interface SendReaderMessageInput {
  sessionId?: string;
  receipt: CursorReceipt | null;
  content: string;
  requestId?: string;
  attachmentIds?: readonly string[];
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
  newSession?(sessionId: string): Promise<ReaderHostResult<ReadingWindow>>;
  resumeReading?(sessionId: string): Promise<ReaderHostResult<ReadingWindow>>;
  subscribe?(listener: (result: ReaderHostResult<ReadingWindow>) => void): () => void;
  stop?(): Promise<ReaderHostResult<ReadingWindow>>;
  approve?(input: ReaderApprovalResponse): Promise<ReaderHostResult<ReadingWindow>>;
  upload?(file: File): Promise<ReaderHostResult<ReaderAttachment>>;
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
