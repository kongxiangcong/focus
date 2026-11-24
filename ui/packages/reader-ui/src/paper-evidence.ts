import type { ReadingDocument, ValidatedAnswerEvidence } from "@focus/reader-contracts";
import type { EvidenceProjection } from "./source-evidence";

type Chunk = NonNullable<ReadingDocument["translation"]>["chunks"][number];
type Lines = readonly [number, number];

export type PaperEvidence = {
  evidence: ValidatedAnswerEvidence;
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
  if (projection.kind === "unavailable") return { evidence, translationChunks: [] };
  const { sourceLines, quoteOffsets } = projection;
  const currentBlocks = pdf?.blocks.filter(block => overlapsSourceLines(block.sourceLines, sourceLines) &&
    (!quoteOffsets || !block.offsets || block.offsets[0] < quoteOffsets[1] && quoteOffsets[0] < block.offsets[1])) ?? [];
  const blockIds = currentBlocks.map(block => block.blockId);
  const translationChunks = document.translation?.status === "ready" ? document.translation.chunks
    .filter(chunk => matchesTranslationChunk(chunk, sourceLines, blockIds)).map(chunk => chunk.id) : [];
  return { evidence, translationChunks };
}
