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
  outline?: readonly { chunkId: string; index: number; sectionPath: readonly string[] }[];
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
  backend?: string;
  backends?: readonly { id: string; label: string; unavailableReason?: string | null }[];
  run: null | {
    runId: string;
    status: "running" | "approval" | "stopping" | "completed" | "failed" | "interrupted";
    error: string | null;
    progress?: { label: string; startedAt: number; updatedAt: number; finishedAt?: number };
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

export interface LibraryTopic {
  topicId: string;
  title: string;
  sourceIds: readonly string[];
}

export interface LibraryUpload { topic: string; uploader: string }

export interface LibrarySource {
  shortName?: string;
  format?: "PDF" | "HTML" | "Markdown";
  publishedAt?: string | null;
  venue?: string | null;
  uploader?: string | null;
  readingStatus?: "unplanned" | "ready" | "reading" | "completed";
  sourceId: string;
  title: string;
  kind: "paper" | "article";
  parseStatus: "ready" | "invalid";
  error: string | null;
  progress: { completed: number; total: number; planId: string | null; chunkId: string | null };
  /** Total saved Notes across this Source's Plans; records have no timestamps. */
  noteCount: number;
  topicIds: readonly string[];
}

export interface ReaderHost {
  listTopics?(): Promise<ReaderHostResult<readonly LibraryTopic[]>>;
  listSources?(): Promise<ReaderHostResult<readonly LibrarySource[]>>;
  uploadSource?(file: File, fields: LibraryUpload): Promise<ReaderHostResult<ReadingWindow>>;
  deleteSource?(sourceId: string): Promise<ReaderHostResult<ReadingWindow>>;
  rereadSource?(sourceId: string): Promise<ReaderHostResult<ReadingWindow>>;
  openSource?(sourceId: string): Promise<ReaderHostResult<ReadingWindow>>;
  selectBackend?(backend: string, sessionId: string): Promise<ReaderHostResult<ReadingWindow>>;
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

/** Stable request/session identifiers, including LAN HTTP where randomUUID is absent. */
export function createReaderId(): string {
  if (typeof globalThis.crypto.randomUUID === "function") return globalThis.crypto.randomUUID();
  // getRandomValues is also available outside secure contexts. Keep UUID v4
  // entropy and format; these IDs provide retry deduplication, not authentication.
  const bytes = globalThis.crypto.getRandomValues(new Uint8Array(16));
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  const hex = Array.from(bytes, byte => byte.toString(16).padStart(2, "0")).join("");
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}
