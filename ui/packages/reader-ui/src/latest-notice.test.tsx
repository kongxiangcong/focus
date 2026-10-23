import { act, renderHook } from "@testing-library/react";
import { expect, it } from "vitest";
import { useLatestNotice } from "./latest-notice";

it("keeps dismissal through repeated review and only rearms after progress settles", () => {
  const { result, rerender } = renderHook(({scope, progress, requested}) => useLatestNotice(scope, progress, requested),
    {initialProps:{scope:"workspace/source/session/discussion",progress:"plan/chunk2",requested:true}});
  expect(result.current.visible).toBe(true);
  act(() => result.current.dismiss());
  for (let n=0;n<3;n++) {
    rerender({scope:"workspace/source/session/discussion",progress:"plan/chunk2",requested:false});
    rerender({scope:"workspace/source/session/discussion",progress:"plan/chunk2",requested:true});
    expect(result.current.visible).toBe(false);
  }
  rerender({scope:"workspace/source/session/discussion",progress:"plan/chunk3",requested:true});
  expect(result.current.visible).toBe(false);
  rerender({scope:"workspace/source/session/discussion",progress:"plan/chunk3",requested:false});
  expect(result.current.visible).toBe(false);
  rerender({scope:"workspace/source/session/discussion",progress:"plan/chunk3",requested:true});
  expect(result.current.visible).toBe(true);
});
it("isolates scopes and retains dismissal when switching back; remount resets presentation memory", () => {
  const props={scope:"a",progress:"plan/chunk2",requested:true};
  const app=renderHook(p=>useLatestNotice(p.scope,p.progress,p.requested),{initialProps:props});
  act(()=>app.result.current.dismiss());
  for(const scope of ['other-session','other-source','other-workspace','other-discussion']) {
    app.rerender({...props,scope});expect(app.result.current.visible).toBe(true);
    app.rerender(props);expect(app.result.current.visible).toBe(false);
  }
  app.unmount();
  const fresh=renderHook(()=>useLatestNotice(props.scope,props.progress,true));
  expect(fresh.result.current.visible).toBe(true);
});
