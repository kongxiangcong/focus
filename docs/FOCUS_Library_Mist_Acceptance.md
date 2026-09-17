# Library / Reading / Settings — 2026-09-17 delivery

Base: `ee8e0ff`. This report describes the Library / Mist delivery now published
to the repository's `main` branch.

## Delivered

- ADR 0008 fixes the directory and navigation contract before implementation.
- Existing canonical `sources/<source-id>/` data is read in place. Topic membership
  stays in ordered `topic.yaml.sources`; no source assets or progress are copied.
- Library file projection: Source Title, paper/article, Parser Bundle validation
  status, Cursor-derived progress, saved Notes count and Topics; title search and
  Topic filtering remain presentation-only.
- Library API: `GET /library/topics`, `GET /library/sources`, PDF binary
  `POST /library/sources?name=<filename>`, `DELETE /library/sources/:id`,
  `POST /library/sources/:id/reread`; an additional `POST .../:id/open` loads a Source.
  JSON POST operations take `{}`. All responses use the existing `ok/value/error`
  envelope and existing Host/Origin authentication. Upload returns HTTP 202 and a
  ReadingWindow task projection; it does not block HTTP until MinerU finishes.
- Upload immediately starts the existing Host Agent with paper-parser. Parser chooses
  the title/short name and installs the canonical bundle. The Host checks the installed
  byte-identical original and bundle validity before considering the task successful;
  successful input staging is removed. Failed input is kept for retry in conversation.
- Delete removes the complete Source directory, its Cursor entry and all Topic
  membership references, and prunes active Host references. Reference-write failure
  restores the Source directory. Successful deletion retains no trash directory.
- Reread clears all Notes and selected Plan/Chunk for that Source, preserves bundle,
  old fixed Plans and cached translations, starts a fresh conversation, and invokes
  focus-map/focus-read. Backend prerequisites are checked before clearing data.
  Planning or translation failure is visible; the Source can be opened again to retry.
- ReaderHost has optional Library capabilities and an optional read-only outline.
- Standalone routes `/library`, `/reading`, `/settings`; `/` lands in Library.
  Python production serving and Vite development proxy support all three entries.
- Production Mist uses a left outline/shortcuts, centered current output, fading
  history, native interruptible scrolling and a compact collapsible composer in a
  reserved bottom area. Long outputs stay scrollable. Current output follows new
  content unless the reader deliberately reviews history. Returning to new output
  does not change Cursor. Reduced motion/transparency and higher contrast are handled.
- Markdown and bound bundle figures render through existing components and the
  restricted asset route. Questions and the conversation remain source-anchored;
  ordinary reading does not request automatic explanation or duplicate translation.
- Backend selection uses the existing Host setting and fresh-conversation semantics;
  font size has four localStorage-backed choices. Mist is the only enabled theme;
  the other four themes are visibly reserved for later integration.

## Decisions and workflow conflicts

| Existing decision / workflow | Treatment in this delivery |
| --- | --- |
| ADR 0005 revision of 2026-09-16 selects a single unified page and normal-contrast history | Superseded explicitly by ADR 0008 per this request. The unified layout remains a backward-compatible component option, while Standalone uses Mist. |
| focus-map reinitialize preserves every old Reading Record, including Notes | Library reread overrides Notes preservation: clears Notes in every Plan and resets selection before replanning. Fixed old Plans and translations survive. A failed new plan leaves an unplanned Source rather than restoring erased Notes. |
| ADR 0001 / focus-read say no compatibility layer | Existing canonical data is supported in place, including an omitted current_topic_id normalized on mutation. No second state authority or guessed conversion is added. Recognized legacy papers/ bundles are rejected with a migration message; no actual legacy/private workspace was supplied to migrate. |
| paper-parser / ADR 0003 reuse identical PDF originals | Preserved to respect Source Identity and the single authoritative source tree. Each distinct original gets its own Source; identical uploads do not create duplicates. |
| focus-read normally instructs the host to present translated text | Existing web presentation contract remains: the reading card displays saved translation and images, while conversation displays requested Agent answers. No automatic explanations are added. |
| ADR 0007 marks WorkBuddy unavailable | Preserved. Settings expose the backend and reason, with selection disabled. CodeBuddy is not mislabeled as WorkBuddy. |
| Notes have no per-note timestamp | UI labels and reports total saved Notes, not a fabricated “recent” time window. A precise recent-Notes metric is not implemented. |

`prototypes/lightfield/` is unchanged, verified by Git diff. The formal UI specification
now points to ADR 0008 and retains the prior specification as historical context.

## Automated evidence

- `pnpm reader:typecheck`: pass.
- `pnpm reader:test`: 24 tests pass (17 Reader UI + 7 Standalone).
- `pnpm reader:build`: pass; Vite retains its >500 kB bundle-size advisory.
- New Library backend suite: 9 pass, using real Core files and a protocol double.
  Covers canonical compatibility, Notes reset and bundle/translation preservation,
  new Plan numbering, delete/Topic/Host cleanup, traversal and active-run rejection,
  write-failure rollback, PDF API/authentication, successful staging cleanup/reuse,
  and rejection of an Agent completion without an installed bundle.
- Existing web Host suite: 21 pass. Source Library / Topic suite: 6 pass.
- Full Python run before the final three added Library cases: 105 pass / 1 fail.
  The failure is `test_active_skill_surface_contains_only_five_public_skills`:
  the repository already contains 12 additional design/engineering skills. The same
  failure was reproduced in an untouched detached worktree at `ee8e0ff`.
  No skill or unrelated boundary test was deleted or weakened to hide this failure.
- HTTP smoke checks against a synthetic Host: all three production routes return
  HTML 200; Library sources API returns JSON 200. Vite proxy was not browser-verified.
- `git diff --check`: pass.

## Acceptance not yet established

This is code and automated/protocol evidence, not live-model or visual acceptance.
The environment has no `MINERU_API_TOKEN` and no installed pinned Codex runtime.
A genuine PDF → hosted MinerU → Source → model-authored Plan → translation run has
not been performed. No credentials were requested in chat or written to the repo.

The supplied Browser surface rejected local application access with
`net::ERR_BLOCKED_BY_CLIENT`. Consequently desktop/mobile appearance, exact vertical
settling, real image rendering and full browser-driven delete/reread are not marked
as manually verified. UI tests use jsdom; backend tests use a protocol double.

To finish local acceptance with the real runtime:

1. Install the dependencies described by the existing Host setup; provide MinerU
   credentials through `MINERU_API_TOKEN` and configure the selected Codex backend.
2. Start Host on its default loopback port 8765 with a test Workspace, then run
   `pnpm reader:dev` and open `http://localhost:5173/`.
3. Confirm Library landing; upload a new PDF. Open task conversation for approvals
   or parser errors. Check one valid Source directory, figures and no extra Source tree.
4. Open the Source, ask a question, review history and then Continue once; verify
   that only Continue changes the Cursor and that it advances exactly one Chunk.
5. Check Mist center landing/long content, image loading, composer collapse, narrow
   viewport and accessibility preferences; change font size, refresh and confirm retention.
6. In the disposable test Workspace, reread and verify Notes reset/bundle preservation;
   delete and verify Source directory, Topic references and Cursor entry are removed.
7. Change to any actually available alternative backend; verify a fresh conversation
   and unchanged Source assets and Cursor. WorkBuddy remains unavailable at this base.
