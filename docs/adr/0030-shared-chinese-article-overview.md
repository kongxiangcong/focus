---
status: accepted
---

# Share a Chinese article structure and plain-language guide between Library and Reader

2026-10-21: the user requested a Library quick preview and a formal first-reading
introduction with the same Chinese structure followed by a short plain-language guide.
This extends ADR 0010's introduction and ADR 0027's source actions; navigation,
source anchors, cursor, notes and historical review retain their existing semantics.

## Asset and compatibility boundary

Each Plan may contain `overview.json`, an additive derived presentation asset. It
contains the Chinese tree, chunk-to-node bindings, guide, generation status/error,
and identity (`sourceId`, `planId`, Parser Bundle fingerprint, chunks digest,
`article-overview-v1`, publication revision). It is separate from `structure.json`
because the latter participates in existing Plan readiness checks. Backfill must
not rewrite that file, chunks, translations, progress or cursor. There is no startup
migration or bulk generation. Missing/invalid/stale content requires explicit preparation.

The selected Plan wins over an unactivated replacement candidate. Before the first
selection, preview uses the preparation Plan without selecting it. A Plan belonging
to a replaced Bundle is rejected and requires the existing replan/activation flow.
Both entry points read the same asset through `/library/sources/:id/overview`.
The reading snapshot uses its nodes and bindings when ready. Reads validate identity
and content; the browser requests uncached data and polls the visible panel so another
entry's publication becomes visible. No independent browser content cache is stored.

## Preparation and publication

The existing Reading Runtime, full-source range extraction, candidate-only model calls,
workspace lease and per-source `reading_workers` are reused. A new source uses existing
Reading Preparation to establish its Plan (including translations/check); on completion,
the same worker prepares the overview. A legacy source with a Plan can prepare only the
overview, without translating or replacing its Plan. Concurrent requests reuse the worker
and ready asset. Conflicting replan/resume work cannot strand a second task behind an
already-running overview worker. Generation may continue after closing the preview.

A valid existing Chinese Plan tree is reused. Otherwise the model first produces the
Chinese skeleton against actual source and fixed chunks;
Core validates hierarchy, coverage, binding and Chinese headings. A second call receives
that validated skeleton and the same source to write the guide. The guide targets
300–400 characters and is limited to 500 non-whitespace characters. Validation failures
receive at most two repair attempts, never truncation. Generation is bounded by the
existing CandidateTurns runtime. Publication rechecks source/Plan identity, attempt and
workspace ownership; interruptions/failures remain retryable. Readiness of old reading
assets is not invalidated by a guide failure.

Style requirements are model instructions, not a claim that a Chinese-character check
proves translation fidelity or factual correctness. In particular, chip characterization,
system modeling and physical system measurements must stay distinct.

## UI

List and card rows expose Article Structure beside Reading Blog, including narrow layouts.
The modal uses the shared ArticleStructure rendering and guide, supports Escape/Close,
contains scrolling and restores trigger focus without scrolling and the Library scroll
position. The Library component stays mounted, preserving filters. The reader retains its
read/review controls and shows Enter Body only with the prepared introduction. Viewing or
preparing never invokes open/start/continue/reset. Already-started sources keep their position.

Validation and current environment limits: [acceptance record](../design/article-overview-acceptance.md).
