export type ReaderStatus = "empty" | "reading" | "completed";

export type ChunkPresentationStatus =
  | "source-ready"
  | "translation-required"
  | "presented";

export interface CursorReceipt {
  sourceId: string;
  planId: string;
  chunkId: string;
  readingRevision?: number;
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

export type BlogArtifactName = "value_analysis" | "reading_blog" | "html";
export type BlogRegenerationTarget = BlogArtifactName | "all";

export type BlogArtifactStatus =
  | "pending"
  | "generating"
  | "completed"
  | "failed"
  | "not_applicable";

/** One Blog Output: the two Markdown artifacts plus the merged single-file page. */
export interface BlogStatus {
  attemptId?: string | null;
  sourceId: string;
  generated: boolean;
  artifacts: Record<BlogArtifactName, { status: BlogArtifactStatus; updatedAt: string | null }>;
  valueAnalysis: { applicable: boolean | null; direction: string | null; reason: string | null };
  verificationLevel: string | null;
  warnings: readonly string[];
  methodVersion: string | null;
  runStatus?: string | null;
  executing?: boolean;
  error?: { errorId: string; message: string } | null;
}

export type ReaderMessageRole = "user" | "assistant";

export interface ReaderMessage {
  messageId: string;
  reference?: CursorReceipt | null;
  chunkId: string;
  role: ReaderMessageRole;
  content: string;
  sourceId?: string | null;
  sourceDeleted?: boolean;
}

export interface SourceNote {
  noteId: string;
  sourceId: string;
  revision: number;
  content: string;
  kind: "example" | "conclusion" | "question" | "thought" | "concept";
  origin: "user" | "dialogue";
  evidenceRole: "source_claim" | "explanation" | "unresolved_question";
  bundle: string;
  anchor: { sourceId: string; bundle: string; sourceLines: readonly [number, number]; quote?: string } | null;
  referenceStatus: "current" | "historical" | "unavailable";
  sourceUpdated: boolean;
  deleted: boolean;
  canUndo: boolean;
}

export interface ReadingProgressEntry {
  progress_id: string;
  trigger_request_id: string;
  source_id: string;
  bundle: string;
  plan_id: string;
  chunk_id: string;
  reading_pass: number;
  operation: "continue" | "finish";
  status: "pending" | "generating" | "saved" | "failed" | "interrupted" | "deleted";
  revision: number;
  fact: string;
  topic: string | null;
  user_understanding: string | null;
  deleted: boolean;
  error: string | null;
}

export interface SourceNoteOperation {
  sourceId: string;
  status: "changed" | "conflict";
  operation?: "edit" | "delete" | "undo";
  note?: SourceNote;
  current?: SourceNote;
  attemptedContent?: string | null;
}
export type SourceNoteRequestResult = SourceNoteOperation | { status: "saved"; note: SourceNote } | { status: "cancelled" };

export interface ReadingWindow {
  workspace?: { workspaceId: string; instanceId: string; path: string };
  workItems?: readonly { kind: "chat" | "preparation" | "blog" | "ingestion" | "progress"; targetId: string; status: string; label: string; error?: string | null; dismissed?: boolean }[];
  configuration?: BackendConfigurationState;
  clearBusySources?: readonly string[];
  reviewChunk?: ReaderChunk | null;
  readingUnavailable?: string;
  unavailableReferences?: readonly { sourceId: string; planId: string; chunkId: string; reason: string }[];
  readingRevision?: number;
  readingOperation?: { operation: string; source_id: string; run_id?: string; status?: string;
    plan_id?: string; previous_chunk_id?: string | null; chunk_id?: string | null; reading_revision?: number } | null;
  preparations?: Readonly<Record<string, ReadingPreparation>>;
  outline?: readonly { chunkId: string; index: number; sectionPath: readonly string[] }[];
  revision?: number;
  sessionId?: string;
  discussionId?: string;
  discussions?: readonly { discussionId: string; sourceId: string }[];
  sessionFresh?: boolean;
  readingStarted?: boolean;
  resetVersion?: number;
  /** Persistent frontier, also available when a fresh session hides its cards. */
  navigationCurrent?: ReaderChunk | null;
  timeline?: readonly ({ kind: "reading"; chunk: ReaderChunk; eventId?: string } | { kind: "message"; messageId: string })[];
  status: ReaderStatus;
  source: ReaderSource;
  /** Images bound to the current Source, including figures in unread Chunks. */
  figures?: readonly ReaderImage[];
  current: ReaderChunk | null;
  /** Complete ordered Reading Chunks before `current`; the Reader UI does not cache a second history. */
  history: readonly ReaderChunk[];
  conversation: readonly ReaderMessage[];
  agent?: ReaderAgentState;
  /** Blog Output projection per Source id; absent when the Host has no blog surface. */
  blog?: Readonly<Record<string, BlogStatus>>;
  sourceNotes?: readonly SourceNote[];
  readingProgress?: readonly ReadingProgressEntry[];
  progressOperation?: { status: "changed" | "conflict"; entry?: ReadingProgressEntry; current?: ReadingProgressEntry; attempted_content?: string | null } | null;
  noteFeedback?: { sourceId: string; status: "saved" | "failed" } | null;
  noteOperation?: SourceNoteOperation | null;
}

export interface ReadingPreparation {
  attempt?: string;
  dismissed?: boolean;
  timed_out?: boolean;
  source_id: string;
  status: "running" | "ready" | "failed" | "cancelled" | "interrupted" | "bundle_changed" | "commit_conflict";
  step: string;
  total: number;
  completed: number;
  ready: boolean;
  error: string | null;
  plan_id: string | null;
  glossary_revision?: string | null;
  selected_plan_id?: string | null;
  selected_ready?: boolean;
  candidate?: boolean;
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

export interface FinishReadingInput {
  sessionId?: string;
  receipt: CursorReceipt;
  requestId?: string;
}

export interface RereadReadingInput {
  sessionId?: string;
  receipt: { sourceId: string; planId: string; chunkId: string | null; readingRevision: number };
  requestId?: string;
}

export interface SendReaderMessageInput {
  sessionId?: string;
  receipt: CursorReceipt | null;
  content: string;
  sourceId?: string;
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

export interface IngestionTarget { topicTitle?: string; topicId?: string }

export type IngestionStatus =
  | "awaiting_confirmation"
  | "confirmed"
  | "processing"
  | "status_check_required"
  | "retry_waiting"
  | "failed"
  | "commit_conflict"
  | "topic_attachment_pending"
  | "cancelled"
  | "interrupted"
  | "completed";

export interface SourceDeletionImpact {
  sourceId: string; title: string; topics: readonly LibraryTopic[];
  assets: { bundle: boolean; blog: boolean; notes: boolean; plans: number; progress: boolean };
}

export interface ProcessingBatch {
  dismissed?: boolean;
  batchId: string;
  topicId: string | null;
  status: "confirmed" | "running" | "paused" | "completed" | "partial";
  error: { error_id: string; message: string } | null;
  executing?: boolean;
  items: readonly {
    dismissed?: boolean;
    itemId: string; fileName: string; sourceId: string | null;
    status: "queued" | "processing" | "completed" | "failed" | "cancelled" | "partial" | "deleted";
    ingestionStatus: string; blog: BlogStatus | null;
    error: { error_id: string; message: string } | null;
    remoteReference?: boolean;
    parserBackend?: "local-mineru" | "cloud";
    selectionReason?: string;
    parserProgress?: { status?: string; [key: string]: unknown };
    resubmitRisk?: { choice_id: string } | null;
  }[];
}

export interface IngestionItem {
  dismissed?: boolean;
  itemId: string;
  fileName: string;
  status: IngestionStatus;
  topicTitle: string | null;
  topicId: string | null;
  sourceId: string | null;
  documentStatus: string;
  topicStatus: string;
  services?: readonly string[];
  confirmation?: { services: readonly string[]; purpose: string; scope: string } | null;
  /** Staging returned this unfinished task for the same original instead of a new one. */
  duplicate?: boolean;
  /** A persisted remote task reference exists for the unfinished parse step. */
  remoteReference?: boolean;
  parserBackend?: "local-mineru" | "cloud";
  selectionReason?: string;
  parserProgress?: { status?: string; [key: string]: unknown };
  /** The risk choice bound to the current acceptance-unknown state, if any. */
  resubmitRisk?: { choiceId: string } | null;
  error?: { errorId: string; message: string };
  topicError?: { errorId: string; message: string };
}

export interface LibrarySource {
  shortName?: string;
  format?: "PDF" | "HTML" | "Markdown";
  publishedAt?: string | null;
  venue?: string | null;
  uploader?: string | null;
  preparation?: { ready: boolean; completed: number; total: number } | null;
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
  clearFinishedStatuses?(requestId: string): Promise<ReaderHostResult<ReadingWindow>>;
  listTopics?(): Promise<ReaderHostResult<readonly LibraryTopic[]>>;
  listSources?(): Promise<ReaderHostResult<readonly LibrarySource[]>>;
  listInbox?(): Promise<ReaderHostResult<readonly IngestionItem[]>>;
  listBatches?(): Promise<ReaderHostResult<readonly ProcessingBatch[]>>;
  createTopic?(title: string): Promise<ReaderHostResult<unknown>>;
  manageTopic?(topicId: string, action: "rename" | "delete" | "attach" | "detach" | "reorder", input: { title?: string; sourceId?: string; sourceIds?: readonly string[] }): Promise<ReaderHostResult<unknown>>;
  renameSource?(sourceId: string, title: string): Promise<ReaderHostResult<unknown>>;
  deletionImpact?(sourceId: string): Promise<ReaderHostResult<SourceDeletionImpact>>;
  startBatch?(itemIds: readonly string[], requestId: string, generateBlog?: boolean): Promise<ReaderHostResult<ProcessingBatch>>;
  controlBatch?(batchId: string, action: "stop" | "continue" | "cancel-item" | "remove-item" | "retry-item" | "resubmit-item", requestId: string, itemId?: string, riskChoiceId?: string): Promise<ReaderHostResult<ProcessingBatch>>;
  stageIngestion?(file: File, target: IngestionTarget): Promise<ReaderHostResult<IngestionItem>>;
  /** `generateBlog` is the Inbox checkbox: one confirmation, one authorized follow-up. */
  confirmIngestion?(itemId: string, generateBlog?: boolean): Promise<ReaderHostResult<IngestionItem>>;
  startIngestion?(itemId: string, requestId: string): Promise<ReaderHostResult<IngestionItem>>;
  blogStatus?(sourceId: string): Promise<ReaderHostResult<BlogStatus>>;
  generateBlog?(sourceId: string, requestId: string): Promise<ReaderHostResult<BlogStatus>>;
  regenerateBlog?(sourceId: string, requestId: string, artifact: BlogRegenerationTarget): Promise<ReaderHostResult<BlogStatus>>;
  cancelBlog?(sourceId: string): Promise<ReaderHostResult<BlogStatus>>;
  blogUrl?(sourceId: string): string;
  processIngestion?(itemId: string, requestId: string): Promise<ReaderHostResult<IngestionItem>>;
  continueIngestion?(itemId: string, requestId: string): Promise<ReaderHostResult<IngestionItem>>;
  /** Explicit resubmission after the user accepted the duplicate-parsing risk. */
  resubmitIngestion?(itemId: string, requestId: string, riskChoiceId: string): Promise<ReaderHostResult<IngestionItem>>;
  cancelIngestion?(itemId: string): Promise<ReaderHostResult<IngestionItem>>;
  sourceOriginalUrl?(sourceId: string): string;
  sourceContentUrl?(sourceId: string): string;
  deleteSource?(sourceId: string): Promise<ReaderHostResult<ReadingWindow>>;
  saveSourceDetails?(sourceId: string, title: string, topicIds: readonly string[], requestId: string): Promise<ReaderHostResult<ReadingWindow>>;
  clearSource?(sourceId: string, requestId: string): Promise<ReaderHostResult<ReadingWindow>>;
  replanSource?(sourceId: string, requestId?: string): Promise<ReaderHostResult<ReadingWindow>>;
  rereadSource?(sourceId: string): Promise<ReaderHostResult<ReadingWindow>>;
  openSource?(sourceId: string, requestId?: string): Promise<ReaderHostResult<ReadingWindow>>;
  activateReadingCandidate?(sourceId: string, planId: string, readingRevision: number, requestId: string): Promise<ReaderHostResult<ReadingWindow>>;
  dismissPreparation?(sourceId: string, attempt: string): Promise<ReaderHostResult<ReadingWindow>>;
  resumePreparation?(sourceId: string, requestId: string): Promise<ReaderHostResult<ReadingWindow>>;
  cancelPreparation?(sourceId: string): Promise<ReaderHostResult<ReadingWindow>>;
  selectDiscussionSource?(sourceId: string, discussionId?: string): Promise<ReaderHostResult<ReadingWindow>>;
  changeSourceNote?(sourceId: string, noteId: string, operation: "edit" | "delete" | "undo",
    expectedRevision: number, requestId: string, content?: string): Promise<ReaderHostResult<ReadingWindow>>;
  sourceNoteRequestResult?(sourceId: string, requestId: string): Promise<ReaderHostResult<SourceNoteRequestResult | null>>;
  retryReadingProgress?(progressId: string, requestId: string): Promise<ReaderHostResult<ReadingWindow>>;
  cancelReadingProgress?(progressId: string): Promise<ReaderHostResult<ReadingWindow>>;
  changeReadingProgress?(progressId: string, operation: "edit" | "delete", expectedRevision: number,
    requestId: string, content?: string): Promise<ReaderHostResult<ReadingWindow>>;
  backendSetup?(action: BackendSetupAction, input: BackendSetupInput): Promise<ReaderHostResult<BackendSetupResult>>;
  saveBackendConfiguration?(input: BackendSetupInput): Promise<ReaderHostResult<ReadingWindow>>;
  refreshBackendConfiguration?(): Promise<ReaderHostResult<ReadingWindow>>;
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
  finishReading?(input: FinishReadingInput): Promise<ReaderHostResult<ReadingWindow>>;
  rereadReading?(input: RereadReadingInput): Promise<ReaderHostResult<ReadingWindow>>;
  reviewChunk?(sourceId: string, planId: string, chunkId: string, requestId?: string): Promise<ReaderHostResult<ReadingWindow>>;
  readingRequestResult?(requestId: string): Promise<ReaderHostResult<ReadingWindow["readingOperation"]>>;
  sendMessage(
    input: SendReaderMessageInput,
    signal?: AbortSignal,
  ): Promise<ReaderHostResult<ReadingWindow>>;
}

export function cursorReceipt(window: ReadingWindow): CursorReceipt | null {
  const chunk = window.navigationCurrent ?? window.current;
  if (chunk === null) {
    return null;
  }
  return {
    sourceId: chunk.sourceId,
    planId: chunk.planId,
    chunkId: chunk.chunkId,
    ...(window.readingRevision === undefined ? {} : { readingRevision: window.readingRevision }),
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
export type BackendSetupAction = "inspect" | "prepare" | "account" | "login-start" | "login-status" | "login-cancel" | "check" | "models";
export interface BackendConfiguration {
  backend: "codex" | "deepseek";
  model: string;
  runtimePath: string | null;
  credentialFile: string | null;
}
export interface BackendConfigurationState {
  saved: BackendConfiguration;
  effective: BackendConfiguration;
  pending: boolean;
  busy: boolean;
  refreshBlocked: boolean;
  preferences?: Partial<Record<"codex" | "deepseek", Omit<Partial<BackendConfiguration>, 'model'> & { model?: string | null }>>;
  operationId?: string;
}
export interface BackendSetupInput {
  backend: "codex" | "deepseek";
  runtimePath?: string;
  model?: string;
  credentialFile?: string;
  loginId?: string;
  requestId?: string;
  preferences?: Partial<Record<'codex' | 'deepseek', Pick<BackendSetupInput, 'model' | 'runtimePath' | 'credentialFile'>>>;
}
export interface BackendSetupResult {
  backend: string;
  runtimePath: string | null;
  status: string;
  message: string;
  authUrl?: string;
  loginId?: string;
  environmentId?: string;
  dependencyStatus?: string;
  checkedModel?: string;
  catalogStatus?: string;
  catalogMessage?: string;
  models?: string[];
}
