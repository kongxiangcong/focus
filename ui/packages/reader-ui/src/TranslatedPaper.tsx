import type { ReadingDocument, ReadingTranslationSegment } from "@focus/reader-contracts";
import { MarkdownContent } from "./MarkdownContent";
import { SourceEvidenceMarkers } from "./SourceEvidenceMarkers";
import type { PaperEvidence } from "./paper-evidence";

type Passage = Omit<ReadingTranslationSegment, "sourceOffsets" | "granularity"> &
  Partial<Pick<ReadingTranslationSegment, "sourceOffsets" | "granularity">>;

export function TranslatedPaper({ document, evidence }: { document: ReadingDocument; evidence: readonly PaperEvidence[] }) {
  const translation = document.translation;
  const passages: readonly Passage[] = translation?.segments ?? translation?.chunks ?? [];
  return <article>{passages.map(passage => {
    const items = evidence.filter(item => item.translationChunks.includes(passage.id)).map(item => item.evidence);
    return <section key={passage.id} data-translation-chunk={passage.id} data-source-line={passage.sourceLines[0]}
      data-source-end={passage.sourceLines[1]} data-source-offset-start={passage.sourceOffsets?.[0]} data-source-offset-end={passage.sourceOffsets?.[1]}
      data-source-block-ids={passage.blockIds.join(" ") || undefined}
      data-translation-granularity={passage.granularity}
      data-evidence-block={items.map(item => item.evidenceId).join(" ") || undefined}>
      <SourceEvidenceMarkers items={items} /><MarkdownContent text={passage.text} sourceId={document.sourceId} />
    </section>;
  })}</article>;
}
