import { useLayoutEffect, useRef, useState } from "react";
import type { SourceNote } from "@focus/reader-contracts";
import type { ResolvedMark } from "../annotation-projection";
import { AnnotationCard } from "./AnnotationCard";
import { ChunkNotes, type ChunkNotesProps } from "./ChunkNotes";
import { useRailLayout } from "./rail-layout";

export interface AnnotationRailProps extends ChunkNotesProps {
  marks: readonly ResolvedMark[];
  linkedKey?: string | null;
  onLink: (key: string | null) => void;
  onEdit: (note: SourceNote) => void;
  onDelete: (mark: ResolvedMark) => void;
  onStackedChange?: (stacked: boolean) => void;
}

export function AnnotationRail({ marks, linkedKey, onLink, onEdit, onDelete, onStackedChange, ...props }: AnnotationRailProps) {
  const aside = useRef<HTMLElement>(null), anchored = useRef<HTMLDivElement>(null), passage = useRef<HTMLElement>(null);
  const [stacked, setStacked] = useState(false);
  const stackedCallback = useRef(onStackedChange); stackedCallback.current = onStackedChange;
  const cards = marks.filter(mark => mark.note && !mark.note.deleted);
  // Highlight weight changes can move a line without changing the overall passage height.
  const signature = JSON.stringify(cards.map(mark => [mark.key, mark.start, mark.end, !!mark.highlight, mark.highlight?.revision, mark.note?.revision, mark.note?.content]));
  useLayoutEffect(() => {
    const rail = aside.current, grid = rail?.closest<HTMLElement>(".reading-group-passage");
    passage.current = grid?.querySelector<HTMLElement>(".reading-group-source") ?? null;
    if (!rail) return;
    const root = rail.closest<HTMLElement>(".focus-reader");
    let frame = 0, stopped = false;
    const measure = () => {
      frame = 0; if (stopped) return;
      let width = rail.getBoundingClientRect().width;
      if (grid && root && rail.dataset.annoRail === "stacked") {
        const style = getComputedStyle(root), area = grid.getBoundingClientRect().width;
        width = root.dataset.notesLayout === "split" ? area / 4 : area - (parseFloat(style.getPropertyValue("--reader-column")) || area) - (parseFloat(style.getPropertyValue("--reader-notes-gap")) || 32);
      }
      setStacked(root?.dataset.readingNarrow === "true" || (width > 0 && width < 200));
    };
    const schedule = () => { if (!stopped && !frame) frame = requestAnimationFrame(measure); };
    const observer = typeof ResizeObserver === "undefined" ? undefined : new ResizeObserver(schedule);
    observer?.observe(rail); if (grid) observer?.observe(grid);
    const attributes = new MutationObserver(schedule); if (root) attributes.observe(root, { attributes: true, attributeFilter: ["data-reading-narrow", "data-notes-layout", "data-reading-measure"] });
    window.addEventListener("resize", schedule); schedule();
    return () => { stopped = true; cancelAnimationFrame(frame); observer?.disconnect(); attributes.disconnect(); window.removeEventListener("resize", schedule); stackedCallback.current?.(false); };
  }, []);
  useLayoutEffect(() => { stackedCallback.current?.(stacked); }, [stacked]);
  useRailLayout(anchored, passage, signature, stacked);
  function pulse(key: string) {
    for (const element of passage.current?.querySelectorAll<HTMLElement>(".reader-anno[data-anno-key]") ?? []) {
      if (element.dataset.annoKey !== key) continue;
      element.classList.remove("is-pulse"); void element.offsetWidth; element.classList.add("is-pulse");
    }
  }
  return <aside ref={aside} className="reader-anno-rail" data-anno-rail={stacked ? "stacked" : "anchored"} aria-label={`第 ${props.chunk.index} 段笔记`}>
    <div ref={anchored} className="reader-anno-rail__anchored">{cards.map(mark => <AnnotationCard key={mark.key} mark={mark}
      linked={linkedKey === mark.key} onLink={onLink} onEdit={onEdit} onDelete={onDelete} onPulse={pulse} />)}</div>
    <div className="reader-anno-rail__foot"><ChunkNotes {...props} /></div>
  </aside>;
}
