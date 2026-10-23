import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { flyFromRect, flyIn, motionAllowed, snapshotCards, sweepOut, useAnnotationMotion } from "./useAnnotationMotion";

function rect(x: number, y: number, width = 200, height = 80) { return new DOMRect(x, y, width, height); }
function geometry(el: HTMLElement, box: DOMRect) { vi.spyOn(el, "getBoundingClientRect").mockReturnValue(box); return el; }
let animations: { target: Element; frames: Keyframe[]; options: KeyframeAnimationOptions; animation: Animation; end: () => void }[];
beforeEach(() => {
  vi.useFakeTimers(); animations = [];
  vi.stubGlobal("matchMedia", vi.fn(() => ({ matches: false, addEventListener: vi.fn(), removeEventListener: vi.fn() })));
  vi.stubGlobal("requestAnimationFrame", (callback: FrameRequestCallback) => setTimeout(() => callback(16), 16));
  vi.stubGlobal("cancelAnimationFrame", clearTimeout);
  Object.defineProperty(Element.prototype, "animate", { configurable: true, writable: true, value: vi.fn(function (this: Element, frames: Keyframe[], options: KeyframeAnimationOptions) {
    let end!: () => void;
    const finished = new Promise<Animation>(resolve => { end = () => resolve(animation); });
    const animation = { finished, cancel: vi.fn(), finish: vi.fn(() => end()), playState: "running" } as unknown as Animation;
    animations.push({ target: this, frames: frames as Keyframe[], options: options as KeyframeAnimationOptions, animation, end });
    return animation;
  }) });
});
afterEach(() => { cleanup(); document.body.replaceChildren(); delete document.documentElement.dataset.reducedMotion; vi.restoreAllMocks(); vi.unstubAllGlobals(); vi.useRealTimers(); });

it("creates no JS animation for either reduced-motion setting and completes a sweep synchronously", () => {
  const card = document.createElement("div"), done = vi.fn();
  document.documentElement.dataset.reducedMotion = "true";
  expect(motionAllowed()).toBe(false);
  sweepOut([card], ["--anno-hl-w"], done);
  expect(done).toHaveBeenCalledOnce(); expect(flyIn(card, { x: 10, y: 10 }, { delay: 0 })).toBeNull();
  delete document.documentElement.dataset.reducedMotion;
  vi.mocked(matchMedia).mockReturnValue({ matches: true } as MediaQueryList);
  expect(flyFromRect(card, rect(0, 0))).toBeNull(); expect(animations).toEqual([]);
});

it("flies a card from its bulb into its existing packed top without changing layout coordinates", () => {
  const card = geometry(document.createElement("div"), rect(400, 300)); card.dataset.top = "120";
  flyIn(card, { x: 100, y: 200 }, { delay: 35 });
  expect(animations[0].frames).toEqual([{ opacity: 0, transform: "translate(-300px, 20px) scale(.12)" }, { opacity: 1, transform: "translate(0, 120px) scale(1)" }]);
  expect(animations[0].options).toMatchObject({ delay: 35, duration: 380, fill: "backwards" });
});

it("snapshots only visible cards and makes every flying clone inert and unfocusable", () => {
  const root = document.createElement("main"); document.body.append(root);
  root.innerHTML = '<div class="reader-anno-card" data-anno-card="n:one" tabindex="0"><button id="private-control">edit</button><a href="#x">link</a></div><div data-anno-card="n:outside"></div>';
  geometry(root.children[0] as HTMLElement, rect(400, 100)); geometry(root.children[1] as HTMLElement, rect(400, -500));
  const ghosts = snapshotCards(root); expect(ghosts).toHaveLength(1);
  expect(ghosts[0].element.getAttribute("aria-hidden")).toBe("true"); expect(ghosts[0].element.hasAttribute("inert")).toBe(true);
  expect(ghosts[0].element.querySelector("#private-control")).toBeNull();
  expect([...ghosts[0].element.querySelectorAll("button,a")].every(el => el.getAttribute("tabindex") === "-1")).toBe(true);
});

function surface() {
  const root = document.createElement("div"); root.className = "focus-reader";
  root.innerHTML = '<div class="focus-stream"><div class="reading-group-source"></div><span class="reader-anno" data-anno-key="h:one"></span><button data-anno-bulb="n:one"></button><div class="reader-anno-card" data-anno-card="n:one"></div></div>';
  document.body.append(root); const stream = root.firstElementChild as HTMLElement;
  geometry(stream.querySelector(".reading-group-source")!, rect(100, 80));
  geometry(stream.querySelector("[data-anno-bulb]")!, rect(200, 200, 17, 17));
  geometry(stream.querySelector("[data-anno-card]")!, rect(500, 200));
  geometry(stream.querySelector(".reader-anno")!, rect(100, 200));
  return { root, stream: { current: stream } };
}

