import { memo } from "react";
import Markdown, { type Components, defaultUrlTransform } from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";
import "katex/dist/katex.min.css";

const components: Components = {
  table: ({ children }) => <div className="focus-table" tabIndex={0}><table>{children}</table></div>,
  a: ({ children, href }) => <a href={href} target="_blank" rel="noreferrer">{children}</a>,
  img: ({ src, alt }) => <img src={src} alt={alt ?? ""} loading="lazy" />,
};
const remarkPlugins = [remarkGfm, remarkMath];
const rehypePlugins = [rehypeKatex];
export const MarkdownContent = memo(function MarkdownContent({ text, sourceId }: { text: string; sourceId?: string }) {
  return <div className="focus-markdown"><Markdown remarkPlugins={remarkPlugins} rehypePlugins={rehypePlugins}
    components={components} urlTransform={(url, key) => {
      if (sourceId && key === "src" && !/^(?:[a-z]+:|\/)/i.test(url)) {
        return `/reader/assets/${encodeURIComponent(sourceId)}/${url}`;
      }
      return defaultUrlTransform(url);
    }}>{text}</Markdown></div>;
});
