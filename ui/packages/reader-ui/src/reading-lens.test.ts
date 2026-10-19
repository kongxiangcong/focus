import { describe, expect, it } from "vitest";
import { advanceReadingLens, lockReadingLens, type LensSelection } from "./reading-lens";

const groups = [{ id: "a", top: 0 }, { id: "b", top: 200 }, { id: "c", top: 400 }, { id: "d", top: 600 }];
const state = (id = "a"): LensSelection => ({ id, candidate: null, since: 0, lockedUntil: 0 });
describe("reading lens visual selection", () => {
  it("requires 24px crossing and a continuous 140ms dwell", () => {
    expect(advanceReadingLens(state(), groups, 223, 0)).toEqual(state());
    const pending = advanceReadingLens(state(), groups, 224, 10);
    expect(advanceReadingLens(pending, groups, 240, 149).id).toBe("a");
    expect(advanceReadingLens(pending, groups, 240, 150).id).toBe("b");
  });
  it("resets dwell when the candidate changes or returns inside the deadband", () => {
    const pending = advanceReadingLens(state(), groups, 230, 0);
    expect(advanceReadingLens(pending, groups, 220, 120).candidate).toBeNull();
    const changed = advanceReadingLens(pending, groups, 440, 120);
    expect(advanceReadingLens(changed, groups, 440, 259).id).toBe("a");
    expect(advanceReadingLens(changed, groups, 440, 260).id).toBe("c");
  });
  it("uses the opposite edge of the same boundary on upward scrolling", () => {
    expect(advanceReadingLens(state("c"), groups, 377, 0).candidate).toBeNull();
    const pending = advanceReadingLens(state("c"), groups, 376, 0);
    expect(advanceReadingLens(pending, groups, 376, 140).id).toBe("b");
  });
  it("locks a new paragraph for 700ms without scanning intervening groups", () => {
    const locked = lockReadingLens("d", 100);
    expect(advanceReadingLens(locked, groups, 30, 799)).toBe(locked);
    const pending = advanceReadingLens(locked, groups, 30, 800);
    expect(pending.id).toBe("d");
    expect(advanceReadingLens(pending, groups, 30, 940).id).toBe("a");
  });
  it("commits only groups where scrolling actually dwells", () => {
    let selection = state();
    const commits: string[] = [];
    for (const [time, line] of [[0, 230], [60, 430], [120, 630], [260, 630], [300, 350], [440, 350]]) {
      const next = advanceReadingLens(selection, groups, line, time);
      if (selection.id !== next.id) commits.push(next.id);
      selection = next;
    }
    expect(commits).toEqual(["d", "b"]);
  });
  it("keeps selection when no groups are available", () => {
    const initial = state();
    expect(advanceReadingLens(initial, [], 500, 1000)).toBe(initial);
  });
});
