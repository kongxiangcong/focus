import { afterEach, describe, expect, it, vi } from "vitest";
import { ReadingScroll, layoutTop, startLine, tailSpace, scrollDuration, easeOutQuart } from "./reading-scroll";

function fixture() {
  const pane = document.createElement('main'), end = document.createElement('div'), spacer = document.createElement('div');
  document.body.append(pane); pane.append(end, spacer);
  Object.defineProperties(pane, { clientHeight: { value: 800, configurable: true }, scrollHeight: { value: 4000 } });
  Object.defineProperty(end, 'offsetTop', { value: 2000 });
  const follow = { current: true }, notify = vi.fn();
  const control = new ReadingScroll(pane, end, spacer, follow, notify);
  return { pane, end, spacer, follow, notify, control };
}
afterEach(() => { document.body.innerHTML = ''; delete document.documentElement.dataset.reducedMotion; vi.restoreAllMocks(); });
describe('reading scroll', () => {
  it('uses offsets instead of transformed client rectangles, even with a shared offset ancestor', () => {
    const { pane } = fixture(); const el = document.createElement('div'); pane.append(el);
    Object.defineProperty(pane, 'offsetTop', { value: 50 }); Object.defineProperty(el, 'offsetTop', { value: 350 });
    el.getBoundingClientRect = () => { throw new Error('entrance transform must not be measured'); };
    expect(layoutTop(pane, el)).toBe(300); expect(startLine(pane)).toBe(80);
  });
  it('reserves enough space for short and long groups and a growing viewport', () => {
    expect(tailSpace(800, 80, 100, 0)).toBe(620);
    expect(tailSpace(800, 80, 1200, 0)).toBe(128);
    expect(tailSpace(800, 80, 1200, 300, 500)).toBe(500);
    expect(scrollDuration(100)).toBe(280); expect(scrollDuration(5000)).toBe(520); expect(easeOutQuart(.5)).toBe(.9375);
  });
  it('lands both group sizes on the same line, jumps 40px below and returns exactly', () => {
    document.documentElement.dataset.reducedMotion = 'true';
    const { pane, control } = fixture(); const el = document.createElement('div'); pane.append(el);
    Object.defineProperty(el, 'offsetTop', { value: 1200 });
    control.land(el); expect(pane.scrollTop).toBe(1120);
    pane.scrollTop = 500; control.jump(el); expect(pane.scrollTop).toBe(1080);
    control.goBack(); expect(pane.scrollTop).toBe(500);
  });
  it('cancels animation immediately and only resumes paused follow on downward return to latest', () => {
    const { pane, control, follow, notify } = fixture();
    const cancel = vi.spyOn(globalThis, 'cancelAnimationFrame');
    control.animateTo(1000); control.userIntent(true); expect(cancel).toHaveBeenCalled(); expect(follow.current).toBe(false);
    expect(notify).toHaveBeenLastCalledWith(true, false);
    pane.scrollTop = 1100; control.onScroll(); expect(follow.current).toBe(false);
    pane.scrollTop = 1160; control.onScroll(); expect(follow.current).toBe(true);
    control.dispose();
  });
  it('uses the streaming answer bottom instead of the document end', () => {
    const { pane, control } = fixture(); const answer = document.createElement('div'); answer.dataset.streaming = 'true'; pane.append(answer);
    Object.defineProperties(answer, { offsetTop: { value: 400 }, offsetHeight: { value: 300 } });
    control.streaming = true; expect(control.latestBottom()).toBe(700);
    control.streaming = false; expect(control.latestBottom()).toBe(2000);
  });
  it('captures the first source block crossing the line and restores after reflow', () => {
    const { pane, control } = fixture(); pane.innerHTML += '<article class="focus-reading"><div class="focus-markdown"><p>source</p></div></article>';
    const p = pane.querySelector('p')!; let top = 300;
    Object.defineProperties(p, { offsetTop: { get: () => top }, offsetHeight: { value: 200 } });
    pane.scrollTop = 250; control.capture(); top = 420; control.restore(); expect(pane.scrollTop).toBe(370);
  });
});


it('dismisses each notice without moving or resuming follow, including streaming updates', () => {
  document.documentElement.dataset.reducedMotion = 'true';
  const { pane, end, control, follow, notify } = fixture();
  const target = document.createElement("div"); pane.append(target);
  Object.defineProperty(target, "offsetTop", { value: 1200 });
  pane.scrollTop = 500; control.jump(target); control.contentChanged();
  const top = pane.scrollTop;
  control.dismissLatest(); expect(notify).toHaveBeenLastCalledWith(false, true);
  control.dismissBack(); expect(notify).toHaveBeenLastCalledWith(false, false);
  control.streaming = true; control.contentChanged(); control.onScroll();
  expect(notify).toHaveBeenLastCalledWith(false, false);
  expect(pane.scrollTop).toBe(top); expect(follow.current).toBe(false);
  control.jump(target); expect(notify).toHaveBeenLastCalledWith(false, true);
  control.userIntent(true); expect(notify).toHaveBeenLastCalledWith(true, true);
  control.dispose();
});
