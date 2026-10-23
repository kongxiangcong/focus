import { useLayoutEffect, useRef, useState, type RefObject } from "react";
import type { ReaderChunk, ReadingWindow, SourceNote } from "@focus/reader-contracts";
interface Options {
  view: ReadingWindow | null; groups: readonly { id: string; chunk: ReaderChunk | null }[];
  projected: Map<string, SourceNote[]>; stream: RefObject<HTMLElement | null>;
  onToast: (message: string, action?: { label: string; run: () => void }) => void;
  onJump: (target: HTMLElement) => void;
}
export function useNoteFeedback(options: Options) {
  const latest = useRef(options); latest.current = options;
  const seen = useRef<{ scope: string; ids: Set<string> } | null>(null);
  const sequence = useRef(0);
  const [fresh, setFresh] = useState<{ noteId: string; groupId: string; token: number } | null>(null);
  useLayoutEffect(() => {
    const { view, groups, projected } = options;
    if (!view) return;
    const scope = `${view.source.sourceId}:${view.resetVersion ?? 0}:${view.noteClearVersion ?? 0}`;
    const notes = view.sourceNotes ?? [], previous = seen.current;
    seen.current = { scope, ids: new Set(notes.map(note => note.noteId)) };
    if (!previous || previous.scope !== scope) { setFresh(null); return; }
    if (view.noteFeedback?.status !== "saved" || view.noteFeedback.sourceId !== view.source.sourceId) return;
    const additions = notes.filter(note => !previous.ids.has(note.noteId) && !note.deleted && !note.sentence && note.origin === "dialogue");
    const note = additions.at(-1); if (!note) return;
    const groupId = [...projected].find(([, items]) => items.some(item => item.noteId === note.noteId))?.[0];
    const group = groups.find(item => item.id === groupId);
    if (!group?.chunk) { setFresh(null); options.onToast("已存为整篇笔记，可在资料栏查看"); return; }
    setFresh({ noteId: note.noteId, groupId: group.id, token: ++sequence.current });
    options.onToast(`已存为第 ${group.chunk.index} 段的小段笔记`, { label: "查看", run: () => {
      const current = latest.current;
      const now = current.view;
      if (!now || `${now.source.sourceId}:${now.resetVersion ?? 0}:${now.noteClearVersion ?? 0}` !== scope) return;
      const owner = [...current.projected].find(([, items]) => items.some(item => item.noteId === note.noteId))?.[0];
      if (owner) setFresh({ noteId: note.noteId, groupId: owner, token: ++sequence.current });
      requestAnimationFrame(() => {
        const target = Array.from(current.stream.current?.querySelectorAll<HTMLElement>("[data-chunk-note-id], [data-note-id]") ?? []).find(el => (el.dataset.chunkNoteId ?? el.dataset.noteId) === note.noteId);
        if (!target) return;
        current.onJump(target);
        target.classList.remove("is-new"); void target.offsetWidth; target.classList.add("is-new");
      });
    } });
  }, [options.view]);
  return { freshNoteId: fresh?.noteId, freshGroupId: fresh?.groupId, freshToken: fresh?.token };
}
