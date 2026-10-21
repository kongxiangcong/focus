# Article structure and guide — implementation and acceptance

Date: 2026-10-21. Base: main `a9b1a656feb62e530e6b9f9723780c4d14c631d5`.

## Implemented

- Library list/card actions: Article Structure next to Reading Blog; narrow layouts retain both.
- Independent modal with title, Chinese tree, plain-language guide; Escape/Close and contained scrolling.
- Same `overview.json` publication and shared renderer in first-reading introduction and preview.
- Full original-source input, Chinese heading/tree validation, guide generation after the validated tree,
  300–400-character prompt target, 500-character non-whitespace ceiling with bounded repair, no truncation.
- Missing/running/failure/retry states, per-source worker deduplication, additive legacy backfill, version checks.
- Existing Chinese Plan trees are reused. English legacy headings are not shown as the prepared overview.
- No preview open/start/continue calls; no cursor/state writes during preparation. Existing Plan readiness,
  chunk identities, translations, notes and review semantics remain unchanged.

## Executed checks

- `pnpm reader:typecheck`: passed.
- `pnpm reader:build`: passed (existing large-bundle advisory).
- `python -m unittest discover -s tests -p test_article_overview.py -v`: 7 integration tests.
  Uses real Core/Host, on-disk assets and a real HTTP server with controlled model candidates.
  Covers fresh Plan creation, Chinese-tree reuse, cursor-neutral preview/prepare, identical reader/preview
  publication, explicit start, concurrency, failure/retry, legacy backfill, stale/corrupt assets and language/length validation.
- Reader UI ArticleStructure and ArticleOverviewPanel suites: 9 tests, including ordering, loading,
  retry identity, duplicate suppression, stale response isolation and explicit body entry.
- Standalone full test run: 150 existing tests passed; two old assertions failed because the requested
  actions add buttons and a repeated Reading Blog label. Updated these assertions to the new product behavior.
  Targeted rerun of those two plus two new list/card preview tests: all 4 passed. New checks cover filter,
  scroll and trigger-focus preservation, close/cancel and absence of reading side effects.
- Existing structure + Stage 4 preparation/navigation/discussion regression suite: 34 passed.
  Its fixture imports a retired, missing `.agents/skills/focus-read/scripts/focus_read.py` at module load.
  For this run only, an in-memory harness omitted that unused CLI module import; the fixture methods,
  production code and all test assertions were unchanged. The repository's broken CLI fixture dependency
  has not been silently represented as a passing unmodified test command.
- `git diff --check`: passed.

## Not verified; required before final acceptance

**Actual desktop and mobile browser acceptance is NOT complete.** The Browser extension tool returned
“Browser access requires the originating browser context.” The permitted cloud-browser fallback attempted
`http://127.0.0.1:8766/` and returned `net::ERR_CONNECTION_REFUSED`: it cannot reach this execution environment's
local Host. No browser screenshot, layout, touch, actual scrolling or native focus result is claimed.
jsdom tests are interaction regressions, not a substitute for browser acceptance.

No real private article/Parser Bundle, including Raptor, was available in this checkout/environment.
The integration article and model responses are explicitly synthetic fixtures. No live provider generation,
Raptor factual review, Chinese-language editorial acceptance or deployed-system measurement claim is made.
The runtime prompt distinguishes chip characterization, modeled/system deployment evaluation and physical
system measurement, but this instruction still needs verification against actual generated content.

## Remaining manual acceptance sequence

1. On a reachable development Host with its configured backend, import an actual article (prefer Raptor).
2. In Library, preserve a search/status/topic filter and scroll down. Open Article Structure from list and card.
3. Prepare once; also open the formal reader while preparation runs. Confirm one per-source model task.
4. Inspect title → Chinese major hierarchy → guide. Count only guide text (normally 300–400, maximum 500),
   check source fidelity, chapter order/names, causal transitions and qualification of evidence.
5. Compare the same source/Plan/revision at both entry points. Close by button and Escape and verify position.
6. Repeat at desktop and 390px mobile viewport, including long title, deep tree, scroll and close controls.
7. Save `state.json`, Notes and existing Plan files before preview/backfill; verify unchanged after.
8. Exercise an actual provider failure and retry, restart during generation, existing started/completed Plan,
   continue, historical review and note saving. Confirm a Bundle change cannot expose an obsolete guide.
