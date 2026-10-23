import type { ComponentProps } from "react";
import type Markdown from "react-markdown";
import { unified } from "unified";
import remarkParse from "remark-parse";
import remarkRehype from "remark-rehype";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";
import rehypeRaw from "rehype-raw";
import rehypeSanitize, { defaultSchema } from "rehype-sanitize";
import { normalizeMathMarkdown } from "./math-markdown";
import type { HastNode } from "./annotatable-text";

export const remarkPlugins = [remarkGfm, remarkMath];
const schema = {
  ...defaultSchema,
  attributes: {
    ...defaultSchema.attributes,
    code: [["className", /^language-./, "math-inline", "math-display"]],
    td: [...(defaultSchema.attributes?.td ?? []), "colSpan", "rowSpan"],
    th: [...(defaultSchema.attributes?.th ?? []), "colSpan", "rowSpan"],
    img: [...(defaultSchema.attributes?.img ?? []), "role", ["className", "math", "equation"]],
  },
  tagNames: [...(defaultSchema.tagNames ?? []), "figure", "figcaption"],
};
type MarkNode = { type: string; value?: string; tagName?: string; properties?: Record<string, unknown>; children?: MarkNode[] };
// Handle ==highlight== and bold labels that CommonMark leaves literal before Chinese text.
function rehypeInlineFormatting() {
  return (tree: MarkNode) => {
    function visit(parent: MarkNode) {
      if (!parent.children || ["pre", "code"].includes(parent.tagName ?? "")) return;
      parent.children = parent.children.flatMap(child => {
        if (child.type !== "text" || !child.value || !child.value.includes("==") && !child.value.includes("**")) { visit(child); return [child]; }
        const parts: MarkNode[] = [];
        const pattern = /==([^=\n]+)==|\*\*([^*\n]+[：:])\*\*/g;
        let last = 0;
        for (const match of child.value.matchAll(pattern)) {
          if (match.index > last) parts.push({ type: "text", value: child.value.slice(last, match.index) });
          parts.push({ type: "element", tagName: match[1] ? "mark" : "strong", properties: {}, children: [{ type: "text", value: match[1] ?? match[2] }] });
          last = match.index + match[0].length;
        }
        if (!last) return [child];
        if (last < child.value.length) parts.push({ type: "text", value: child.value.slice(last) });
        return parts;
      });
    }
    visit(tree);
  };
}
function rehypeCellMath() {
  return (tree: HastNode) => {
    function visit(parent: HastNode) {
      if (["td", "th"].includes(parent.tagName ?? "")) {
        parent.children = parent.children?.flatMap(node => {
          if (node.type !== "text" || !/[$\\]/.test(node.value ?? "")) return [node];
          const processor = unified().use(remarkParse).use(remarkGfm).use(remarkMath).use(remarkRehype);
          return processor.runSync(processor.parse(normalizeMathMarkdown(node.value ?? ""))).children as HastNode[];
        });
      }
      for (const node of parent.children ?? []) visit(node);
    }
    visit(tree);
  };
}
export const rehypePlugins: NonNullable<ComponentProps<typeof Markdown>["rehypePlugins"]> = [
  rehypeRaw, [rehypeSanitize, schema], rehypeInlineFormatting, rehypeCellMath, rehypeKatex,
];

export function markdownTree(text: string): HastNode {
  const processor = unified().use(remarkParse).use(remarkGfm).use(remarkMath)
    .use(remarkRehype, { allowDangerousHtml: true }).use(rehypePlugins);
  return processor.runSync(processor.parse(normalizeMathMarkdown(text)));
}
