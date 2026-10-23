import { useCallback, useEffect, useLayoutEffect, useRef, useState, type RefObject } from "react";

type SweepProperty = "--anno-hl-w" | "--anno-ul-w";
export interface Ghost { key: string; element: HTMLElement; rect: DOMRect }
export interface DeletionMark { key?: string; highlight?: { highlightId: string }; note?: { noteId: string } }
interface SavedAnnotation { noteId: string; editorRect: DOMRect; token: number }
const easing = { out: "cubic-bezier(.22,.8,.24,1)", inout: "cubic-bezier(.45,0,.2,1)", in: "cubic-bezier(.4,0,1,1)" };

export function motionAllowed() {
  return document.documentElement.dataset.reducedMotion !== "true" && !window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
}
function visible(element: Element) {
  const box = element.getBoundingClientRect();
  return box.bottom >= -40 && box.top <= innerHeight + 40 && box.right >= -40 && box.left <= innerWidth + 40;
}
function token(element: Element, name: string, fallback: string) { return getComputedStyle(element).getPropertyValue(name).trim() || fallback; }
function animate(element: HTMLElement, frames: Keyframe[], duration: number, curve: keyof typeof easing, extra: KeyframeAnimationOptions = {}) {
  if (!motionAllowed() || !element.animate) return null;
  element.dataset.annoMotion = "";
  const animation = element.animate(frames, { duration, easing: token(element, `--reader-ease-${curve}`, easing[curve]), ...extra });
  return animation;
}

/** The callback releases only the visual record; writes and focus never wait here. */
export function sweepOut(elements: Element[], properties: SweepProperty[], done: () => void): () => void {
  if (!motionAllowed() || !elements.length) { done(); return () => {}; }
  let completed = false;
  const from = Object.fromEntries(properties.map(property => [property, "100%"]));
  const to = Object.fromEntries(properties.map(property => [property, "0%"]));
  const animations = elements.filter(visible).map(element => animate(element as HTMLElement, [from, to], 240, "inout", { fill: "forwards" })).filter((value): value is Animation => !!value);
  const finish = () => {
    if (completed) return; completed = true; clearTimeout(timer);
    for (const animation of animations) animation.cancel();
    done();
  };
  const timer = setTimeout(finish, 400);
  if (!animations.length) finish();
  else void Promise.all(animations.map(animation => animation.finished.catch(() => undefined))).then(finish);
  return finish;
}

export function flyIn(card: HTMLElement, from: { x: number; y: number }, { delay }: { delay: number }) {
  const box = card.getBoundingClientRect(), top = Number(card.dataset.top ?? 0);
  return animate(card, [{ opacity: 0, transform: `translate(${from.x - box.left}px, ${top + from.y - box.top}px) scale(.12)` },
    { opacity: 1, transform: `translate(0, ${top}px) scale(1)` }], 380, "out", { delay, fill: "backwards" });
}
export function flyFromRect(card: HTMLElement, rect: DOMRect) {
  const box = card.getBoundingClientRect(), top = Number(card.dataset.top ?? 0), scale = box.width ? rect.width / box.width : 1;
  return animate(card, [{ opacity: .4, transform: `translate(${rect.left - box.left}px, ${top + rect.top - box.top}px) scale(${scale})` },
    { opacity: 1, transform: `translate(0, ${top}px) scale(1)` }], 380, "out", { fill: "backwards" });
}
export function snapshotCards(root: HTMLElement): Ghost[] {
  if (!motionAllowed()) return [];
  return [...root.querySelectorAll<HTMLElement>("[data-anno-card]")].filter(visible).map(card => {
    const element = card.cloneNode(true) as HTMLElement, rect = card.getBoundingClientRect();
    element.setAttribute("aria-hidden", "true"); element.setAttribute("inert", ""); element.tabIndex = -1;
    for (const child of [element, ...element.querySelectorAll<HTMLElement>("*")]) {
      child.removeAttribute("id"); child.removeAttribute("autofocus");
      if (child.matches("button,input,textarea,select,a[href],[tabindex],[contenteditable],summary,audio[controls],video[controls]")) child.tabIndex = -1;
      if (child.hasAttribute("contenteditable")) child.contentEditable = "false";
    }
    Object.assign(element.style, { position: "fixed", left: `${rect.left}px`, top: `${rect.top}px`, width: `${rect.width}px`, height: `${rect.height}px`, right: "auto", transform: "none", transition: "none", margin: "0" });
    return { key: card.dataset.annoCard!, element, rect };
  });
}
export function flyGhostsToBulbs(ghosts: Ghost[], layer: HTMLElement, target: (key: string) => { x: number; y: number } | null) {
  const animations: Animation[] = [];
  ghosts.forEach((ghost, index) => {
    const to = target(ghost.key);
    if (!motionAllowed() || !to) { ghost.element.remove(); return; }
    layer.append(ghost.element);
    const animation = animate(ghost.element, [{ opacity: 1, transform: "translate(0, 0) scale(1)" },
      { opacity: 0, transform: `translate(${to.x - ghost.rect.left}px, ${to.y - ghost.rect.top}px) scale(.1)` }], 380, "inout", { delay: index * 30, fill: "forwards" });
    if (animation) { animations.push(animation); void animation.finished.catch(() => undefined).then(() => ghost.element.remove()); }
    else ghost.element.remove();
  });
  return animations;
}

