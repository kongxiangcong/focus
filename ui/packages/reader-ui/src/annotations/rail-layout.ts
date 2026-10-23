import { useLayoutEffect, useRef, type RefObject } from "react";

export function layoutCards(items: readonly { key: string; anchorTop: number; height: number }[], gap: number, offset: number) {
  let bottom = -gap;
  return [...items].sort((a, b) => a.anchorTop - b.anchorTop).map(item => {
    const top = Math.max(item.anchorTop, bottom + gap); bottom = top + item.height;
    return { key: item.key, top, displaced: top > item.anchorTop + offset };
  });
}
export function railHeight(passageHeight: number, cards: readonly { top: number; height: number }[]) {
  return Math.max(passageHeight, ...cards.map(card => card.top + card.height + 4));
}

/** One rail owns its measurements; no scroll writes or global mark searches. */
export function useRailLayout(railRef: RefObject<HTMLElement | null>, passageRef: RefObject<HTMLElement | null>,
  signature: string, stacked: boolean) {
  const placed = useRef<{ rail: HTMLElement; mode: string } | null>(null);
  useLayoutEffect(() => {
    const rail = railRef.current, passage = passageRef.current;
    if (!rail || !passage) return;
    const root = rail.closest<HTMLElement>(".focus-reader");
    let frame = 0, settled = 0, disposed = false;
    const suppressModeChange = () => {
      const mode = `${stacked}:${root?.dataset.notesLayout ?? "side"}`;
      if (placed.current?.rail !== rail || placed.current.mode !== mode) {
        rail.classList.add("no-anim"); placed.current = { rail, mode };
      }
    };
    suppressModeChange();
    const measure = () => {
      frame = 0; if (disposed) return;
      suppressModeChange();
      const cards = [...rail.querySelectorAll<HTMLElement>("[data-anno-card]")];
      if (stacked) {
        rail.style.height = "auto";
        for (const card of cards) { card.style.transform = ""; delete card.dataset.top; card.classList.remove("is-displaced"); }
      } else {
        const style = getComputedStyle(rail);
        const gap = parseFloat(style.getPropertyValue("--reader-anno-card-gap")) || 0;
        const offset = parseFloat(style.getPropertyValue("--reader-anno-card-offset")) || 0;
        const rootTop = rail.getBoundingClientRect().top;
        const marks = [...passage.querySelectorAll<HTMLElement>(".reader-anno[data-anno-key]")];
        const items = cards.map(card => {
          const anchor = marks.find(mark => mark.dataset.annoKey === card.dataset.annoCard);
          const rect = anchor?.getClientRects()[0] ?? anchor?.getBoundingClientRect();
          return { key: card.dataset.annoCard!, anchorTop: (rect?.top ?? rootTop) - rootTop - offset, height: card.offsetHeight };
        });
        const packed = layoutCards(items, gap, offset);
        for (const layout of packed) {
          const card = cards.find(item => item.dataset.annoCard === layout.key)!;
          card.style.transform = `translateY(${layout.top}px)`; card.dataset.top = String(layout.top);
          card.classList.toggle("is-displaced", layout.displaced);
        }
        rail.style.height = `${railHeight(passage.getBoundingClientRect().height, packed.map(item => ({ top: item.top, height: items.find(card => card.key === item.key)!.height })))}px`;
      }
      if (!settled) settled = requestAnimationFrame(() => { settled = 0; if (!disposed) rail.classList.remove("no-anim"); });
    };
    const schedule = () => { if (!disposed && !frame) frame = requestAnimationFrame(measure); };
    const observer = typeof ResizeObserver === "undefined" ? undefined : new ResizeObserver(schedule);
    const modes = new MutationObserver(schedule);
    if (root) modes.observe(root, { attributes: true, attributeFilter: ["data-notes-layout"] });
    observer?.observe(passage); observer?.observe(rail);
    const stream = passage.closest(".focus-stream"); if (stream) observer?.observe(stream);
    for (const card of rail.querySelectorAll("[data-anno-card]")) observer?.observe(card);
    document.fonts?.ready.then(schedule); window.addEventListener("resize", schedule); schedule();
    return () => { disposed = true; cancelAnimationFrame(frame); cancelAnimationFrame(settled); observer?.disconnect(); modes.disconnect(); window.removeEventListener("resize", schedule); };
  }, [railRef, passageRef, signature, stacked]);
}
