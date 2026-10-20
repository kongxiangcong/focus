---
status: accepted
---

# Source Library list and details panel

2026-10-20: adopt direction A from the [Library redesign specification](../design/FOCUS_LIBRARY_REDESIGN_SPEC.md): one Reading Source per row with one primary reading action, and a single selected Source details panel. The optional card view remains, uses the same status/action model, and opens the same panel. The default is list view; an existing `focus.libraryView` preference takes precedence.

This replaces the “详情展开承载……” presentation in [FOCUS_UI_CDS2_DESIGN_SPEC.md §5.2](../design/FOCUS_UI_CDS2_DESIGN_SPEC.md#52-知识库) and its row/card-local disclosure. Full title, parsing information, preparation notices, Blog Output artifacts, source links and management/reset/delete actions live in the panel. Desktop space permits docking; narrower space uses an overlay, and mobile uses a modal bottom panel. Closed retained panels and menus leave the accessibility tree and cannot receive input while their visual exit finishes.

## One authority, presentation-only projections

- The status vocabulary is one pure mapping of existing Source, preparation and Blog Output data. Labels do not reinterpret preparation readiness or change the primary action's established conditions.
- Topic completed/total counts and Unfiled are presentation projections. Unfiled is a reserved UI sentinel, never a real Topic or a Host argument. Topic manifests remain the only membership/order authority; the same Reading Source, Cursor, Notes and assets are shared across Topics.
- A drag previews order locally and submits exactly one existing `manageTopic(topicId, "reorder", { sourceIds })` on drop through the existing management/error/retry path. Failure restores authoritative order. Alt+Arrow and menu moves reuse existing ordering operations. Busy, search, status-filter and card-view guards prevent ambiguous ordering.
- Continue Reading derives only from the existing ReadingWindow Source and current/navigation Chunk. Missing data suppresses it; no recent-reading timestamp or next-Source operation is invented.
- Ingestion shadow rows use the same taskInbox/taskBatches projections and recovery callbacks as the task frame. They add no polling, alternate recovery state or automatic resubmission.

## Unchanged business semantics

Upload and its confirmation, ingestion and processing scope, Reading Preparation, starting/continuing/reviewing reading, candidate activation, replanning, Reset Source Reading, deletion, Blog Output generation/cancellation/retry, and Source/Topic management retain their Host methods, request identities, confirmations and error/retry semantics. Existing busy/active/managementBusy locks remain authoritative. ReaderHost contracts, Core/Host/Python code, persisted data formats, Topic membership ownership and Reading Cursor authority do not change. No new dependency or second asset store is introduced.

The design does not add Topic Reading navigation, automatic next-Source selection, recent-reading sorting, independent Topic progress, or new backend endpoints. Upload in a Topic only prefills the existing editable Topic field; the user still confirms the existing processing scope.

## Consequences and verification

The list improves scanning without duplicating management controls per row; the panel introduces explicit focus/keyboard, retained-exit and responsive-layout responsibilities. Status filters can hide the selected Source and ordering is intentionally paused while filtered. HTML drag-and-drop is not a touch guarantee: menu moves remain the pointer alternative.

[Acceptance and evidence](../design/library-redesign-acceptance.md) distinguish unit/static checks from unexecuted browser assertions. Screenshots were waived; native touch, real IME, assistive technology, real private data and non-Chromium behavior are not claimed verified.
