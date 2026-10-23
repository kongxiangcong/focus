# Unified latest notice
Goal: one 回到最新 action; dismiss for the stable reading frontier, not viewport position.
Route/scope: editorial-ui Integrate + preserve, small; reader navigation only.
Authority: 2026-10-23 user request supersedes separate review/progress/back notices in reading-controls-update and reading redesign. Existing tokens and scroll engine own geometry/motion.
Surfaces: Mist/conversation reader, desktop/narrow/fullscreen, keyboard.
Contracts: no Host/domain writes; preserve follow, streaming/stop, annotations and folds. Use workspace/source/session/discussion + frontier plan/chunk identity. Dismissal is component memory, retained when switching scopes within this reader; refresh resets it (no new durable preference requested). After a frontier change, stale review state cannot itself show a notice: wait until review condition clears and is entered again.
Reference: PR26 0fde3fd; FocusReader, ReadingScroll. No external reference.
Acceptance: focused lifecycle tests, reader suite/typecheck/build, browser single notice/dismiss/review/advance/scope/keyboard/return plus existing fold/annotation regressions.
Open items: none. “返回刚才位置” is intentionally replaced by latest, not an undo-scroll operation. Keep underlying scroll contracts intact.
