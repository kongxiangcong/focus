import { useEffect, useRef, useState } from "react";
import { createReaderId, type ReaderChunk, type ReaderHost, type ReadingWindow, type SourceNote } from "@focus/reader-contracts";
import { MarkdownContent } from "../MarkdownContent";

export interface ChunkNoteListProps {
  chunk: ReaderChunk;
  notes: readonly SourceNote[];
  host: ReaderHost;
  onAccept: (value: ReadingWindow) => void;
  onToast?: (message: string, action?: { label: string; run: () => void }) => void;
  freshNoteId?: string | null;
  resetVersion?: number;
  noteClearVersion?: number;
  createSignal?: number;
  hideCreate?: boolean;
  onEditingChange?: (editing: boolean) => void;
  onSaved?: (note: SourceNote) => void;
}

const kinds = { thought: "想法", conclusion: "结论", question: "问题", example: "例子", concept: "概念" };
type EditableKind = "thought" | "conclusion" | "question";

export function ChunkNoteList({ chunk, notes, host, onAccept, onToast, freshNoteId, createSignal = 0,
  hideCreate, onEditingChange, onSaved, resetVersion = 0, noteClearVersion = 0 }: ChunkNoteListProps) {
  const [editor, setEditor] = useState<"new" | SourceNote | null>(null), [text, setText] = useState("");
  const [kind, setKind] = useState<EditableKind>("thought"), [busy, setBusy] = useState(false), [error, setError] = useState("");
  const [bundleChanged, setBundleChanged] = useState(false);
  const [conflict, setConflict] = useState<SourceNote | null>(null);
  const scope = `${chunk.sourceId}:${chunk.planId}:${chunk.chunkId}:${resetVersion}:${noteClearVersion}`;
  const currentScope = useRef(scope); currentScope.current = scope;
  const requestIds = useRef(new Map<string, string>());
  const priorScope = useRef(scope);
  const createDraftKey = `${chunk.sourceId}:${chunk.planId}:${chunk.chunkId}`;
  const draftKey = editor && editor !== "new" ? `${chunk.sourceId}:note:${editor.noteId}` : createDraftKey;
  function storedDrafts(): Record<string, { text: string; kind: EditableKind }> {
    try { return JSON.parse(sessionStorage.getItem("focus.chunkNoteDrafts") ?? "{}"); } catch { return {}; }
  }
  function persist(value: string | null, selectedKind = kind, key = draftKey) {
    try { const all = storedDrafts(); if (value === null) delete all[key]; else all[key] = { text: value, kind: selectedKind };
      sessionStorage.setItem("focus.chunkNoteDrafts", JSON.stringify(all)); } catch { /* Input remains in component state. */ }
  }
  const open = () => { const saved = storedDrafts()[createDraftKey]; setEditor("new"); setText(saved?.text ?? ""); setKind(saved?.kind ?? "thought"); setError(""); setBundleChanged(false); setConflict(null); };
  function edit(note: SourceNote) { const saved = storedDrafts()[`${chunk.sourceId}:note:${note.noteId}`];
    setEditor(note); setText(saved?.text ?? note.content); setError(""); setBundleChanged(false); setConflict(null); }
  useEffect(() => { if (createSignal > 0) open(); }, [createSignal]);
  useEffect(() => { onEditingChange?.(editor !== null); }, [!!editor, onEditingChange]);
  useEffect(() => { if (priorScope.current === scope) return; priorScope.current = scope;
    setEditor(null); setText(""); setBusy(false); setError(""); setBundleChanged(false); setConflict(null); requestIds.current.clear(); }, [scope]);
  const requestId = (key: string) => {
    if (!requestIds.current.has(key)) requestIds.current.set(key, createReaderId());
    return requestIds.current.get(key)!;
  };
  async function save(wholeSource = false) {
    const editing = editor && editor !== "new" ? editor : null;
    if ((!editing && !host.createSourceNote) || (editing && !host.changeSourceNote) || !text.trim() || busy) return;
    const capturedScope = scope;
    const content = text.trim(), expected = conflict?.revision ?? editing?.revision;
    const key = JSON.stringify([editing?.noteId ?? "create", expected, content, kind, wholeSource]);
    setBusy(true); setError("");
    const result = editing ? await host.changeSourceNote!(chunk.sourceId, editing.noteId, "edit", expected!, requestId(key), content)
      : await host.createSourceNote!({ sourceId: chunk.sourceId, requestId: requestId(key), content, kind, origin: "user",
        ...(wholeSource ? {} : { chunk: { planId: chunk.planId, chunkId: chunk.chunkId } }) });
    if (currentScope.current !== capturedScope) return;
    setBusy(false);
    if (!result.ok) { setError(result.error.message); setBundleChanged(result.error.code === "note_bundle_changed"); return; }
    onAccept(result.value); requestIds.current.delete(key);
    if (result.value.noteOperation?.status === "conflict") {
      setConflict(result.value.noteOperation.current ?? null); setError("笔记已由另一处修改；你的输入仍在，可查看新版后重新提交。"); return;
    }
    const note = result.value.noteOperation?.note;
    persist(null); setEditor(null); setText(""); setBundleChanged(false);
    if (note) onSaved?.(note);
  }
  async function change(note: SourceNote, operation: "delete" | "undo") {
    if (!host.changeSourceNote) return;
    const capturedScope = scope, key = JSON.stringify([note.noteId, note.revision, operation]);
    const result = await host.changeSourceNote(chunk.sourceId, note.noteId, operation, note.revision, requestId(key), undefined);
    if (currentScope.current !== capturedScope) return;
    if (!result.ok) { setError(result.error.message); onToast?.("小段笔记未更新", { label: "重试", run: () => void change(note, operation) }); return; }
    onAccept(result.value); requestIds.current.delete(key);
    if (result.value.noteOperation?.status === "conflict") { setError("笔记已由另一处修改，请查看当前版本后重试。"); return; }
    const changed = result.value.noteOperation?.note;
    if (operation === "delete" && changed) onToast?.("已删除小段笔记", { label: "撤销", run: () => void change(changed, "undo") });
  }
  return <>
    <ol>{notes.filter(note => !note.deleted && !note.sentence).map(note => <li className={`reader-chunk-notes__item${note.noteId === freshNoteId ? " is-new" : ""}`} key={note.noteId} data-chunk-note-id={note.noteId}>
      <div className="reader-chunk-notes__meta"><span className="reader-chunk-notes__tag">{kinds[note.kind]}</span>{note.origin === "dialogue" && <span className="reader-chunk-notes__tag reader-chunk-notes__tag--dlg">来自讨论</span>}
        {host.changeSourceNote && <span className="reader-chunk-notes__actions"><button className="reader-anno-ghost" onClick={() => edit(note)}>编辑</button><button className="reader-anno-ghost danger" onClick={() => void change(note, "delete")}>删除</button></span>}</div>
      <MarkdownContent text={note.content} sourceId={note.sourceId} />
    </li>)}</ol>
    {editor && <div className="reader-anno-editor">
      {editor === "new" && <div className="reader-anno-kinds" role="radiogroup" aria-label="笔记类型">{(["thought", "conclusion", "question"] as const).map(value =>
        <button key={value} role="radio" aria-checked={kind === value} onClick={() => { setKind(value); persist(text, value); }}>{kinds[value]}</button>)}</div>
      }
      <textarea autoFocus aria-label="小段笔记" placeholder="写下这一段的笔记…" maxLength={8000} value={text} onChange={event => { setText(event.target.value); persist(event.target.value); }} onKeyDown={event => {
        if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing && event.nativeEvent.keyCode !== 229) { event.preventDefault(); void save(); }
        else if (event.key === "Escape") { persist(null); setEditor(null); }
      }} />
      <div className="reader-anno-editor__bar"><small>Enter 保存 · Shift+Enter 换行 · Esc 取消</small>
        <button className="reader-anno-ghost" onClick={() => { persist(null); setEditor(null); }}>取消</button>
        <button className="reader-anno-primary" disabled={busy || !text.trim()} onClick={() => void save()}>保存</button></div>
      {error && <p role="alert">{error}</p>}
      {conflict && <p>已保存版本：{conflict.content}</p>}
      {bundleChanged && <button className="reader-anno-ghost" disabled={busy} onClick={() => void save(true)}>存为整篇笔记</button>}
    </div>}
    {!hideCreate && host.createSourceNote && <div className="reader-chunk-notes__bar"><button className="reader-anno-ghost" onClick={open}>+ 记小段笔记</button></div>}
  </>;
}
