import { hastTextNodes, type HastNode } from "./annotatable-text";

export interface RenderMark {
  key: string; start: number; end: number; highlightId?: string; noteId?: string;
  pending?: boolean; fresh?: ("hl" | "note")[]; ariaLabel: string;
}
const element = (tagName: string, properties: Record<string, unknown>, children: HastNode[]): HastNode => ({ type: "element", tagName, properties, children });
const textNode = (value: string): HastNode => ({ type: "text", value });

function bulb(mark: RenderMark): HastNode {
  const path = (d: string) => element("path", { d }, []);
  return element("span", { className: ["reader-anno-bulb-anchor"], dataAnnoUi: "" }, [element("button", {
    className: ["reader-anno-bulb", ...(mark.fresh?.includes("note") ? ["is-new"] : [])], dataAnnoUi: "", dataAnnoBulb: mark.key,
    type: "button", ariaLabel: "查看备注", title: "查看备注",
  }, [element("svg", { viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: 2.4, strokeLinecap: "round", strokeLinejoin: "round", ariaHidden: "true" }, [
    path("M15 14c.2-1 .7-1.7 1.5-2.5 1-.9 1.5-2.2 1.5-3.5A6 6 0 0 0 6 8c0 1 .2 2.2 1.5 3.5.7.7 1.3 1.5 1.5 2.5"), path("M9 18h6"), path("M10 22h4"),
  ])])]);
}

export function rehypeAnnotations(options: { items: readonly RenderMark[] }): (tree: HastNode) => void {
  return tree => {
    if (!options.items.length) return;
    const items = [...options.items].sort((a, b) => a.start - b.start), seen = new Set<string>();
    // Capture original nodes first; injected text and bulb UI must not advance offsets.
    for (const { node, parent, start } of hastTextNodes(tree)) {
      const value = node.value ?? "", end = start + value.length, parts: HastNode[] = [];
      let cursor = 0;
      for (const mark of items) {
        if (mark.start >= end || mark.end <= start) continue;
        const from = Math.max(0, mark.start - start), to = Math.min(value.length, mark.end - start);
        if (from > cursor) parts.push(textNode(value.slice(cursor, from)));
        const classes = ["reader-anno", ...(mark.highlightId ? ["reader-anno--hl"] : []), ...(mark.noteId ? ["reader-anno--note"] : []),
          ...(mark.pending ? ["reader-anno--pending"] : []), ...(mark.fresh?.includes("hl") ? ["is-new-hl"] : []), ...(mark.fresh?.includes("note") ? ["is-new-note"] : [])];
        function span(value: string, tail = false): HastNode {
          const first = !seen.has(mark.key); seen.add(mark.key);
          return element("span", { className: [...classes, ...(tail ? ["reader-anno--tail"] : [])], dataAnnoKey: mark.key,
            ...(first ? { tabIndex: 0, role: "button", ariaLabel: mark.ariaLabel } : {}) }, [textNode(value)]);
        }
        const segment = value.slice(from, to);
        if (start + to === mark.end) {
          const tail = Array.from(segment).at(-1)!;
          const head = segment.slice(0, -tail.length);
          if (head) parts.push(span(head));
          parts.push(element("span", { className: ["reader-anno-nb"] }, [span(tail, true), ...(mark.noteId ? [bulb(mark)] : [])]));
        } else parts.push(span(segment));
        cursor = to;
      }
      if (!parts.length) continue;
      if (cursor < value.length) parts.push(textNode(value.slice(cursor)));
      const index = parent.children!.indexOf(node);
      parent.children!.splice(index, 1, ...parts);
    }
  };
}
