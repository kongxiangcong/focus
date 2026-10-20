import { useEffect, useLayoutEffect, useRef, type RefObject } from "react";
import type { LibrarySource } from "@focus/reader-contracts";

export const reducedLibraryMotion = () => document.documentElement.dataset.reducedMotion === "true" || !!globalThis.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
const token = (name: string) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
const duration = (name: string) => { const value = token(name); return parseFloat(value) * (value.endsWith("ms") ? 1 : 1000) || 0; };
const offset = (node: HTMLElement) => {
  const transform = getComputedStyle(node).transform;
  if (!transform || transform === "none") return 0;
  if (typeof DOMMatrixReadOnly !== "undefined") return new DOMMatrixReadOnly(transform).m42;
  return Number(transform.match(/^matrix\([^,]+,[^,]+,[^,]+,[^,]+,[^,]+,\s*([^,)]+)/)?.[1]) || 0;
};

export function useLibraryMotion(root: RefObject<HTMLElement | null>, rows: readonly LibrarySource[], sources: readonly LibrarySource[], loading: boolean, context: string, ordered: boolean) {
  const known = useRef<Set<string> | null>(null), positions = useRef(new Map<string, number>()), previous = useRef({ context: "", ids: "" });
  const animations = useRef(new Map<HTMLElement, Animation>());
  const ids = JSON.stringify(rows.map(source => source.sourceId)), allIds = JSON.stringify(sources.map(source => source.sourceId));
  useLayoutEffect(() => {
    if (loading) return;
    const arrivals = new Set<string>();
    if (known.current) sources.forEach(source => { if (!known.current!.has(source.sourceId)) arrivals.add(source.sourceId); });
    else known.current = new Set();
    sources.forEach(source => known.current!.add(source.sourceId));
    const sameContext = previous.current.context === context;
    const oldIds: string[] = previous.current.ids ? JSON.parse(previous.current.ids) : [];
    const sameMembers = oldIds.length === rows.length && rows.every(source => oldIds.includes(source.sourceId));
    const next = new Map<string, number>();
    root.current?.querySelectorAll<HTMLElement>("[data-source-id]").forEach(node => {
      const id = node.dataset.sourceId!, before = positions.current.get(id), currentOffset = offset(node);
      animations.current.get(node)?.cancel(); animations.current.delete(node);
      const scroller = node.closest<HTMLElement>(".library-sources"), top = node.getBoundingClientRect().top + (scroller?.scrollTop ?? 0); next.set(id, top);
      if (reducedLibraryMotion() || !node.animate || !sameContext) return;
      let animation: Animation | undefined;
      if (ordered && sameMembers && before !== undefined && Math.abs(before + currentOffset - top) > 0) animation = node.animate([{ transform: `translateY(${before + currentOffset - top}px)` }, { transform: "none" }], { duration: duration("--reader-duration-travel"), easing: token("--reader-ease-inout") });
      else if (arrivals.has(id)) animation = node.animate([{ opacity: 0, transform: `translateY(${token("--reader-gap-sm")})` }, { opacity: 1, transform: "none" }], { duration: duration("--reader-duration-move"), easing: token("--reader-ease-out") });
      if (animation) { animations.current.set(node, animation); animation.onfinish = () => animations.current.delete(node); }
    });
    animations.current.forEach((animation, node) => { if (!node.isConnected) { animation.cancel(); animations.current.delete(node); } });
    positions.current = next; previous.current = { context, ids };
  }, [ids, allIds, loading, context, ordered, root]);
  useEffect(() => {
    const cancel = () => { if (reducedLibraryMotion()) { animations.current.forEach(animation => animation.cancel()); animations.current.clear(); } };
    const observer = new MutationObserver(cancel), preference = globalThis.matchMedia?.("(prefers-reduced-motion: reduce)");
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ["data-reduced-motion"] }); preference?.addEventListener?.("change", cancel);
    return () => { observer.disconnect(); preference?.removeEventListener?.("change", cancel); animations.current.forEach(animation => animation.cancel()); animations.current.clear(); };
  }, []);
}
