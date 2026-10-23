import { expect, it } from "vitest";
import { layoutCards, railHeight } from "./rail-layout";

it("orders cards by sentence position and moves later cards below earlier content", () => {
  expect(layoutCards([{ key: "second", anchorTop: 10, height: 20 }, { key: "first", anchorTop: 5, height: 30 },
    { key: "third", anchorTop: 100, height: 15 }])).toEqual([
    { key: "first", top: 5, displaced: false }, { key: "second", top: 43, displaced: true }, { key: "third", top: 100, displaced: false },
  ]);
});
it("clamps the first card above the rail and reserves space beneath the last card", () => {
  expect(layoutCards([{ key: "first", anchorTop: -6, height: 20 }])).toEqual([{ key: "first", top: 0, displaced: false }]);
  expect(railHeight(120, [{ top: 0, height: 20 }, { top: 100, height: 60 }])).toBe(164);
  expect(railHeight(200, [{ top: 0, height: 20 }])).toBe(200);
  expect(railHeight(80, [])).toBe(80);
});
