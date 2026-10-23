import type { AnnotationLayer, ReaderChunk, ReadingHighlight, SentenceLocator, SentenceQuote, SourceNote } from "@focus/reader-contracts";

export type Located = { kind: "highlight"; item: ReadingHighlight } | { kind: "note"; item: SourceNote & { sentence: SentenceLocator } };
export interface ResolvedMark { key: string; start: number; end: number; highlight?: ReadingHighlight; note?: SourceNote & { sentence: SentenceLocator } }
export interface PendingAnnotation { start: number; end: number; layer: AnnotationLayer; requestId?: string }

export function quoteAt(text: string, start: number, end: number): SentenceQuote {
  return { exact: text.slice(start, end), prefix: text.slice(Math.max(0, start - 32), start).replace(/^[\uDC00-\uDFFF]/, ""), suffix: text.slice(end, end + 32).replace(/[\uD800-\uDBFF]$/, "") };
}

export function resolveRange(text: string, loc: Pick<SentenceLocator, "range" | "quote">): { start: number; end: number } | null {
  const { range, quote } = loc;
  if (!quote.exact) return null;
  if (text.slice(range.start, range.end) === quote.exact) return { ...range };
  let winner = -1, best = -1;
  for (let start = text.indexOf(quote.exact); start >= 0; start = text.indexOf(quote.exact, start + 1)) {
    let prefix = 0, suffix = 0;
    while (prefix < Math.min(start, quote.prefix.length) && text[start - 1 - prefix] === quote.prefix[quote.prefix.length - 1 - prefix]) prefix++;
    const end = start + quote.exact.length;
    while (suffix < quote.suffix.length && text[end + suffix] === quote.suffix[suffix]) suffix++;
    const score = prefix + suffix;
    if (score > best || (score === best && Math.abs(start - range.start) < Math.abs(winner - range.start))) { winner = start; best = score; }
  }
  return winner < 0 ? null : { start: winner, end: winner + quote.exact.length };
}

export function groupLocated(highlights: readonly ReadingHighlight[], notes: readonly SourceNote[], groups: readonly { id: string; chunk: ReaderChunk | null }[]): Map<string, Located[]> {
  const records: Located[] = [...highlights.map(item => ({ kind: "highlight" as const, item })), ...notes.flatMap(item => item.sentence ? [{ kind: "note" as const, item: { ...item, sentence: item.sentence } }] : [])];
  const projected = new Map<string, Located[]>();
  for (const record of records) {
    const { item } = record;
    if (item.deleted || item.sourceUpdated) continue;
    const loc = record.kind === "highlight" ? record.item : record.item.sentence;
    const anchor = record.kind === "highlight" ? record.item : record.item.anchor;
    if (!anchor) continue;
    const eligible = groups.filter(group => group.chunk?.sourceId === item.sourceId && group.chunk.bundleVersion === anchor.bundle);
    const exact = eligible.filter(group => group.chunk!.planId === loc.planId && group.chunk!.chunkId === loc.chunkId);
    let owner = exact.at(-1);
    if (!owner) {
      let overlap = 0;
      for (const group of eligible) {
        const chunk = group.chunk!;
        const lines = Math.min(chunk.sourceLines[1], anchor.sourceLines[1]) - Math.max(chunk.sourceLines[0], anchor.sourceLines[0]) + 1;
        if (lines > 0 && (lines > overlap || (lines === overlap && chunk.index <= owner!.chunk!.index))) { owner = group; overlap = lines; }
      }
    }
    if (owner) projected.set(owner.id, [...(projected.get(owner.id) ?? []), record]);
  }
  return projected;
}

export function buildMarks(text: string, located: readonly Located[], layer: AnnotationLayer): { marks: ResolvedMark[]; lost: Located[] } {
  const lost: Located[] = [], marks: ResolvedMark[] = [];
  const candidates = located.flatMap(record => {
    const loc = record.kind === "highlight" ? record.item : record.item.sentence;
    if (loc.layer !== layer || record.item.deleted || record.item.sourceUpdated) return [];
    const range = resolveRange(text, loc);
    if (!range) { lost.push(record); return []; }
    return [{ record, ...range }];
  }).sort((a, b) => a.start - b.start || (a.record.kind === b.record.kind ? 0 : a.record.kind === "note" ? -1 : 1));
  for (const { record, start, end } of candidates) {
    const same = marks.find(mark => mark.start === start && mark.end === end);
    if (same) {
      if (record.kind === "highlight" && !same.highlight) same.highlight = record.item;
      else if (record.kind === "note" && !same.note) { same.note = record.item; same.key = `n:${record.item.noteId}`; }
      else lost.push(record);
    } else if (marks.some(mark => start < mark.end && end > mark.start)) lost.push(record);
    else marks.push({ start, end, key: record.kind === "note" ? `n:${record.item.noteId}` : `h:${record.item.highlightId}`,
      ...(record.kind === "note" ? { note: record.item } : { highlight: record.item }) });
  }
  return { marks, lost };
}
