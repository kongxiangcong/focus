import { hastTextNodes, type HastNode } from "./annotatable-text";

export interface RenderMark {
  key: string; start: number; end: number; highlightId?: string; noteId?: string;
  sharedNoteId?: string; interactive?: boolean;
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
      const touching = items.filter(mark => mark.start < end && mark.end > start);
      if (!touching.length || !value) continue;
      const cuts = new Set([start, end]);
      const tails = new Map<number, RenderMark[]>();
      for (const mark of touching) {
        cuts.add(Math.max(start, mark.start));
        cuts.add(Math.min(end, mark.end));
        if (mark.sharedNoteId || mark.end > end) continue;
        const tail = Array.from(value.slice(0, mark.end - start)).at(-1)!;
        cuts.add(mark.end - tail.length);
        tails.set(mark.end, [...(tails.get(mark.end) ?? []), mark]);
      }
      const offsets = [...cuts].sort((a, b) => a - b);
      for (let i = 1; i < offsets.length; i++) {
        const from = offsets[i - 1], to = offsets[i];
        const segment = textNode(value.slice(from - start, to - start));
        const owners = touching.filter(mark => mark.start <= from && mark.end >= to);
        if (!owners.length) { parts.push(segment); continue; }
        const legacy = owners.find(mark => !mark.sharedNoteId);
        const shared = owners.filter(mark => mark.sharedNoteId);
        const control = legacy ?? shared.find(mark => mark.interactive);
        const first = control && !seen.has(control.key);
        if (control) seen.add(control.key);
        const tail = tails.get(to) ?? [];
        const classes = ["reader-anno", ...(legacy?.highlightId ? ["reader-anno--hl"] : []), ...(legacy?.noteId ? ["reader-anno--note"] : []),
          ...(legacy?.pending ? ["reader-anno--pending"] : []), ...(legacy?.fresh?.includes("hl") ? ["is-new-hl"] : []),
          ...(legacy?.fresh?.includes("note") ? ["is-new-note"] : []), ...(tail.length ? ["reader-anno--tail"] : []),
          ...(shared.length ? ["reader-anno--shared-note"] : [])];
        const span = element("span", { className: classes, dataAnnoKey: control?.key,
          dataSharedNoteIds: shared.length ? Array.from(new Set(shared.map(mark => mark.sharedNoteId))).join(" ") : undefined,
          ...(first ? { tabIndex: 0, role: "button", ariaLabel: control.ariaLabel } : {}) }, [segment]);
        parts.push(tail.length ? element("span", { className: ["reader-anno-nb"] },
          [span, ...tail.filter(mark => mark.noteId).map(bulb)]) : span);
      }
      const index = parent.children!.indexOf(node);
      parent.children!.splice(index, 1, ...parts);
    }
  };
}
