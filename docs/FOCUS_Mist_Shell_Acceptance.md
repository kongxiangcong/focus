# Mist shell and central conversation — 2026-09-17

Base: `3005a5d` (`main`). Implementation branch: `fix/mist-workspace-flow`.

The supplied `dist/assets/index-HhzMOQEl.css` is not tracked at this base. The
implementation uses the exact tokens supplied in the request. Production Mist
lives in `FocusReader.tsx`; there is no separate `MistReader.tsx` at this base.

## Changes

- Shared Mist tokens, serif reading text, 86px application rail, white reading
  cards, restrained shadows and the requested responsive breakpoints.
- Library source cards, Topic/title filtering, PDF/HTML picker and drop target,
  compact empty states. Existing open/delete/reread behavior is preserved.
- Desktop Companion contains backend status, prompt links, composer and required
  stop/approval/error controls. Assistant content is rendered only in the central
  timeline through MarkdownContent. Streaming updates reuse the message ID.
  Missing message references in partial timelines are appended without duplicate
  cards. The separate execution-detail output is removed from AgentControls.
- Continue remains an explicit Core operation; prompt navigation does not change
  Cursor. Chunk translation/source switching and image rendering are preserved.
- Brightness and four-position font slider persist locally. Backend switching
  uses ReaderHost; WorkBuddy stays disabled. ADR 0008 records the visual revision.

## Verification

- `pnpm --filter @focus/standalone typecheck`: passed.
- `pnpm reader:typecheck`: all packages passed.
- `pnpm reader:test`: 27 passed (18 reader-ui, 9 standalone).
- `pnpm reader:build`: passed. Existing bundle-size advisory remains.
- `git diff --check`: passed.
- No changes to host/, .agents/, reader-contracts, the HTTP adapter, dependencies,
  lockfile, or prototypes/lightfield/.

A local headless Chromium inspected Library, Reading and Settings at 1280×800,
850×900 and 390×844, on both Vite 5173 and the unchanged Python Host static
handler at 8765: 18 page/viewport combinations. Document scroll width/height
matched the viewport; no horizontally escaping visible elements were found.
Rail, composer and card layout were visually inspected. Matching computed
paper/ink/font/grid values were checked between development and production.
Because the container has no Chinese fonts, temporary Noto fonts were provided
only to the QA browser. They are not project dependencies or bundled assets.

A synthetic service behind the real Python Host HTTP/SSE handler returned a
prompt and two successive assistant snapshots. The real HttpReaderHost sent the
prompt, received SSE updates, and rendered one final Markdown answer centrally.
Companion contained the prompt but no assistant answer; Cursor stayed at 01.
There were no browser JavaScript errors. Unit tests additionally cover stale
snapshot rejection, unsubscribe cleanup, historical references, upload failures,
HTML drop/invalid-file rejection, appearance persistence and destructive-action
confirmation. This is transport/UI evidence, not live model evidence.

## Remaining backend/runtime limits

The user's no-backend/no-protocol-change boundary was honored:

| Requested behavior | Actual boundary and UI behavior |
| --- | --- |
| HTML Library upload | `host/server.py` rejects non-PDF Library uploads. Picker/drop accepts HTML and submits through the existing adapter; the returned error is visible. Successful HTML registration is not claimed. |
| Recent reading time | `LibrarySource` has no timestamp. Cards display “最近阅读 · 暂无记录”; no timestamp is invented or inferred from progress. |
| Network switch | Network access is a Host CLI setting (`--network`), with no settings API. The switch is disabled and marked “待接入”. |
| Live Codex acceptance | The normal Host entrypoint cannot start here because `openai-codex==0.154.0` is unavailable. The HTTP/static/SSE smoke service does not execute a model, parser or real Workspace mutations. |

Build artifacts are ignored by Git. After checking out this branch on the user's
machine, run `pnpm reader:build` and restart their configured Host to serve the
same UI on 8765. This session does not restart the user's separate local machine.
