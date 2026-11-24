import type { ReadingDocument, ReadingTranslationSegment, SourceNote } from "@focus/reader-contracts";
import { MarkdownContent } from "./MarkdownContent";
import { ChunkNoteLinks } from "./ChunkNoteLinks";
import { SourceEvidenceMarkers } from "./SourceEvidenceMarkers";
import type { PaperEvidence } from "./paper-evidence";
import { segmentNoteMarks, type ChunkNoteLink } from "./selected-source-note";

type Passage = Omit<ReadingTranslationSegment, "sourceOffsets" | "granularity"> &
  Partial<Pick<ReadingTranslationSegment, "sourceOffsets" | "granularity">>;

export function TranslatedPaper({ document, evidence, notes, noteLinks }: {
  document: ReadingDocument; evidence: readonly PaperEvidence[]; notes: readonly SourceNote[]; noteLinks: readonly ChunkNoteLink[];
}) {
  const translation = document.translation;
  const passages: readonly Passage[] = translation?.segments ?? translation?.chunks ?? [];
  const linksByPassage = new Map<string, ChunkNoteLink[]>();
  for (const link of noteLinks) {
    const [low, high] = link.sourceOffsets;
    const passage = passages.find(({ sourceOffsets }) => sourceOffsets && sourceOffsets[0] < high && low < sourceOffsets[1]);
    if (!passage) continue;
    const links = linksByPassage.get(passage.id) ?? [];
    links.push(link);
    linksByPassage.set(passage.id, links);
  }
  return <article>{passages.map(passage => {
    const items = evidence.filter(item => item.translationChunks.includes(passage.id)).map(item => item.evidence);
    const marks = segmentNoteMarks(passage, notes);
    const links = linksByPassage.get(passage.id);
    return <section key={passage.id} data-translation-chunk={passage.id} data-source-line={passage.sourceLines[0]}
      data-source-end={passage.sourceLines[1]} data-source-offset-start={passage.sourceOffsets?.[0]} data-source-offset-end={passage.sourceOffsets?.[1]}
      data-source-block-ids={passage.blockIds.join(" ") || undefined}
      data-translation-granularity={passage.granularity}
      data-evidence-block={items.map(item => item.evidenceId).join(" ") || undefined}>
      <SourceEvidenceMarkers items={items} /><MarkdownContent text={passage.text} sourceId={document.sourceId} marks={marks} />
      {links && <ChunkNoteLinks links={links} />}
    </section>;
  })}</article>;
}
