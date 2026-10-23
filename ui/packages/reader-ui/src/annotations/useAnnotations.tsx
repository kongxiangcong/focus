import { useCallback, useEffect, useMemo, useRef, useState, type RefObject } from "react";
import { createReaderId, type AnnotationLayer as TextLayer, type ReaderChunk, type ReaderHost, type ReadingWindow, type SourceNote } from "@focus/reader-contracts";
import { blockOf, domAnnotatableText, domOffset } from "../annotatable-text";
import { groupLocated, quoteAt, type Located, type PendingAnnotation, type ResolvedMark } from "../annotation-projection";
import { chunkKey } from "../ReadingChunk";
import { AnnotationBubble } from "./AnnotationBubble";
import { AnnotationEditor } from "./AnnotationEditor";
import { AnnotationLayer } from "./AnnotationLayer";
import { AnnotationNotePop } from "./AnnotationNotePop";
import { AnnotationToast } from "./AnnotationToast";
import { useAnnotationDrafts } from "./useAnnotationDrafts";
import { useAnnotationActions } from "./useAnnotationActions";
import { editorKey, type AnnotationToastValue, type EditorTarget, type SelectionDraft } from "./types";

type Group = { id: string; chunk: ReaderChunk | null };
interface Registry { chunkKey: string; marks: readonly ResolvedMark[]; lost: readonly Located[]; layer: TextLayer; text: string; signature: string }
type Float = { kind: "selection"; draft: SelectionDraft; rect: DOMRect; crossBlock: boolean; partial: boolean }
  | { kind: "annotation"; mark: ResolvedMark; group: string; rect: DOMRect }
  | { kind: "editor"; target: EditorTarget; rect: DOMRect; conflict?: string }
  | { kind: "note"; note: SourceNote; rect: DOMRect };
interface Submitted { target: EditorTarget; text: string; scope: string }
const emptyWindow: ReadingWindow = { status: "reading", source: { sourceId: "", title: "", topicId: null }, current: null, history: [], conversation: [] };

