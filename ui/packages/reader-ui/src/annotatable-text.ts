/** UTF-16 text offsets shared by browser selections and the rendered HAST. */
export const EXCLUDE_SELECTOR = ".katex, figure, [data-anno-ui], script, style";
const TABLE_PARENTS = new Set(["table", "thead", "tbody", "tfoot", "tr"]);
const BLOCK_SELECTOR = "p, li, h1, h2, h3, h4, h5, h6, td, th, blockquote";

export interface HastNode {
  type: string; value?: string; tagName?: string;
  properties?: Record<string, unknown>; children?: HastNode[];
}

function excluded(node: HastNode): boolean {
  const classes = node.properties?.className;
  return ["figure", "script", "style"].includes(node.tagName ?? "") ||
    (Array.isArray(classes) ? classes : String(classes ?? "").split(/\s+/)).includes("katex") ||
    Object.hasOwn(node.properties ?? {}, "dataAnnoUi") || Object.hasOwn(node.properties ?? {}, "data-anno-ui");
}

export function hastTextNodes(tree: HastNode): { node: HastNode; parent: HastNode; start: number }[] {
  const nodes: { node: HastNode; parent: HastNode; start: number }[] = [];
  let pos = 0;
  function visit(parent: HastNode) {
    if (excluded(parent)) return;
    for (const node of parent.children ?? []) {
      if (node.type === "text") {
        if (TABLE_PARENTS.has(parent.tagName ?? "") && !node.value?.trim()) continue;
        nodes.push({ node, parent, start: pos }); pos += node.value?.length ?? 0;
      } else visit(node);
    }
  }
  visit(tree); return nodes;
}

export function hastAnnotatableText(tree: HastNode): string {
  return hastTextNodes(tree).map(({ node }) => node.value ?? "").join("");
}

function excludedAncestor(root: Element, node: Node): Element | null {
  let excluded: Element | null = null;
  for (let el = node.nodeType === 1 ? node as Element : node.parentElement; el; el = el.parentElement) {
    if (el.matches(EXCLUDE_SELECTOR)) excluded = el;
    if (el === root) break;
  }
  return excluded;
}

export function domAnnotatableText(root: Element): { text: string; nodes: { node: Text; start: number }[] } {
  const nodes: { node: Text; start: number }[] = [];
  let text = "";
  const walker = root.ownerDocument.createTreeWalker(root, 4, { acceptNode(node) {
    return excludedAncestor(root, node) || (TABLE_PARENTS.has(node.parentElement?.tagName.toLowerCase() ?? "") && !node.textContent?.trim()) ? 2 : 1;
  } });
  for (let next = walker.nextNode(); next; next = walker.nextNode()) {
    const node = next as Text; nodes.push({ node, start: text.length }); text += node.data;
  }
  return { text, nodes };
}

export function domOffset(root: Element, container: Node, offset: number, edge: "start" | "end"): number | null {
  if (!root.contains(container) || !Number.isInteger(offset) || offset < 0) return null;
  const { nodes } = domAnnotatableText(root);
  const before = (boundary: Node) => nodes.reduce((total, { node }) => total +
    ((node.compareDocumentPosition(boundary) & 4) && !boundary.contains(node) ? node.data.length : 0), 0);
  const excluded = excludedAncestor(root, container);
  if (excluded) {
    // Excluded subtrees contribute zero text; both edges snap to their shared boundary.
    return before(excluded);
  }
  if (container.nodeType === 3) {
    const text = container as Text;
    if (offset > text.length) return null;
    const match = nodes.find(item => item.node === text);
    return match ? match.start + offset : before(text);
  }
  if (container.nodeType !== 1 || offset > container.childNodes.length) return null;
  const child = container.childNodes[offset];
  return child ? before(child) : before(container) + nodes.reduce((total, { node }) => total + (container.contains(node) ? node.data.length : 0), 0);
}

export function blockOf(root: Element, node: Node): Element | null {
  if (!root.contains(node)) return null;
  for (let el = node.nodeType === 1 ? node as Element : node.parentElement; el; el = el.parentElement) {
    if (el.matches(BLOCK_SELECTOR)) return el;
    if (el === root) break;
  }
  return null;
}
