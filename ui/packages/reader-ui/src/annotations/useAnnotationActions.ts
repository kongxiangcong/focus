import { useCallback, useEffect, useRef, useState } from "react";
import { createReaderId, readerFailure, type CreateHighlightInput, type CreateSourceNoteInput, type HighlightOperation,
  type ReaderHost, type ReaderHostResult, type ReadingHighlight, type ReadingWindow, type SentenceLocator, type SourceNote, type SourceNoteOperation, type SourceNoteRequestResult } from "@focus/reader-contracts";

export interface AnnotationActionToast { message: string; actionLabel?: string; action?: () => void }
export interface AnnotationActionOptions {
  host: ReaderHost; view: ReadingWindow; accept: (view: ReadingWindow) => void; scope: string;
  onNoteSaved?: (requestId: string, note: SourceNote) => void;
  onNoteFailed?: (requestId: string) => void;
  onNoteConflict?: (requestId: string, current: SourceNote, attemptedContent: string) => void;
}
interface Write {
  entity: "highlight" | "note"; operation: "create" | "edit" | "delete" | "undo";
  requestId: string; sourceId: string; highlightInput?: CreateHighlightInput; noteInput?: CreateSourceNoteInput;
  highlight?: ReadingHighlight; note?: SourceNote; content?: string;
}
interface Overlay { epoch: number; write: Write; highlight?: ReadingHighlight; note?: SourceNote }
interface JournalEntry { scope: string; write: Write }
const JOURNAL_KEY = "focus.annotationRequests";
const id = () => createReaderId().replaceAll("-", "");

function journal(): JournalEntry[] {
  try {
    const entries: unknown = JSON.parse(sessionStorage.getItem(JOURNAL_KEY) ?? "[]");
    return Array.isArray(entries) ? entries.filter(entry => entry && typeof entry.scope === "string" && typeof entry.write?.requestId === "string" &&
      typeof entry.write?.sourceId === "string" && ["highlight", "note"].includes(entry.write.entity) && ["create", "edit", "delete", "undo"].includes(entry.write.operation)) : [];
  } catch { return []; }
}
function saveJournal(scope: string, write: Write, remove = false) {
  try {
    const entries = journal().filter(entry => entry.scope !== scope || entry.write.requestId !== write.requestId);
    if (!remove) entries.push({ scope, write });
    if (entries.length) sessionStorage.setItem(JOURNAL_KEY, JSON.stringify(entries)); else sessionStorage.removeItem(JOURNAL_KEY);
  } catch { /* A storage restriction must not prevent an explicit write. */ }
}
function mergeRecords<T extends { revision: number }>(incoming: readonly T[], existing: readonly T[], key: (record: T) => string): T[] {
  const records = new Map(existing.map(record => [key(record), record]));
  for (const record of incoming) if (!records.has(key(record)) || records.get(key(record))!.revision <= record.revision) records.set(key(record), record);
  return [...records.values()];
}
function operation(write: Write, view: ReadingWindow): HighlightOperation | SourceNoteOperation | null | undefined {
  return write.entity === "highlight" ? view.highlightOperation : view.noteOperation;
}
function acknowledged(write: Write, result: ReaderHostResult<ReadingWindow>): boolean {
  const op = result.ok ? operation(write, result.value) : null;
  return !!op && op.status !== "conflict" && (write.entity === "highlight" ? !!(op as HighlightOperation).highlight : !!(op as SourceNoteOperation).note);
}
function sameLocator(a: SentenceLocator | null | undefined, b: SentenceLocator | null | undefined): boolean {
  return !!a && !!b && a.planId === b.planId && a.chunkId === b.chunkId && a.layer === b.layer && a.range.start === b.range.start && a.range.end === b.range.end && a.quote.exact === b.quote.exact;
}