/** One owner for every flight so retoggling, source reset and reduced motion can finish cleanly. */
export function useAnnotationMotion<T extends DeletionMark>({ stream, scope, layout, savedAnnotation }: {
  stream: RefObject<HTMLElement | null>; scope: string; layout: string; savedAnnotation?: SavedAnnotation | null;
}) {
  const [retained, setRetained] = useState<T[]>([]);
  const running = useRef(new Set<Animation>()), cleanups = useRef(new Set<() => void>()), frames = useRef(new Set<number>());
  const pending = useRef<{ next: boolean; positions: Map<HTMLElement, number>; ghosts: Ghost[] } | null>(null);
  const version = useRef(0), lastSave = useRef(0), previousLayout = useRef(layout);
  const deleting = useRef(new Map<string, Promise<void>>());
  const keep = useCallback((animation: Animation | null, after?: () => void) => {
    if (!animation) { after?.(); return; }
    running.current.add(animation);
    void animation.finished.catch(() => undefined).then(() => {
      if (!running.current.delete(animation)) return;
      animation.cancel(); after?.();
    });
  }, []);
  const clear = useCallback(() => {
    version.current++;
    for (const animation of running.current) animation.cancel(); running.current.clear();
    for (const frame of frames.current) cancelAnimationFrame(frame); frames.current.clear();
    const callbacks = [...cleanups.current]; cleanups.current.clear(); callbacks.forEach(callback => callback());
    stream.current?.closest(".focus-reader")?.querySelectorAll(".reader-anno-ghost-layer").forEach(layer => layer.remove());
    stream.current?.querySelectorAll<HTMLElement>("[data-anno-bulb]").forEach(bulb => bulb.style.removeProperty("--bulb-delay"));
    pending.current = null; deleting.current.clear();
  }, [stream]);
  const later = useCallback((callback: () => void) => {
    const frame = requestAnimationFrame(() => { frames.current.delete(frame); callback(); }); frames.current.add(frame);
  }, []);
  const beforeAttachChange = useCallback((next: boolean) => {
    clear();
    const root = stream.current;
    if (!root || !motionAllowed()) return;
    pending.current = { next, positions: new Map([...root.querySelectorAll<HTMLElement>(".reading-group-source")].filter(visible).map(element => [element, element.getBoundingClientRect().left])), ghosts: next ? [] : snapshotCards(root) };
  }, [clear, stream]);

  useLayoutEffect(() => {
    const changed = previousLayout.current !== layout; previousLayout.current = layout;
    if (!changed || !pending.current) return;
    const transition = pending.current; pending.current = null; const ownVersion = version.current;
    // Rails perform their first packing in rAF. Two frames leave that measurement authoritative.
    later(() => later(() => {
      if (ownVersion !== version.current || !motionAllowed() || !stream.current) return;
      const root = stream.current;
      for (const [element, left] of transition.positions) {
        if (!element.isConnected || !visible(element)) continue;
        const dx = left - element.getBoundingClientRect().left;
        if (dx) keep(animate(element, [{ transform: `translateX(${dx}px)` }, { transform: "none" }], 380, "out"));
      }
      const bulbs = [...root.querySelectorAll<HTMLElement>("[data-anno-bulb]")];
      if (transition.next) {
        const cards = [...root.querySelectorAll<HTMLElement>("[data-anno-card]")].filter(visible);
        cards.forEach((card, index) => {
          if (card.closest("[data-anno-rail=stacked]")) return;
          const bulb = bulbs.find(element => element.dataset.annoBulb === card.dataset.annoCard);
          if (!bulb) return;
          const box = bulb.getBoundingClientRect(), passage = card.closest(".reading-group-passage")?.querySelector<HTMLElement>(".reading-group-source");
          const dx = passage ? (transition.positions.get(passage) ?? passage.getBoundingClientRect().left) - passage.getBoundingClientRect().left : 0;
          keep(flyIn(card, { x: box.left + dx, y: box.top }, { delay: index * 35 }));
        });
        for (const notes of root.querySelectorAll<HTMLElement>(".reader-anno-rail__foot .reader-chunk-notes")) if (visible(notes)) {
          notes.classList.add("is-entering");
          const remove = () => notes.classList.remove("is-entering"); const timer = setTimeout(() => { remove(); cleanups.current.delete(cancel); }, 500);
          const cancel = () => { clearTimeout(timer); remove(); }; cleanups.current.add(cancel);
        }
      } else {
        const layer = document.createElement("div"); layer.className = "reader-anno-ghost-layer"; layer.setAttribute("aria-hidden", "true"); layer.setAttribute("inert", "");
        root.closest(".focus-reader")?.append(layer);
        for (const animation of flyGhostsToBulbs(transition.ghosts, layer, key => {
          const bulb = bulbs.find(element => element.dataset.annoBulb === key); if (!bulb || !visible(bulb)) return null;
          const box = bulb.getBoundingClientRect(); return { x: box.left, y: box.top };
        })) keep(animation);
        const removeLayer = () => layer.remove();
        const timer = setTimeout(() => { removeLayer(); cleanups.current.delete(cancel); }, 900);
        const cancel = () => { clearTimeout(timer); removeLayer(); }; cleanups.current.add(cancel);
        bulbs.filter(visible).forEach((bulb, index) => bulb.style.setProperty("--bulb-delay", `${260 + Math.min(index, 8) * 30}ms`));
        const reset = () => bulbs.forEach(bulb => bulb.style.removeProperty("--bulb-delay"));
        const delayTimer = setTimeout(() => { reset(); cleanups.current.delete(cancelDelay); }, 900);
        const cancelDelay = () => { clearTimeout(delayTimer); reset(); }; cleanups.current.add(cancelDelay);
      }
    }));
  }, [layout, stream, later, keep]);

  useLayoutEffect(() => {
    if (!savedAnnotation || savedAnnotation.token === lastSave.current) return;
    lastSave.current = savedAnnotation.token;
    if (layout === "off" || !motionAllowed()) return;
    const ownVersion = version.current;
    later(() => later(() => {
      if (ownVersion !== version.current || !motionAllowed()) return;
      const card = [...stream.current?.querySelectorAll<HTMLElement>("[data-anno-card]") ?? []].find(element => element.dataset.annoCard === `n:${savedAnnotation.noteId}`);
      if (!card || !visible(card)) return;
      const saved = () => {
        if (!card.isConnected || ownVersion !== version.current || !motionAllowed()) return;
        card.classList.add("is-saved");
        const timer = setTimeout(() => { card.classList.remove("is-saved"); cleanups.current.delete(cancel); }, 260);
        const cancel = () => { clearTimeout(timer); card.classList.remove("is-saved"); }; cleanups.current.add(cancel);
      };
      if (card.closest("[data-anno-rail=stacked]")) saved(); else keep(flyFromRect(card, savedAnnotation.editorRect), saved);
    }));
  }, [savedAnnotation, layout, stream, later, keep]);

  const deleteMark = useCallback((mark: T, request: () => Promise<void>) => {
    const key = mark.key ?? (mark.note ? `n:${mark.note.noteId}` : `h:${mark.highlight?.highlightId}`);
    const alreadyDeleting = deleting.current.get(key); if (alreadyDeleting) return alreadyDeleting;
    // Start the durable request first; only a captured display record survives the sweep.
    const result = request();
    if (!motionAllowed() || !stream.current) return result;
    const elements = [...stream.current.querySelectorAll<HTMLElement>(".reader-anno[data-anno-key]")].filter(element => element.dataset.annoKey === key && visible(element));
    if (!elements.length) return result;
    deleting.current.set(key, result);
    setRetained(items => [...items, mark]);
    const properties: SweepProperty[] = [...(mark.highlight ? ["--anno-hl-w" as const] : []), ...(mark.note ? ["--anno-ul-w" as const] : [])];
    const exits: Animation[] = [];
    let finish: (() => void) | undefined;
    finish = sweepOut(elements, properties, () => {
      setRetained(items => items.filter(item => item !== mark));
      for (const animation of exits) { running.current.delete(animation); animation.cancel(); }
      deleting.current.delete(key); if (finish) cleanups.current.delete(finish);
    });
    cleanups.current.add(finish);
    if (mark.note) for (const element of stream.current.querySelectorAll<HTMLElement>("[data-anno-bulb],[data-anno-card]")) {
      if ((element.dataset.annoBulb ?? element.dataset.annoCard) !== key || !visible(element)) continue;
      const top = Number(element.dataset.top ?? 0), card = element.hasAttribute("data-anno-card");
      const animation = animate(element, [{ opacity: 1, transform: card ? `translate(0, ${top}px) scale(1)` : "scale(1)" },
        { opacity: 0, transform: card ? `translate(10px, ${top}px) scale(.97)` : "scale(.3)" }], 170, "in", { fill: "forwards" });
      if (animation) { exits.push(animation); running.current.add(animation); void animation.finished.catch(() => undefined); }
    }
    return result;
  }, [stream, keep]);

  useEffect(() => {
    const reduce = () => { if (!motionAllowed()) { for (const animation of running.current) { try { animation.finish(); } catch { /* Already idle. */ } } clear(); setRetained([]); } };
    const media = window.matchMedia?.("(prefers-reduced-motion: reduce)"); media?.addEventListener?.("change", reduce);
    const observer = new MutationObserver(reduce); observer.observe(document.documentElement, { attributes: true, attributeFilter: ["data-reduced-motion"] });
    return () => { media?.removeEventListener?.("change", reduce); observer.disconnect(); };
  }, [clear]);
  useEffect(() => { clear(); setRetained([]); return clear; }, [scope, clear]);
  return { retained, deleteMark, beforeAttachChange };
}
