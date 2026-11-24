export type SourceLines = readonly [number, number];
export type SourcePosition = { lines: SourceLines; offset?: number };

const sourceBlock = "[data-source-line]";
const readingLineFraction = .32;

export function sourceLinesAt(block: HTMLElement): SourceLines {
  return [Number(block.dataset.sourceLine), Number(block.dataset.sourceEnd ?? block.dataset.sourceLine)];
}

export function sourcePositionAt(block: HTMLElement): SourcePosition {
  const offset = block.dataset.sourceOffsetStart;
  return { lines: sourceLinesAt(block), offset: offset === undefined ? undefined : Number(offset) };
}

export function blockAtReadingLine(pane: HTMLElement) {
  const viewport = pane.getBoundingClientRect();
  const readingLine = viewport.top + pane.clientHeight * readingLineFraction;
  const blocks = pane.querySelectorAll<HTMLElement>(sourceBlock);
  let start = 0, end = blocks.length;
  while (start < end) {
    const middle = Math.floor((start + end) / 2);
    if (blocks[middle].getBoundingClientRect().bottom <= readingLine) start = middle + 1;
    else end = middle;
  }
  const block = blocks[start];
  if (block && block.getBoundingClientRect().top < viewport.bottom) return block;
}

export function blockAtSourcePosition(pane: HTMLElement, position: SourcePosition) {
  const { lines: [first, last], offset } = position;
  let exactLine: HTMLElement | undefined, intersectingLine: HTMLElement | undefined;
  for (const block of pane.querySelectorAll<HTMLElement>(sourceBlock)) {
    const [start, end] = sourceLinesAt(block);
    if (start > last) break;
    if (end < first) continue;
    const offsetStart = Number(block.dataset.sourceOffsetStart), offsetEnd = Number(block.dataset.sourceOffsetEnd);
    if (offset !== undefined && offsetStart <= offset && offset < offsetEnd) return block;
    if (start <= first && first <= end) exactLine ??= block;
    intersectingLine ??= block;
  }
  return exactLine ?? intersectingLine;
}

export function fractionAtReadingLine(pane: HTMLElement, block: HTMLElement) {
  const bounds = block.getBoundingClientRect();
  const relative = pane.getBoundingClientRect().top + pane.clientHeight * readingLineFraction - bounds.top;
  return Math.max(0, Math.min(.99, relative / Math.max(1, bounds.height)));
}

export function restoreReadingLine(pane: HTMLElement, block: HTMLElement, fraction: number) {
  const bounds = block.getBoundingClientRect();
  const delta = bounds.top + bounds.height * fraction - pane.getBoundingClientRect().top - pane.clientHeight * readingLineFraction;
  if (Math.abs(delta) > 1) pane.scrollTop += delta;
}
