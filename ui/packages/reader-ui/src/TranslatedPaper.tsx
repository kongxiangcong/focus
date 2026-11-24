import type { ReadingDocument, ReadingTranslationSegment } from "@focus/reader-contracts";
import { Fragment } from "react";
import { MarkdownContent } from "./MarkdownContent";
import { SourceEvidenceMarkers } from "./SourceEvidenceMarkers";
import type { PaperEvidence } from "./paper-evidence";
import type { RenderMark } from "./rehype-annotations";

type Passage = Omit<ReadingTranslationSegment, "sourceOffsets" | "granularity"> &
  Partial<Pick<ReadingTranslationSegment, "sourceOffsets" | "granularity">>;

export function TranslatedPaper({ document, evidence, fallback, originalMarks }: {
  document: ReadingDocument; evidence: readonly PaperEvidence[]; fallback?: PaperEvidence; originalMarks: readonly RenderMark[];
}) {
  const translation = document.translation;
  const passages: readonly Passage[] = translation?.segments ?? translation?.chunks ?? [];
  const lines = fallback?.fallbackLines;
  const nextPassage = lines ? passages.findIndex(passage => passage.sourceLines[0] > lines[1]) : -1;
  const excerpt = fallback && lines && <section aria-label="原文证据" lang={document.language}>
    <span className="source-excerpt-language" data-anno-ui="">原文</span>
    <MarkdownContent text={document.markdown} sourceId={document.sourceId} marks={originalMarks}
      sourceEvidence={{ document, evidence: [fallback.evidence], excerpt: lines }} />
  </section>;
  return <article>{passages.map((passage, index) => {
    const items = evidence.filter(item => item.segmentIds.includes(passage.id)).map(item => item.evidence);
    return <Fragment key={passage.id}>
      {index === nextPassage && excerpt}
      <section data-translation-chunk={passage.id} data-source-line={passage.sourceLines[0]}
        data-source-end={passage.sourceLines[1]} data-source-offset-start={passage.sourceOffsets?.[0]} data-source-offset-end={passage.sourceOffsets?.[1]}
        data-source-block-ids={passage.blockIds.join(" ") || undefined}
        data-translation-granularity={passage.granularity} lang={passage.granularity === "source" ? document.language : "zh"}
        data-evidence-block={items.map(item => item.evidenceId).join(" ") || undefined}>
        <SourceEvidenceMarkers items={items} /><MarkdownContent text={passage.text} sourceId={document.sourceId} />
      </section>
    </Fragment>;
  })}{nextPassage === -1 && excerpt}</article>;
}
