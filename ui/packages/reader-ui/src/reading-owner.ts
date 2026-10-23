import type { ReaderChunk, SentenceLocator, SourceNote } from "@focus/reader-contracts";

/** Choose one display occurrence without changing a note's Source-owned location.
 * Exact Plan/Chunk wins; otherwise use greatest line overlap, then smallest
 * chunk index. Equal repeated occurrences use their last display in the stream.
 */
export function readingOwner<T extends { chunk: ReaderChunk | null }>(groups: readonly T[], sourceId: string,
  location: Pick<NonNullable<SourceNote["anchor"]>, "sourceId" | "bundle" | "sourceLines">,
  exact?: Pick<SentenceLocator, "planId" | "chunkId"> | null, allowOverlap = true): T | undefined {
  const eligible = groups.filter(({ chunk }) => chunk && chunk.sourceId === sourceId && chunk.sourceId === location.sourceId &&
    !!chunk.bundleVersion && chunk.bundleVersion === location.bundle);
  const matched = exact && eligible.filter(({ chunk }) => chunk!.planId === exact.planId && chunk!.chunkId === exact.chunkId).at(-1);
  if (matched) return matched;
  if (!allowOverlap) return;
  let owner: T | undefined, overlap = 0;
  for (const group of eligible) {
    const chunk = group.chunk!;
    const lines = Math.min(chunk.sourceLines[1], location.sourceLines[1]) - Math.max(chunk.sourceLines[0], location.sourceLines[0]) + 1;
    if (lines > 0 && (lines > overlap || (lines === overlap && chunk.index <= owner!.chunk!.index))) {
      owner = group; overlap = lines;
    }
  }
  return owner;
}
