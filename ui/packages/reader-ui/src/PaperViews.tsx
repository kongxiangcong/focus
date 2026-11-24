import type { ReadingDocument } from "@focus/reader-contracts";
import { MarkdownContent } from "./MarkdownContent";
import { SourceEvidenceMarkers } from "./SourceEvidenceMarkers";
import type { PaperEvidence } from "./paper-evidence";

export function TranslatedPaper({ document, evidence }: { document: ReadingDocument; evidence: readonly PaperEvidence[] }) {
  return <article>{document.translation?.chunks.map(chunk => {
    const items = evidence.filter(item => item.translationChunks.includes(chunk.id)).map(item => item.evidence);
    return <section key={chunk.id} data-translation-chunk={chunk.id} data-source-line={chunk.sourceLines[0]} data-source-end={chunk.sourceLines[1]}
      data-evidence-block={items.map(e => e.evidenceId).join(" ") || undefined}>
      <SourceEvidenceMarkers items={items} /><MarkdownContent text={chunk.text} sourceId={document.sourceId} />
    </section>;
  })}</article>;
}