export function useAnnotations({ host, view, accept, stream, groups, onReference, attached }: {
  host: ReaderHost; view: ReadingWindow | null; accept: (view: ReadingWindow) => void;
  stream: RefObject<HTMLElement | null>; groups: readonly Group[]; onReference: (chunk: ReaderChunk, text?: string) => void; attached: boolean;
}) {
  const scope = `${view?.source.sourceId ?? ""}:${view?.resetVersion ?? 0}:${view?.noteClearVersion ?? 0}`;
  const [float, setFloat] = useState<Float | null>(null), [text, setText] = useState("");
  const [linkedKey, setLinkedKey] = useState<string | null>(null), [registryVersion, setRegistryVersion] = useState(0);
  const [localToast, setLocalToast] = useState<AnnotationToastValue | null>(null);
  const registry = useRef(new Map<string, Registry>()), reports = useRef(new Map<string, (key: string, marks: readonly ResolvedMark[], lost: readonly Located[], layer: TextLayer, text: string) => void>());
  const origin = useRef<HTMLElement | null>(null), submitted = useRef(new Map<string, Submitted>()), drafts = useAnnotationDrafts();
  const latest = useRef({ float, text, scope, groups, attached }); latest.current = { float, text, scope, groups, attached };
  const priorScope = useRef(scope);
  const close = useCallback((restore = false) => { setFloat(null); setLinkedKey(null); if (restore) origin.current?.focus({ preventScroll: true }); }, []);
  const saved = useCallback((id: string, note: SourceNote) => {
    const item = submitted.current.get(id); submitted.current.delete(id);
    if (!item || item.scope !== latest.current.scope) return;
    const key = editorKey(item.target);
    if (drafts.read(key) === item.text) drafts.write(key, null);
    const current = latest.current;
    if (current.float?.kind === "editor" && editorKey(current.float.target) === key && current.text === item.text) {
      close(); requestAnimationFrame(() => {
        const markKey = `n:${note.noteId}`;
        const candidates = Array.from(stream.current?.querySelectorAll<HTMLElement>("[data-anno-bulb], [data-anno-card], .reader-anno[tabindex]") ?? []);
        const target = candidates.find(el => current.attached ? el.dataset.annoCard === markKey : el.dataset.annoBulb === markKey)
          ?? candidates.find(el => el.dataset.annoKey === markKey);
        target?.focus({ preventScroll: true });
      });
    }
  }, [close, drafts.read, drafts.write, stream]);
  const failed = useCallback((id: string) => {
    const item = submitted.current.get(id);
    if (!item || item.scope !== latest.current.scope) return;
    const current = latest.current;
    if (current.float?.kind === "editor" && editorKey(current.float.target) === editorKey(item.target)) return;
    const rect = origin.current?.getBoundingClientRect() ?? new DOMRect(16, 80, 200, 20);
    setText(drafts.read(editorKey(item.target)) ?? item.text); setFloat({ kind: "editor", target: item.target, rect });
  }, [drafts.read]);
  const conflicted = useCallback((id: string, current: SourceNote, attempted: string) => {
    const item = submitted.current.get(id); submitted.current.delete(id);
    if (!item || item.scope !== latest.current.scope) return;
    const active = latest.current.float;
    const value = active?.kind === "editor" && editorKey(active.target) === editorKey(item.target) ? latest.current.text : drafts.read(editorKey(item.target)) ?? attempted;
    setText(value); setFloat({ kind: "editor", target: { isNew: false, note: current },
      rect: active?.rect ?? origin.current?.getBoundingClientRect() ?? new DOMRect(16, 80, 200, 20), conflict: current.content });
  }, [drafts.read]);
  const actions = useAnnotationActions({ host, view: view ?? emptyWindow, accept, scope, onNoteSaved: saved, onNoteFailed: failed, onNoteConflict: conflicted });
  const located = useMemo(() => groupLocated(actions.highlights, actions.notes, groups), [actions.highlights, actions.notes, groups]);
  useEffect(() => {
    if (priorScope.current === scope) return;
    const oldSource = priorScope.current.split(":")[0];
    if (oldSource === view?.source.sourceId) drafts.clearSource(oldSource);
    priorScope.current = scope; submitted.current.clear(); registry.current.clear(); reports.current.clear();
    close(); setText(""); setLocalToast(null);
  }, [scope, close, drafts.clearSource, view?.source.sourceId]);
  const showToast = useCallback((message: string, action?: { label: string; run: () => void }) => {
    actions.dismissToast(); setLocalToast({ message, actionLabel: action?.label, action: action?.run });
  }, [actions.dismissToast]);
  const dismissToast = useCallback(() => { setLocalToast(null); actions.dismissToast(); }, [actions.dismissToast]);
  const onMarks = useCallback((group: string) => {
    if (!reports.current.has(group)) reports.current.set(group, (key, marks, lost, layer, value) => {
      const signature = JSON.stringify([key, layer, value, marks.map(mark => [mark.key, mark.start, mark.end, mark.highlight?.revision, mark.note?.revision]), lost.map(item => item.kind === "note" ? item.item.noteId : item.item.highlightId)]);
      const previous = registry.current.get(group);
      registry.current.set(group, { chunkKey: key, marks, lost, layer, text: value, signature });
      if (previous?.signature !== signature) setRegistryVersion(version => version + 1);
    });
    return reports.current.get(group)!;
  }, []);
  const lostSentenceNoteIds = useMemo(() => new Set([...registry.current.entries()].filter(([id]) => groups.some(group => group.id === id)).flatMap(([, entry]) => entry.lost.flatMap(item => item.kind === "note" ? [item.item.noteId] : []))), [registryVersion, groups]);
  useEffect(() => {
    for (const el of stream.current?.querySelectorAll<HTMLElement>("[data-anno-key], [data-anno-card]") ?? []) el.classList.toggle("is-linked", (el.dataset.annoKey ?? el.dataset.annoCard) === linkedKey);
  }, [linkedKey, registryVersion, stream]);
  function markElements(key: string) { return Array.from(stream.current?.querySelectorAll<HTMLElement>("[data-anno-key]") ?? []).filter(el => el.dataset.annoKey === key); }
  function markRect(key: string, last = false): DOMRect | undefined {
    const elements = markElements(key), el = last ? elements.at(-1) : elements[0];
    if (!el) return;
    const rects = el.getClientRects(); return (last ? rects[rects.length - 1] : rects[0]) ?? el.getBoundingClientRect();
  }
  function fallbackRect(note: SourceNote) {
    const group = groups.find(item => item.chunk?.sourceId === note.sourceId && item.chunk.planId === note.sentence?.planId && item.chunk.chunkId === note.sentence.chunkId);
    const el = Array.from(stream.current?.querySelectorAll<HTMLElement>("[data-reading-group]") ?? []).find(item => item.dataset.readingGroup === group?.id);
    const box = el?.getBoundingClientRect(); return box ? new DOMRect(box.left, box.bottom, box.width, 0) : new DOMRect(16, 80, 200, 20);
  }
  function draftRect(draft: SelectionDraft) {
    const article = Array.from(stream.current?.querySelectorAll<HTMLElement>(".focus-reading") ?? []).find(el => el.dataset.chunkKey === chunkKey(draft.chunk) && (!draft.groupId || el.closest<HTMLElement>("[data-reading-group]")?.dataset.readingGroup === draft.groupId));
    const root = article?.querySelector(".focus-markdown"); if (!root) return;
    if (article?.dataset.annotationLayer !== draft.layer) { const box = article!.getBoundingClientRect(); return new DOMRect(box.left, box.bottom, box.width, 0); }
    const { nodes } = domAnnotatableText(root);
    const start = nodes.find(item => draft.start >= item.start && draft.start < item.start + item.node.length);
    const end = [...nodes].reverse().find(item => draft.end > item.start && draft.end <= item.start + item.node.length);
    if (!start || !end) return;
    const range = document.createRange(); range.setStart(start.node, draft.start - start.start); range.setEnd(end.node, draft.end - end.start);
    const rects = range.getClientRects(); return rects[rects.length - 1] ?? range.getBoundingClientRect();
  }
  function openTarget(target: EditorTarget, rect: DOMRect) {
    if (latest.current.float?.kind === "editor" && latest.current.text.trim() && editorKey(latest.current.float.target) !== editorKey(target)) return;
    const value = drafts.read(editorKey(target)) ?? (target.isNew ? "" : target.note.content);
    setText(value); setFloat({ kind: "editor", target, rect }); setLocalToast(null);
    window.getSelection()?.removeAllRanges();
  }
  function openEditor(note: SourceNote) {
    const key = `n:${note.noteId}`; origin.current = markElements(key)[0] ?? null;
    openTarget({ isNew: false, note }, markRect(key, true) ?? fallbackRect(note));
  }
  function openNote(note: SourceNote) {
    if (latest.current.float?.kind === "editor" && latest.current.text.trim()) return;
    const key = `n:${note.noteId}`;
    origin.current = Array.from(stream.current?.querySelectorAll<HTMLElement>("[data-anno-bulb]") ?? []).find(el => el.dataset.annoBulb === key) ?? markElements(key)[0] ?? null;
    setFloat({ kind: "note", note, rect: origin.current?.getBoundingClientRect() ?? fallbackRect(note) }); setLinkedKey(key);
  }
  function cancelEditor() {
    if (float?.kind !== "editor") return;
    const target = float.target, value = text, rect = float.rect;
    drafts.write(editorKey(target), null); submitted.current.forEach((item, id) => { if (editorKey(item.target) === editorKey(target)) submitted.current.delete(id); });
    close(true);
    if (value.trim()) showToast(target.isNew ? "已放弃这条备注" : "已放弃修改", { label: "撤销", run: () => {
      drafts.write(editorKey(target), value); setText(value); setFloat({ kind: "editor", target, rect }); setLocalToast(null);
    } });
  }
  async function saveEditor() {
    if (float?.kind !== "editor" || !text.trim() || actions.busy) return;
    const target = float.target, id = createReaderId().replaceAll("-", ""), captured = text;
    submitted.current.set(id, { target, text: captured, scope }); setLocalToast(null);
    target.isNew ? await actions.createNote({ sourceId: target.draft.chunk.sourceId, requestId: id, content: captured, kind: "thought", origin: "user",
      chunk: { planId: target.draft.chunk.planId, chunkId: target.draft.chunk.chunkId }, sentence: { layer: target.draft.layer, range: { start: target.draft.start, end: target.draft.end }, quote: target.draft.quote } })
      : await actions.editNote(target.note, captured, id);
  }
  function draftForMark(mark: ResolvedMark, group: string): SelectionDraft | null {
    const entry = registry.current.get(group), chunk = groups.find(item => item.id === group)?.chunk;
    return entry && chunk ? { chunk, layer: entry.layer, start: mark.start, end: mark.end,
      quote: quoteAt(entry.text, mark.start, mark.end), text: entry.text.slice(mark.start, mark.end), groupId: group } : null;
  }
  const temporary = (mark: ResolvedMark) => mark.highlight?.highlightId.startsWith("p-") || mark.note?.noteId.startsWith("p-");
  function addHighlight(draft: SelectionDraft) {
    setLocalToast(null); close(); window.getSelection()?.removeAllRanges();
    void actions.createHighlight({ sourceId: draft.chunk.sourceId, requestId: createReaderId().replaceAll("-", ""), chunk: { planId: draft.chunk.planId, chunkId: draft.chunk.chunkId },
      layer: draft.layer, range: { start: draft.start, end: draft.end }, quote: draft.quote });
  }
  const readSelection = useCallback(() => {
    if (latest.current.float?.kind === "editor") return;
    const selection = window.getSelection();
    if (!selection?.rangeCount || selection.isCollapsed || !selection.toString().trim()) { if (latest.current.float?.kind === "selection") close(); return; }
    const range = selection.getRangeAt(0), startElement = range.startContainer.nodeType === 1 ? range.startContainer as Element : range.startContainer.parentElement;
    const article = startElement?.closest<HTMLElement>(".focus-reading"), root = startElement?.closest<HTMLElement>(".focus-markdown");
    if (!article || !root || !stream.current?.contains(article) || !root.contains(range.endContainer)) return;
    const group = article.closest<HTMLElement>("[data-reading-group]")?.dataset.readingGroup;
    const chunk = latest.current.groups.find(item => item.id === group)?.chunk;
    if (!chunk) return;
    const entry = registry.current.get(group!), layer = article.dataset.annotationLayer === "translation" ? "translation" : "source";
    const value = domAnnotatableText(root).text;
    let start = domOffset(root, range.startContainer, range.startOffset, "start"), end = domOffset(root, range.endContainer, range.endOffset, "end");
    if (start === null || end === null) return;
    while (start < end && /\s/.test(value[start])) start++;
    while (end > start && /\s/.test(value[end - 1])) end--;
    if (start >= end) return;
    const marks = entry?.layer === layer ? entry.marks : [], containing = marks.find(mark => start! >= mark.start && end! <= mark.end);
    const rect = range.getBoundingClientRect();
    if (containing && !temporary(containing)) { origin.current = markElements(containing.key)[0] ?? null; setFloat({ kind: "annotation", mark: containing, group: group!, rect }); return; }
    const partial = marks.some(mark => start! < mark.end && end! > mark.start);
    const crossBlock = !blockOf(root, range.startContainer) || blockOf(root, range.startContainer) !== blockOf(root, range.endContainer) || end - start > 2000;
    setFloat({ kind: "selection", draft: { chunk, layer, start, end, quote: quoteAt(value, start, end), text: value.slice(start, end), groupId: group }, rect, crossBlock, partial });
  }, [close, stream]);
  useEffect(() => {
    const root = stream.current; if (!root) return;
    let pointerDown = false, timer: ReturnType<typeof setTimeout> | undefined;
    const down = (event: PointerEvent) => {
      const element = event.target as Element;
      if (element.closest?.("[data-anno-ui]")) return;
      pointerDown = true;
      const active = latest.current.float;
      if (active?.kind === "editor" && latest.current.text.trim()) return;
      if (active?.kind === "editor") { drafts.write(editorKey(active.target), null); close(); }
      else if (!element.closest?.("[data-anno-key], [data-anno-bulb]")) close();
    };
    const up = (event: PointerEvent) => { pointerDown = false; if (!(event.target as Element).closest?.("[data-anno-ui]")) timer = setTimeout(readSelection, 0); };
    const change = () => { if (pointerDown) return; clearTimeout(timer); timer = setTimeout(readSelection, 220); };
    const resize = () => { if (latest.current.float?.kind === "selection") close(); };
    const escape = (event: KeyboardEvent) => { if (event.key === "Escape" && latest.current.float?.kind !== "editor") close(true); };
    document.addEventListener("pointerdown", down); document.addEventListener("pointerup", up); document.addEventListener("selectionchange", change);
    document.addEventListener("keydown", escape); window.addEventListener("resize", resize);
    return () => { clearTimeout(timer); document.removeEventListener("pointerdown", down); document.removeEventListener("pointerup", up); document.removeEventListener("selectionchange", change); document.removeEventListener("keydown", escape); window.removeEventListener("resize", resize); };
  }, [stream, readSelection, close, drafts.write, !!view]);
  useEffect(() => {
    const active = latest.current.float;
    if (active && !(active.kind === "editor" && latest.current.text.trim())) close();
  }, [attached]);
  function delegated(event: { target: EventTarget | null; preventDefault: () => void }, keyboard = false) {
    if (latest.current.float?.kind === "editor" && latest.current.text.trim()) return;
    const el = (event.target as Element).closest<HTMLElement>("[data-anno-bulb], [data-anno-key]");
    if (!el || (window.getSelection()?.toString().trim() && !keyboard)) return;
    const key = el.dataset.annoBulb ?? el.dataset.annoKey;
    const found = [...registry.current.entries()].map(([group, entry]) => ({ group, mark: entry.marks.find(mark => mark.key === key) })).find(item => item.mark);
    if (!found?.mark || temporary(found.mark)) return;
    event.preventDefault(); origin.current = el; setLinkedKey(key!);
    if (el.dataset.annoBulb && found.mark.note) openNote(found.mark.note);
    else setFloat({ kind: "annotation", mark: found.mark, group: found.group, rect: markRect(key!) ?? el.getBoundingClientRect() });
  }
  const pending = float?.kind === "editor" && float.target.isNew ? { ...float.target.draft, requestId: editorKey(float.target) } satisfies PendingAnnotation : null;
  let overlay = null;
  if (float) {
    const mark = float.kind === "annotation" ? float.mark : null;
    const getRect = () => {
      if (float.kind === "editor") return float.target.isNew ? draftRect(float.target.draft) ?? float.rect : markRect(`n:${float.target.note.noteId}`, true) ?? fallbackRect(float.target.note);
      if (float.kind === "annotation") return markRect(float.mark.key) ?? float.rect;
      if (float.kind === "note") {
        const bulb = Array.from(stream.current?.querySelectorAll<HTMLElement>("[data-anno-bulb]") ?? []).find(el => el.dataset.annoBulb === `n:${float.note.noteId}`);
        return (!attached ? bulb?.getBoundingClientRect() : markRect(`n:${float.note.noteId}`, true)) ?? fallbackRect(float.note);
      }
      return float.rect;
    };
    overlay = <AnnotationLayer stream={stream} getRect={getRect} bubble={float.kind === "selection" || float.kind === "annotation"} label={float.kind === "editor" ? "编辑备注" : "备注"}>
      {float.kind === "editor" ? <AnnotationEditor value={text} busy={actions.busy} conflict={float.conflict} onChange={value => { setText(value); drafts.write(editorKey(float.target), value); }} onSave={() => void saveEditor()} onCancel={cancelEditor} />
      : float.kind === "note" ? <AnnotationNotePop note={float.note} onEdit={() => openEditor(float.note)} onDelete={() => { close(); setLocalToast(null); void actions.deleteMark({ note: float.note, highlight: [...registry.current.values()].flatMap(entry => entry.marks).find(item => item.note?.noteId === float.note.noteId)?.highlight }); }} />
      : <AnnotationBubble mode={float.kind} highlight={!!mark?.highlight} hasNote={!!mark?.note} crossBlock={float.kind === "selection" && float.crossBlock} overlap={float.kind === "selection" && float.partial}
        canHighlight={!!host.createHighlight && (!mark?.highlight || !!host.changeHighlight)} canNote={!!host.createSourceNote || !!mark?.note && !!host.changeSourceNote}
        onHighlight={() => { if (float.kind === "selection") addHighlight(float.draft); else if (mark) {
          if (mark.highlight) { close(); setLocalToast(null); void actions.deleteMark({ highlight: mark.highlight }); }
          else { const draft = draftForMark(mark, float.group); if (draft) addHighlight(draft); }
        } }} onNote={() => { if (float.kind === "selection") openTarget({ isNew: true, draft: float.draft }, float.rect);
          else if (mark?.note) openEditor(mark.note); else if (mark) { const draft = draftForMark(mark, float.group); if (draft) openTarget({ isNew: true, draft }, markRect(mark.key, true) ?? float.rect); } }}
        onDelete={() => { if (mark) { close(); setLocalToast(null); void actions.deleteMark(mark); } }}
        onReference={() => { if (float.kind === "selection") { onReference(float.draft.chunk, float.draft.text); close(); window.getSelection()?.removeAllRanges(); } }} />}
    </AnnotationLayer>;
  }
  return { located, pending, onMarks, linkedKey, setLinkedKey, registry: registry.current, lostSentenceNoteIds, openEditor, openNote,
    deleteMark: actions.deleteMark, showToast, fresh: actions.fresh, notes: actions.notes, highlights: actions.highlights,
    overlay, toast: <AnnotationToast toast={localToast ?? actions.toast ?? null} onDismiss={dismissToast} />,
    readSelection, closeSelection: () => { if (float?.kind === "selection") close(); },
    onClick: delegated,
    onKeyDown: (event: { key: string; target: EventTarget | null; preventDefault: () => void }) => { if (["Enter", " "].includes(event.key)) delegated(event, true); },
    onPointerOver: (event: { target: EventTarget | null }) => { const el = (event.target as Element).closest<HTMLElement>("[data-anno-key]"); if (el) setLinkedKey(el.dataset.annoKey ?? null); },
    onPointerOut: () => setLinkedKey(null) };
}
