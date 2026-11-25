import type { ReadingDocument, ValidatedAnswerEvidence } from "@focus/reader-contracts";
import type { EvidenceProjection } from "./source-evidence";

type Lines = readonly [number, number];

export type PaperEvidence = {
  evidence: ValidatedAnswerEvidence;
  segmentIds: readonly string[];
  fallbackLines?: Lines;
};

export function overlapsSourceLines(a: Lines, b: Lines) {
  return a[0] <= b[1] && b[0] <= a[1];
}

export function locatePaperEvidence(document: ReadingDocument, projection: EvidenceProjection): PaperEvidence {
  const { evidence } = projection;
  const translation = document.translation;
  if (projection.kind === "unavailable" || !projection.quoteOffsets) return { evidence, segmentIds: [] };
  // Canonical offsets come from the verified original quote. Each segment's
  // range is validated by the Host, including historical groups and retained originals.
  const [start, end] = projection.quoteOffsets;
  const segments = translation?.status === "ready" && translation.bundleVersion === document.bundleVersion
    ? translation.segments ?? [] : [];
  const segmentIds = segments
    .filter(segment => segment.sourceOffsets[0] < end && start < segment.sourceOffsets[1])
    .map(segment => segment.id);
  return { evidence, segmentIds, fallbackLines: segmentIds.length ? undefined : projection.sourceLines };
}
