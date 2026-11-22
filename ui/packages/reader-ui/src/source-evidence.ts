import type { ReadingDocument, ValidatedAnswerEvidence } from "@focus/reader-contracts";
import { hastTextNodes, type HastNode } from "./annotatable-text";
import { normalizeMathWithLines } from "./math-markdown";
import { markdownTree } from "./markdown-pipeline";

type Positioned = HastNode & { position?: { start: { line: number }; end: { line: number } } };
type SourceRange = { sourceLines: readonly [number, number]; quoteOffsets?: readonly [number, number] };
export type EvidenceProjection = { evidence: ValidatedAnswerEvidence } & (
  | { kind: "unavailable" }
  | ({ kind: "block" } & SourceRange)
  | ({ kind: "exact"; start: number; end: number } & SourceRange)
);

function findCanonicalQuote(markdown: string, starts: readonly number[], evidence: ValidatedAnswerEvidence): SourceRange | undefined {
  const [first, last] = evidence.sourceLines;
  const lower = starts[first - 1], upper = starts[last] ?? markdown.length;
  if (lower === undefined || first < 1 || last < first || last > starts.length) return undefined;
  const normalize = (value: string) => value.replace(/\r\n?/g, "\n");
  const exact = normalize(evidence.quote.exact), prefix = normalize(evidence.quote.prefix), suffix = normalize(evidence.quote.suffix);
  let matched: number | undefined;
  for (let at = markdown.indexOf(exact, lower); at >= 0 && at + exact.length <= upper; at = markdown.indexOf(exact, at + 1)) {
    if (at < prefix.length || !markdown.startsWith(prefix, at - prefix.length) || !markdown.startsWith(suffix, at + exact.length)) continue;
    if (matched !== undefined) return undefined;
    matched = at;
  }
  if (matched === undefined) return undefined;
  const line = first + (markdown.slice(lower, matched).match(/\n/g)?.length ?? 0);
  const codePointLength = (value: string) => value.length - (value.match(/[\uD800-\uDBFF][\uDC00-\uDFFF]/g)?.length ?? 0);
  const start = codePointLength(markdown.slice(0, matched));
  return { sourceLines: [line, line + (exact.match(/\n/g)?.length ?? 0)], quoteOffsets: [start, start + codePointLength(exact)] };
}

function resolve(tree: HastNode, document: ReadingDocument, evidence: readonly ValidatedAnswerEvidence[]): EvidenceProjection[] {
  if (!evidence.length) return [];
  const lines = new Map<HastNode, readonly [number, number]>();
  const canonical = normalizeMathWithLines(document.markdown).lines;
  function visit(node: Positioned, inherited?: readonly [number, number]) {
    const span = node.position ? [canonical[node.position.start.line - 1]?.[0] ?? 0, canonical[node.position.end.line - 1]?.[1] ?? 0] as const : inherited;
    if (span) lines.set(node, span);
    node.children?.forEach(child => visit(child, span));
  }
  visit(tree);
  const nodes = hastTextNodes(tree), text = nodes.map(n => n.node.value ?? "").join("");
  const markdown = document.markdown.replace(/\r\n?/g, "\n");
  const starts = [0, ...Array.from(markdown.matchAll(/\n/g), m => m.index! + 1)];
  if (starts.at(-1) === markdown.length) starts.pop();
  return evidence.map(e => {
    const no = { evidence: e, kind: "unavailable" as const };
    if (e.sourceId !== document.sourceId || e.bundleVersion !== document.bundleVersion) return no;
    const [first, last] = e.sourceLines;
    if (!e.quote.exact.trim()) return no;
    const verified = findCanonicalQuote(markdown, starts, e);
    const block = verified && tree.children?.some(n => {
      const span = lines.get(n);
      return span && span[0] <= verified.sourceLines[1] && span[1] >= verified.sourceLines[0];
    });
    if (e.renderGranularity || e.blockIds || e.layoutVersion || e.pdfRegions) {
      if (!verified) return no;
      if (e.renderGranularity === "block") return { evidence: e, kind: "block", ...verified };
    }
    const candidates: number[] = [];
    for (let at = text.indexOf(e.quote.exact); at !== -1; at = text.indexOf(e.quote.exact, at + 1)) {
      const touched = nodes.filter(n => n.start < at + e.quote.exact.length && n.start + (n.node.value?.length ?? 0) > at);
      if (touched.length && touched.every(n => { const span = lines.get(n.node); return span && span[0] >= first && span[1] <= last; }) &&
        text.slice(0, at).endsWith(e.quote.prefix) && text.slice(at + e.quote.exact.length).startsWith(e.quote.suffix)) candidates.push(at);
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

export function rehypeSourceEvidence(options: { document: ReadingDocument; evidence: readonly ValidatedAnswerEvidence[]; active?: string }) {
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
        for (const p of owners.filter(p => p.end === start + to)) parts.push({ type: "element", tagName: "button", properties: {
          type: "button", dataAnnoUi: "", className: ["source-evidence-number"], dataEvidence: p.evidence.evidenceId,
          ariaLabel: `返回回答证据 ${p.evidence.displayNumber}`,
        }, children: [{ type: "text", value: String(p.evidence.displayNumber) }] });
      }
      parent.children!.splice(parent.children!.indexOf(node), 1, ...parts);
    }
    const canonical = normalizeMathWithLines(options.document.markdown).lines;
    for (const child of tree.children ?? []) {
      const span = (child as Positioned).position;
      if (child.type !== "element" || !span) continue;
      const first = canonical[span.start.line - 1]?.[0] ?? 0, last = canonical[span.end.line - 1]?.[1] ?? 0;
      child.properties = { ...child.properties, dataSourceLine: first };
      const fallback = projections.filter(p => p.kind === "block" && first <= p.sourceLines[1] && last >= p.sourceLines[0]);
      if (fallback.length) {
        child.properties.dataEvidenceBlock = fallback.map(p => p.evidence.evidenceId).join(" ");
        // Keep tables and figures structurally valid: the floating card supplies
        // the reverse link for object/block fallbacks, without inserting text
        // into table row groups or formula markup.
      }
    }
  };
}