it("animates each visible card once from its bulb and cancels flights and ghosts when toggled again", async () => {
  const { root, stream } = surface();
  const { result, rerender } = renderHook(({ layout }) => useAnnotationMotion({ stream, scope: "s:0", layout }), { initialProps: { layout: "off" } });
  act(() => result.current.beforeAttachChange(true)); rerender({ layout: "side" });
  await act(async () => { vi.advanceTimersByTime(48); });
  const cardFlights = animations.filter(item => item.target.matches("[data-anno-card]"));
  expect(cardFlights).toHaveLength(1); expect(cardFlights[0].frames[0].transform).toContain("-300px");
  act(() => result.current.beforeAttachChange(false)); rerender({ layout: "off" });
  await act(async () => { vi.advanceTimersByTime(48); });
  expect(cardFlights[0].animation.cancel).toHaveBeenCalled();
  expect(root.querySelectorAll(".reader-anno-ghost-layer [data-anno-card]")).toHaveLength(1);
  act(() => result.current.beforeAttachChange(true));
  expect(root.querySelectorAll(".reader-anno-ghost-layer")).toHaveLength(0);
});

it("sends a delete before animating and keeps only its visual record until sweep completion", async () => {
  const { stream } = surface(); const events: string[] = [];
  const mock = vi.mocked(Element.prototype.animate).getMockImplementation()!;
  vi.mocked(Element.prototype.animate).mockImplementation(function (this: Element, ...args) { events.push("animate"); return mock.apply(this, args); });
  const { result } = renderHook(() => useAnnotationMotion({ stream, scope: "s:0", layout: "off" }));
  const mark = { highlight: { highlightId: "one" } };
  const request = vi.fn(async () => { events.push("request"); });
  act(() => { void result.current.deleteMark(mark, request); });
  expect(events[0]).toBe("request"); expect(result.current.retained).toHaveLength(1);
  await act(async () => { vi.advanceTimersByTime(401); });
  expect(result.current.retained).toEqual([]); expect(request).toHaveBeenCalledOnce();
});

it("flies the saved card from the editor geometry, then clears its saved outline", async () => {
  const { stream } = surface();
  const { rerender } = renderHook(({ savedAnnotation }) => useAnnotationMotion({ stream, scope: "s:0", layout: "side", savedAnnotation }),
    { initialProps: { savedAnnotation: null as { noteId: string; editorRect: DOMRect; token: number } | null } });
  rerender({ savedAnnotation: { noteId: "one", editorRect: rect(150, 120, 300, 180), token: 1 } });
  await act(async () => { vi.advanceTimersByTime(48); });
  expect(animations).toHaveLength(1); expect(animations[0].frames[0]).toEqual({ opacity: .4, transform: "translate(-350px, -80px) scale(1.5)" });
  await act(async () => { animations[0].end(); });
  expect(stream.current.querySelector("[data-anno-card]")?.classList.contains("is-saved")).toBe(true);
  await act(async () => { vi.advanceTimersByTime(261); });
  expect(stream.current.querySelector("[data-anno-card]")?.classList.contains("is-saved")).toBe(false);
});

it("finishes active flights immediately when the root reduced-motion preference changes", async () => {
  const { root, stream } = surface();
  const { result, rerender } = renderHook(({ layout }) => useAnnotationMotion({ stream, scope: "s:0", layout }), { initialProps: { layout: "side" } });
  act(() => result.current.beforeAttachChange(false)); rerender({ layout: "off" });
  await act(async () => { vi.advanceTimersByTime(48); });
  expect(root.querySelector(".reader-anno-ghost-layer")).not.toBeNull();
  await act(async () => { document.documentElement.dataset.reducedMotion = "true"; await Promise.resolve(); });
  expect(root.querySelector(".reader-anno-ghost-layer")).toBeNull();
  expect(animations.every(item => vi.mocked(item.animation.cancel).mock.calls.length > 0)).toBe(true);
  const count = animations.length;
  act(() => result.current.beforeAttachChange(true)); rerender({ layout: "side" });
  await act(async () => { vi.advanceTimersByTime(48); });
  expect(animations).toHaveLength(count);
});
