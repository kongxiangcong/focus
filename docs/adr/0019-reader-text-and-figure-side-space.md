---
status: accepted
---

# Share one side space between figures and reading materials

The user's 2026-09-30 figure split request supersedes ADR 0005/0008's placement of
large source illustrations in the central stream. ADR 0018's Reading Timeline,
historical Continue, anchored drafts, session recovery and task semantics remain.

- The central scroll owns source text, formulas, tables and discussion in their
  existing event order. Standalone source images become small figure links.
- Desktop reading uses approximately 60% text / 40% side space. A pointer and
  keyboard separator respects 340px text and 280px side minima. The closed text
  flow is centered with its reading maximum. Narrow screens use a drawer.
- Figures and notes/progress/discussion history share one side space and never
  create a third reading column. Changing tabs keeps note and question drafts.
- A new reading occurrence selects its Chunk's images in source order; no images
  closes the side space. Full-source navigation can select unread figures without
  opening an unread Chunk. Source changes discard figure selection and language
  presentation state. The navigation disclosure starts collapsed.
- Image identity resolves Source-relative paths and Host asset URLs, normalizing
  encoded paths and local fragments/query variants. It does not deduplicate unrelated
  paths by filename. Missing figure numbers use an explicit filename-based illustration
  label rather than inventing an original figure number.
- Captions follow the displayed original/translation where available and fall back
  to existing source metadata. No translation, Plan or parsing operation is invoked.
  Tables, rasterized tables, equations, inline prose images and code stay in the text.
- Source images in discussion become side-space links. Images outside the current
  source catalogue retain inline rendering. Magnification uses a modal browser top
  layer, with fit/original-size viewing, Close, Escape and focus restoration.
- Figure selection, disclosure, tab and column width are UI state. They never
  write Cursor, Reading Progress Entries or draft provenance. Only column width
  is stored locally. Side operations suppress layout-induced automatic following;
  actual new timeline content retains the existing follow/manual-pause behavior.
- ReaderChunk.images and ReadingWindow.figures keep their existing shape. Host
  extends only its read-only full-source figure projection to include HTML captions
  and filter required table/equation content. The existing Core Bundle validation
  and reading-data authority are unchanged.

Validation and boundaries: [implementation report](../requirements/FOCUS_Reader_Figures_Report.md).
