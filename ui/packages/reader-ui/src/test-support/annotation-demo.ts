import type { ReadingHighlight, SourceNote } from "@focus/reader-contracts";
import { markdownTree } from "../markdown-pipeline";
import { hastAnnotatableText } from "../annotatable-text";
import { quoteAt } from "../annotation-projection";

interface AnnotationDemo {
  chunks: readonly { sourceId: string; planId: string; chunkId: string; bundleVersion?: string; sourceLines: readonly number[]; sourceMarkdown: string }[];
  markSeeds: readonly { chunkId: string; exact: string; highlight: boolean; note: string }[];
}

/** Resolve the shared prototype seeds using the production Markdown text contract. */
export function seedMarks(demo: AnnotationDemo): { highlights: ReadingHighlight[]; notes: SourceNote[] } {
  const highlights: ReadingHighlight[] = [], notes: SourceNote[] = [];
  const texts = new Map(demo.chunks.map(chunk => [chunk.chunkId, hastAnnotatableText(markdownTree(chunk.sourceMarkdown))]));
  demo.markSeeds.forEach((seed, index) => {
    const chunk = demo.chunks.find(chunk => chunk.chunkId === seed.chunkId), text = texts.get(seed.chunkId);
    const start = text?.indexOf(seed.exact) ?? -1;
    if (!chunk || text === undefined || start < 0) throw new Error(`Annotation demo quote is missing from ${seed.chunkId}`);
    const end = start + seed.exact.length;
    const sentence = { planId: chunk.planId, chunkId: chunk.chunkId, layer: "source" as const, range: { start, end }, quote: quoteAt(text, start, end) };
    const sourceLines: readonly [number, number] = [chunk.sourceLines[0], chunk.sourceLines[1]], bundle = chunk.bundleVersion ?? "anno-v1";
    const id = (index + 1).toString(16).padStart(31, "0");
    if (seed.highlight) highlights.push({ highlightId: `a${id}`, sourceId: chunk.sourceId, revision: 1, bundle, sourceLines,
      ...sentence, deleted: false, canUndo: true, sourceUpdated: false });
    if (seed.note) notes.push({ noteId: `b${id}`, sourceId: chunk.sourceId, revision: 1, bundle, content: seed.note, sentence,
      kind: "thought", origin: "user", evidenceRole: "explanation", anchor: { sourceId: chunk.sourceId, bundle, sourceLines },
      placement: null, referenceStatus: "current", deleted: false, canUndo: true, sourceUpdated: false });
  });
  return { highlights, notes };
}
