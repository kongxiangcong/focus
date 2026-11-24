import type { ReaderChunk, ReadingDocument, SourceNote, SourceTextSelectionInput } from "@focus/reader-contracts";
import { domAnnotatableText, domOffset, hastAnnotatableText, hastTextNodes, type HastNode } from "./annotatable-text";
import { normalizeMathWithLines } from "./math-markdown";
import { markdownTree } from "./markdown-pipeline";
import type { RenderMark } from "./rehype-annotations";

type Positioned = HastNode & { position?: { start: { offset?: number }; end: { offset?: number } } };
type TextPosition = { renderStart: number; renderEnd: number; start: number; end: number };
const documentPositions = new WeakMap<ReadingDocument, ReturnType<typeof positionedText>>();

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

export function captureSourceText(root: HTMLElement, range: Range, document: ReadingDocument): SourceTextSelectionInput | undefined {
  const plan = document.readingPlan;
  if (!plan) return;
  const start = domOffset(root, range.startContainer, range.startOffset, "start");
  const end = domOffset(root, range.endContainer, range.endOffset, "end");
  if (start === null || end === null || start >= end) return;
  const { text, positions, canonical } = positionedDocument(document);
  if (domAnnotatableText(root).text !== text) return;
  const ranges: { start: number; end: number }[] = [];
  for (const position of positions) {
    if (position.renderStart < start || position.renderEnd > end) continue;
    const last = ranges.at(-1);
    if (last?.end === position.start) last.end = position.end;
    else ranges.push({ start: position.start, end: position.end });
  }
  const readable = ranges.filter(span => canonical.slice(span.start, span.end).join("").trim());
  if (readable.some(span => plan.chunks.some(chunk => span.start < chunk.sourceOffsets[1] && span.end > chunk.sourceOffsets[0]))) {
    return { layer: "source", planId: plan.planId, bundleVersion: document.bundleVersion, ranges: readable };
  }
}

export function noteBelongsToChunk(note: SourceNote, chunk: ReaderChunk) {
  return note.sourceId === chunk.sourceId && note.bundle === chunk.bundleVersion &&
    note.selection?.planId === chunk.planId && note.selection.chunkIds.includes(chunk.chunkId);
}

function noteMarks(positions: readonly TextPosition[], notes: readonly SourceNote[], sourceOffset: number, interactive: boolean): RenderMark[] {
  return notes.flatMap(note => {
    const marks: RenderMark[] = [];
    if (!note.selection || note.selection.layer !== "source") return marks;
    const ranges = note.selection.ranges;
    let range = 0;
    for (const pos of positions) {
      while (ranges[range] && ranges[range].end <= pos.start + sourceOffset) range++;
      const span = ranges[range];
      if (!span) break;
      if (span.start > pos.start + sourceOffset || span.end < pos.end + sourceOffset) continue;
      const previous = marks.at(-1);
      if (previous?.end === pos.renderStart) previous.end = pos.renderEnd;
      else marks.push({ key: `shared:${note.noteId}:${marks.length}`, start: pos.renderStart, end: pos.renderEnd,
        sharedNoteId: note.noteId, interactive, ariaLabel: "查看小段笔记" });
    }
    return marks;
  });
}

export function documentNoteMarks(document: ReadingDocument, notes: readonly SourceNote[]) {
  const selected = notes.filter(note => !note.deleted && !note.sourceUpdated && note.sourceId === document.sourceId &&
    note.bundle === document.bundleVersion && note.selection?.planId === document.readingPlan?.planId && !!note.selection);
  return selected.length ? noteMarks(positionedDocument(document).positions, selected, 0, true) : [];
}

export function chunkNoteMarks(chunk: ReaderChunk, notes: readonly SourceNote[]) {
  if (chunk.sourceOffset === undefined) return [];
  const selected = notes.filter(note => !note.deleted && !note.sourceUpdated && noteBelongsToChunk(note, chunk));
  return selected.length ? noteMarks(positionedText(chunk.sourceMarkdown).positions, selected, chunk.sourceOffset, false) : [];
}
