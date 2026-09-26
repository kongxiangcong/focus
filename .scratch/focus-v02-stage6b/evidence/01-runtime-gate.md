# Stage 6B ticket 01 evidence

2026-09-26. Baseline: `6ff461d` plus 14 pre-existing modified/untracked files. Ticket 01 acceptance completed; tickets 02–05 have not started. Full-suite failures below are pre-existing and remain explicitly unpassed.

## Credentials correction

The initial SDK probe inspected process environment only and omitted the repository `.env`. It therefore returned `MISSING_CREDENTIAL`. That was a probe setup error, not absence of the user's DeepSeek API or credentials. After the user pointed to `.env`, the probe loaded only `DEEPSEEK_API_KEY` into the SDK child configuration and returned `completed` / `FOCUS_OK` in 2.94 seconds. The earlier external-blocker conclusion is withdrawn. No secret values were printed or committed.

## Real Runtime evidence

- Installed official `deepseek-harness-sdk` / `deepseek-harness-runtime-bin` `0.1.5rc1` in the repository `.venv`; the SDK itself declares a same-version Runtime dependency. These are recorded versions, not product version gates.
- DeepSeek Runtime: `.venv/Lib/site-packages/deepseek_harness_runtime/runtime/deepseek-harness-sdk-runtime-win-x64.exe`, model `deepseek-v4-flash`. Both isolated direct-SDK probe and new Host setup adapter completed the minimal request successfully. Each uses an explicit isolated `dsh_home`; personal DSH profiles were not used.
- DeepSeek tool probe used the official SDK, `sdk-minimal` plus an invocation patch disabling both persistent shell producers, and the official MCP client plugin connected to a temporary loopback probe server. Model requested `focus_probe(action=echo)` and received `FOCUS_TOOL_OK`, then requested `action=write` and received an error. Recorded calls: echo allowed; write refused. Probe `finish_reason=completed`.
- That tool probe proves the SDK can round-trip through an external tool bridge and observe its refusal. It does not prove full FOCUS business-tool integration. Inspection of the actual native request/header log found only `mcp__focus__focus_probe` in this probe and no tools in the connectivity request. No business writes were performed by the probe.
- Codex explicit Runtime: `.venv/Lib/site-packages/codex_cli_bin/bin/codex.exe`, reported `codex-cli 0.154.0`. Personal ChatGPT authentication was reused through `account/read`; no API-key login was initiated. `model/list` returned default `gpt-6-astra`; a minimal request through the new setup entry succeeded with that model.
- A `gpt-6-sol` probe was rejected by the actual Runtime/account as unsupported. It is not offered in the settings defaults. Available app models were not treated as this Runtime's capability catalog.
- PATH-selected `C:/Users/72449/AppData/Roaming/npm/codex.CMD` failed on the personal config value `service_tier=default` (`unknown variant`, expected `fast` or `flex`). There was no silent fallback. Success above was a separate, explicit selection of the packaged executable, not automatic recovery. Personal configuration was not changed.
- SDK `close()` returned after probes. This is not a claim of native log deletion, archival, or complete process-tree cleanup.

## Browser evidence

Used the actual standalone build at `http://127.0.0.1:8767/settings`, with an isolated empty Knowledge Base and real Host.

1. Selected DeepSeek, clicked connectivity check, observed checking then minimal-request success and actual executable path. The current effective Backend remained Codex.
2. Selected Codex; the previous success immediately became unchecked.
3. Entered the explicit packaged Codex path, clicked connectivity check, observed checking then minimal-request success and actual executable path.

No authentication secrets were entered into browser state or storage. Real browser OAuth for an unsigned-in account, clean machine installation and complete business flows are not passed by this evidence.

## Deterministic evidence

- Public Host setup tests cover explicit missing path/no fallback/no business changes; shared personal Codex authentication with environment Key excluded; DeepSeek `.env` loading without leaking credentials or activating a Backend; OAuth waiting/cancel/recheck; actionable sanitized provider failure; and independent partial install failure.
- UI regression checks a late success after changing configuration is discarded and does not activate a Backend.
- Existing backend registry/proxy suite: 10 passed.
- Initial frontend baseline: typecheck passed; 60 tests passed (31 reader-ui + 29 standalone). Subsequent focused setup UI test passed.
- Python baseline, started before product edits: 324 tests, 8 failures and 30 errors. Examples: legacy `prepare_chunk` now rejected as `Unsupported FOCUS operation`; stale reading references rejected as `原版本引用不可定位`; legacy reread entry rejected as not integrated. The raw local log is `python-baseline.txt` and is not committed. These are not counted as Stage 6B passes and were not silently rewritten.

## Final checks and review

- Real Codex ChatGPT `gpt-6-astra` tool probe completed: `focus_probe(echo)` allowed, `focus_probe(write)` refused. It used ephemeral read-only input and no private Knowledge Base.
- Separate fixture-wire inspection used the actual Codex executable with a temporary loopback model endpoint; outgoing connectivity request had `tools=[]`. This is fixture protocol evidence, not a second real model request or a product fallback provider.
- Public Host setup suite: 11 passed, including actual Windows launcher child-process termination after initialization timeout. Registry/proxy: 10 passed. Frontend typecheck and production build passed; full frontend suite: 61 passed (31 reader-ui, 30 standalone).
- Final Python suite: 335 tests, 8 failures and 30 errors. Compared all 38 failing test identities with the before-edit baseline: no added or removed failures. The 11 new setup tests passed. The whole repository suite is NOT green.
- Standards and Spec review agents each reviewed the intended staged diff. Fixed all findings: enforce ChatGPT-only on business sessions and CLI paths; preserve never-approve on the connectivity turn; prepare both dependencies on first settings entry; terminate the selected Windows launcher process tree. Both reviewers confirmed no remaining actionable findings in their reviewed scope.
- Original 14-file dirty-state hash inventory remained unchanged. Only ticket 01 files are committed.

## Scope boundaries

Real browser OAuth for a signed-out account and clean-machine installation remain release-ticket evidence gaps, as listed above. Full business workflow integration belongs to ticket 02; saved/effective configuration and cross-page refresh behavior to ticket 03; retention to ticket 04; clean installation/full release acceptance to ticket 05.

## Sources

Inspected the installed SDK source and [official Python SDK documentation](https://github.com/deepseek-ai/deepseek-harness/blob/master/python/sdk/README.md), live [PyPI metadata](https://pypi.org/pypi/deepseek-harness-sdk/json), and [Codex App Server documentation](https://learn.chatgpt.com/docs/app-server). Documentation availability does not replace the separately listed real Runtime and browser observations.
