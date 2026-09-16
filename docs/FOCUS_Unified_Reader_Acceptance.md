# Unified Reader implementation and acceptance — 2026-09-16

## Baseline and changes

Remote main: `67bceeb60b3bf5b342452333b37803a3b0188e3f`, tree
`c65e51cc4f09388f0c8638bfb35c5039edaf9fb5`. Retrieved remote branch and full tree
through the GitHub connector; verified every tracked blob against the clean local
cache (`852154a`). The working clone is isolated from the previous checkout.

- Replaced the formal Reader's companion panel, historical fading and atmosphere
  controls with one central source / translation / question / answer stream.
- Added Host-owned session reset/archive, blank session persistence, explicit resume,
  new thread creation on next request, and stop/join before reset. No Core asset is
  deleted or reset. Timeline stores references, not copies of reading text.
- Distinguished question references from the current Cursor. Continue remains explicit,
  locked against duplicate clicks, and idempotent by request ID.
- Added shared Markdown, GFM tables, code, links, images and KaTeX rendering. Removed
  unused old chrome and transition code. Source text and translation toggle in place.
- Draft remains editable during work. Send retries retain captured request IDs and
  content; changed drafts survive successful retry. Upload and approval retries are
  separate. Fresh sessions ignore late upload results and stale snapshots.
- Default loopback access goes directly into the Reader without a token prompt.
  An explicitly configured token or public-origin deployment retains authentication.
- Updated ADR 0005, ADR 0006 and the formal UI specification; ADR 0004 is unchanged.

## Automated verification

| Check | Result |
| --- | --- |
| TypeScript, all three UI packages | PASS |
| UI and adapter tests | 17 PASS |
| Production Vite build | PASS; size warning for combined Markdown/KaTeX bundle |
| Host/Core protocol integration tests | 15 PASS |
| Full Python suite | 69 PASS, 1 pre-existing failure |
| Git whitespace check | PASS |

Behavior tests cover explicit-only advancement (Space does not advance), duplicate
Continue suppression, historical references, completion questions, source/translation
toggling and draft preservation, safe Markdown rendering, precise send retries,
upload retry, approval failure recovery, generation-time drafts, scroll-follow opt-out,
session reset, late snapshot/upload isolation, new thread versus resume, restart of a
fresh session, archived chat, unchanged Core files, and loopback Origin enforcement.

The full-suite failure is
`test_repository_boundaries.RepositoryBoundaryTests.test_active_skill_surface_contains_only_five_public_skills`:
it expects exactly the five reading skills, but the baseline also contains the
retained UI design skills. Those skills were not changed by this task.

## Browser and live-runtime boundary

A real Python Host/Core test server was started with synthetic reading assets and a
streaming protocol double for browser acceptance. The supported Cloud Browser could
not open `http://127.0.0.1:8766`: `net::ERR_BLOCKED_BY_CLIENT`. No alternate browser
control mechanism was used to bypass this restriction.

Consequently desktop/narrow-screen screenshots, actual browser scrolling, mobile
soft-keyboard behavior, streaming Markdown visual stability, and browser refresh /
approval recovery are NOT claimed as passed. The tests above exercise the relevant
state transitions in jsdom and the real Host/Core with a protocol double, not a live
Codex response. Live model/MinerU acceptance is also not claimed for this revision.

## Remaining interactive acceptance

Open the locally running Host in a supported browser; default loopback needs no token.
Use the formal app (not a prototype) and check at desktop and 390px widths:

1. Start empty, upload/open a source, send a question, confirm all answers stay central.
2. Read long Markdown with code, tables, links, images and formulas; verify no page-wide
   horizontal overflow. Toggle source/translation without losing a draft.
3. During a streaming answer, scroll upward and type the next draft. Verify no forced
   return to the bottom; use New Content to return explicitly.
4. Reference an old paragraph, ask about it, then cancel the reference. Verify the
   persistent Cursor moves only when Next is explicitly requested.
5. Exercise a real permission request, failed submission/retry, disconnect/reconnect
   and upload retry. Verify each recovery repeats only its own operation.
6. Choose Stop and New during generation/approval, then refresh. Verify clean display,
   preserved Core assets/Cursor, no old event projection, and a newly created thread.
7. On a physical phone, show the soft keyboard and verify draft/send/stop remain usable.
