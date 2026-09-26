---
name: focus-read
description: Read a registered FOCUS Source through ReaderHost, ask source-bound questions, review read passages, and save explicit Source Notes.
---

# Focus Read

Use the ReaderHost reading view for the selected Source. The Reading Application and Core own preparation, the selected Plan, the formal reading position, and request receipts. The Source Notes service owns notes. Treat the browser view as a projection of those assets.

## Open and read

Select one registered Source. If it has no ready Plan, explicitly start preparation for that Source. Preparation covers the saved Bundle, translates applicable passages, checks consistency, and reports ready or a recoverable failure. A ready notification does not open or move the reading view: open the ready Plan explicitly. If a new candidate is being prepared, keep the selected Plan available until the reader activates the candidate.

Show the saved current Chunk with its source location, formulas, images, and captions. Offer the original text alongside a saved translation. Reading and language switching use saved assets; they do not call a model. The view shows one Chunk at a time.

Advance only on explicit reading intent such as “下一段” or “继续阅读”. Use the current versioned receipt and a stable request ID; resolve a retry from the stored request result. Viewing the final Chunk does not complete the Source. Use the explicit finish action after the final Chunk. A bare “继续” after an explanation continues that explanation. Review only passages already read; return to the formal position before continuing. Rereading explicitly starts a new round of the same selected Plan.

## Questions and evidence

Bind each question to the Source and Bundle the reader is viewing. When the question concerns a current or reviewed Chunk, capture that Plan and Chunk at send time. Keep that reference on the answer even if formal progress later changes. Follow-up explanations and understanding checks leave reading progress unchanged. A Source may also be discussed without a Plan; discussion never creates a Plan.

Use bounded Source search and range reads when the cited passage is insufficient. Distinguish source evidence from inference, and state when support is missing. Search and discussion do not advance reading.

## Notes

Save a Source Note only after an explicit reader request. The Host binds the request to the Source and Bundle; the Source Notes service validates and persists it. Notes are a single Source asset across Topics, rereads, and Plan rebuilds. Show and edit them through the same service in reading, review, and completion views. Keep chat and preparation context out of Notes. Historical anchors should open the archived original when available or report that the original is unavailable.

For exact Host routes and payloads, read `host/server.py` and `ui/packages/reader-contracts/src/index.ts`. The `scripts/focus_read.py` command offers only historical read-only diagnostics. Stage 4 reading and Notes use ReaderHost operations.
