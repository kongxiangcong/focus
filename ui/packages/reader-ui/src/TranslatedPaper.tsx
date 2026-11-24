import type { ReadingDocument, ReadingTranslationSegment, SourceNote } from "@focus/reader-contracts";
import { Fragment } from "react";
import { MarkdownContent } from "./MarkdownContent";
import { ChunkNoteLinks } from "./ChunkNoteLinks";
import { SourceEvidenceMarkers } from "./SourceEvidenceMarkers";
import type { PaperEvidence } from "./paper-evidence";
import type { RenderMark } from "./rehype-annotations";
import { segmentNoteMarks, type ChunkNoteLink } from "./selected-source-note";
import type { SourceLines } from "./source-position";

type Passage = Omit<ReadingTranslationSegment, "sourceOffsets" | "granularity"> &
  Partial<Pick<ReadingTranslationSegment, "sourceOffsets" | "granularity">>;

export function TranslatedPaper({ document, evidence, fallback, originalMarks, notes, noteLinks, originalSection }: {
  document: ReadingDocument; evidence: readonly PaperEvidence[]; fallback?: PaperEvidence; originalMarks: readonly RenderMark[];
  notes: readonly SourceNote[]; noteLinks: readonly ChunkNoteLink[];
  originalSection?: SourceLines;
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
  const lines = fallback?.fallbackLines;
  const nextPassage = lines ? passages.findIndex(passage => passage.sourceLines[0] > lines[1]) : -1;
  const excerpt = fallback && lines && <section aria-label="原文证据" lang={document.language}>
    <span className="source-excerpt-language" data-anno-ui="">原文</span>
    <MarkdownContent text={document.markdown} sourceId={document.sourceId} marks={originalMarks}
      sourceEvidence={{ document, evidence: [fallback.evidence], excerpt: lines }} />
  </section>;
  const sectionIndex = originalSection ? passages.findIndex(passage => passage.sourceLines[0] >= originalSection[0]) : -1;
  const sectionHeading = originalSection && <section data-original-section="" aria-label="原文章节" lang={document.language}>
    <MarkdownContent text={document.markdown} sourceId={document.sourceId} marks={originalMarks}
      sourceEvidence={{ document, evidence: [], excerpt: originalSection }} />
  </section>;
  return <article>{passages.map((passage, index) => {
    const items = evidence.filter(item => item.segmentIds.includes(passage.id)).map(item => item.evidence);
    const marks = segmentNoteMarks(passage, notes);
    const links = linksByPassage.get(passage.id);
    return <Fragment key={passage.id}>
      {index === nextPassage && excerpt}
      {index === sectionIndex && sectionHeading}
      <section data-translation-chunk={passage.id} data-source-line={passage.sourceLines[0]}
        data-source-end={passage.sourceLines[1]} data-source-offset-start={passage.sourceOffsets?.[0]} data-source-offset-end={passage.sourceOffsets?.[1]}
        data-source-block-ids={passage.blockIds.join(" ") || undefined}
        data-translation-granularity={passage.granularity} lang={passage.granularity === "source" ? document.language : "zh"}
        data-evidence-block={items.map(item => item.evidenceId).join(" ") || undefined}>
        <SourceEvidenceMarkers items={items} /><MarkdownContent text={passage.text} sourceId={document.sourceId} marks={marks.length ? marks : undefined} />
        {links && <ChunkNoteLinks links={links} />}
      </section>
    </Fragment>;
  })}{nextPassage === -1 && excerpt}{sectionIndex === -1 && sectionHeading}</article>;
}
