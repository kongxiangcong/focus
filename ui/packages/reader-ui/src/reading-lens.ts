import { useLayoutEffect, useRef, useState } from "react";

export interface LensPosition { id: string; top: number }
export interface LensSelection { id: string; candidate: string | null; since: number; lockedUntil: number }
export const lockReadingLens = (id: string, now: number): LensSelection => ({ id, candidate: null, since: now, lockedUntil: now + 700 });

/** Pure visual selection. Positions and reading line share scroll-content coordinates. */
export function advanceReadingLens(state: LensSelection, groups: readonly LensPosition[], line: number, now: number): LensSelection {
  if (!groups.length || now < state.lockedUntil) return state;
  const current = groups.findIndex(group => group.id === state.id);
  let next = 0;
  groups.forEach((group, index) => { if (group.top <= line) next = index; });
  // Cross the boundary by 24px in either direction before starting the dwell clock.
  if (next === current || (next > current && line - groups[next].top < 24)
    || (next < current && groups[current].top - line < 24)) {
    return state.candidate === null ? state : { ...state, candidate: null };
  }
  const id = groups[next].id;
  if (id !== state.candidate) return { ...state, candidate: id, since: now };
  return now - state.since >= 140 ? { ...state, id, candidate: null } : state;
}

/** One surface and one pending dwell timer; scroll, never hover, drives selection. */
export function useReadingLens(scope: string, ids: readonly string[], enabled: boolean) {
  const document = useRef<HTMLDivElement>(null);
  const surface = useRef<HTMLDivElement>(null);
  const selection = useRef<LensSelection | null>(null);
  const [activeId, setActiveId] = useState<string | null>(null);
  const signature = JSON.stringify(ids);
  const jump = useRef<(id: string) => void>(() => {});

  useLayoutEffect(() => {
    const root = document.current;
    const pane = root?.closest<HTMLElement>(".focus-stream");
    if (!enabled || !root || !pane || !ids.length) {
      selection.current = null; setActiveId(null); return;
    }
    const groups = Array.from(root.querySelectorAll<HTMLElement>("[data-lens-group]"));
    let timer: ReturnType<typeof setTimeout> | undefined;
    const place = () => {
      const group = groups.find(el => el.dataset.lensGroup === selection.current?.id);
      if (!group || !surface.current) return;
      surface.current.style.transform = `translateY(${group.offsetTop - 18}px)`;
      surface.current.style.height = `${group.offsetHeight + 36}px`;
    };
    const commit = (id: string) => { setActiveId(id); place(); };
    const sample = () => {
      clearTimeout(timer);
      if (!selection.current) return;
      const now = performance.now();
      const bounds = pane.getBoundingClientRect();
      const positions = groups.map(el => ({ id: el.dataset.lensGroup!, top: el.getBoundingClientRect().top - bounds.top + pane.scrollTop }));
      const previous = selection.current;
      selection.current = advanceReadingLens(previous, positions, pane.scrollTop + pane.clientHeight * .32, now);
      if (previous.id !== selection.current.id) commit(selection.current.id);
      if (now < selection.current.lockedUntil) timer = setTimeout(sample, selection.current.lockedUntil - now);
      else if (selection.current.candidate) timer = setTimeout(sample, Math.max(1, 140 - (now - selection.current.since)));
    };
    jump.current = id => {
      clearTimeout(timer);
      selection.current = lockReadingLens(id, performance.now());
      commit(id);
    };
    // Restored timelines start at their latest occurrence; new occurrences lock directly.
    jump.current(ids[ids.length - 1]);
    pane.addEventListener("scroll", sample, { passive: true });
    const observer = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(place);
    observer?.observe(root);
    groups.forEach(group => observer?.observe(group));
    return () => { clearTimeout(timer); observer?.disconnect(); pane.removeEventListener("scroll", sample); jump.current = () => {}; };
  }, [scope, signature, enabled]);

  return { document, surface, activeId, focus: (id: string) => jump.current(id) };
}
