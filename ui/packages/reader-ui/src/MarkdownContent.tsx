import { Children, memo, type ComponentProps, type ReactNode } from "react";
import Markdown, { type Components, defaultUrlTransform } from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";
import rehypeRaw from "rehype-raw";
import rehypeSanitize, { defaultSchema } from "rehype-sanitize";
import "katex/dist/katex.min.css";

const components: Components = {
  table: ({ children }) => <div className="focus-table" tabIndex={0}><table>{children}</table></div>,
  td: ({ children, colSpan, rowSpan }) => <td colSpan={colSpan} rowSpan={rowSpan}><CellContent>{children}</CellContent></td>,
  th: ({ children, colSpan, rowSpan }) => <th colSpan={colSpan} rowSpan={rowSpan}><CellContent>{children}</CellContent></th>,
  a: ({ children, href }) => <a href={href} target="_blank" rel="noreferrer">{children}</a>,
  img: ({ src, alt }) => <img src={src} alt={alt ?? ""} loading="lazy" />,
};
const remarkPlugins = [remarkGfm, remarkMath];
const schema = {
  ...defaultSchema,
  attributes: {
    ...defaultSchema.attributes,
    code: [["className", /^language-./, "math-inline", "math-display"]],
    td: [...(defaultSchema.attributes?.td ?? []), "colSpan", "rowSpan"],
    th: [...(defaultSchema.attributes?.th ?? []), "colSpan", "rowSpan"],
  },
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
const rehypePlugins: NonNullable<ComponentProps<typeof Markdown>["rehypePlugins"]> = [
  rehypeRaw, [rehypeSanitize, schema], rehypeInlineFormatting, rehypeKatex,
];
// MinerU emits HTML tables; Markdown does not parse math inside raw HTML cells.
function CellContent({ children }: { children: ReactNode }) {
  return Children.map(children, child => typeof child === "string" && child.includes("$")
    ? <Markdown remarkPlugins={remarkPlugins} rehypePlugins={rehypePlugins}>{child}</Markdown>
    : child);
}
export const MarkdownContent = memo(function MarkdownContent({ text, sourceId }: { text: string; sourceId?: string }) {
  return <div className="focus-markdown"><Markdown remarkPlugins={remarkPlugins} rehypePlugins={rehypePlugins}
    components={components} urlTransform={(url, key) => {
      if (sourceId && key === "src" && !/^(?:[a-z]+:|\/)/i.test(url)) {
        return `/reader/assets/${encodeURIComponent(sourceId)}/${url}`;
      }
      return defaultUrlTransform(url);
    }}>{text}</Markdown></div>;
});
