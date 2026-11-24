import type { AnnotationLayer, MarkdownTextRange, ReaderChunk, ReadingDocument, ReadingTranslationSegment, SourceNote, SourceTextSelectionInput } from "@focus/reader-contracts";
import { domAnnotatableText, domOffset, hastAnnotatableText, hastTextNodes, type HastNode } from "./annotatable-text";
import { normalizeMathWithLines } from "./math-markdown";
import { markdownTree } from "./markdown-pipeline";
import type { RenderMark } from "./rehype-annotations";

type Positioned = HastNode & { position?: { start: { offset?: number }; end: { offset?: number } } };
type TextPosition = { renderStart: number; renderEnd: number; start: number; end: number };
const documentPositions = new WeakMap<ReadingDocument, ReturnType<typeof positionedText>>();
type TranslatedPassage = Pick<ReadingTranslationSegment, "id" | "text">;
const segmentPositions = new WeakMap<TranslatedPassage, ReturnType<typeof positionedText>>();

/** Project positioned Markdown text onto the same UTF-16 stream as DOM selections. */
function positionedText(markdown: string) {
  const normalized = normalizeMathWithLines(markdown);
  const canonical = Array.from(markdown);
  const codePointAt: number[] = [];
  for (let index = 0, offset = 0; index < canonical.length; index++) {
    for (let width = 0; width < canonical[index].length; width++) codePointAt[offset++] = index;
  }
  const positions: TextPosition[] = [];
  const entities = new Map<string, string>();
  function decode(token: string) {
    if (token === "\r\n" || token === "\r") return "\n";
    if (token.length === 1) return token;
    if (token[0] === "\\") return token.slice(1);
    let result = entities.get(token);
    if (result === undefined) {
      // Give the Markdown parser inline context to decode a character reference.
      result = hastAnnotatableText(markdownTree(`a${token}z`)).slice(1, -1);
      entities.set(token, result);
    }
    return result;
  }
  const nodes = hastTextNodes(markdownTree(markdown));
  for (const { node, parent, start } of nodes) {
    const value = node.value ?? "";
    const position = (node as Positioned).position ?? (parent.tagName === "code" ? (parent as Positioned).position : undefined);
    const from = position?.start.offset, to = position?.end.offset;
    if (from === undefined || to === undefined || !value) continue;
    let raw = normalized.markdown.slice(from, to), base = from;
    const inlineCode = parent.tagName === "code" && !(node as Positioned).position && /^`+/.exec(raw);
    if (inlineCode) {
      base += inlineCode[0].length;
      raw = raw.slice(inlineCode[0].length, -inlineCode[0].length);
      if (raw.startsWith(" ") && raw.endsWith(" ") && raw.trim()) { raw = raw.slice(1, -1); base++; }
    }
    const mapped: TextPosition[] = [];
    let cursor = 0, atLineStart = false;
    for (const token of raw.matchAll(/\\[!-/:-@[-`{-~]|&(?:#(?:\d{1,7}|x[\da-f]{1,6})|[\da-z]{1,31});|\r\n?|[\s\S]/giu)) {
      const original = token[0];
      const decoded = inlineCode ? original.replace(/\r\n?|\n/, " ") : decode(original);
      if (atLineStart && /^[\t >]$/.test(original) && !value.startsWith(decoded, cursor)) continue;
      if (!value.startsWith(decoded, cursor)) { cursor = -1; break; }
      const first = normalized.sourceOffsetAt(base + token.index);
      const last = normalized.sourceOffsetAt(base + token.index + original.length - 1);
      if (first !== null && last !== null) mapped.push({ renderStart: start + cursor, renderEnd: start + cursor + decoded.length,
        start: codePointAt[first], end: codePointAt[last] + 1 });
      cursor += decoded.length;
      atLineStart = decoded === "\n";
    }
    if (cursor === value.length) for (const position of mapped) positions.push(position);
  }
  return { text: nodes.map(({ node }) => node.value ?? "").join(""), positions, canonical };
}

function positionedDocument(document: ReadingDocument) {
  let positioned = documentPositions.get(document);
  if (!positioned) {
    positioned = positionedText(document.markdown);
    documentPositions.set(document, positioned);
  }
  return positioned;
}

function positionedSegment(segment: TranslatedPassage) {
  let positioned = segmentPositions.get(segment);
  if (!positioned) {
    positioned = positionedText(segment.text);
    segmentPositions.set(segment, positioned);
  }
  return positioned;
}

function selectedRanges(root: HTMLElement, range: Range, { text, positions, canonical }: ReturnType<typeof positionedText>) {
  const start = root.contains(range.startContainer) ? domOffset(root, range.startContainer, range.startOffset, "start") : 0;
  const end = root.contains(range.endContainer) ? domOffset(root, range.endContainer, range.endOffset, "end") : text.length;
  if (start === null || end === null || start >= end || domAnnotatableText(root).text !== text) return [];
  const ranges: MarkdownTextRange[] = [];
  for (const position of positions) {
    if (position.renderStart < start || position.renderEnd > end) continue;
    const last = ranges.at(-1);
    if (last?.end === position.start) last.end = position.end;
    else ranges.push({ start: position.start, end: position.end });
  }
  return ranges.filter(span => canonical.slice(span.start, span.end).join("").trim());
}

