import type { ReadingDocument, ReadingSection } from "@focus/reader-contracts";
import { hastAnnotatableText, type HastNode } from "./annotatable-text";
import { markdownTree } from "./markdown-pipeline";
import { normalizeMathWithLines } from "./math-markdown";
import type { SourceLines, SourcePosition } from "./source-position";

type Heading = { level: number; title: string; lines: SourceLines };
type Positioned = HastNode & { position?: { start: { line: number }; end: { line: number } } };

function headings(markdown: string): Heading[] {
  const { lines } = normalizeMathWithLines(markdown);
  return (markdownTree(markdown).children ?? []).flatMap((node: Positioned) => {
    const level = /^h([1-6])$/.exec(node.tagName ?? "");
    const position = node.position;
    if (!level || !position) return [];
    const first = lines[position.start.line - 1]?.[0], last = lines[position.end.line - 1]?.[1];
    const title = hastAnnotatableText(node).replace(/\s+/g, " ").trim();
    return first && last && title ? [{ level: Number(level[1]), title, lines: [first, last] }] : [];
  });
}

function markdownSections(headings: readonly Heading[]): ReadingSection[] {
  const ancestors: ReadingSection[] = [];
  return headings.map(heading => {
    while (ancestors.length && ancestors.at(-1)!.level >= heading.level) ancestors.pop();
    const section = { id: `heading-${heading.lines[0]}`, parentId: ancestors.at(-1)?.id ?? null,
      level: heading.level, title: heading.title, sourceLines: heading.lines };
    ancestors.push(section);
    return section;
  });
}

const arabicNumber = /^(\d+(?:\.\d+)*)(?:[.、)．]\s*|\s+)/;
const otherNumber = /^(?:[IVXLCDM]+[.)]\s+|第[〇零一二三四五六七八九十百千\d]+[章节篇部]\s*|附录\s*[A-Z]\b\s*|Appendix\s+[A-Z]\b\s*)/i;

export type DirectorySection = {
  id: string; parentId: string | null; originalTitle: string; translatedTitle: string;
  position: SourcePosition; translatedHeading: boolean; children: DirectorySection[];
};

export function sectionAtLine(sections: readonly DirectorySection[], line: number) {
  let low = 0, high = sections.length;
  while (low < high) {
    const middle = Math.floor((low + high) / 2);
    if (sections[middle].position.lines[0] <= line) low = middle + 1;
    else high = middle;
  }
  return sections[low - 1];
}

export function sourceSections(document: ReadingDocument | null) {
  const roots: DirectorySection[] = [], order: DirectorySection[] = [];
  const byId = new Map<string, DirectorySection>();
  if (!document) return { roots, order, byId };

  const renderedHeadings = headings(document.markdown);
  const headingByLine = new Map(renderedHeadings.map(heading => [heading.lines[0], heading]));
  const sections = document.sections ?? markdownSections(renderedHeadings);
  const first = sections[0];
  const articleTitle = first?.level === 1 && sections[1]?.parentId === first.id &&
    (headingByLine.get(first.sourceLines[0])?.title ?? first.title).toLowerCase() === document.title.trim().toLowerCase() ? first.id : undefined;
  const blocks = document.blocks ?? [];
  const blocksById = new Map(blocks.map(block => [block.blockId, block]));
  const blocksByLine = new Map(blocks.map(block => [block.sourceLines?.[0], block]));
  const translation = document.translation;
  const mapped = translation?.status === "ready" && translation.bundleVersion === document.bundleVersion &&
    (translation.readingVersion === undefined || document.readingVersion === undefined || translation.readingVersion === document.readingVersion)
    ? translation.segments ?? [] : [];
  const passages = new Map(mapped.filter(segment => segment.granularity !== "group" && segment.blockIds.length === 1)
    .map(segment => [segment.blockIds[0], segment]));
  const numbers = new Map<string | null, number>();
  const prefixes = new Map<string, string>();

  for (const section of sections) {
    if (section.id === articleTitle) continue;
    const parent = section.parentId ? byId.get(section.parentId) : undefined;
    const parentId = parent?.id ?? null;
    const heading = headingByLine.get(section.sourceLines[0]);
    const title = heading?.title ?? section.title;
    const lines = heading?.lines ?? [section.sourceLines[0], section.sourceLines[0]] as const;
    const block = section.startBlockId ? blocksById.get(section.startBlockId) : blocksByLine.get(lines[0]);
    const segment = block && passages.get(block.blockId);
    let translated: string | undefined;
    let translatedHeading = false;
    if (block && segment && segment.sourceOffsets[0] === block.offsets[0] && segment.sourceOffsets[1] === block.offsets[1] &&
      segment.sourceLines[0] === lines[0] && segment.sourceLines[1] === lines[1]) {
      const candidates = headings(segment.text);
      translatedHeading = candidates.length === 1 && candidates[0].level === section.level && candidates[0].lines[0] === 1;
      if (translatedHeading && segment.granularity === "block") translated = candidates[0].title;
    }

    const authored = arabicNumber.exec(title);
    const prefix = parent ? `${prefixes.get(parent.id)}.` : "";
    const authoredIndex = authored?.[1].startsWith(prefix) ? Number(authored[1].slice(prefix.length).split(".")[0]) : 0;
    const index = Math.max((numbers.get(parentId) ?? 0) + 1, authoredIndex);
    numbers.set(parentId, index);
    const number = authored?.[1] ?? `${prefix}${index}`;
    prefixes.set(section.id, number);
    const otherAuthored = otherNumber.exec(title);
    const originalTitle = authored || otherAuthored ? title : `${number} ${title}`;
    let translatedTitle = originalTitle;
    if (translated) {
      const translatedNumber = arabicNumber.exec(translated);
      if (translatedNumber?.[1] === number || otherNumber.test(translated)) translatedTitle = translated;
      else {
        const label = (authored?.[0] ?? otherAuthored?.[0] ?? number).trimEnd();
        translatedTitle = `${label} ${translated.replace(arabicNumber, "")}`;
      }
    }
    const entry = { id: section.id, parentId, originalTitle, translatedTitle, translatedHeading,
      position: { lines, offset: block?.offsets[0] }, children: [] };
    (parent?.children ?? roots).push(entry);
    order.push(entry);
    byId.set(section.id, entry);
  }
  return { roots, order, byId };
}
