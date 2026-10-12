import { unified } from "unified";
import remarkParse from "remark-parse";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";

type Node = { type: string; children?: Node[]; position?: { start: { offset?: number }; end: { offset?: number } } };
type Range = [number, number];
type Edit = { start: number; end: number; value: string };
const parser = unified().use(remarkParse).use(remarkGfm).use(remarkMath);
const protectedTypes = new Set(["code", "inlineCode", "link", "linkReference", "image", "imageReference", "definition", "html", "math", "inlineMath"]);
const texCommand = /\\[a-zA-Z]+/;

/** Normalize TeX notation before CommonMark consumes delimiter backslashes.
 * Code, links, raw HTML and existing dollar math remain byte for byte intact.
 */
export function normalizeMathMarkdown(markdown: string): string {
  if (!markdown.includes("\\")) return markdown;
  const protectedRanges: Range[] = [];
  function visit(node: Node) {
    if (protectedTypes.has(node.type) && node.position?.start.offset !== undefined && node.position.end.offset !== undefined) {
      protectedRanges.push([node.position.start.offset, node.position.end.offset]);
      return;
    }
    node.children?.forEach(visit);
  }
  visit(parser.parse(markdown) as Node);
  const edits: Edit[] = [];
  function overlaps(start: number, end: number) {
    return protectedRanges.some(([a, b]) => start < b && end > a) || edits.some(edit => start < edit.end && end > edit.start);
  }
  // Plain square brackets are a compatibility form only when they contain TeX.
  const delimiters = /(?<!\\)\\\(([\s\S]*?)\\\)|(?<!\\)\\\[([\s\S]*?)\\\]|(?<!\\)\[([^\[\]\n]+)\](?![\[(])/g;
  for (const match of markdown.matchAll(delimiters)) {
    const start = match.index, end = start + match[0].length;
    const [inline, display, bracket] = match.slice(1);
    const value = (inline ?? display ?? bracket ?? "").trim();
    if (!value || overlaps(start, end) || bracket !== undefined && !texCommand.test(value)) continue;
    const lineStart = markdown.lastIndexOf("\n", start - 1) + 1;
    const nextLine = markdown.indexOf("\n", end);
    const alone = !markdown.slice(lineStart, start).trim() && !markdown.slice(end, nextLine < 0 ? markdown.length : nextLine).trim();
    edits.push({ start, end, value: inline === undefined && alone ? `$$\n${value}\n$$` : `$${value.replace(/\n/g, " ")}$` });
  }
  // Generated reading text sometimes contains a standalone symbolic expression.
  // Require a TeX command and reject prose, Markdown syntax and existing math.
  for (const match of markdown.matchAll(/^[ \t]*(.+?)[ \t]*$/gm)) {
    const start = match.index, end = start + match[0].length, value = match[1];
    if (overlaps(start, end) || !texCommand.test(value) || /[$`<>\[\]]/.test(value)) continue;
    const symbols = value.replace(/\\[a-zA-Z]+/g, "");
    if (/[^a-zA-Z0-9_^{},.()+\-=*/|:;!\s]/.test(symbols) || /[a-zA-Z]{3,}/.test(symbols)) continue;
    edits.push({ start, end, value: `$$\n${value}\n$$` });
  }
  let end = 0;
  const result: string[] = [];
  for (const edit of edits.sort((a, b) => a.start - b.start)) {
    result.push(markdown.slice(end, edit.start), edit.value);
    end = edit.end;
  }
  result.push(markdown.slice(end));
  return result.join("");
}
