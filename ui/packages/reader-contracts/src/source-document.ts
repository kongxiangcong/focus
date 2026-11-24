/** Source identity is independent of a Reading Plan and its translated chunks. */
export interface SourceScope { sourceId: string; bundleVersion: string }

/** Host-validated quotation and its location in a particular Source Bundle. */
export interface ValidatedAnswerEvidence extends SourceScope {
  evidenceId: string; messageId: string; discussionId: string; answerRevision: string;
  layoutVersion?: string; blockIds?: readonly string[]; sectionIds?: readonly string[];
  renderGranularity?: "block" | "exact";
  pdfRegions?: readonly { pageIndex: number; pageNumber: number;
    bboxes: readonly (readonly [number, number, number, number])[]; granularity: "block" | "page" | "line" }[];
  displayNumber: number; sourceLines: readonly [number, number];
  quote: { exact: string; prefix: string; suffix: string };
  relation: "supports" | "contradicts" | "context";
}
export type PdfBox = readonly [number, number, number, number];

export interface ReadingViewBookmark {
  readingVersion: number;
  bundleVersion: string;
  line: number;
  sourceOffset?: number;
  fraction?: number;
  offset?: number;
}

export interface ReadingTranslationSegment {
  id: string;
  text: string;
  blockIds: readonly string[];
  sourceLines: readonly [number, number];
  /** Half-open Unicode code-point offsets in canonical Markdown. */
  sourceOffsets: readonly [number, number];
  /** Legacy text may only be verifiable as one contiguous group. */
  granularity: "block" | "group" | "source";
}

export interface ReadingSection {
  id: string;
  parentId: string | null;
  level: number;
  title: string;
  sourceLines: readonly [number, number];
  startBlockId?: string;
}

export interface ReadingDocument extends SourceScope { generation?: number; title: string; markdown: string; lineCount: number;
  readingVersion?: number;
  bookmark?: ReadingViewBookmark | null;
  /** Prepared Chunk boundaries in canonical Markdown code points. */
  readingPlan?: { planId: string; chunks: readonly { chunkId: string; sourceOffsets: readonly [number, number] }[] } | null;
  /** A null value indicates that the Host has no original file to open. */
  original?: { format: "pdf" | "html" | "markdown" } | null;
  /** Half-open Unicode code-point offsets in canonical Markdown. */
  blocks?: readonly { blockId: string; offsets: readonly [number, number];
    sourceLines?: readonly [number, number]; pageNumber?: number }[];
  sections?: readonly ReadingSection[];
  pdf?: { version: string; pdfHash: string;
    pages?: readonly { page: number; width?: number; height?: number; rotation?: number }[];
    blocks: readonly {
    blockId: string; page: number; bbox: PdfBox | null; bboxes?: readonly PdfBox[]; sourceLines: readonly [number, number];
    /** Half-open Unicode code-point offsets in canonical Markdown. */
    offsets?: readonly [number, number]
  }[] };
  language?: string;
  translation?: {
    status: string;
    readingVersion?: number;
    bundleVersion?: string;
    segments?: readonly ReadingTranslationSegment[];
    /** Compatibility with Hosts that expose a translation by Plan. */
    planId?: string;
    chunks: readonly { id: string; text: string; blockIds: readonly string[]; sourceLines: readonly [number, number] }[];
  };
}
export interface ReadingOpening extends SourceScope {
  status: "missing" | "running" | "ready" | "failed"; error?: string;
  structure?: readonly { id: string; parentId: string | null; title: string; sourceLines: readonly [number, number] }[];
  guide?: string;
}
