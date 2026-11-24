import type { ChunkNoteLink } from "./selected-source-note";

export function ChunkNoteLinks({ links }: { links: readonly ChunkNoteLink[] }) {
  return <span data-anno-ui="">
    {links.map(link => <button key={link.index} type="button" className="source-chunk-note-link"
      data-shared-note-link={link.noteId} aria-label={`第 ${link.index} 段小段笔记 · ${link.count}`}>
      小段笔记 · {link.count}
    </button>)}
  </span>;
}
