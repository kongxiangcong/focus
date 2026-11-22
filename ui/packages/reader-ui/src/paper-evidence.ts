import type { ReadingDocument, ValidatedAnswerEvidence } from "@focus/reader-contracts";
import type { EvidenceProjection } from "./source-evidence";

export type PaperPdf = NonNullable<ReadingDocument["pdf"]>;
type Block = PaperPdf["blocks"][number];
type Chunk = NonNullable<ReadingDocument["translation"]>["chunks"][number];
type Lines = readonly [number, number];

export type PaperEvidence = {
  evidence: ValidatedAnswerEvidence;
  pdfBlocks: readonly Block[];
  pdfPages: readonly number[];
  translationChunks: readonly string[];
};

export function overlapsSourceLines(a: Lines, b: Lines) {
  return a[0] <= b[1] && b[0] <= a[1];
}

export function matchesTranslationChunk(chunk: Chunk, lines: Lines, blockIds: readonly string[]) {
  return overlapsSourceLines(chunk.sourceLines, lines) &&
    (!chunk.blockIds.length || !blockIds.length || chunk.blockIds.some(id => blockIds.includes(id)));
}

export function locatePaperEvidence(document: ReadingDocument, projection: EvidenceProjection): PaperEvidence {
  const { evidence } = projection;
  const pdf = document.pdf;
  if (projection.kind === "unavailable" || !pdf) return { evidence, pdfBlocks: [], pdfPages: [], translationChunks: [] };
  const { sourceLines, quoteOffsets } = projection;
  const currentBlocks = pdf.blocks.filter(block => overlapsSourceLines(block.sourceLines, sourceLines) &&
    (!quoteOffsets || !block.offsets || block.offsets[0] < quoteOffsets[1] && quoteOffsets[0] < block.offsets[1]));
  const knownPage = (page: number) => Number.isSafeInteger(page) && page > 0 &&
    (!pdf.pages?.length || pdf.pages.some(entry => entry.page === page));
  const layoutMatches = evidence.layoutVersion === pdf.version;
  const pdfBlocks = layoutMatches ? currentBlocks.filter(block =>
    knownPage(block.page) && evidence.blockIds?.includes(block.blockId)) : [];
  const pdfPages = layoutMatches ? [...new Set([
    ...pdfBlocks.map(block => block.page),
    ...(evidence.pdfRegions ?? []).filter(region => region.pageIndex === region.pageNumber - 1 && knownPage(region.pageNumber))
      .map(region => region.pageNumber),
  ])] : [];
  const blockIds = currentBlocks.map(block => block.blockId);
  const translationChunks = document.translation?.status === "ready" ? document.translation.chunks
    .filter(chunk => matchesTranslationChunk(chunk, sourceLines, blockIds)).map(chunk => chunk.id) : [];
  return { evidence, pdfBlocks, pdfPages, translationChunks };
}