/** Ephemeral write overlays; ReadingWindow remains the durable Host authority. */
export function useAnnotationActions(options: AnnotationActionOptions) {
  const optionsRef = useRef(options); optionsRef.current = options;
  const scopeRef = useRef(options.scope), epochRef = useRef(0), mounted = useRef(true);
  if (scopeRef.current !== options.scope) { scopeRef.current = options.scope; epochRef.current++; }
  const observedView = useRef(options.view), latestView = useRef(options.view);
  if (observedView.current !== options.view) { observedView.current = options.view; latestView.current = options.view; }
  const sequence = useRef(0), acceptedSequence = useRef(0);
  const [overlays, setOverlays] = useState<Map<string, Overlay>>(new Map());
  const [recovering, setRecovering] = useState<{ epoch: number; count: number }>({ epoch: 0, count: 0 });
  const [toastState, setToast] = useState<{ epoch: number; token: number; value: AnnotationActionToast } | null>(null);
  const toastToken = useRef(0), toastTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const [freshIds, setFreshIds] = useState<Map<string, { epoch: number; flag: "hl" | "note" }>>(new Map());
  const freshTimers = useRef(new Set<ReturnType<typeof setTimeout>>());
  const flights = useRef(new Map<string, { epoch: number; identity: string; promise: Promise<ReaderHostResult<ReadingWindow>> }>());
  const active = (epoch: number) => mounted.current && epoch === epochRef.current;

  const dismissToast = useCallback(() => { clearTimeout(toastTimer.current); setToast(null); }, []);
  function showToast(value: AnnotationActionToast, epoch: number) {
    if (!active(epoch)) return;
    clearTimeout(toastTimer.current);
    const token = ++toastToken.current;
    setToast({ epoch, token, value: { ...value, ...(value.action ? { action: () => { if (active(epoch)) value.action!(); } } : {}) } });
    toastTimer.current = setTimeout(() => { if (active(epoch)) setToast(current => current?.token === token ? null : current); }, 6000);
  }
  function markFresh(entity: "highlight" | "note", recordId: string, epoch: number) {
    const key = `${entity}:${recordId}`;
    setFreshIds(current => new Map(current).set(key, { epoch, flag: entity === "highlight" ? "hl" : "note" }));
    const timer = setTimeout(() => {
      freshTimers.current.delete(timer);
      if (active(epoch)) setFreshIds(current => { const next = new Map(current); next.delete(key); return next; });
    }, 800);
    freshTimers.current.add(timer);
  }
  function acceptSnapshot(snapshot: ReadingWindow, seq: number, epoch: number) {
    if (!active(epoch) || snapshot.source.sourceId !== optionsRef.current.view.source.sourceId) return;
    const previous = latestView.current;
    const older = snapshot.revision !== undefined && previous.revision !== undefined ? snapshot.revision < previous.revision : seq < acceptedSequence.current;
    const next: ReadingWindow = { ...(older ? previous : snapshot),
      sourceHighlights: mergeRecords(snapshot.sourceHighlights ?? [], previous.sourceHighlights ?? [], record => record.highlightId),
      sourceNotes: mergeRecords(snapshot.sourceNotes ?? [], previous.sourceNotes ?? [], record => record.noteId),
      highlightOperation: snapshot.highlightOperation, noteOperation: snapshot.noteOperation };
    latestView.current = next; acceptedSequence.current = Math.max(seq, acceptedSequence.current);
    optionsRef.current.accept(next);
  }
  function optimistic(write: Write, epoch: number): Overlay {
    const view = latestView.current;
    const pointer = write.highlightInput?.chunk ?? write.noteInput?.chunk;
    const chunk = pointer ? [view.current, ...view.history, view.reviewChunk, view.navigationCurrent, ...(view.timeline ?? []).flatMap(event => event.kind === "reading" ? [event.chunk] : [])].find(c => c?.planId === pointer.planId && c.chunkId === pointer.chunkId && c.sourceId === write.sourceId) : null;
    if (write.operation === "create" && write.highlightInput && chunk) return { epoch, write, highlight: {
      highlightId: `p-${write.requestId}`, sourceId: write.sourceId, revision: 0, bundle: chunk.bundleVersion ?? "", sourceLines: chunk.sourceLines,
      ...write.highlightInput.chunk, layer: write.highlightInput.layer, range: write.highlightInput.range, quote: write.highlightInput.quote, deleted: false, canUndo: false, sourceUpdated: false } };
    if (write.operation === "create" && write.noteInput) {
      const input = write.noteInput;
      return { epoch, write, note: { noteId: `p-${write.requestId}`, sourceId: input.sourceId, revision: 0, bundle: chunk?.bundleVersion ?? "", content: input.content,
        kind: input.kind, origin: input.origin, evidenceRole: input.kind === "question" ? "unresolved_question" : "explanation",
        anchor: chunk ? { sourceId: input.sourceId, bundle: chunk.bundleVersion ?? "", sourceLines: chunk.sourceLines } : null, placement: null,
        sentence: input.sentence && input.chunk ? { ...input.sentence, ...input.chunk } : null, deleted: false, canUndo: false, sourceUpdated: false, referenceStatus: "current" } };
    }
    return { epoch, write, ...(write.highlight ? { highlight: { ...write.highlight, deleted: write.operation === "delete" } } : {}),
      ...(write.note ? { note: { ...write.note, deleted: write.operation === "delete", ...(write.operation === "edit" ? { content: write.content! } : {}) } } : {}) };
  }
  async function dispatch(write: Write): Promise<ReaderHostResult<ReadingWindow>> {
    const host = optionsRef.current.host;
    try {
      if (write.highlightInput && host.createHighlight) return await host.createHighlight(write.highlightInput);
      if (write.noteInput && host.createSourceNote) return await host.createSourceNote(write.noteInput);
      if (write.highlight && host.changeHighlight) return await host.changeHighlight(write.sourceId, write.highlight.highlightId, write.operation as "delete" | "undo", write.highlight.revision, write.requestId);
      if (write.note && host.changeSourceNote) return await host.changeSourceNote(write.sourceId, write.note.noteId, write.operation as "edit" | "delete" | "undo", write.note.revision, write.requestId, write.content);
      return readerFailure("unavailable", "宿主不支持此标注操作");
    } catch (error) { return readerFailure("unavailable", error instanceof Error ? error.message : "保存失败，请重试", true); }
  }
  function noteFailed(write: Write) { if (write.entity === "note" && ["create", "edit"].includes(write.operation)) optionsRef.current.onNoteFailed?.(write.requestId); }
  function receive(write: Write, result: ReaderHostResult<ReadingWindow>, seq: number, epoch: number, quiet: boolean) {
    if (!active(epoch)) return;
    if (result.ok) {
      acceptSnapshot(result.value, seq, epoch);
      const op = operation(write, result.value);
      if (op?.status === "conflict") {
        saveJournal(scopeRef.current, write, true); noteFailed(write);
        const current = write.entity === "note" ? (op as SourceNoteOperation).current : undefined;
        if (current) optionsRef.current.onNoteConflict?.(write.requestId, current, write.content ?? write.noteInput?.content ?? "");
        if (!quiet) showToast({ message: write.entity === "note" ? "备注已更新，请检查当前内容后重新保存" : "标注已更新，请重新选择后操作" }, epoch);
        return;
      }
      if (acknowledged(write, result)) {
        saveJournal(scopeRef.current, write, true);
        if (!quiet) dismissToast();
        if (write.entity === "note") {
          const note = (op as SourceNoteOperation).note!;
          if (["create", "edit"].includes(write.operation)) optionsRef.current.onNoteSaved?.(write.requestId, note);
          if (write.operation === "create") markFresh("note", note.noteId, epoch);
        } else if (write.operation === "create") markFresh("highlight", (op as HighlightOperation).highlight!.highlightId, epoch);
        return;
      }
    }
    noteFailed(write);
    const bundleChanged = !result.ok && ["highlight_bundle_changed", "note_bundle_changed"].includes(result.error.code);
    if (bundleChanged) saveJournal(scopeRef.current, write, true);
    if (!quiet) showToast(bundleChanged ? { message: "这段原文已更新，标注未保存" } : {
      message: write.entity === "highlight" ? "重点未保存" : "备注未保存", actionLabel: "重试", action: () => { void run(write, epoch); },
    }, epoch);
  }
  function run(write: Write, epoch = epochRef.current, quiet = false): Promise<ReaderHostResult<ReadingWindow>> {
    if (!active(epoch) || write.sourceId !== optionsRef.current.view.source.sourceId) return Promise.resolve(readerFailure("unavailable", "阅读上下文已改变"));
    write = structuredClone(write);
    const identity = JSON.stringify(write), existing = flights.current.get(write.requestId);
    if (existing?.epoch === epoch) return existing.identity === identity ? existing.promise : Promise.resolve(readerFailure("invalid-request", "请求已用于不同内容"));
    const scope = scopeRef.current, seq = ++sequence.current;
    saveJournal(scope, write);
    setOverlays(current => new Map(current).set(write.requestId, optimistic(write, epoch)));
    const promise = (async () => {
      const result = await dispatch(write);
      if (!active(epoch)) return readerFailure("unavailable", "阅读上下文已改变");
      receive(write, result, seq, epoch, quiet);
      return result;
    })().finally(() => {
      if (flights.current.get(write.requestId)?.epoch === epoch) flights.current.delete(write.requestId);
      if (active(epoch)) setOverlays(current => { const next = new Map(current); next.delete(write.requestId); return next; });
    });
    flights.current.set(write.requestId, { epoch, identity, promise });
    return promise;
  }

  function changedRecord(write: Write, result: ReaderHostResult<ReadingWindow>): Write | null {
    if (!acknowledged(write, result) || !result.ok) return null;
    const op = operation(write, result.value)!;
    return { ...write, requestId: id(), operation: "undo", highlight: (op as HighlightOperation).highlight, note: (op as SourceNoteOperation).note };
  }
  async function removeOrRestore(writes: Write[], completed: Write[], epoch: number, restoring = false): Promise<void> {
    const results = await Promise.all(writes.map(write => run(write, epoch, true)));
    if (!active(epoch)) return;
    const failed: Write[] = [], success = [...completed];
    results.forEach((result, index) => {
      const write = writes[index];
      if (acknowledged(write, result)) { const inverse = changedRecord(write, result); if (inverse) success.push(inverse); }
      else failed.push(write);
    });
    if (failed.length) {
      const retryable = results.some(result => !result.ok && !["highlight_bundle_changed", "note_bundle_changed"].includes(result.error.code));
      showToast({ message: restoring ? "部分标注未恢复" : success.length ? "标注只删除了一部分" : "标注未删除",
        ...(retryable ? { actionLabel: "重试", action: () => { void removeOrRestore(failed, success, epoch, restoring); } } : {}) }, epoch);
    } else showToast(restoring ? { message: "已恢复标注" } : { message: "已删除标注", actionLabel: "撤销", action: () => { void removeOrRestore(success, [], epoch, true); } }, epoch);
  }

  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; epochRef.current++; clearTimeout(toastTimer.current); for (const timer of freshTimers.current) clearTimeout(timer); };
  }, []);
  useEffect(() => {
    setOverlays(new Map()); setFreshIds(new Map()); dismissToast();
    const epoch = epochRef.current, entries = journal().filter(entry => entry.scope === options.scope && entry.write.sourceId === options.view.source.sourceId);
    setRecovering({ epoch, count: entries.length });
    for (const { write } of entries) void (async () => {
      const host = optionsRef.current.host;
      let result: ReaderHostResult<HighlightOperation | SourceNoteRequestResult | null>;
      try {
        result = write.entity === "highlight" && host.highlightRequestResult ? await host.highlightRequestResult(write.sourceId, write.requestId)
          : write.entity === "note" && host.sourceNoteRequestResult ? await host.sourceNoteRequestResult(write.sourceId, write.requestId)
          : readerFailure("unavailable", "标注请求结果不可用");
      } catch { result = readerFailure("unavailable", "标注请求结果不可用", true); }
      if (!active(epoch)) return;
      if (result.ok && result.value?.status === "cancelled") { saveJournal(options.scope, write, true); noteFailed(write); }
      else if (result.ok && result.value) {
        const snapshot = { ...latestView.current };
        if (write.entity === "highlight") {
          const op = result.value as HighlightOperation; snapshot.highlightOperation = { ...op, sourceId: write.sourceId };
          const record = op.highlight ?? op.current;
          if (record) snapshot.sourceHighlights = mergeRecords([record], snapshot.sourceHighlights ?? [], h => h.highlightId);
        } else {
          const op = result.value as SourceNoteOperation; snapshot.noteOperation = { ...op, sourceId: write.sourceId };
          const record = op.note ?? op.current;
          if (record) snapshot.sourceNotes = mergeRecords([record], snapshot.sourceNotes ?? [], n => n.noteId);
        }
        receive(write, { ok: true, value: snapshot }, ++sequence.current, epoch, false);
      } else { noteFailed(write); showToast({ message: write.entity === "highlight" ? "重点未保存" : "备注未保存", actionLabel: "重试", action: () => { void run(write, epoch); } }, epoch); }
      setRecovering(current => current.epoch === epoch ? { epoch, count: Math.max(0, current.count - 1) } : current);
    })();
  }, [options.scope]);

  const currentOverlays = [...overlays.values()].filter(item => item.epoch === epochRef.current);
  const highlights = [...(options.view.sourceHighlights ?? [])], notes = [...(options.view.sourceNotes ?? [])];
  for (const overlay of currentOverlays) {
    if (overlay.highlight) {
      const i = highlights.findIndex(h => h.highlightId === overlay.highlight!.highlightId);
      const committed = overlay.write.operation === "create" && highlights.some(h => !h.deleted && !h.highlightId.startsWith("p-") && sameLocator(h, overlay.highlight));
      if (i < 0 && !committed) highlights.push(overlay.highlight); else if (i >= 0 && highlights[i].revision <= overlay.highlight.revision) highlights[i] = overlay.highlight;
    }
    if (overlay.note) {
      const i = notes.findIndex(n => n.noteId === overlay.note!.noteId);
      const committed = overlay.write.operation === "create" && notes.some(n => !n.deleted && !n.noteId.startsWith("p-") && n.content === overlay.note!.content && n.kind === overlay.note!.kind && n.origin === overlay.note!.origin &&
        (sameLocator(n.sentence, overlay.note!.sentence) || (!n.sentence && !overlay.note!.sentence && JSON.stringify(n.anchor) === JSON.stringify(overlay.note!.anchor))));
      if (i < 0 && !committed) notes.push(overlay.note); else if (i >= 0 && notes[i].revision <= overlay.note.revision) notes[i] = overlay.note;
    }
  }
  const fresh: Record<string, ("hl" | "note")[]> = {};
  for (const highlight of highlights) if (freshIds.get(`highlight:${highlight.highlightId}`)?.epoch === epochRef.current || currentOverlays.some(item => item.write.operation === "create" && item.highlight?.highlightId === highlight.highlightId)) {
    fresh[`h:${highlight.highlightId}`] = ["hl"];
    for (const note of notes) if (note.sentence?.planId === highlight.planId && note.sentence.chunkId === highlight.chunkId && note.sentence.layer === highlight.layer &&
      note.sentence.range.start === highlight.range.start && note.sentence.range.end === highlight.range.end) fresh[`n:${note.noteId}`] = ["hl"];
  }
  for (const note of notes) if (freshIds.get(`note:${note.noteId}`)?.epoch === epochRef.current || currentOverlays.some(item => item.write.operation === "create" && item.note?.noteId === note.noteId)) fresh[`n:${note.noteId}`] = [...(fresh[`n:${note.noteId}`] ?? []), "note"];
  return {
    highlights, notes, fresh, toast: toastState?.epoch === epochRef.current ? toastState.value : null, dismissToast,
    busy: currentOverlays.length > 0 || (recovering.epoch === epochRef.current && recovering.count > 0),
    createHighlight: (input: CreateHighlightInput) => run({ entity: "highlight", operation: "create", sourceId: input.sourceId, requestId: input.requestId, highlightInput: input }),
    createNote: (input: CreateSourceNoteInput) => run({ entity: "note", operation: "create", sourceId: input.sourceId, requestId: input.requestId, noteInput: input }),
    editNote: (note: SourceNote, content: string, requestId = id()) => run({ entity: "note", operation: "edit", sourceId: note.sourceId, requestId, note, content }),
    deleteMark: ({ highlight, note }: { highlight?: ReadingHighlight; note?: SourceNote }) => removeOrRestore([
      ...(highlight ? [{ entity: "highlight" as const, operation: "delete" as const, sourceId: highlight.sourceId, requestId: id(), highlight }] : []),
      ...(note ? [{ entity: "note" as const, operation: "delete" as const, sourceId: note.sourceId, requestId: id(), note }] : []),
    ], [], epochRef.current),
  };
}
