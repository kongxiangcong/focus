import { useState } from "react";
import { ChevronDown } from "./ReaderIcons";
import type { DirectorySection, sourceSections } from "./source-sections";

export function SectionDirectory({ id, open, sections, line, translated, onJump }: {
  id: string; open: boolean; sections: ReturnType<typeof sourceSections>; line: number | undefined;
  translated: boolean; onJump: (section: DirectorySection) => void;
}) {
  const [collapsed, setCollapsed] = useState<ReadonlySet<string>>(() => new Set());
  let active: DirectorySection | undefined;
  if (line !== undefined) for (const section of sections.order) {
    if (section.position.lines[0] > line) break;
    active = section;
  }
  for (let parent = active?.parentId; parent; parent = sections.byId.get(parent)?.parentId) {
    if (collapsed.has(parent)) active = sections.byId.get(parent);
  }

  function list(entries: readonly DirectorySection[], listId?: string, hidden = false) {
    return <ul id={listId} role="list" hidden={hidden}>{entries.map(section => {
      const title = translated ? section.translatedTitle : section.originalTitle;
      const branchId = `${id}-${section.position.lines[0]}`;
      const expanded = !collapsed.has(section.id);
      return <li key={section.id}>
        <div className="source-directory-row">
          {!!section.children.length && <button type="button" className="source-directory-branch" aria-label={`${title}的子章节`}
            aria-controls={branchId} aria-expanded={expanded} onClick={() => setCollapsed(previous => {
              const next = new Set(previous);
              if (!next.delete(section.id)) next.add(section.id);
              return next;
            })}><ChevronDown /></button>}
          <button type="button" className="source-directory-title" aria-current={section.id === active?.id ? "location" : undefined}
            onClick={() => onJump(section)}>{title}</button>
        </div>
        {!!section.children.length && list(section.children, branchId, !expanded)}
      </li>;
    })}</ul>;
  }

  return <nav id={id} className="source-directory" aria-label="目录" hidden={!open}>{list(sections.roots)}</nav>;
}
