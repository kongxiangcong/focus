import { unified } from "unified";
import remarkParse from "remark-parse";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import remarkRehype from "remark-rehype";
import rehypeRaw from "rehype-raw";
import type { ReaderChunk, ReaderImage } from "@focus/reader-contracts";

export type Figure = ReaderImage & { id: string; sourceId: string; label: string; bodyCaption?: boolean };
export type FigureNode = { type: string; value?: string; tagName?: string; properties?: Record<string, unknown>; children?: FigureNode[]; data?: { readerFigure?: Figure };
  position?: { start: { line: number; column: number }; end: { line: number; column: number } } };
export const figureNumber = /(?:图|fig(?:ure)?\.?)\s*[-.:：]?\s*(\d+[a-z]?)(?!\d)/i;
const captionHeading = /^\s*(?:图|fig(?:ure)?\.?|table|tab\.?|表|equation|formula|公式)\s*[-.:：]?\s*\d+/i;
const necessaryCaption = /^\s*(?:table|tab\.?|表|equation|formula|公式)(?:\s*[-.:：]?\s*\d+|\s*$)/i;
function decode(value: string) { try { return decodeURIComponent(value); } catch { return value; } }
export function imageUrl(src: string, sourceId: string) {
  const value = src.trim().replace(/\\/g, "/");
  if (/^(?:https?:|\/)/i.test(value)) return value;
  if (/^[a-z]+:/i.test(value)) return "";
  return `/reader/assets/${encodeURIComponent(sourceId)}/${value.replace(/^\.\//, "")}`;
}
export function imageIdentity(src: string, sourceId: string) {
  const resolved = imageUrl(src, sourceId);
  if (!resolved) return "";
  const url = new URL(resolved, "https://focus.invalid");
  // The Host asset URL and relative Parser Bundle path name the same image.
  return `${sourceId}:${url.origin === "https://focus.invalid" ? "" : url.origin}${decode(url.pathname)}${url.origin === "https://focus.invalid" ? "" : url.search}`;
}
function text(node: FigureNode): string {
  if (node.type === "text") return node.value ?? "";
  const content = (node.children ?? []).map(text).join("");
  if (String(node.properties?.className ?? "").includes("math")) return `$${content}$`;
  return content;
}
function equation(node: FigureNode) {
  return necessaryCaption.test(String(node.properties?.alt ?? "")) ||
    /(?:^|\/)equations?\//i.test(String(node.properties?.src ?? "")) ||
    /(?:^|[\s,-])(?:math|equation)(?:$|[\s,-])/i.test(String(node.properties?.className ?? "")) || node.properties?.role === "math";
}
/** Structural scan: never remove table cells, math, code, or inline prose images. */
export function scanFigures(tree: FigureNode, sourceId: string, inline = false, markdown?: string) {
  const found: (ReaderImage & { bodyCaption: boolean })[] = [], protectedIds = new Set<string>();
  const nodes: { node: FigureNode; id: string }[] = [];
  const lines = markdown?.split("\n");
  function visit(node: FigureNode, ancestors: FigureNode[], siblings: FigureNode[], index: number) {
    if (node.tagName === "img") {
      const src = String(node.properties?.src ?? ""), id = imageIdentity(src, sourceId);
      const block = [...ancestors].reverse().find(a => ["root", "p", "figure", "div"].includes(a.tagName ?? a.type));
      const protectedImage = equation(node) || ancestors.some(a => ["table", "pre", "code"].includes(a.tagName ?? "") || /math/.test(String(a.properties?.className ?? "")) || a.properties?.role === "math");
      const blockText = block ? text(block).trim() : "";
      const ownCaption = captionHeading.test(blockText);
      const position = node.position;
      const ownLine = lines && position && !(lines[position.start.line - 1] ?? "").slice(0, position.start.column - 1).trim() && !(lines[position.end.line - 1] ?? "").slice(position.end.column - 1).trim();
      const independent = ownLine || !block || ["root", "figure", "div"].includes(block.tagName ?? block.type) || block.tagName === "p" && (!blockText || ownCaption);
      if (protectedImage || !inline && !independent) { protectedIds.add(id); return; }
      if (!id) return;
      const figure = [...ancestors].reverse().find(a => a.tagName === "figure");
      const captionNode = figure?.children?.find(a => a.tagName === "figcaption");
      let caption = captionNode ? text(captionNode).trim() : ownCaption ? blockText : String(node.properties?.alt ?? "").trim();
      // Markdown captions often occupy the paragraph following the image block.
      const parent = ancestors[ancestors.indexOf(block!) - 1];
      const blockIndex = parent?.children?.indexOf(block!) ?? -1;
      const adjacent = blockIndex >= 0 ? parent?.children?.slice(blockIndex + 1).find(a => a.type !== "text" || !!a.value?.trim()) : siblings[index + 1];
      const adjacentCaption = !captionNode && !ownCaption && adjacent && captionHeading.test(text(adjacent));
      if (adjacentCaption) caption = text(adjacent!).trim();
      if (necessaryCaption.test(caption)) { protectedIds.add(id); return; }
      found.push({ src: imageUrl(src, sourceId), caption, bodyCaption: !!captionNode || ownCaption || !!adjacentCaption }); nodes.push({ node, id }); return;
    }
    node.children?.forEach((child, i, children) => visit(child, [...ancestors, node], children, i));
  }
  visit(tree, [], [], 0);
  return { found, protectedIds, nodes };
}
const parser = unified().use(remarkParse).use(remarkGfm).use(remarkMath).use(remarkRehype, { allowDangerousHtml: true }).use(rehypeRaw);
const cache = new Map<string, ReturnType<typeof scanFigures>>();
export function extractFigures(markdown: string, sourceId: string) {
  const key = `${sourceId}\0${markdown}`;
  let result = cache.get(key);
  if (!result) {
    result = scanFigures(parser.runSync(parser.parse(markdown)) as FigureNode, sourceId, false, markdown);
    if (cache.size >= 160) cache.delete(cache.keys().next().value!);
    cache.set(key, result);
  }
  return result;
}
export function mergeFigures(sourceId: string, ...lists: readonly (readonly ReaderImage[])[]): Figure[] {
  const map = new Map<string, Figure>();
  for (const image of lists.flat()) {
    const id = imageIdentity(image.src, sourceId);
    if (!id) continue;
    const old = map.get(id);
    // First list owns order and language; supplementary metadata only fills gaps.
    if (!old) map.set(id, { ...image, src: imageUrl(image.src, sourceId), id, sourceId, label: "" });
    else if ((!old.caption || /^(?:figure|image|img|图片|插图)$/i.test(old.caption) || !figureNumber.test(old.caption) && figureNumber.test(image.caption)) && image.caption) old.caption = image.caption;
  }
  return [...map.values()].map(f => ({ ...f, label: f.caption.match(figureNumber) ? `图 ${f.caption.match(figureNumber)![1]}` : `插图 ${decode(new URL(f.src, "https://focus.invalid").pathname.split("/").at(-1)!)}` }));
}
export function chunkFigures(chunk: ReaderChunk, original = false): Figure[] {
  const source = extractFigures(chunk.sourceMarkdown, chunk.sourceId);
  const active = extractFigures(!original && chunk.translation !== null ? chunk.translation : chunk.sourceMarkdown, chunk.sourceId);
  const translated = new Map(active.found.map(i => [imageIdentity(i.src, chunk.sourceId), i]));
  return mergeFigures(chunk.sourceId, source.found.map(i => {
    const localized = translated.get(imageIdentity(i.src, chunk.sourceId));
    return localized && (localized.bodyCaption || !i.bodyCaption) ? localized : i;
  }), active.found,
    chunk.images.filter(i => !source.protectedIds.has(imageIdentity(i.src, chunk.sourceId)) && !active.protectedIds.has(imageIdentity(i.src, chunk.sourceId))));
}
