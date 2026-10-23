import { cleanup, fireEvent, render } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import type { ReaderChunk } from "@focus/reader-contracts";
import demo from "../../../../tests/fixtures/reading-annotations-demo.json";
import { seedMarks } from "./test-support/annotation-demo";
import { groupLocated } from "./annotation-projection";
import { ReadingChunk } from "./ReadingChunk";
import { domAnnotatableText } from "./annotatable-text";

afterEach(cleanup);
const chunks: ReaderChunk[] = demo.chunks.map(chunk => ({ ...chunk, presentationStatus: "source-ready", sourceLines: [chunk.sourceLines[0], chunk.sourceLines[1]] }));
it("renders all six prototype annotations, merging the shared highlight and note interval", () => {
  const { highlights, notes } = seedMarks(demo);
  const groups = chunks.map(chunk => ({ id: chunk.chunkId, chunk }));
  const located = groupLocated(highlights, notes, groups);
  const onMarks = vi.fn();
  const { container } = render(<>{chunks.map(chunk => <ReadingChunk key={chunk.chunkId} chunk={chunk} located={located.get(chunk.chunkId)} onReference={vi.fn()} onMarks={onMarks} />)}</>);
  const keys = new Set([...container.querySelectorAll("[data-anno-key]")].map(el => el.getAttribute("data-anno-key")));
  expect(keys.size).toBe(6);
  expect(container.querySelectorAll(".reader-anno-bulb")).toHaveLength(4);
  const combined = new Set([...container.querySelectorAll(".reader-anno--hl.reader-anno--note")].map(el => el.getAttribute("data-anno-key")));
  expect(combined.size).toBe(1);
  expect(onMarks.mock.calls.flatMap(call => call[1])).toHaveLength(6);
  expect(onMarks.mock.calls.every(call => call[2].length === 0)).toBe(true);
  for (const root of container.querySelectorAll(".focus-markdown")) expect(domAnnotatableText(root).text).not.toContain("查看备注");
});

it("reports current layer and resolved text without duplicating callbacks on equivalent rerenders", () => {
  const chunk = { ...chunks[0], translation: "只有译文" }, onMarks = vi.fn(), onLayerChange = vi.fn(), onReference = vi.fn();
  const props = { chunk, onReference, onMarks, onLayerChange };
  const { getByRole, rerender } = render(<ReadingChunk {...props} />);
  expect(onMarks.mock.calls.at(-1)?.slice(3)).toEqual(["translation", "只有译文"]);
  const calls = onMarks.mock.calls.length;
  rerender(<ReadingChunk {...props} />);
  expect(onMarks.mock.calls).toHaveLength(calls);
  fireEvent.click(getByRole("button", { name: "查看原文" }));
  expect(onMarks.mock.calls.at(-1)?.[3]).toBe("source");
  expect(onLayerChange.mock.calls.at(-1)).toEqual([chunk, "source"]);
});
