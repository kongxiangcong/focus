/** Source identity is independent of a Reading Plan and its translated chunks. */
export interface SourceScope { sourceId: string; bundleVersion: string }

/** Host-validated source bytes. Rendering must still resolve the exact visible range. */
export interface ValidatedAnswerEvidence extends SourceScope {
  evidenceId: string; messageId: string; discussionId: string; answerRevision: string;
  displayNumber: number; sourceLines: readonly [number, number];
  quote: { exact: string; prefix: string; suffix: string };
  relation: "supports" | "contradicts" | "context";
}
export interface ReadingDocument extends SourceScope { generation?: number; title: string; markdown: string; lineCount: number }
export interface ReadingOpening extends SourceScope {
  status: "missing" | "running" | "ready" | "failed"; error?: string;
  structure?: readonly { id: string; parentId: string | null; title: string; sourceLines: readonly [number, number] }[];
  guide?: string;
}
