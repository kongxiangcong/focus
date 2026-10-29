# Streaming output isolation — 2026-10-26

Base: main `37e1ae4`. Reproduction and fix are on `fix/streaming-throughput`.
Raw timing metadata: [streaming-2026-10-26.json](streaming-2026-10-26.json).
No model settings, reasoning strength, history retention or output limits changed.

## Reproduction

`tests/streaming_benchmark.py` constructs two real on-disk fixture Sources, 170
messages, 253 timeline entries (83 historical reading references), and a 651,208
byte session. It feeds 300 distinct Chinese characters through the real
CodexBackend translator and Host notification handler at 5 ms intervals, with an
actual HTTP SSE consumer. Every historical reference has an explicit controlled
2 ms delay **in addition to** real Core validation. This models repeatable disk /
validation cost; it is not a measurement of the user's actual disk or model.

The same script was first run in a detached unmodified `37e1ae4` worktree, then
against the fix. Subscription baseline construction finishes before the producer
starts; baseline time is recorded separately. No upstream inference or tools run.
Results depend on thread scheduling: other baseline runs produced larger delays.

| Metric | main | fixed |
| --- | ---: | ---: |
| First Host application after arrival | 2.32 ms | 3.36 ms |
| First SSE send after arrival | 261.11 ms | 13.46 ms |
| First SSE receive after arrival | 268.13 ms | 13.63 ms |
| Last Host application behind producer | 6995.90 ms | 3.09 ms |
| Last SSE send behind producer | 7249.36 ms | 4.92 ms |
| Last SSE receive behind producer | 7251.29 ms | 5.01 ms |
| Maximum shared-lock acquisition wait | 321.10 ms | 0.30 ms |
| Maximum queued fragments | 198 | 1 |
| Full projections during baseline + text phase | 31 | 1 |
| Exact concatenated output and persisted terminal text | yes | yes |

The producer takes about 1.495 s. The old consumer finishes about 8.75 s after
producer start; the fixed consumer finishes about 1.500 s after start. No growing
backlog remains in this workload. A separate earlier 20 ms/reference reproduction
measured approximately 1.77 s snapshots, a queue peak of 298 and 4.01 s final Host
lag. These synthetic results establish the local bottleneck; they are not a claim
about live gpt-6-astra throughput or time to first model token.

## Root cause and implementation

SSE previously held `service.condition` (the same RLock as notification handling)
while calling full `snapshot()` and JSON encoding. Historical reference validation,
Source overviews and task projection therefore prevented the next token from being
applied. `changed()` additionally rescanned reading state for every fragment.

Text notifications now persist and publish an absolute message replacement without
calling `changed()` or Core. A structural generation advances on business changes,
including worker completion; ordinary text only advances the transport revision.
SSE sends at most one update per 16 ms, coalescing cumulative text instead of
retaining an unbounded queue of fragments. `message/completed` is an authoritative
replacement too. Persistence frequency is unchanged: every applied fragment is
saved synchronously, and existing terminal/stop/failure receipts remain durable.
No extra uncommitted-output loss window is introduced.

Full SSE projections and read-only HTTP refreshes capture session state under the
lock and project on a detached read view outside it. Worker dictionaries are
captured too. Discussion identity allocation/legacy-message binding stays on the
authority. Publication checks structural generation and the atomic Core state
file's mtime; a structural race discards and retries the projection. Text arriving
while a baseline is built follows that baseline as an absolute replacement.
Existing business-command responses that already own the Host lock retain their
atomic locked projection; this change does not promise that every explicit
business operation is free of lock contention.

Every connection starts with an authoritative snapshot. Text frames carry the
baseline revision, new revision, session and workspace instance identities. The
adapter replaces messages by ID, adds timeline identities once, preserves stable
reading/notes/highlights/figure objects, and rejects gaps or stale identities by
reconnecting. Old connection callbacks and closed subscriptions are ignored.
Workspace changes close the old stream. Source changes and clearing are structural
changes and require a new baseline. Expensive Markdown parsing is memoized by its
semantic inputs; current callbacks are forwarded through a ref. Stable source
figure projection, paragraph groups and note projection are retained across text.

## Verification

- Backend: `test_streaming` (5), `test_web_host` (22),
  `test_source_discussion` (18), `test_workspace_binding` (12),
  `test_stage6b_clear_retention` (8), `test_reading_highlights_host` (8),
  `test_direct_source_notes` (7), `test_status_clear_host` (3): all passed.
- Frontend: full reader UI 206 tests and standalone 179 tests passed;
  final adapter rerun 23 tests passed. Type checking and production build passed.
- `tests/streaming_browser.py` launches the production UI with Chromium, real
  EventSource and Host, 170 large messages / 253 entries, and a synthetic Codex
  protocol stream at 10 ms cadence. It reloads mid-answer and after completion,
  asserts exact distinct-character output, one message occurrence and continued
  incremental DOM updates. 300 characters are reliably persisted.
- Browser sample: first Host application 8.85 ms after producer start, first
  EventSource receive 15.62 ms, first DOM display 36.42 ms. After midstream reload,
  49 distinct displayed lengths were observed; maximum display gap 447.90 ms.
  Terminal text first displayed about 444 ms after final Host application,
  including terminal snapshot/render work. This residual terminal rendering cost
  is visible and is not reported as zero latency.
- The browser smoke test uses the project's real UI, not a replacement merge demo.
  The benchmark asserts bounded queue and final lag; off-lock race, persisted
  completion, refresh/reconnect, stop/late data, discussion identity, clearing,
  source/workspace changes and stable Markdown parsing have regression coverage.

Run from the repository root:

```sh
.venv/bin/python -m unittest discover -s tests -p 'test_streaming.py'
pnpm reader:typecheck
pnpm reader:test
pnpm reader:build
FOCUS_PLAYWRIGHT_MODULE=/path/to/playwright-core/index.mjs \
FOCUS_CHROMIUM_EXECUTABLE=/usr/bin/chromium \
.venv/bin/python tests/streaming_browser.py
```

To compare main, copy `tests/streaming_benchmark.py` into a detached `37e1ae4`
worktree's tests directory and run it with the same Python dependencies. It creates
and removes only synthetic fixtures. It neither invokes inference nor inspects
credentials. Its JSON output contains timings, sizes and counts only.

## Unverified boundaries

The original knowledge-base directory and an equivalent confirmed authorized live
Codex / gpt-6-astra inference environment were not available for this verification.
There is no live-model end-to-end result and no claim that the production incident
has been resolved online. Model/network time to first output and real tool latency
are unmeasured here; synthetic tools take zero time. Fragment arrival in the
benchmark begins at the synthetic Codex adapter, not native Codex stdout; existing
transport tests cover protocol handling, not real network performance. SQLite
synchronous per-fragment persistence may become a further bottleneck for much
larger sessions or slower disks. A cold/full structural projection still costs
work; long command responses can still contend as described above.
