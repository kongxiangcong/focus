# Preserve shared disclosure focus treatment
Status: resolved
Type: task

Goal / scope: editorial-ui Integrate + preserve, tiny CSS correction after independent Review. Restore shared keyboard/high-contrast focus without changing disclosure layout or state.
Authority: current user repair authorization; reading redesign §1.3/§2; reader-shell shared focus rules and focus-tokens.css remain numerical owners.
Surface: paragraph discussion disclosure in both reader appearances; light/dark, compact/comfortable, wide/narrow.
Contracts: all IDs, storage, grouping, drafts, navigation and cancellation unchanged. No backend or animation changes.
Reference: PR26 09ef3a7, mist-reader.css:373.
Acceptance: reproduce computed 2px high-contrast outline, delete override, rerun browser matrix verifying shared color and 3px width; build. No open decisions.

## Answer
Removed only the dedicated outline override. Added browser regression assertions and density coverage. Validation and uncovered areas: docs/design/discussion-fold-review.md. User authorized commit/push, not merge/deploy.
