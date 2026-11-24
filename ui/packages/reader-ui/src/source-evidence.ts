import type { ReaderMessage, ReadingDocument, ValidatedAnswerEvidence } from "@focus/reader-contracts";
import { hastTextNodes, type HastNode } from "./annotatable-text";
import { normalizeMathWithLines } from "./math-markdown";
import { markdownTree } from "./markdown-pipeline";
import type { ChunkNoteLink } from "./selected-source-note";

export function messageEvidence(message: ReaderMessage, scope: { sourceId: string }, discussionId?: string | null) {
  return (message.evidence ?? []).filter(e => e.sourceId === scope.sourceId &&
    e.messageId === message.messageId && e.discussionId === discussionId && e.answerRevision === message.answerRevision &&
    message.content.includes(`[[e:${e.evidenceId}]]`));
}

export function answerEvidenceKey({ messageId, displayNumber }: ValidatedAnswerEvidence) {
  return JSON.stringify([messageId, displayNumber]);
}

export function citedMarkdown(message: ReaderMessage, evidence: readonly ValidatedAnswerEvidence[], hideEvidence = false) {
  return message.content.replace(/\[\[e:([0-9a-f]{24})\]\]/g, (_, id: string) => {
    if (hideEvidence) return "";
    const e = evidence.find(e => e.evidenceId === id);
    return e ? `[${e.displayNumber}](#e-${id})` : "〔原文证据不可定位〕";
  }).replace(/\[\[e:[^\]]*$/, "");
}

type Point = { line: number; offset?: number };
type Positioned = HastNode & { position?: { start: Point; end: Point } };
type SourceRange = { sourceLines: readonly [number, number]; quoteOffsets?: readonly [number, number] };
const codePointLength = (value: string) => value.length - (value.match(/[\uD800-\uDBFF][\uDC00-\uDFFF]/g)?.length ?? 0);
export type EvidenceProjection = { evidence: ValidatedAnswerEvidence } & (
  | { kind: "unavailable" }
  | ({ kind: "block" } & SourceRange)
  | ({ kind: "exact"; start: number; end: number } & SourceRange)
);

function findCanonicalQuote(markdown: string, starts: readonly number[], evidence: ValidatedAnswerEvidence): (SourceRange & { quoteOffsets: readonly [number, number]; canonicalStart: number }) | undefined {
  const [first, last] = evidence.sourceLines ?? [];
  if (!Number.isSafeInteger(first) || !Number.isSafeInteger(last)) return undefined;
  const lower = starts[first - 1], upper = starts[last] === undefined ? markdown.length : starts[last] - 1;
  if (lower === undefined || first < 1 || last < first || last > starts.length) return undefined;
  const normalize = (value: string) => value.replace(/\r\n?/g, "\n");
  const exact = normalize(evidence.quote.exact), prefix = normalize(evidence.quote.prefix), suffix = normalize(evidence.quote.suffix);
  if (!exact.trim()) return undefined;
  let matched: number | undefined;
  for (let at = markdown.indexOf(exact, lower); at >= 0 && at + exact.length <= upper; at = markdown.indexOf(exact, at + 1)) {
    if (at < prefix.length || !markdown.startsWith(prefix, at - prefix.length) || !markdown.startsWith(suffix, at + exact.length)) continue;
    if (matched !== undefined) return undefined;
    matched = at;
  }
  if (matched === undefined) return undefined;
  const line = first + (markdown.slice(lower, matched).match(/\n/g)?.length ?? 0);
  const start = codePointLength(markdown.slice(0, matched));
  return { sourceLines: [line, line + (exact.match(/\n/g)?.length ?? 0)], quoteOffsets: [start, start + codePointLength(exact)], canonicalStart: matched };
}

function canonicalQuoteLocator(document: ReadingDocument) {
  const markdown = document.markdown.replace(/\r\n?/g, "\n");
  const starts = [0, ...Array.from(markdown.matchAll(/\n/g), m => m.index! + 1)];
  if (starts.at(-1) === markdown.length) starts.pop();
  return (evidence: ValidatedAnswerEvidence) =>
    evidence.sourceId === document.sourceId && evidence.bundleVersion === document.bundleVersion
      ? findCanonicalQuote(markdown, starts, evidence) : undefined;
}

export function evidenceBySourceBlock(document: ReadingDocument, evidence: readonly ValidatedAnswerEvidence[]) {
  const byBlock = new Map<string, ValidatedAnswerEvidence[]>();
  if (!document.blocks?.length || !evidence.length) return byBlock;
  const locate = canonicalQuoteLocator(document);
  for (const item of evidence) {
    const range = locate(item);
    if (!range) continue;
    const [start, end] = range.quoteOffsets;
    for (const block of document.blocks) {
      if (block.offsets[0] >= end || block.offsets[1] <= start) continue;
      const matches = byBlock.get(block.blockId);
      if (!matches) byBlock.set(block.blockId, [item]);
      else if (!matches.includes(item)) matches.push(item);
    }
  }
  return byBlock;
}

function resolve(tree: HastNode, document: ReadingDocument, evidence: readonly ValidatedAnswerEvidence[]): EvidenceProjection[] {
  if (!evidence.length) return [];
  const lines = new Map<HastNode, readonly [number, number]>();
  const original = document.markdown;
  const normalized = normalizeMathWithLines(original);
  const canonical = normalized.lines;
  function visit(node: Positioned, inherited?: readonly [number, number]) {
    const span = node.position ? [canonical[node.position.start.line - 1]?.[0] ?? 0, canonical[node.position.end.line - 1]?.[1] ?? 0] as const : inherited;
    if (span) lines.set(node, span);
    node.children?.forEach(child => visit(child, span));
  }
  visit(tree);
  const nodes = hastTextNodes(tree), text = nodes.map(n => n.node.value ?? "").join("");
  const locate = canonicalQuoteLocator(document);
  return evidence.map(e => {
    const no = { evidence: e, kind: "unavailable" as const };
    if (e.sourceId !== document.sourceId || e.bundleVersion !== document.bundleVersion) return no;
    const [first, last] = e.sourceLines ?? [];
    if (!Number.isSafeInteger(first) || !Number.isSafeInteger(last) || first < 1 || last < first || last > document.lineCount) return no;
    if (!e.quote.exact.trim()) return no;
    const verified = locate(e);
    const block = verified && tree.children?.some(n => {
      const span = lines.get(n);
      return span && span[0] <= verified.sourceLines[1] && span[1] >= verified.sourceLines[0];
    });
    if (!verified && (e.messageId || e.renderGranularity || e.blockIds || e.layoutVersion || e.pdfRegions)) return no;
    const candidates: number[] = [];
    for (let at = text.indexOf(e.quote.exact); at !== -1; at = text.indexOf(e.quote.exact, at + 1)) {
      const touched = nodes.filter(n => n.start < at + e.quote.exact.length && n.start + (n.node.value?.length ?? 0) > at);
      if (!touched.length || !touched.every(n => {
        const span = lines.get(n.node);
        return span && span[0] >= first && span[1] <= last;
      })) continue;
      const renderedContextMatches = text.slice(0, at).endsWith(e.quote.prefix) && text.slice(at + e.quote.exact.length).startsWith(e.quote.suffix);
      if (renderedContextMatches) { candidates.push(at); continue; }
      // Markdown can remove syntax in a signed quote's surrounding context. Verify
      // an unchanged text node's canonical offset before highlighting that occurrence.
      if (!verified || touched.length !== 1) continue;
      const { node, start } = touched[0];
      const offset = (node as Positioned).position?.start.offset;
      const rawStart = offset === undefined ? null : normalized.sourceOffsetAt(offset);
      if (rawStart === null || !original.startsWith(node.value!, rawStart)) continue;
      const rawOffset = rawStart + at - start;
      const canonicalOffset = rawOffset - (original.slice(0, rawOffset).match(/\r\n/g)?.length ?? 0);
      if (canonicalOffset === verified.canonicalStart) candidates.push(at);
    }
    if (candidates.length === 1) return { evidence: e, kind: "exact", start: candidates[0], end: candidates[0] + e.quote.exact.length, ...(verified ?? { sourceLines: e.sourceLines }) };
    return verified && block ? { evidence: e, kind: "block", ...verified } : no;
  });
}

let cached: { markdown: string; tree: HastNode } | undefined;
export function projectEvidence(document: ReadingDocument, evidence: readonly ValidatedAnswerEvidence[]) {
  if (!evidence.length) return [];
  if (cached?.markdown !== document.markdown) cached = { markdown: document.markdown, tree: markdownTree(document.markdown) };
  return resolve(cached.tree, document, evidence);
}

export function rehypeSourceEvidence(options: { document: ReadingDocument; evidence: readonly ValidatedAnswerEvidence[];
  active?: string; noteLinks?: readonly ChunkNoteLink[] }) {
  return (tree: HastNode) => {
    const projections = resolve(tree, options.document, options.evidence);
    const exact = projections.filter(p => p.kind === "exact");
    const nodes = hastTextNodes(tree);
    for (const { node, parent, start } of nodes) {
      const value = node.value ?? "";
      const cuts = new Set([0, value.length]);
      for (const p of exact) {
        if (p.start < start + value.length && p.end > start) { cuts.add(Math.max(0, p.start - start)); cuts.add(Math.min(value.length, p.end - start)); }
      }
      if (cuts.size === 2 && !exact.some(p => p.start <= start && p.end >= start + value.length)) continue;
      const offsets = [...cuts].sort((a, b) => a - b), parts: HastNode[] = [];
      for (let i = 0; i < offsets.length - 1; i++) {
        const from = offsets[i], to = offsets[i + 1];
        const owners = exact.filter(p => p.start <= start + from && p.end >= start + to);
        const child: HastNode = { type: "text", value: value.slice(from, to) };
        parts.push(owners.length ? { type: "element", tagName: "mark", properties: {
          className: ["source-evidence", ...(owners.some(p => p.evidence.evidenceId === options.active) ? ["is-active"] : [])],
          dataEvidenceIds: owners.map(p => p.evidence.evidenceId).join(" "),
        }, children: [child] } : child);
      }
      parent.children!.splice(parent.children!.indexOf(node), 1, ...parts);
    }
    function findMarkedEvidence(node: HastNode, ids: Set<string>) {
      const marked = node.properties?.dataEvidenceIds;
      if (typeof marked === "string") marked.split(" ").forEach(id => ids.add(id));
      node.children?.forEach(child => findMarkedEvidence(child, ids));
    }
    const canonical = normalizeMathWithLines(options.document.markdown).lines;
    const starts = [0];
    for (const line of options.document.markdown.replace(/\r\n?/g, "\n").split("\n")) {
      starts.push(starts[starts.length - 1] + codePointLength(line) + 1);
    }
    const blocks = options.document.blocks ?? [];
    const remainingNoteLinks = new Set(options.noteLinks);
    let blockIndex = 0;
    tree.children = tree.children?.flatMap(child => {
      const span = (child as Positioned).position;
      if (child.type !== "element" || !span) return [child];
      const first = canonical[span.start.line - 1]?.[0] ?? 0, last = canonical[span.end.line - 1]?.[1] ?? 0;
      if (!first || !last) return [child];
      const start = starts[first - 1], end = starts[last] - 1;
      while (blockIndex < blocks.length && blocks[blockIndex].offsets[1] <= start) blockIndex++;
      const blockIds = [];
      for (let index = blockIndex; index < blocks.length && blocks[index].offsets[0] < end; index++) {
        blockIds.push(blocks[index].blockId);
      }
      child.properties = { ...child.properties, dataSourceLine: first, dataSourceEnd: last,
        dataSourceOffsetStart: start, dataSourceOffsetEnd: end, dataSourceBlockIds: blockIds.join(" ") || undefined };
      const notes = [...remainingNoteLinks].filter(({ sourceOffsets: [low, high] }) => start < high && low < end);
      for (const note of notes) remainingNoteLinks.delete(note);
      const after: HastNode[] = notes.length ? [{ type: "element", tagName: "span", properties: {
        dataAnnoUi: "", dataSourceChunkNotes: notes.map(note => note.index).join(" "),
      }, children: [] }] : [];
      const fallback = projections.filter(p => p.kind === "block" && first <= p.sourceLines[1] && last >= p.sourceLines[0]);
      if (fallback.length) child.properties.dataEvidenceBlock = fallback.map(p => p.evidence.evidenceId).join(" ");
      const marked = new Set<string>();
      if (exact.length) findMarkedEvidence(child, marked);
      const items = projections.filter(p => marked.has(p.evidence.evidenceId) || fallback.includes(p));
      if (!items.length) return [child, ...after];
      const marker: HastNode = { type: "element", tagName: "span", properties: {
        dataAnnoUi: "", dataSourceEvidenceMarkers: items.map(p => p.evidence.evidenceId).join(" "),
      }, children: [] };
      if (child.tagName && /^(?:p|h[1-6])$/.test(child.tagName)) {
        child.children?.push(marker);
        return [child, ...after];
      }
      return [child, marker, ...after];
    });
  };
}
