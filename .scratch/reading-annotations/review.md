# Reading annotations independent review

Baseline: `883c456fbebee4d8e95269942ed48c3be07cf145` → reviewed integration `7e08b5c5b222f1dc388b72bdfea6f56ef73eac64`.

The Standards and Spec reviewers worked independently and read-only. Their findings remain separate below. Implementation and regression evidence are in [delivery.md](delivery.md).

## Standards

1. **P2 — Hard violation: persistence uniqueness and overlap.** `SourceHighlights.save` inserted another active record for a new request ID without checking active highlights or sentence notes. Two tabs could save the same stale selection and create duplicate IDs; projection then hid one as lost. ADR 0033 D7/D10 forbids partial overlap and permits at most one highlight and one sentence note on an identical range. Conflict checks must cover create and undo restoration transactionally.
2. **P3 — Hard violation: geometry tokens were unused.** `AnnotationRail` used a literal 200px threshold; `rail-layout` used literal 8px/6px packing values. The current design index requires values from `focus-tokens.css`, where narrow-rail, card-gap and card-offset tokens already exist. Read computed tokens and pass them into packing.
3. **P3 — Judgement call: duplicated owner selection.** `SourceNotesPanel`, annotation projection and note projection repeated Source/Bundle eligibility, maximum line overlap and tie-breaking. Extract the shared owner selection while preserving exact Plan/Chunk preference, smaller-index ties and the last repeated occurrence.

Standards: **3 findings**, worst **P2**. The third is a refactoring judgement, not a documented-rule violation.

## Spec

1. **P3 — M13 disabled on ordinary repacking.** Spec §7.4 requires a 240ms transform transition, suppressed on first layout and attachment toggles. `useRailLayout` added `.no-anim` whenever a content/revision signature changed, so editing a taller remark or deleting an earlier card made later cards jump. Restrict suppression to initial/layout changes.
2. **P2 — Invalid keyboard selection retained an actionable stale bubble.** Spec §5.3 requires the selection to remain inside one Chunk Markdown root; §6.2 supports debounced keyboard selection. Extending a selection across a Chunk boundary returned without clearing the prior bubble. Its actions still targeted the earlier substring. An isolated regression reproduced this; invalid selections must close the old selection bubble while preserving a nonempty remark editor.

Spec: **2 findings**, worst **P2**. No scope-creep findings.

## Resolution

One implementer fixed all five findings in `bef1ecb83bc8b35b9f286467bc60c7ee35fafff8`, merged as `71d72a54f56d92dd35255ae469e3ef644f5e7de3`. The fixes and their public regressions are documented in [delivery.md](delivery.md#independent-review-fixes).

### Standards recheck

The original independent reviewer rechecked all three findings against `71d72a5`: **3 closed, 0 remaining**. Transactional occupancy covers both entity types and undo restoration; geometry comes from computed tokens; all three owner callers share `readingOwner`. Independent checks passed 14 Core tests, 23 frontend tests in five files, and four additional same-entity undo-conflict combinations. The reviewer's sandbox could not bind the HTTP socket (`WinError 10013`); HTTP validation is covered by the implementer's elevated Host tests and the integration full regression, rather than counted as an independent reviewer pass.

### Spec recheck

The original independent reviewer rechecked both findings against `71d72a5`: **2 closed, 0 remaining**. Ordinary content/revision repacking retains M13; initial/layout-mode changes suppress it. Invalid cross-root keyboard selections close the stale bubble while preserving editor drafts. Independent checks passed all 19 tests in three relevant files. No new scope-creep finding was reported.

Both rechecks were read-only and left the reviewed HEAD and working tree unchanged. These are separate Standards and Spec conclusions; browser, full regression and unverified physical-input scope remain recorded in the delivery evidence.