export function captureSourceText(root: HTMLElement, range: Range, document: ReadingDocument): SourceTextSelectionInput | undefined {
  const plan = document.readingPlan;
  if (!plan || !range.intersectsNode(root)) return;
  const ranges = selectedRanges(root, range, positionedDocument(document));
  if (ranges.some(span => plan.chunks.some(chunk => span.start < chunk.sourceOffsets[1] && span.end > chunk.sourceOffsets[0]))) {
    return { layer: "source", planId: plan.planId, bundleVersion: document.bundleVersion, ranges };
  }
}

export function captureTranslatedText(pane: HTMLElement, range: Range, document: ReadingDocument): SourceTextSelectionInput | undefined {
  const translation = document.translation, plan = document.readingPlan;
  if (!plan || !translation?.segments || translation.readingVersion === undefined) return;
  const segments = new Map(translation.segments.map(segment => [segment.id, segment]));
  const ranges = [...pane.querySelectorAll<HTMLElement>("[data-translation-chunk] > .focus-markdown")].flatMap(root => {
    const segment = segments.get(root.parentElement?.dataset.translationChunk ?? "");
    if (!segment || !range.intersectsNode(root)) return [];
    return selectedRanges(root, range, positionedSegment(segment)).map(span => ({ ...span, segmentId: segment.id }));
  });
  if (ranges.length) return { layer: "translation", planId: plan.planId,
    bundleVersion: document.bundleVersion, readingVersion: translation.readingVersion, ranges };
}

export function noteBelongsToChunk(note: SourceNote, chunk: ReaderChunk) {
  return note.sourceId === chunk.sourceId && note.bundle === chunk.bundleVersion &&
    note.selection?.planId === chunk.planId && note.selection.chunkIds.includes(chunk.chunkId);
}

function noteMarks(positions: readonly TextPosition[], noteId: string, ranges: readonly MarkdownTextRange[],
                   offset: number, interactive: boolean): RenderMark[] {
  const marks: RenderMark[] = [];
  let range = 0;
  for (const pos of positions) {
    while (ranges[range] && ranges[range].end <= pos.start + offset) range++;
    const span = ranges[range];
    if (!span) break;
    if (span.start > pos.start + offset || span.end < pos.end + offset) continue;
    const previous = marks.at(-1);
    if (previous?.end === pos.renderStart) previous.end = pos.renderEnd;
    else marks.push({ key: `shared:${noteId}:${marks.length}`, start: pos.renderStart, end: pos.renderEnd,
      sharedNoteId: noteId, interactive, ariaLabel: "查看小段笔记" });
  }
  return marks;
}

export function sharedDocumentNotes(document: ReadingDocument, notes: readonly SourceNote[]) {
  return notes.filter(note => !note.deleted && !note.sourceUpdated && note.sourceId === document.sourceId &&
    note.bundle === document.bundleVersion && note.selection && note.selection.planId === document.readingPlan?.planId &&
    (note.selection.layer === "source" || note.selection.readingVersion === document.translation?.readingVersion));
}

export function documentNoteMarks(document: ReadingDocument, notes: readonly SourceNote[]) {
  return notes.flatMap(({ noteId, selection }) => selection?.layer === "source"
    ? noteMarks(positionedDocument(document).positions, noteId, selection.ranges, 0, true) : []);
}

export function segmentNoteMarks(segment: TranslatedPassage, notes: readonly SourceNote[]) {
  return notes.flatMap(({ noteId, selection }) => {
    const ranges = selection?.layer === "translation" ? selection.ranges.filter(span => span.segmentId === segment.id) : [];
    return ranges.length ? noteMarks(positionedSegment(segment).positions, noteId, ranges, 0, true) : [];
  });
}

export function chunkNoteMarks(chunk: ReaderChunk, layer: AnnotationLayer, notes: readonly SourceNote[]) {
  const offset = layer === "source" ? chunk.sourceOffset : 0;
  const markdown = layer === "source" ? chunk.sourceMarkdown : chunk.translation;
  if (offset === undefined || markdown === null) return [];
  const selected = notes.filter(note => !note.deleted && !note.sourceUpdated && noteBelongsToChunk(note, chunk) &&
    note.selection?.layer === layer);
  if (!selected.length) return [];
  const { positions } = positionedText(markdown);
  return selected.flatMap(({ noteId, selection }) => {
    const ranges = selection?.layer === "source" ? selection.ranges :
      selection?.chunkRanges.find(entry => entry.chunkId === chunk.chunkId)?.ranges;
    return ranges ? noteMarks(positions, noteId, ranges, offset, false) : [];
  });
}

export interface ChunkNoteLink {
  index: number;
  noteId: string;
  count: number;
  sourceOffsets: readonly [number, number];
}

export function chunkNoteLinks(document: ReadingDocument, notes: readonly SourceNote[]): ChunkNoteLink[] {
  if (!notes.length) return [];
  const segments = new Map(document.translation?.segments?.map(segment => [segment.id, segment.sourceOffsets]));
  return (document.readingPlan?.chunks ?? []).flatMap((chunk, index) => {
    const matches = notes.filter(note => note.selection?.chunkIds.includes(chunk.chunkId));
    if (!matches.length) return [];
    const [first, last] = chunk.sourceOffsets;
    const selection = matches[0].selection!;
    const ranges = selection.layer === "source" ? selection.ranges.map(({ start, end }) => [start, end] as const) :
      selection.ranges.flatMap(span => { const offsets = segments.get(span.segmentId); return offsets ? [offsets] : []; });
    const start = ranges.find(([start, end]) => start < last && first < end)?.[0];
    return [{ index: index + 1, noteId: matches[0].noteId, count: matches.length,
      sourceOffsets: start === undefined ? chunk.sourceOffsets : [Math.max(first, start), last] }];
  });
}
